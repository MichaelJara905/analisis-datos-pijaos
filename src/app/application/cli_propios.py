"""Creación de propios desde la terminal.

Ejemplo:

    python -m src.app.application.cli_propios propios.xlsx \\
        --ultimo-pro PRO5715 --salida salidas/

`propios.xlsx` (o .csv) trae las columnas NOMBRE, VALOR y CUPS. Genera:
    <PREFIJO>_creacion.txt     nombre|PRO####|valor|CUPS
    <PREFIJO>_carga_cups.txt   PRO####;valor;PRO;0;0;
    <PREFIJO>_asignacion.csv   qué código recibió cada solicitud
    <PREFIJO>_hallazgos.csv    correcciones, advertencias y bloqueos

Anota el último código asignado: es el punto de partida de la próxima vez.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.app.application import propios_service, referencias_service
from src.app.domain.cargues.propios import CodigoInvalido
from src.app.infrastructure.excel.propios import (
    LecturaPropiosFallida,
    leer_solicitudes,
)
from src.app.infrastructure.referencias.repositorio import ReferenciaNoDisponible


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepara la creación de propios.")
    parser.add_argument("solicitudes", help="Excel o CSV con NOMBRE, VALOR y CUPS")
    parser.add_argument("--ultimo-pro", required=True, help="último código usado, ej. PRO5715")
    parser.add_argument("--salida", default="salidas", help="carpeta de salida")
    parser.add_argument("--referencias", default=None, help="carpeta con el SUPERHOMOLOGADOR")
    parser.add_argument("--solo-analizar", action="store_true", help="no escribe archivos")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = construir_parser().parse_args(argv)
    ruta = Path(args.solicitudes)

    if not ruta.exists():
        print(f"No existe el archivo: {ruta}", file=sys.stderr)
        return 2

    cups_conocidos = None
    if args.referencias:
        try:
            cups_conocidos = referencias_service.cargar_soat_por_cups(args.referencias).keys()
        except ReferenciaNoDisponible as error:
            print(f"No se pudo cargar el homologador: {error}", file=sys.stderr)
            return 4

    try:
        solicitudes = leer_solicitudes(ruta)
        lista = propios_service.crear_propios(
            solicitudes, args.ultimo_pro, cups_conocidos=cups_conocidos
        )
    except (LecturaPropiosFallida, CodigoInvalido) as error:
        print(str(error), file=sys.stderr)
        return 3

    print("Resumen:")
    for clave, valor in propios_service.resumen(lista).items():
        print(f"  {clave:14} {valor}")

    bloqueados = [p for p in lista if p.bloqueado]
    for p in bloqueados[:15]:
        motivo = next(h.problema for h in p.hallazgos if h.severidad.value == "BLOQUEANTE")
        print(f"  fila {p.fila:>5}  BLOQUEADO  {motivo}")

    if args.solo_analizar:
        return 0

    rutas = propios_service.generar_salidas(lista, args.salida)
    print("\nArchivos generados:")
    for clave, destino in rutas.items():
        print(f"  {clave:11} {destino}")

    asignados = [p.codigo for p in lista if p.codigo]
    if asignados:
        print(f"\nÚltimo código asignado: {asignados[-1]} (úsalo en la próxima ejecución)")
        return 0

    print("\nNo se generó TXT: ninguna solicitud quedó lista.")
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
