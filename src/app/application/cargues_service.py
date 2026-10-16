"""Caso de uso: preparar un anexo tarifario para el cargue en GEMANET.

Orquesta las capas: lee con infrastructure, valida con domain y arma los
reportes que consume la interfaz.

El archivo original nunca se modifica. Todo lo que produce el proceso se
escribe en una carpeta de salida aparte, con fecha y hora en el nombre.
"""

from __future__ import annotations

import csv
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import BinaryIO

from openpyxl import load_workbook

from src.app.domain.cargues import parsing, rules, txt_writer, validators
from src.app.infrastructure.excel import anexos
from src.app.domain.cargues.model import (
    Hallazgo,
    Registro,
    ResultadoCargue,
    Severidad,
)


# ============================================================
# PROCESO
# ============================================================

def procesar_anexo(
    origen: str | Path | BinaryIO,
    tipo_cargue: str,
    *,
    nombre_archivo: str | None = None,
    hoja: str | None = None,
    fila_encabezado: int | None = None,
    mapeo_manual: dict[str, str] | None = None,
    soat_por_cups: Mapping[str, Iterable[str]] | None = None,
) -> ResultadoCargue:
    """Lee un anexo y devuelve el resultado completo del análisis.

    No escribe nada en disco: eso lo hace `generar_salidas`.
    """

    anexo = anexos.leer_anexo(
        origen,
        tipo_cargue,
        hoja=hoja,
        fila_encabezado=fila_encabezado,
        mapeo_manual=mapeo_manual,
    )

    registros = [
        validators.construir_registro(fila, tipo_cargue)
        for fila in anexo.filas
    ]

    validators.validar_duplicados(registros)

    if tipo_cargue != rules.CARGUE_CUPS:
        validators.validar_descripciones_repetidas(registros)
    else:
        validators.validar_codigos_propios_y_traslados(registros)

    generales: list[Hallazgo] = []

    if tipo_cargue == rules.CARGUE_CUPS:
        if soat_por_cups is None:
            generales.append(
                Hallazgo(
                    fila=anexo.fila_encabezado,
                    campo="archivo",
                    severidad=Severidad.ADVERTENCIA,
                    problema="no se validó contra el homologador",
                    regla="no se indicó la carpeta de referencias",
                    sugerencia=(
                        "indicar la carpeta con el SUPERHOMOLOGADOR para "
                        "cruzar CUPS y códigos SOAT"
                    ),
                )
            )
        else:
            sin_cruce = validators.validar_contra_homologador(
                registros, soat_por_cups
            )
            if sin_cruce:
                generales.append(
                    Hallazgo(
                        fila=anexo.fila_encabezado,
                        campo="archivo",
                        severidad=Severidad.ADVERTENCIA,
                        problema=(
                            f"{sin_cruce} registros tienen un CUPS que no está "
                            "en el homologador y no se pudieron cruzar"
                        ),
                        regla="solo se valida lo que el homologador conoce",
                        sugerencia="revisar esos códigos manualmente",
                    )
                )

    if not registros:
        generales.append(
            Hallazgo(
                fila=anexo.fila_encabezado,
                campo="archivo",
                severidad=Severidad.BLOQUEANTE,
                problema="no se encontraron filas con datos bajo los encabezados",
                regla="el anexo debe tener registros",
                sugerencia="verificar la hoja y la fila de encabezados",
            )
        )

    faltantes = [
        campo
        for campo in ("tipo_tarifa", "codigo_ley", "porcentaje")
        if campo not in anexo.mapeo
    ]
    if tipo_cargue != rules.CARGUE_INS and faltantes:
        generales.append(
            Hallazgo(
                fila=anexo.fila_encabezado,
                campo="archivo",
                severidad=Severidad.ADVERTENCIA,
                problema=(
                    "el anexo no trae columnas de "
                    f"{', '.join(faltantes)}"
                ),
                regla="sin esas columnas no se pueden cargar tarifas reguladas",
                sugerencia="confirmar que todo el anexo es de tarifa propia",
            )
        )

    return ResultadoCargue(
        tipo_cargue=tipo_cargue,
        archivo_origen=nombre_archivo or str(origen),
        hoja=anexo.hoja,
        fila_encabezado=anexo.fila_encabezado,
        mapeo_columnas=anexo.mapeo,
        registros=registros,
        hallazgos_generales=generales,
    )


@dataclass
class AnexoMultihoja:
    """Todos los registros de un anexo con varias hojas del mismo tipo."""

    tipo_cargue: str
    registros: list[Registro]
    hojas_usadas: list[str]
    hojas_omitidas: list[str]
    hallazgos_generales: list[Hallazgo]


def procesar_anexo_multihoja(
    origen: str | Path,
    tipo_cargue: str,
    *,
    hojas: list[str] | None = None,
    soat_por_cups: Mapping[str, Iterable[str]] | None = None,
) -> AnexoMultihoja:
    """Procesa todas las hojas de un anexo que corresponden a un tipo.

    Un anexo suele traer varias hojas del mismo tipo (imagenología,
    laboratorio, tablas...). Sin `hojas`, se toman las que se reconocen
    para el tipo y cuyo nombre no apunta a otro tipo; en medicamentos e
    insumos, si alguna hoja lo dice por su nombre, solo esas. El resultado
    informa qué hojas entraron y cuáles no, para poder verificarlo.
    """

    libro = load_workbook(origen, data_only=True, read_only=True)
    try:
        nombres = list(libro.sheetnames)
        candidatas = anexos.detectar_hojas(libro, tipo_cargue)
    finally:
        libro.close()

    if hojas is not None:
        pedidas = {h.strip() for h in hojas}
        elegidas = [c for c in candidatas if c.nombre.strip() in pedidas]
        inexistentes = pedidas - {c.nombre.strip() for c in elegidas}
        if inexistentes:
            raise anexos.LecturaFallida(
                "Hojas no reconocidas para un cargue "
                f"{tipo_cargue}: {', '.join(sorted(inexistentes))}. "
                f"Hojas del archivo: {', '.join(nombres)}"
            )
    else:
        elegidas = [
            c for c in candidatas
            if anexos._puntaje_por_nombre(c.nombre, tipo_cargue) >= 0
        ]
        if tipo_cargue != rules.CARGUE_CUPS:
            con_pista = [
                c for c in elegidas
                if anexos._puntaje_por_nombre(c.nombre, tipo_cargue) > 0
            ]
            elegidas = con_pista or elegidas

    if not elegidas:
        raise anexos.LecturaFallida(
            f"Ninguna hoja del anexo se reconoce como {tipo_cargue}. "
            f"Hojas del archivo: {', '.join(nombres)}"
        )

    registros: list[Registro] = []
    generales: list[Hallazgo] = []
    vistos: set[str] = set()

    for hoja in sorted(elegidas, key=lambda h: nombres.index(h.nombre)):
        resultado = procesar_anexo(
            origen,
            tipo_cargue,
            nombre_archivo=Path(origen).name,
            hoja=hoja.nombre,
            fila_encabezado=hoja.fila_encabezado,
            soat_por_cups=soat_por_cups,
        )
        for registro in resultado.registros:
            registro.hoja = hoja.nombre.strip()
        registros.extend(resultado.registros)

        for hallazgo in resultado.hallazgos_generales:
            if hallazgo.problema not in vistos:
                vistos.add(hallazgo.problema)
                generales.append(hallazgo)

    usadas = [h.nombre.strip() for h in elegidas]
    omitidas = [n.strip() for n in nombres if n.strip() not in usadas]

    return AnexoMultihoja(
        tipo_cargue=tipo_cargue,
        registros=registros,
        hojas_usadas=usadas,
        hojas_omitidas=omitidas,
        hallazgos_generales=generales,
    )


# ============================================================
# SALIDAS
# ============================================================

def _marca_de_tiempo() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def filas_de_reporte(resultado: ResultadoCargue) -> list[dict[str, object]]:
    """Hallazgos en formato tabular, listos para exportar o mostrar."""

    return [h.como_dict() for h in resultado.hallazgos]


def filas_de_registros(resultado: ResultadoCargue) -> list[dict[str, object]]:
    """Todos los registros con su estado y la línea que generarían."""

    filas: list[dict[str, object]] = []

    for registro in resultado.registros:
        filas.append(
            {
                "fila": registro.fila,
                "estado": _estado(registro),
                "codigo": registro.codigo,
                "tipo_tarifa": registro.tipo_tarifa,
                "codigo_ley": registro.codigo_ley,
                "porcentaje": registro.porcentaje,
                "valor_original": registro.valor_original,
                "valor_final": "" if registro.valor is None else registro.valor,
                "descripcion_original": registro.descripcion_original,
                "descripcion_final": registro.descripcion,
                "linea_txt": _linea_previa(registro, resultado.tipo_cargue),
            }
        )

    return filas


_CREAR_PROPIO = re.compile(r"\b(?:CREAR|CREACION)\b.*\bPROPIOS?\b")


def candidatos_a_propio(resultado: ResultadoCargue) -> list[dict[str, object]]:
    """Registros que probablemente necesitan un propio, separados para revisión.

    El sistema no crea nada: solo los junta para que una persona decida.
    Motivos: el anexo dice "crear propio" en alguna columna, o es un traslado.
    """

    candidatos: list[dict[str, object]] = []

    for registro in resultado.registros:
        motivos: list[str] = []

        textos = [
            parsing.normalizar_encabezado(valor)
            for clave, valor in registro.crudo.items()
            if clave != "_fila" and valor is not None
        ]
        if any(_CREAR_PROPIO.search(t) for t in textos):
            motivos.append("el anexo dice 'crear propio'")
        if registro.codigo in rules.CODIGOS_TRASLADO:
            motivos.append("traslado: va como PRO o como propio")

        if motivos:
            candidatos.append(
                {
                    "fila": registro.fila,
                    "codigo": registro.codigo,
                    "descripcion": registro.descripcion_original,
                    "valor_original": registro.valor_original,
                    "estado": _estado(registro),
                    "motivo": "; ".join(motivos),
                }
            )

    return candidatos


def _estado(registro: Registro) -> str:
    if registro.bloqueado:
        return "BLOQUEADO"
    if registro.tiene_advertencias:
        return "REVISAR"
    return "LISTO"


def _linea_previa(registro: Registro, tipo_cargue: str) -> str:
    if registro.bloqueado:
        return ""
    try:
        return txt_writer.construir_linea(registro, tipo_cargue)
    except txt_writer.GeneracionFallida:
        return ""


def _escribir_csv(
    filas: list[dict[str, object]],
    ruta: Path,
    columnas: list[str],
) -> Path:
    ruta.parent.mkdir(parents=True, exist_ok=True)

    # utf-8-sig para que Excel abra bien las tildes del reporte.
    with ruta.open("w", encoding="utf-8-sig", newline="") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=columnas, delimiter=";")
        escritor.writeheader()
        for fila in filas:
            escritor.writerow(fila)

    return ruta


def generar_salidas(
    resultado: ResultadoCargue,
    carpeta: str | Path,
    *,
    prefijo: str | None = None,
    incluir_bloqueados: bool = False,
) -> dict[str, Path]:
    """Escribe el TXT y los reportes en la carpeta indicada.

    Args:
        incluir_bloqueados: normalmente False. Los registros bloqueados no
            deben llegar a GEMANET.

    Returns:
        Diccionario con las rutas generadas.
    """

    destino = Path(carpeta)
    nombre = prefijo or f"{resultado.tipo_cargue}_{_marca_de_tiempo()}"
    rutas: dict[str, Path] = {}

    registros = (
        resultado.registros if incluir_bloqueados else resultado.listos
    )

    if registros:
        rutas["txt"] = txt_writer.escribir_txt(
            registros,
            resultado.tipo_cargue,
            destino / f"{nombre}.txt",
        )

    reporte = filas_de_reporte(resultado)
    if reporte:
        rutas["reporte"] = _escribir_csv(
            reporte,
            destino / f"{nombre}_hallazgos.csv",
            list(reporte[0].keys()),
        )

    detalle = filas_de_registros(resultado)
    if detalle:
        rutas["detalle"] = _escribir_csv(
            detalle,
            destino / f"{nombre}_registros.csv",
            list(detalle[0].keys()),
        )

    pendientes = candidatos_a_propio(resultado)
    if pendientes:
        rutas["propios_pendientes"] = _escribir_csv(
            pendientes,
            destino / f"{nombre}_propios_pendientes.csv",
            list(pendientes[0].keys()),
        )

    return rutas
