"""Lectura de la lista de propios que se quieren crear.

Acepta Excel (.xlsx) o CSV con las columnas NOMBRE, VALOR y CUPS, en
cualquier orden y con la fila de encabezados en cualquier lugar de las
primeras 20 filas.
"""

from __future__ import annotations

import csv
from pathlib import Path

from openpyxl import load_workbook

from src.app.domain.cargues.parsing import normalizar_encabezado
from src.app.domain.cargues.propios import SolicitudPropio

ALIAS = {
    "nombre": ("NOMBRE", "NOMBRE DEL PROPIO", "DESCRIPCION", "SERVICIO"),
    "valor": ("VALOR", "TARIFA", "PRECIO", "VALOR UNITARIO"),
    "cups": ("CUPS", "CODIGO CUPS", "CUPS ASOCIADO"),
}
MAXIMO_FILAS_ENCABEZADO = 20


class LecturaPropiosFallida(Exception):
    """No se pudo leer la lista de propios."""


def _mapear(fila: list[object]) -> dict[str, int]:
    normalizados = {
        i: normalizar_encabezado(v) for i, v in enumerate(fila) if v is not None
    }
    columnas: dict[str, int] = {}
    for campo, alias in ALIAS.items():
        for nombre in alias:
            hallado = next(
                (i for i, t in normalizados.items()
                 if t == nombre and i not in columnas.values()),
                None,
            )
            if hallado is not None:
                columnas[campo] = hallado
                break
    return columnas


def _filas_de(ruta: Path) -> list[list[object]]:
    if ruta.suffix.lower() == ".csv":
        with ruta.open(encoding="utf-8-sig", newline="") as archivo:
            muestra = archivo.read(4096)
            archivo.seek(0)
            delimitador = ";" if muestra.count(";") >= muestra.count(",") else ","
            return [list(f) for f in csv.reader(archivo, delimiter=delimitador)]

    libro = load_workbook(ruta, data_only=True, read_only=True)
    try:
        return [list(f) for f in libro.worksheets[0].iter_rows(values_only=True)]
    finally:
        libro.close()


def leer_solicitudes(origen: str | Path) -> list[SolicitudPropio]:
    ruta = Path(origen)
    filas = _filas_de(ruta)

    for numero, fila in enumerate(filas[:MAXIMO_FILAS_ENCABEZADO], start=1):
        columnas = _mapear(fila)
        if len(columnas) == len(ALIAS):
            break
    else:
        raise LecturaPropiosFallida(
            "No se encontró una fila con las columnas NOMBRE, VALOR y CUPS "
            f"en las primeras {MAXIMO_FILAS_ENCABEZADO} filas de '{ruta.name}'."
        )

    solicitudes: list[SolicitudPropio] = []
    for indice, fila in enumerate(filas[numero:], start=numero + 1):
        if all(c is None or str(c).strip() == "" for c in fila):
            continue

        def celda(campo: str) -> object:
            posicion = columnas[campo]
            return fila[posicion] if posicion < len(fila) else None

        solicitudes.append(
            SolicitudPropio(
                fila=indice,
                nombre=celda("nombre"),
                valor=celda("valor"),
                cups=celda("cups"),
            )
        )

    return solicitudes
