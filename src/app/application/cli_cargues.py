"""Uso del cargue desde la terminal, sin levantar la aplicación.

Ejemplo:

    python -m src.app.application.cli_cargues anexo_traumasur.xlsx \\
        --tipo INS --salida salidas/

Genera en la carpeta de salida:
    <TIPO>_<fecha>.txt             archivo para GEMANET
    <TIPO>_<fecha>_hallazgos.csv   qué se corrigió y qué hay que revisar
    <TIPO>_<fecha>_registros.csv   cada fila con su estado y su línea
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.app.application import cargues_service
from src.app.domain.cargues import rules
from src.app.domain.cargues.model import Severidad
from src.app.infrastructure.excel.anexos import LecturaFallida


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepara un anexo tarifario para el cargue en GEMANET.",
    )
    parser.add_argument("anexo", help="ruta del archivo Excel")
    parser.add_argument(
        "--tipo",
        required=True,
        choices=rules.TIPOS_DE_CARGUE,
        help="tipo de cargue",
    )
    parser.add_argument(
        "--salida",
        default="salidas",
        help="carpeta donde se escriben los resultados (por defecto: salidas)",
    )
    parser.add_argument("--hoja", default=None, help="forzar una hoja")
    parser.add_argument(
        "--fila-encabezado",
        type=int,
        default=None,
        help="forzar la fila de encabezados (base 1)",
    )
    parser.add_argument(
        "--solo-analizar",
        action="store_true",
        help="no escribe archivos, solo muestra el resumen",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    argumentos = construir_parser().parse_args(argv)
    ruta = Path(argumentos.anexo)

    if not ruta.exists():
        print(f"No existe el archivo: {ruta}", file=sys.stderr)
        return 2

    try:
        resultado = cargues_service.procesar_anexo(
            ruta,
            argumentos.tipo,
            nombre_archivo=ruta.name,
            hoja=argumentos.hoja,
            fila_encabezado=argumentos.fila_encabezado,
        )
    except LecturaFallida as error:
        print(f"No se pudo leer el anexo:\n{error}", file=sys.stderr)
        return 3

    _imprimir_resumen(resultado)

    if argumentos.solo_analizar:
        return 0

    rutas = cargues_service.generar_salidas(resultado, argumentos.salida)

    print("\nArchivos generados:")
    for clave, destino in rutas.items():
        print(f"  {clave:9} {destino}")

    if not resultado.listos:
        print("\nNo se generó TXT: ningún registro quedó listo.")
        return 1

    print(
        "\nRevisa el reporte antes de subir el archivo a GEMANET. "
        "El anexo original no fue modificado."
    )
    return 0


def _imprimir_resumen(resultado) -> None:
    resumen = resultado.resumen()

    print(f"Anexo   : {resultado.archivo_origen}")
    print(f"Cargue  : {resultado.tipo_cargue}")
    print(f"Hoja    : {resultado.hoja} (encabezados en la fila "
          f"{resultado.fila_encabezado})")
    print("Columnas:")
    for campo, encabezado in resultado.mapeo_columnas.items():
        print(f"  {campo:12} <- {encabezado}")

    print("\nResumen:")
    for clave, valor in resumen.items():
        print(f"  {clave:20} {valor}")

    bloqueantes = [
        h for h in resultado.hallazgos if h.severidad is Severidad.BLOQUEANTE
    ]
    if bloqueantes:
        print(f"\nPrimeros bloqueos ({len(bloqueantes)} en total):")
        for hallazgo in bloqueantes[:15]:
            print(f"  fila {hallazgo.fila:>5}  {hallazgo.campo:12} {hallazgo.problema}")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
