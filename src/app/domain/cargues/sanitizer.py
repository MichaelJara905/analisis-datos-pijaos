"""Saneamiento de descripciones para el cargue GEMANET.

Este saneador es DISTINTO de `modules.tarifas.transformations.sanitize_text`.
Aquel borra todo lo que no sea letra, número o espacio, lo cual sirve para
cargar a base de datos pero destruye las referencias de los insumos:

    "CATETER 8 FR X 240 CM (REF HBD-W-18-19-20)"
    -> "CATETER 8 FR X 240 CM REF HBD W 18 19 20"

Los TXT que GEMANET aceptó conservan paréntesis, guiones, comas y barras.
Por eso aquí solo se toca lo que efectivamente daña el cargue.
"""

from __future__ import annotations

import re
import unicodedata

from src.app.domain.cargues import rules

_PATRON_NUMERO = re.compile(rules.PATRON_NUMERO_ABREVIADO)
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def _quitar_tildes(texto: str) -> str:
    """Quita tildes y diéresis dejando la letra base.

    La Ñ también se resuelve aquí: se descompone en N + tilde combinante,
    y al eliminar la tilde queda N.
    """

    descompuesto = unicodedata.normalize("NFD", texto)
    return "".join(
        caracter
        for caracter in descompuesto
        if not unicodedata.combining(caracter)
    )


def sanear_descripcion(texto: str | None) -> tuple[str, list[str]]:
    """Devuelve la descripción lista para el TXT y la lista de cambios.

    Nunca se cambia nada en silencio: cada transformación aplicada queda
    descrita en la segunda parte de la tupla.

    Orden de aplicación:
        1. Caracteres de control y saltos de línea.
        2. "N°" / "Nº"  ->  "NRO".
        3. Tabla de reemplazos explícitos.
        4. Tildes y Ñ.
        5. Espacios de los extremos.

    Returns:
        (descripcion_saneada, cambios)
    """

    if texto is None:
        return "", []

    original = str(texto)
    cambios: list[str] = []
    valor = original

    # 1. Caracteres de control: romperían el archivo línea a línea.
    if _CONTROL.search(valor):
        valor = _CONTROL.sub(" ", valor)
        cambios.append("se eliminaron caracteres de control o saltos de línea")

    # 2. El símbolo de grados pegado a una N significa "número".
    if _PATRON_NUMERO.search(valor):
        valor = _PATRON_NUMERO.sub(rules.REEMPLAZO_NUMERO_ABREVIADO, valor)
        cambios.append("N° -> NRO")

    # 3. Tabla de reemplazos.
    hubo_eliminacion = False
    for origen, destino in rules.REEMPLAZOS_DE_CARACTERES.items():
        if origen in valor:
            valor = valor.replace(origen, destino)
            visible = destino if destino else "(eliminado)"
            cambios.append(f"{origen} -> {visible}")
            if destino == "":
                hubo_eliminacion = True

    # Eliminar un carácter puede dejar dos espacios pegados donde antes
    # había uno solo. Ese espacio de más sí se quita.
    if hubo_eliminacion and re.search(r" {2,}", valor):
        valor = re.sub(r" {2,}", " ", valor)
        cambios.append("se unieron los espacios que quedaron al eliminar caracteres")

    # 4. Tildes y Ñ.
    sin_tildes = _quitar_tildes(valor)
    if sin_tildes != valor:
        cambios.append("se quitaron tildes / Ñ")
        valor = sin_tildes

    # 5. Espacios sobrantes en los extremos. Los internos se respetan:
    #    hay descripciones válidas en GEMANET con doble espacio.
    if rules.COMPACTAR_ESPACIOS_INTERNOS:
        compactado = re.sub(r"\s+", " ", valor)
        if compactado != valor:
            cambios.append("se compactaron espacios internos")
            valor = compactado

    if rules.FORZAR_MAYUSCULAS and valor != valor.upper():
        valor = valor.upper()
        cambios.append("se convirtió a mayúsculas")

    if valor != valor.strip():
        valor = valor.strip()
        cambios.append("se quitaron espacios de los extremos")

    return valor, cambios


def caracteres_no_soportados(texto: str) -> list[str]:
    """Caracteres que siguen fuera de ASCII después del saneamiento.

    El sistema no adivina qué hacer con ellos: los reporta para que se
    agregue la regla correspondiente a `rules.REEMPLAZOS_DE_CARACTERES`.
    """

    return sorted({c for c in texto if ord(c) > 126})


def describir_caracter(caracter: str) -> str:
    """Nombre legible de un carácter, para los mensajes de error."""

    try:
        nombre = unicodedata.name(caracter)
    except ValueError:
        nombre = "sin nombre"
    return f"'{caracter}' (U+{ord(caracter):04X}, {nombre})"
