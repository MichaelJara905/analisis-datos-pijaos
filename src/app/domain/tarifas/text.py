"""Normalización de texto del módulo de tarifas.

Python puro, sin Polars ni Streamlit: son reglas de negocio y por eso viven
en el dominio.

Ojo con la diferencia entre los dos saneadores del proyecto:

    domain/tarifas/text.py      -> limpieza agresiva para cargar a base de
                                   datos y para comparar descripciones.
    domain/cargues/sanitizer.py -> limpieza mínima para el TXT de GEMANET,
                                   que conserva paréntesis, guiones, comas
                                   y barras porque el sistema los acepta.

No se deben usar el uno por el otro: `sanitize_text` destruiría las
referencias de los insumos en un cargue.
"""

from __future__ import annotations

import re
import unicodedata

ALLOWED_DESCRIPTION_PATTERN = r"^[A-Za-z0-9\s.,;:/()\-]*$"


def sanitize_text(value: str | None) -> str | None:
    """Sanitiza un valor de texto para almacenarlo o compararlo.

    Aplicaciones:

    - Elimina tildes.
    - Convierte caracteres Unicode equivalentes.
    - Elimina símbolos extraños.
    - Normaliza espacios.
    - Convierte el texto a mayúsculas.
    """

    if value is None:
        return None

    value = str(value)

    value = unicodedata.normalize("NFKD", value)
    value = "".join(
        character
        for character in value
        if not unicodedata.combining(character)
    )

    value = value.upper()
    value = re.sub(r"[^A-Z0-9\s]", " ", value)
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def normalize_description_for_matching(value: str | None) -> str | None:
    """Normaliza una descripción para matching sin perder medidas numéricas.

    ``sanitize_text`` está orientada a carga en DB y reemplaza puntos y
    asteriscos por espacios. Para comparar tarifas se conservan separadores
    de medidas como ``3.3`` y ``12*3.5``; los dígitos y las unidades siempre
    permanecen en el texto normalizado.
    """

    if value is None:
        return None

    value = unicodedata.normalize("NFKD", str(value))
    value = "".join(
        character
        for character in value
        if not unicodedata.combining(character)
    ).upper()
    value = value.replace("×", "*")
    value = re.sub(r"(?<=\d),(?=\d)", ".", value)
    value = re.sub(r"[^A-Z0-9.*\s]", " ", value)
    return re.sub(r"\s+", " ", value).strip()
