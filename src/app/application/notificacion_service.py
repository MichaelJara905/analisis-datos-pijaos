"""Documentos para el prestador: CODIGO - DESCRIPCION - VALOR.

Dos usos, desde cualquier proceso (cargue o conciliación):

    Devolución   lo que quedó BLOQUEADO (códigos o descripciones repetidos,
                 códigos que no son códigos, etc.), con el motivo y dónde está
                 en el anexo, para devolvérselo al prestador.
    Notificación lo que se va a parametrizar y, en otra hoja, lo que debe
                 corregir.

La descripción es la que queda en GEMANET (ya saneada) y los códigos van
exactamente como vienen en el anexo.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from src.app.domain.cargues.model import Registro, Severidad
from src.app.infrastructure.excel import notificacion

HOJA_PARAMETRIZAR = "Para parametrizar"
HOJA_CORREGIR = "Por corregir"
HOJA_DEVOLVER = "Para devolver al prestador"

ENCABEZADOS = ["CODIGO", "DESCRIPCION", "VALOR"]
ENCABEZADOS_CORREGIR = ["CODIGO", "DESCRIPCION", "VALOR", "MOTIVO", "UBICACION"]


def _valor(valor: object) -> object:
    return "" if valor is None else valor


def _ubicacion(hoja: object, fila: object) -> str:
    return f"{hoja} - fila {fila}" if hoja else f"fila {fila}"


def filas_para_parametrizar(registros: Iterable[Registro]) -> list[list[object]]:
    return [
        [r.codigo, r.descripcion or r.descripcion_original, _valor(r.valor)]
        for r in registros
    ]


def filas_por_corregir_de_registros(
    registros: Iterable[Registro],
    hoja: str = "",
) -> list[list[object]]:
    """Registros bloqueados, con el motivo de cada uno y su ubicación.

    Quedan ordenados por código para que las filas repetidas aparezcan juntas.
    """

    filas = []
    for r in sorted(registros, key=lambda r: (r.codigo.strip(), r.fila)):
        motivo = "; ".join(
            h.problema for h in r.hallazgos if h.severidad is Severidad.BLOQUEANTE
        )
        filas.append(
            [
                r.codigo,
                r.descripcion_original or r.descripcion,
                r.valor_original or _valor(r.valor),
                motivo,
                _ubicacion(r.hoja or hoja, r.fila),
            ]
        )
    return filas


def filas_por_corregir_de_informe(filas_informe: Iterable[Mapping[str, object]]) -> list[list[object]]:
    """Filas del informe de la conciliación ('faltan con error')."""

    ordenadas = sorted(
        filas_informe, key=lambda f: (str(f.get("codigo", "")).strip(), str(f.get("hoja", "")), int(f.get("fila", 0) or 0))
    )
    return [
        [
            f.get("codigo", ""),
            f.get("descripcion", ""),
            f.get("valor", ""),
            f.get("motivo", ""),
            _ubicacion(f.get("hoja", ""), f.get("fila", "")),
        ]
        for f in ordenadas
    ]


def excel_de_devolucion(por_devolver: list[list[object]]) -> bytes | None:
    """Excel con SOLO lo bloqueado, para devolverlo al prestador; None si no hay."""

    if not por_devolver:
        return None
    return notificacion.crear_excel({HOJA_DEVOLVER: (ENCABEZADOS_CORREGIR, por_devolver)})


def excel_de_notificacion(
    para_parametrizar: list[list[object]],
    por_corregir: list[list[object]] | None = None,
) -> bytes | None:
    """Excel con las hojas que tengan filas; None si no hay nada que notificar."""

    hojas: dict[str, tuple[list[str], list[list[object]]]] = {}
    if para_parametrizar:
        hojas[HOJA_PARAMETRIZAR] = (ENCABEZADOS, para_parametrizar)
    if por_corregir:
        hojas[HOJA_CORREGIR] = (ENCABEZADOS_CORREGIR, por_corregir)

    return notificacion.crear_excel(hojas) if hojas else None
