"""Caso de uso: preparar un anexo tarifario para el cargue en GEMANET.

Orquesta las capas: lee con infrastructure, valida con domain y arma los
reportes que consume la interfaz.

El archivo original nunca se modifica. Todo lo que produce el proceso se
escribe en una carpeta de salida aparte, con fecha y hora en el nombre.
"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import BinaryIO

from src.app.domain.cargues import rules, txt_writer, validators
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

    return rutas
