"""Conciliación de un anexo contra el reporte de GEMANET, desde la terminal.

Ejemplo:

    python -m src.app.application.cli_conciliar anexo.xlsx --tipo CUPS \\
        --gemanet GEMA_CUPS.xlsx --referencias carpeta_refs --salida salidas/

Genera (solo informes, no se crea ningún TXT):
    <TIPO>_<fecha>_faltantes.csv         lo que no está cargado: LISTO PARA CARGAR
                                         (con su línea) o CON ERROR (con el motivo)
    <TIPO>_<fecha>_diferencias.csv       cargado con otro valor o tipo
    <TIPO>_<fecha>_solo_en_gemanet.csv   está en GEMANET y el anexo no lo trae
    <TIPO>_<fecha>_inconsistencias.csv   códigos repetidos y anomalías del reporte
    <TIPO>_<fecha>_resumen.csv           conteos y hojas usadas
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.app.application import conciliacion_service, referencias_service
from src.app.domain.cargues import rules
from src.app.infrastructure.excel.anexos import LecturaFallida
from src.app.infrastructure.excel.gemanet import LecturaGemanetFallida
from src.app.infrastructure.referencias.repositorio import ReferenciaNoDisponible


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Concilia un anexo con lo que ya está cargado en GEMANET.",
    )
    parser.add_argument("anexo", help="ruta del anexo (Excel)")
    parser.add_argument("--tipo", required=True, choices=rules.TIPOS_DE_CARGUE)
    parser.add_argument("--gemanet", required=True, help="reporte exportado de GEMANET (Excel)")
    parser.add_argument("--hojas", default=None, help="hojas del anexo separadas por coma")
    parser.add_argument("--referencias", default=None, help="carpeta con el SUPERHOMOLOGADOR")
    parser.add_argument("--salida", default="salidas", help="carpeta de salida")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = construir_parser().parse_args(argv)

    for ruta in (args.anexo, args.gemanet):
        if not Path(ruta).exists():
            print(f"No existe el archivo: {ruta}", file=sys.stderr)
            return 2

    soat_por_cups = None
    if args.referencias:
        try:
            soat_por_cups = referencias_service.cargar_soat_por_cups(args.referencias)
        except ReferenciaNoDisponible as error:
            print(f"No se pudo cargar el homologador: {error}", file=sys.stderr)
            return 4

    hojas = [h for h in args.hojas.split(",")] if args.hojas else None

    try:
        resultado, procesado, reporte = conciliacion_service.conciliar_anexo(
            args.anexo,
            args.tipo,
            args.gemanet,
            hojas=hojas,
            soat_por_cups=soat_por_cups,
        )
    except (LecturaFallida, LecturaGemanetFallida) as error:
        print(f"No se pudo leer:\n{error}", file=sys.stderr)
        return 3

    print(f"Anexo    : {Path(args.anexo).name}")
    print(f"Reporte  : {reporte.archivo} ({len(reporte.registros)} registros)")
    print(f"Hojas usadas   : {', '.join(procesado.hojas_usadas)}")
    print(f"Hojas omitidas : {', '.join(procesado.hojas_omitidas) or '-'}")
    print("\nConciliación:")
    for clave, valor in resultado.resumen().items():
        print(f"  {clave:28} {valor}")

    rutas = conciliacion_service.generar_informes(resultado, procesado, args.salida)
    print("\nInformes generados:")
    for clave, destino in rutas.items():
        print(f"  {clave:16} {destino}")

    print("\nSolo informes: no se generó ningún TXT. Los originales no se modificaron.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
