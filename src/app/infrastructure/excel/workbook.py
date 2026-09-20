"""Lectura y escritura de archivos Excel.

Toda la dependencia de openpyxl y del formato xlsx vive aquí. Las capas de
aplicación y dominio no saben que los datos vienen de un Excel.
"""

from __future__ import annotations

from io import BytesIO
from typing import BinaryIO

import polars as pl
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

# Columnas que debe traer la plantilla de tarifas.
REQUIRED_COLUMNS = ("codigo_servicio", "descripcion", "valor_servicio")


def read_template(uploaded_file: BinaryIO) -> pl.DataFrame:
    """Lee la plantilla de tarifas y verifica que tenga las columnas.

    No transforma tipos: de eso se encarga la capa de aplicación.
    """

    df = pl.read_excel(uploaded_file)
    df = df.rename({column: str(column).strip().lower() for column in df.columns})

    missing = sorted(set(REQUIRED_COLUMNS) - set(df.columns))
    if missing:
        raise ValueError(
            "La plantilla debe contener las columnas: "
            f"{', '.join(REQUIRED_COLUMNS)}. Faltan: {', '.join(missing)}."
        )

    return df.select(REQUIRED_COLUMNS)


def create_template() -> bytes:
    """Construye la plantilla Excel descargable para el usuario."""

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "tarifas"

    headers = list(REQUIRED_COLUMNS)
    sheet.append(headers)
    sheet.append(["", "Ejemplo de servicio", 0])
    sheet.append(["", "", ""])

    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="146C94")

    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = "A1:C3"
    sheet.column_dimensions["A"].width = 22
    sheet.column_dimensions["B"].width = 55
    sheet.column_dimensions["C"].width = 18

    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def create_excel_download(df: pl.DataFrame, sheet_name: str = "tarifas") -> bytes:
    """Serializa un DataFrame Polars como archivo Excel."""

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = sheet_name[:31]

    sheet.append(df.columns)
    for row in df.iter_rows():
        sheet.append(list(row))

    sheet.freeze_panes = "A2"

    output = BytesIO()
    workbook.save(output)
    return output.getvalue()
