"""Caso de uso: conciliar un anexo con lo que ya está en GEMANET.

Descarta lo que ya está cargado y genera el TXT solo con lo que falta y se
puede cargar. Todo lo demás va a informes aparte: lo que falta pero tiene
error (con su motivo), lo cargado con otro valor o tipo, los códigos
repetidos del anexo y lo que GEMANET tiene y el anexo no.
Los archivos originales nunca se modifican.
"""

from __future__ import annotations

import csv
from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import Path

from src.app.application import cargues_service, notificacion_service
from src.app.domain.cargues import conciliacion, txt_writer
from src.app.domain.cargues.model import Hallazgo, Registro
from src.app.infrastructure.excel import gemanet


def conciliar_anexo(
    anexo: str | Path,
    tipo_cargue: str,
    reporte_gemanet: str | Path,
    *,
    hojas: list[str] | None = None,
    soat_por_cups: Mapping[str, Iterable[str]] | None = None,
) -> tuple[
    conciliacion.ResultadoConciliacion,
    cargues_service.AnexoMultihoja,
    gemanet.ReporteGemanet,
]:
    procesado = cargues_service.procesar_anexo_multihoja(
        anexo, tipo_cargue, hojas=hojas, soat_por_cups=soat_por_cups
    )
    reporte = gemanet.leer_reporte(reporte_gemanet)

    def linea(registro: Registro) -> str:
        try:
            return txt_writer.construir_linea(registro, tipo_cargue)
        except txt_writer.GeneracionFallida:
            return ""

    resultado = conciliacion.conciliar(
        procesado.registros, reporte.registros, tipo_cargue, linea=linea
    )
    resultado.inconsistencias.extend(reporte.anomalias)

    return resultado, procesado, reporte


def _csv(filas: list[dict[str, object]], ruta: Path) -> Path:
    with ruta.open("w", encoding="utf-8-sig", newline="") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=list(filas[0].keys()), delimiter=";")
        escritor.writeheader()
        escritor.writerows(filas)
    return ruta


class TxtInconsistente(Exception):
    """El TXT armado no pasó la verificación final y no se escribió."""


def construir_txt(resultado: conciliacion.ResultadoConciliacion) -> bytes:
    """TXT con SOLO lo que falta en GEMANET y se puede cargar."""

    return txt_writer.construir_bytes(resultado.a_cargar, resultado.tipo_cargue)


def construir_notificacion(resultado: conciliacion.ResultadoConciliacion) -> bytes | None:
    """CODIGO - DESCRIPCION - VALOR de lo que se va a parametrizar, y en otra
    hoja lo que el prestador debe corregir (con el motivo)."""

    return notificacion_service.excel_de_notificacion(
        notificacion_service.filas_para_parametrizar(resultado.a_cargar),
        notificacion_service.filas_por_corregir_de_informe(resultado.faltan_con_error),
    )


def verificar_txt(
    contenido: bytes,
    gemanet: Mapping[str, conciliacion.RegistroGemanet],
) -> list[str]:
    """Verificación final del TXT ya armado, leyéndolo como lo leerá GEMANET.

    Ninguna línea puede repetir un código ni traer uno que ya esté cargado:
    es justo el error "ya existe en este tarifario" que se quiere evitar.
    """

    if not contenido:
        return []

    problemas: list[str] = []
    vistos: set[str] = set()
    for numero, linea in enumerate(contenido.decode("ascii").split("\r\n"), start=1):
        codigo = conciliacion.clave_codigo(linea.split(";")[0])
        if codigo in vistos:
            problemas.append(f"línea {numero}: el código {codigo} se repite en el TXT")
        vistos.add(codigo)
        if codigo in gemanet:
            problemas.append(f"línea {numero}: el código {codigo} ya está en GEMANET")
    return problemas


def generar_informes(
    resultado: conciliacion.ResultadoConciliacion,
    procesado: cargues_service.AnexoMultihoja,
    carpeta: str | Path,
    *,
    prefijo: str | None = None,
    reporte: gemanet.ReporteGemanet | None = None,
    con_txt: bool = True,
) -> dict[str, Path]:
    """Escribe los informes y, salvo `con_txt=False`, el TXT de lo que falta.

    Raises:
        TxtInconsistente: si el TXT repite códigos o trae alguno que ya está
            en GEMANET. En ese caso no se escribe nada.
    """

    destino = Path(carpeta)
    destino.mkdir(parents=True, exist_ok=True)
    nombre = prefijo or f"{resultado.tipo_cargue}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    rutas: dict[str, Path] = {}

    if con_txt and resultado.a_cargar:
        contenido = construir_txt(resultado)
        problemas = verificar_txt(contenido, reporte.registros if reporte else {})
        if problemas:
            raise TxtInconsistente("; ".join(problemas[:5]))
        rutas["txt"] = destino / f"{nombre}_para_cargar.txt"
        rutas["txt"].write_bytes(contenido)

    informes = {
        "faltantes": resultado.faltan_listos + resultado.faltan_con_error,
        "diferencias": resultado.diferencias,
        "solo_en_gemanet": resultado.solo_gemanet,
        "inconsistencias": resultado.inconsistencias,
    }

    for clave, filas in informes.items():
        if filas:
            rutas[clave] = _csv(filas, destino / f"{nombre}_{clave}.csv")

    excel = construir_notificacion(resultado)
    if excel is not None:
        rutas["notificacion"] = destino / f"{nombre}_notificacion.xlsx"
        rutas["notificacion"].write_bytes(excel)

    resumen = [
        {"concepto": clave.replace("_", " "), "cantidad": valor}
        for clave, valor in resultado.resumen().items()
    ]
    resumen.append({"concepto": "lineas del TXT", "cantidad": len(resultado.a_cargar) if "txt" in rutas else 0})
    resumen.append({"concepto": "hojas usadas", "cantidad": ", ".join(procesado.hojas_usadas)})
    resumen.append({"concepto": "hojas omitidas", "cantidad": ", ".join(procesado.hojas_omitidas)})
    rutas["resumen"] = _csv(resumen, destino / f"{nombre}_resumen.csv")

    return rutas


def hallazgos_generales(procesado: cargues_service.AnexoMultihoja) -> list[Hallazgo]:
    return procesado.hallazgos_generales
