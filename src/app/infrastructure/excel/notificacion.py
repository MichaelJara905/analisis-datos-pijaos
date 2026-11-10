"""Escritura del documento para notificar al prestador.

Una hoja por lista, con columnas fijas. Los códigos se escriben como TEXTO
para que Excel no les quite los ceros a la izquierda ni los convierta en
fecha o en número.
"""

from __future__ import annotations

from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

ANCHOS = {"CODIGO": 24, "DESCRIPCION": 72, "VALOR": 16, "MOTIVO": 90, "UBICACION": 30}
COLUMNAS_DE_TEXTO = ("CODIGO", "DESCRIPCION", "MOTIVO", "UBICACION")


def crear_excel(hojas: dict[str, tuple[list[str], list[list[object]]]]) -> bytes:
    """Serializa {nombre_de_hoja: (encabezados, filas)} como un archivo xlsx."""

    libro = Workbook()
    libro.remove(libro.active)

    for nombre, (encabezados, filas) in hojas.items():
        hoja = libro.create_sheet(nombre[:31])
        hoja.append(encabezados)

        for fila in filas:
            hoja.append(list(fila))

        for celda in hoja[1]:
            celda.font = Font(bold=True, color="FFFFFF")
            celda.fill = PatternFill("solid", fgColor="146C94")
            celda.alignment = Alignment(vertical="center")

        for posicion, encabezado in enumerate(encabezados, start=1):
            letra = hoja.cell(row=1, column=posicion).column_letter
            hoja.column_dimensions[letra].width = ANCHOS.get(encabezado, 20)

            for (celda,) in hoja.iter_rows(min_row=2, min_col=posicion, max_col=posicion):
                if encabezado in COLUMNAS_DE_TEXTO:
                    celda.number_format = "@"
                    if celda.value is not None:
                        celda.value = str(celda.value)
                elif encabezado == "VALOR":
                    celda.number_format = "#,##0"

        hoja.freeze_panes = "A2"
        hoja.auto_filter.ref = hoja.dimensions

    salida = BytesIO()
    libro.save(salida)
    return salida.getvalue()
