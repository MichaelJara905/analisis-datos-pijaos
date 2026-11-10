"""Caso de uso: crear propios para GEMANET.

Genera juntos el TXT de creación (`nombre|PRO####|valor|CUPS`) y el TXT de
carga CUPS (`PRO####;valor;PRO;0;0;`), más el reporte de asignación. Solo
incluye las solicitudes sin bloqueos. Nada se crea sin que se invoque
explícitamente este caso de uso.
"""

from __future__ import annotations

import csv
from collections.abc import Collection
from datetime import datetime
from pathlib import Path

from src.app.domain.cargues import propios
from src.app.domain.cargues.model import Severidad
from src.app.domain.cargues.propios import Propio, SolicitudPropio


def filas_de_asignacion(lista: list[Propio]) -> list[dict[str, object]]:
    return [
        {
            "fila": p.fila,
            "estado": "BLOQUEADO" if p.bloqueado else "LISTO",
            "codigo": p.codigo,
            "nombre": p.nombre,
            "valor": "" if p.valor is None else p.valor,
            "cups": p.cups,
            "nombre_original": p.nombre_original,
        }
        for p in lista
    ]


def filas_de_hallazgos(lista: list[Propio]) -> list[dict[str, object]]:
    return [h.como_dict() for p in lista for h in p.hallazgos]


def _csv(filas: list[dict[str, object]], ruta: Path) -> Path:
    with ruta.open("w", encoding="utf-8-sig", newline="") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=list(filas[0].keys()), delimiter=";")
        escritor.writeheader()
        escritor.writerows(filas)
    return ruta


def resumen(lista: list[Propio]) -> dict[str, int]:
    hallazgos = [h for p in lista for h in p.hallazgos]
    return {
        "solicitudes": len(lista),
        "listos": sum(1 for p in lista if not p.bloqueado),
        "bloqueados": sum(1 for p in lista if p.bloqueado),
        "correcciones": sum(1 for h in hallazgos if h.severidad is Severidad.CORRECCION),
        "advertencias": sum(1 for h in hallazgos if h.severidad is Severidad.ADVERTENCIA),
    }


def generar_salidas(
    lista: list[Propio],
    carpeta: str | Path,
    *,
    prefijo: str | None = None,
) -> dict[str, Path]:
    """Escribe los archivos; los originales nunca se tocan."""

    destino = Path(carpeta)
    destino.mkdir(parents=True, exist_ok=True)
    nombre = prefijo or f"PROPIOS_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    rutas: dict[str, Path] = {}

    listos = [p for p in lista if not p.bloqueado]
    if listos:
        rutas["creacion"] = destino / f"{nombre}_creacion.txt"
        rutas["creacion"].write_bytes(propios.construir_bytes_creacion(listos))
        rutas["carga"] = destino / f"{nombre}_carga_cups.txt"
        rutas["carga"].write_bytes(propios.construir_bytes_carga(listos))

    if lista:
        rutas["asignacion"] = _csv(filas_de_asignacion(lista), destino / f"{nombre}_asignacion.csv")
    hallazgos = filas_de_hallazgos(lista)
    if hallazgos:
        rutas["hallazgos"] = _csv(hallazgos, destino / f"{nombre}_hallazgos.csv")

    return rutas


def crear_propios(
    solicitudes: list[SolicitudPropio],
    ultimo_usado: object,
    *,
    cups_conocidos: Collection[str] | None = None,
) -> list[Propio]:
    return propios.preparar_propios(
        solicitudes, ultimo_usado, cups_conocidos=cups_conocidos
    )
