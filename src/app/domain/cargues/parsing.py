"""Conversión de celdas de Excel a los tipos que necesita el TXT.

Todas las funciones devuelven `(valor, problema)`. Cuando algo no se puede
convertir con certeza NO se adivina: se devuelve el problema para que el
registro quede marcado y lo revise una persona.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from src.app.domain.cargues import rules

_SOLO_NUMERO = re.compile(r"^-?\d+(?:[.,]\d+)?$")
_NUMERO_CON_SEPARADORES = re.compile(r"^-?\d{1,3}(?:[.,]\d{3})+(?:[.,]\d{1,2})?$")
_SIMBOLOS_DE_MONEDA = ("$", "COP", "USD", "\u00a0", " ")


def normalizar_encabezado(texto: object) -> str:
    """Normaliza el texto de un encabezado para poder compararlo.

    Mayúsculas, sin tildes, sin signos y con espacios compactados. Así
    'Descripción CUPS ' y 'DESCRIPCION CUPS' son el mismo encabezado.
    """

    if texto is None:
        return ""

    valor = unicodedata.normalize("NFD", str(texto))
    valor = "".join(c for c in valor if not unicodedata.combining(c))
    valor = valor.upper()
    valor = valor.replace("\n", " ").replace("\r", " ")
    valor = re.sub(r"[^A-Z0-9%/().\- ]", " ", valor)
    return re.sub(r"\s+", " ", valor).strip()


def texto_de_celda(valor: object) -> str:
    """Convierte cualquier celda a texto sin introducir ruido.

    Los números enteros guardados como float (451201.0) se escriben sin
    el `.0`, que es un error clásico al leer Excel.
    """

    if valor is None:
        return ""

    if isinstance(valor, bool):
        return str(valor)

    if isinstance(valor, float):
        if valor.is_integer():
            return str(int(valor))
        return repr(valor)

    if isinstance(valor, (datetime, date)):
        return valor.isoformat()

    return str(valor).strip()


def codigo_de_celda(
    valor: object,
    *,
    conservar_espacios: bool = False,
) -> tuple[str, str]:
    """Devuelve el código como texto, sin cambiarle nada.

    El código se respeta tal cual está en la celda: ceros a la izquierda,
    símbolos y mayúsculas incluidos. Con `conservar_espacios` tampoco se
    recortan los espacios de los extremos (los códigos de insumo son del
    prestador y GEMANET ya tiene algunos con espacios).

    Si la celda venía como número, avisa: Excel ya pudo haber perdido los
    ceros a la izquierda y eso no se puede recuperar desde el archivo.
    """

    if conservar_espacios and isinstance(valor, str):
        # Los espacios se respetan; los saltos de línea y tabulaciones de los
        # extremos nunca son parte de un código y no caben en el archivo.
        texto = valor.strip("\r\n\t\x0b\x0c")
    else:
        texto = texto_de_celda(valor).strip()

    if texto.strip() == "":
        return "", "el código está vacío"

    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        return texto, (
            "el código venía como número en Excel; si tenía ceros a la "
            "izquierda ya se perdieron en el archivo"
        )

    return texto, ""


def _a_decimal(texto: str) -> Decimal | None:
    """Interpreta un número escrito con separadores colombianos o ingleses."""

    limpio = texto
    for simbolo in _SIMBOLOS_DE_MONEDA:
        limpio = limpio.replace(simbolo, "")
    limpio = limpio.strip()

    if limpio == "":
        return None

    if _SOLO_NUMERO.match(limpio):
        return _convertir(limpio.replace(",", "."))

    if _NUMERO_CON_SEPARADORES.match(limpio):
        # El último separador manda: si deja 1 o 2 dígitos, es el decimal.
        ultimo_punto = limpio.rfind(".")
        ultima_coma = limpio.rfind(",")
        corte = max(ultimo_punto, ultima_coma)
        decimales = len(limpio) - corte - 1

        if decimales in (1, 2):
            entero = re.sub(r"[.,]", "", limpio[:corte])
            return _convertir(f"{entero}.{limpio[corte + 1:]}")

        return _convertir(re.sub(r"[.,]", "", limpio))

    return None


def _convertir(texto: str) -> Decimal | None:
    try:
        return Decimal(texto)
    except InvalidOperation:
        return None


def valor_de_celda(valor: object) -> tuple[int | None, str, str]:
    """Convierte la tarifa a entero redondeado.

    El redondeo es al peso y "hacia arriba desde el medio", igual que
    Excel: 0.5 sube. Python redondearía al par por defecto.

    Returns:
        (entero, problema, nota)
    """

    if valor is None or (isinstance(valor, str) and valor.strip() == ""):
        return None, "la tarifa está vacía", ""

    if isinstance(valor, bool):
        return None, "la tarifa no es un número", ""

    if isinstance(valor, (int, float)):
        numero = Decimal(str(valor))
    else:
        texto = str(valor).strip()
        comparable = normalizar_encabezado(texto)

        if comparable in {normalizar_encabezado(t) for t in rules.TEXTOS_SIN_TARIFA}:
            return None, f"el registro no tiene tarifa numérica ('{texto}')", ""

        numero = _a_decimal(texto)
        if numero is None:
            return None, f"no se pudo interpretar la tarifa '{texto}'", ""

    if numero < 0:
        return None, f"la tarifa es negativa ({numero})", ""

    entero = int(numero.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    nota = ""
    if Decimal(entero) != numero:
        nota = f"se redondeó {numero} a {entero}"

    return entero, "", nota


def porcentaje_de_celda(valor: object) -> tuple[int, str, str]:
    """Convierte el porcentaje de descuento al entero que espera GEMANET.

    Los anexos lo escriben como fracción (-0,1) y GEMANET lo espera como
    entero (-10). Regla aplicada: si el valor absoluto es menor o igual a 1
    se interpreta como fracción y se multiplica por 100.  (INFERIDO)

    Returns:
        (porcentaje, problema, nota)
    """

    if valor is None or (isinstance(valor, str) and valor.strip() == ""):
        return 0, "", ""

    if isinstance(valor, str):
        texto = valor.strip().replace("%", "")
        comparable = normalizar_encabezado(texto)
        if comparable in {"", "NA", "N/A", "NO APLICA", "PROPIA", "EVENTO", "PAQUETE"}:
            return 0, "", ""
        numero = _a_decimal(texto)
        if numero is None:
            return 0, f"no se pudo interpretar el porcentaje '{valor}'", ""
    else:
        numero = Decimal(str(valor))

    nota = ""
    if numero != 0 and abs(numero) <= 1:
        convertido = numero * 100
        nota = f"se interpretó {numero} como {convertido}%"
        numero = convertido

    entero = int(numero.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if Decimal(entero) != numero:
        nota = (nota + "; " if nota else "") + f"se redondeó {numero} a {entero}"

    if abs(entero) > 100:
        return entero, f"el porcentaje está fuera de rango ({entero})", nota

    return entero, "", nota


def tipo_tarifa_de_celda(valor: object) -> tuple[str, str]:
    """Traduce el texto del anexo al tipo de tarifa del TXT.

    Returns:
        (tipo, problema). Tipo vacío significa que no se pudo determinar.
    """

    texto = normalizar_encabezado(valor)

    if texto == "":
        return "", ""

    if texto in rules.EQUIVALENCIAS_TIPO_TARIFA:
        return rules.EQUIVALENCIAS_TIPO_TARIFA[texto], ""

    # A veces viene como "SOAT - UVB" o "TARIFA UVR".
    for clave, destino in rules.EQUIVALENCIAS_TIPO_TARIFA.items():
        if re.search(rf"\b{clave}\b", texto):
            return destino, ""

    if texto in rules.TIPOS_TARIFA_AMBIGUOS:
        return "", (
            f"'{valor}' no dice cuál manual aplica: GEMANET necesita "
            "UVB, UVR o UVT"
        )

    return "", f"tipo de tarifa no reconocido: '{valor}'"
