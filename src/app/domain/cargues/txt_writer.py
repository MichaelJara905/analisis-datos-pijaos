"""Generación del archivo TXT para el cargue masivo en GEMANET.

Estructura confirmada contra archivos que cargaron correctamente:

    CUMS / INS (6 campos)
        codigo;valor_o_codigo_ley;tipo;porcentaje;descripcion;norma;

    CUPS (5 campos)
        codigo;valor_o_codigo_ley;tipo;porcentaje;norma;

Reglas del archivo:
    - separador ';'
    - cada registro cierra con ';'
    - CRLF entre registros
    - sin salto de línea al final
    - sin espacios fuera de la estructura
"""

from __future__ import annotations

from pathlib import Path

from src.app.domain.cargues import rules
from src.app.domain.cargues.model import Registro


class GeneracionFallida(Exception):
    """El registro no se puede convertir en una línea del TXT."""


def _campo_valor(registro: Registro) -> str:
    """Campo 2: el valor si es tarifa propia, el código ley si es regulada."""

    if registro.es_regulado:
        if not registro.codigo_ley:
            raise GeneracionFallida(
                f"Fila {registro.fila}: tarifa {registro.tipo_tarifa} "
                "sin código ley."
            )
        return registro.codigo_ley

    if registro.valor is None:
        raise GeneracionFallida(
            f"Fila {registro.fila}: tarifa propia sin valor numérico."
        )

    return str(registro.valor)


def construir_linea(registro: Registro, tipo_cargue: str) -> str:
    """Arma la línea de un registro, sin el salto de línea."""

    campos = [
        registro.codigo,
        _campo_valor(registro),
        registro.tipo_tarifa or rules.TARIFA_PROPIA,
        str(registro.porcentaje),
    ]

    if tipo_cargue != rules.CARGUE_CUPS:
        campos.append(registro.descripcion)
    else:
        campos.append(rules.PORCENTAJE_DE_NORMA_POR_DEFECTO)

    if tipo_cargue != rules.CARGUE_CUPS:
        campos.append(rules.PORCENTAJE_DE_NORMA_POR_DEFECTO)

    for campo in campos:
        if rules.SEPARADOR in campo:
            raise GeneracionFallida(
                f"Fila {registro.fila}: el campo '{campo}' contiene ';'."
            )

    return rules.SEPARADOR.join(campos) + rules.TERMINADOR_DE_REGISTRO


def construir_contenido(
    registros: list[Registro],
    tipo_cargue: str,
) -> str:
    """Arma el contenido completo del TXT."""

    lineas = [construir_linea(r, tipo_cargue) for r in registros]
    contenido = rules.FIN_DE_LINEA.join(lineas)

    if lineas and rules.NUEVA_LINEA_AL_FINAL:
        contenido += rules.FIN_DE_LINEA

    return contenido


def construir_bytes(
    registros: list[Registro],
    tipo_cargue: str,
) -> bytes:
    """Contenido del TXT ya codificado, listo para descargar o escribir."""

    contenido = construir_contenido(registros, tipo_cargue)

    try:
        return contenido.encode(rules.CODIFICACION)
    except UnicodeEncodeError as error:  # pragma: no cover - lo evita el saneador
        raise GeneracionFallida(
            "Quedaron caracteres que no se pueden codificar en "
            f"{rules.CODIFICACION}: {error.object[error.start:error.end]!r}"
        ) from error


def escribir_txt(
    registros: list[Registro],
    tipo_cargue: str,
    destino: str | Path,
) -> Path:
    """Escribe el archivo en disco sin tocar ningún original."""

    ruta = Path(destino)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(construir_bytes(registros, tipo_cargue))
    return ruta
