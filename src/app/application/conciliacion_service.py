"""Caso de uso: conciliar un anexo con lo que ya está en GEMANET.

Fase 1: solo informes. No genera TXT; muestra, junto a lo que falta, la
línea con la que se cargaría. Los casos dudosos van a un reporte aparte.
Los archivos originales nunca se modifican.
"""

from __future__ import annotations

import csv
from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import Path

from src.app.application import cargues_service
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


def generar_informes(
    resultado: conciliacion.ResultadoConciliacion,
    procesado: cargues_service.AnexoMultihoja,
    carpeta: str | Path,
    *,
    prefijo: str | None = None,
) -> dict[str, Path]:
    destino = Path(carpeta)
    destino.mkdir(parents=True, exist_ok=True)
    nombre = prefijo or f"{resultado.tipo_cargue}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    informes = {
        "faltantes": resultado.faltan_listos + resultado.faltan_con_error,
        "diferencias": resultado.diferencias,
        "solo_en_gemanet": resultado.solo_gemanet,
        "inconsistencias": resultado.inconsistencias,
    }

    rutas: dict[str, Path] = {}
    for clave, filas in informes.items():
        if filas:
            rutas[clave] = _csv(filas, destino / f"{nombre}_{clave}.csv")

    resumen = [
        {"concepto": clave.replace("_", " "), "cantidad": valor}
        for clave, valor in resultado.resumen().items()
    ]
    resumen.append({"concepto": "hojas usadas", "cantidad": ", ".join(procesado.hojas_usadas)})
    resumen.append({"concepto": "hojas omitidas", "cantidad": ", ".join(procesado.hojas_omitidas)})
    rutas["resumen"] = _csv(resumen, destino / f"{nombre}_resumen.csv")

    return rutas


def hallazgos_generales(procesado: cargues_service.AnexoMultihoja) -> list[Hallazgo]:
    return procesado.hallazgos_generales
