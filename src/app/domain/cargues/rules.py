"""Reglas y configuración de los cargues GEMANET.

Este módulo concentra TODO lo que puede cambiar sin tocar la lógica:
constantes del formato TXT, tabla de reemplazo de caracteres y nombres
alternativos de columnas de los anexos.

Las reglas marcadas como CONFIRMADO fueron verificadas contra archivos TXT
reales que cargaron correctamente en GEMANET. Las marcadas como INFERIDO
son deducciones razonables pendientes de confirmación.
"""

from __future__ import annotations

# ============================================================
# TIPOS DE CARGUE
# ============================================================

CARGUE_CUMS = "CUMS"
CARGUE_INS = "INS"
CARGUE_CUPS = "CUPS"

TIPOS_DE_CARGUE = (CARGUE_CUMS, CARGUE_INS, CARGUE_CUPS)

# PAQ existe en GEMANET pero su estructura todavía no está documentada.
# No se implementa hasta tener un TXT real de referencia.


# ============================================================
# FORMATO DEL ARCHIVO TXT  (CONFIRMADO)
# ============================================================

SEPARADOR = ";"
TERMINADOR_DE_REGISTRO = ";"   # cada registro cierra con separador
FIN_DE_LINEA = "\r\n"          # CRLF entre registros
NUEVA_LINEA_AL_FINAL = False   # el último registro no lleva salto
CODIFICACION = "ascii"         # tras el saneamiento todo queda en ASCII


# ============================================================
# TIPOS DE TARIFA  (CONFIRMADO)
# ============================================================

TARIFA_PROPIA = "PRO"
MANUALES_REGULADOS = ("UVB", "UVR", "UVT")
TIPOS_DE_TARIFA_VALIDOS = (TARIFA_PROPIA,) + MANUALES_REGULADOS

# Texto que aparece en los anexos -> tipo de tarifa del TXT.
# "EVENTO" y "PAQUETE" son modalidades de liquidación, no manuales:
# ambas se cargan como tarifa propia.
EQUIVALENCIAS_TIPO_TARIFA = {
    "PRO": TARIFA_PROPIA,
    "PROPIA": TARIFA_PROPIA,
    "PROPIAS": TARIFA_PROPIA,
    "PROPIO": TARIFA_PROPIA,
    "PROPIOS": TARIFA_PROPIA,
    "EVENTO": TARIFA_PROPIA,
    "PAQUETE": TARIFA_PROPIA,
    "UVB": "UVB",
    "UVR": "UVR",
    "UVT": "UVT",
}

# "SOAT" no se escribe en GEMANET: hay que saber si es UVB, UVR o UVT.
TIPOS_TARIFA_AMBIGUOS = {"SOAT", "ISS", "REGULADA", "REGULADO"}

# Los insumos nunca se cargan con tarifa regulada.  (CONFIRMADO)
CARGUES_SIEMPRE_PROPIOS = (CARGUE_INS,)


# ============================================================
# CAMPO 6 - "PORCENTAJE DE NORMA"
# ============================================================

# Pendiente de definir su origen. Por instrucción expresa va en cero.
PORCENTAJE_DE_NORMA_POR_DEFECTO = "0"


# ============================================================
# TABLA DE CARACTERES
# ============================================================

# Regla especial: el símbolo de grados pegado a una N significa "número".
#   "PUNCION N° 22"  ->  "PUNCION NRO 22"
# Se aplica antes que la tabla general.
PATRON_NUMERO_ABREVIADO = r"[Nn]\s*[°º]"
REEMPLAZO_NUMERO_ABREVIADO = "NRO"

# Reemplazos explícitos. Las tildes y la Ñ se resuelven aparte por
# descomposición Unicode, así no hay que enumerar cada vocal acentuada.
REEMPLAZOS_DE_CARACTERES = {
    ";": ",",        # crítico: rompería la estructura del TXT
    "°": " GRADOS",
    "Ø": "D",
    "ø": "D",
    "º": "O",
    "ª": "A",
    "®": "(R)",
    "™": "(TM)",
    "Ф": "",         # se elimina
    # Comillas y guiones tipográficos -> su equivalente ASCII
    "\u2018": "'",
    "\u2019": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u2013": "-",
    "\u2014": "-",
    "\u00a0": " ",   # espacio duro
    "×": "X",
}

# La descripción NO se pasa a mayúsculas ni se le compactan los espacios
# internos: los TXT válidos conservan el texto tal cual viene del anexo.
FORZAR_MAYUSCULAS = False
COMPACTAR_ESPACIOS_INTERNOS = False


# ============================================================
# FORMATO DE LOS CÓDIGOS
# ============================================================

# CONFIRMADO por el equipo y contrastado con el homologador (8.902 filas) y
# la trazabilidad de la Res. 2706: casi siempre 6 dígitos, a veces con
# letras (estancias 129M01, traslados 601T02...). Los propios son
# PRO + 4 o más dígitos (PRO6212) y se cargan como un CUPS normal.
PATRON_CODIGO_CUPS = r"^(?:[0-9A-Z]{6}|PRO\d{4,})$"
PATRON_CODIGO_PROPIO = r"^PRO\d{4,}$"
PREFIJO_CODIGO_PROPIO = "PRO"
DIGITOS_CODIGO_PROPIO = 4

# Traslados: nunca llevan SOAT; van como PRO (valor o kilometraje) o como
# propios.  (CONFIRMADO por el equipo; son los 4 del homologador)
CODIGOS_TRASLADO = ("601T01", "601T02", "602T01", "602T02")

# Creación de propios: separador distinto al de los demás cargues.
SEPARADOR_PROPIOS = "|"
REEMPLAZO_SEPARADOR_PROPIOS = "-"
PATRON_CODIGO_CUMS = r"^\d+-\d+$"        # CONFIRMADO: expediente-consecutivo
PATRON_CODIGO_INS = r"^[A-Za-z0-9._\-]+$"  # INFERIDO: libre, sin espacios

PATRONES_DE_CODIGO = {
    CARGUE_CUPS: PATRON_CODIGO_CUPS,
    CARGUE_CUMS: PATRON_CODIGO_CUMS,
    CARGUE_INS: PATRON_CODIGO_INS,
}

# Códigos ley del superhomologador: de 4 a 6 dígitos.
PATRON_CODIGO_LEY = r"^\d{4,6}$"


# ============================================================
# TEXTOS QUE NO SON UN VALOR
# ============================================================

# Se detectan para dar un mensaje útil en vez de un "no es número".
TEXTOS_SIN_TARIFA = (
    "BAJO COTIZACION",
    "BAJO COTIZACIÓN",
    "COTIZACION",
    "COTIZACIÓN",
    "NO APLICA",
    "N/A",
    "NA",
    "PENDIENTE",
    "SIN TARIFA",
)


# ============================================================
# ALIAS DE COLUMNAS DE LOS ANEXOS
# ============================================================

# Cada anexo viene con encabezados distintos. El lector normaliza el texto
# del encabezado (mayúsculas, sin tildes, sin signos) y busca coincidencia
# por contenido, en el orden en que aparecen aquí: gana el primero.
#
# Para agregar soporte a un anexo nuevo basta con sumar un alias.

ALIAS_DE_COLUMNAS = {
    CARGUE_INS: {
        "codigo": (
            "COD INTERNO IPS",
            "CODIGO INTERNO IPS",
            "CODIGO INTERNO",
            "COD INTERNO",
            "CODIGO IPS",
            "CODIGO INSUMO",
            "CODIGO DEL INSUMO",
            "CODIGO",
            "COD",
        ),
        "descripcion": (
            "DESCRIPCION INSUMO",
            "DESCRIPCION DEL INSUMO",
            "DESCRIPCION",
            "NOMBRE DEL INSUMO",
            "NOMBRE INSUMO",
            "NOMBRE",
            "DETALLE",
        ),
        "valor": (
            "TARIFA OFERTADA",
            "VALOR UNITARIO",
            "VALOR OFERTADO",
            "VALOR NEGOCIADO",
            "TARIFA",
            "VALOR",
            "PRECIO",
        ),
        "invima": (
            "COD INVIMA",
            "CODIGO INVIMA",
            "REGISTRO INVIMA",
            "INVIMA",
        ),
    },
    CARGUE_CUMS: {
        "codigo": (
            "CONSECUTIVO",
            "CUM",
            "CODIGO CUM",
            "EXPEDIENTE Y CONSECUTIVO",
            "CODIGO",
        ),
        "descripcion": (
            "DESCRIPCION",
            "NOMBRE DEL MEDICAMENTO",
            "MEDICAMENTO",
            "NOMBRE",
        ),
        "valor": (
            "TARIFA OFERTADA",
            "VALOR UNITARIO",
            "TARIFA",
            "VALOR",
            "PRECIO",
        ),
        "expediente": (
            "NO DE EXPEDIENTE",
            "NUMERO DE EXPEDIENTE",
            "EXPEDIENTE",
        ),
        "tipo_tarifa": (
            "TARIFARIO",
            "TIPO DE TARIFA",
            "TIPO TARIFA",
        ),
        "codigo_ley": (
            "CODIGO HOMOLOGO SOAT",
            "CODIGO HOMOLOGO",
            "CODIGO LEY",
            "COD SOAT",
            "CODIGO SOAT",
        ),
        "porcentaje": (
            "TARIFA OFERTADA (% DE DESCUENTO)",
            "PORCENTAJE DE DESCUENTO",
            "% DE DESCUENTO",
            "PORCENTAJE",
            "DESCUENTO",
        ),
    },
    CARGUE_CUPS: {
        "codigo": (
            "CUPS",
            "CODIGO CUPS",
            "CODIGO SERVICIO",
            "CODIGO",
        ),
        "descripcion": (
            "DESCRIPCION CUPS",
            "DESCRIPCION DEL SERVICIO",
            "DESCRIPCION",
            "NOMBRE DEL SERVICIO",
            "NOMBRE",
        ),
        "valor": (
            "VALOR (LIQUIDACION DE ACUERDO A MANUAL Y TARIFA OFERTADA",
            "VALOR LIQUIDACION",
            "TARIFA OFERTADA",
            "VALOR",
            "TARIFA",
            "PRECIO",
        ),
        "tipo_tarifa": (
            "TARIFARIO",
            "MANUAL TARIFARIO",
            "TIPO DE TARIFA",
            "TIPO TARIFA",
        ),
        "codigo_ley": (
            "CODIGO HOMOLOGO SOAT / UVR SI ES ISS",
            "CODIGO HOMOLOGO SOAT",
            "CODIGO HOMOLOGO",
            "CODIGO LEY",
            "COD SOAT",
            "CODIGO SOAT",
        ),
        "porcentaje": (
            "TARIFA OFERTADA (% DE DESCUENTO)",
            "PORCENTAJE DE DESCUENTO",
            "% DE DESCUENTO",
            "PORCENTAJE",
            "DESCUENTO",
        ),
    },
}

# Columnas sin las cuales no se puede armar un registro.
COLUMNAS_OBLIGATORIAS = {
    CARGUE_INS: ("codigo", "descripcion", "valor"),
    CARGUE_CUMS: ("codigo", "descripcion", "valor"),
    CARGUE_CUPS: ("codigo", "valor"),
}

# Palabras del nombre de la hoja que sugieren el tipo de cargue.
# Se usan solo para desempatar cuando varias hojas parecen servir: una hoja
# llamada "SERVICIOS" no debería ganarle a "MEDICAMENTOS" en un cargue CUMS.
PISTAS_DE_HOJA = {
    CARGUE_CUMS: ("MEDICAMENTO", "CUM", "FARMAC"),
    CARGUE_INS: ("INSUMO", "DISPOSITIVO", "MATERIAL"),
    CARGUE_CUPS: ("SERVICIO", "CUPS", "PROCEDIMIENTO"),
}

# Peso de cada tipo de coincidencia al elegir la hoja.
PUNTOS_COINCIDENCIA_EXACTA = 2
PUNTOS_COINCIDENCIA_PARCIAL = 1
PUNTOS_PISTA_DE_HOJA = 5

# Máximo de filas que se revisan buscando la fila de encabezados.
MAXIMO_FILAS_PARA_ENCABEZADO = 40

# Mínimo de columnas reconocidas para aceptar una fila como encabezado.
MINIMO_COLUMNAS_RECONOCIDAS = 2

# Filas vacías consecutivas que se toleran antes de dar por terminada la hoja.
FILAS_VACIAS_PARA_CORTAR = 25
