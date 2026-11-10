"""Documento para notificar al prestador: CODIGO - DESCRIPCION - VALOR.

Se genera desde cualquier proceso (cargue o conciliación) con lo que se va a
parametrizar, y opcionalmente con una segunda hoja de lo que el prestador
debe corregir y por qué. La descripción es la que queda en GEMANET (ya
saneada) y los códigos van exactamente como vienen en el anexo.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from src.app.domain.cargues.model import Registro, Severidad
from src.app.infrastructure.excel import notificacion

HOJA_PARAMETRIZAR = "Para parametrizar"
HOJA_CORREGIR = "Por corregir"

ENCABEZADOS = ["CODIGO", "DESCRIPCION", "VALOR"]
ENCABEZADOS_CORREGIR = ["CODIGO", "DESCRIPCION", "VALOR", "MOTIVO"]


def _valor(valor: object) -> object:
    return "" if valor is None else valor


def filas_para_parametrizar(registros: Iterable[Registro]) -> list[list[object]]:
    return [
        [r.codigo, r.descripcion or r.descripcion_original, _valor(r.valor)]
        for r in registros
    ]


def filas_por_corregir_de_registros(registros: Iterable[Registro]) -> list[list[object]]:
    """Registros bloqueados, con el motivo de cada uno."""

    filas = []
    for r in registros:
        motivo = "; ".join(
            h.problema for h in r.hallazgos if h.severidad is Severidad.BLOQUEANTE
        )
        filas.append(
            [r.codigo, r.descripcion_original or r.descripcion, r.valor_original or _valor(r.valor), motivo]
        )
    return filas


def filas_por_corregir_de_informe(filas_informe: Iterable[Mapping[str, object]]) -> list[list[object]]:
    """Filas del informe de la conciliación ('faltan con error')."""

    return [
        [f.get("codigo", ""), f.get("descripcion", ""), f.get("valor", ""), f.get("motivo", "")]
        for f in filas_informe
    ]


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
