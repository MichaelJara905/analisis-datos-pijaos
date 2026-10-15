"""Construcción y validación de los registros del cargue.

Cada fila cruda del anexo se convierte en un `Registro`. Todo lo que se
corrige queda registrado; todo lo que no se puede resolver con certeza se
marca para revisión en vez de adivinarse.
"""

from __future__ import annotations

import re
from collections import Counter

from src.app.domain.cargues import parsing, rules, sanitizer
from src.app.domain.cargues.model import Hallazgo, Registro, Severidad


# ============================================================
# CONSTRUCCIÓN DE UN REGISTRO
# ============================================================

def construir_registro(
    fila: dict[str, object],
    tipo_cargue: str,
) -> Registro:
    """Convierte una fila cruda en un registro validado."""

    numero = int(fila.get("_fila", 0))
    registro = Registro(fila=numero, crudo=dict(fila))

    _procesar_codigo(registro, fila, tipo_cargue)
    _procesar_descripcion(registro, fila, tipo_cargue)
    _procesar_tarifa(registro, fila, tipo_cargue)

    return registro


# ------------------------------------------------------------
# Código
# ------------------------------------------------------------

def _procesar_codigo(
    registro: Registro,
    fila: dict[str, object],
    tipo_cargue: str,
) -> None:
    codigo, aviso = parsing.codigo_de_celda(fila.get("codigo"))
    registro.codigo = codigo

    if codigo == "":
        registro.agregar(
            Hallazgo(
                fila=registro.fila,
                campo="codigo",
                severidad=Severidad.BLOQUEANTE,
                problema="el código está vacío",
                regla="todo registro debe tener código",
                sugerencia="completar el código en el anexo",
            )
        )
        return

    if aviso:
        registro.agregar(
            Hallazgo(
                fila=registro.fila,
                campo="codigo",
                severidad=Severidad.ADVERTENCIA,
                problema=aviso,
                valor_original=codigo,
                valor_final=codigo,
                regla="los códigos deben guardarse como texto en el Excel",
                sugerencia="verificar contra el anexo original",
            )
        )

    patron = rules.PATRONES_DE_CODIGO[tipo_cargue]
    if not re.match(patron, codigo):
        registro.agregar(
            Hallazgo(
                fila=registro.fila,
                campo="codigo",
                severidad=Severidad.BLOQUEANTE,
                problema=f"el código '{codigo}' no cumple el formato de {tipo_cargue}",
                valor_original=codigo,
                regla=_texto_regla_codigo(tipo_cargue),
                sugerencia=_sugerencia_codigo(codigo, tipo_cargue),
            )
        )

    # En CUMS el código es expediente-consecutivo. Si el anexo trae el
    # expediente en otra columna, se avisa cuando no coincide.
    if tipo_cargue == rules.CARGUE_CUMS and fila.get("expediente"):
        expediente = parsing.texto_de_celda(fila.get("expediente"))
        if expediente and not codigo.startswith(expediente):
            registro.agregar(
                Hallazgo(
                    fila=registro.fila,
                    campo="codigo",
                    severidad=Severidad.ADVERTENCIA,
                    problema=(
                        f"el código '{codigo}' no empieza por el expediente "
                        f"'{expediente}' de la misma fila"
                    ),
                    regla="el código CUMS es expediente-consecutivo",
                    sugerencia="revisar cuál de las dos columnas es la correcta",
                )
            )


def _sugerencia_codigo(codigo: str, tipo_cargue: str) -> str:
    base = "corregir el código o confirmar que es un código propio"
    if tipo_cargue == rules.CARGUE_CUPS and re.fullmatch(r"\d{5}", codigo):
        return (
            f"{base}; si es un CUPS al que Excel le quitó el cero inicial, "
            f"sería '0{codigo}' (verificar en el homologador)"
        )
    return base


def validar_codigos_propios_y_traslados(registros: list[Registro]) -> None:
    """Los traslados y los propios (PRO####) nunca se cargan como regulados."""

    for registro in registros:
        es_propio = re.match(rules.PATRON_CODIGO_PROPIO, registro.codigo)
        es_traslado = registro.codigo in rules.CODIGOS_TRASLADO
        if not (es_propio or es_traslado) or not registro.es_regulado:
            continue

        registro.agregar(
            Hallazgo(
                fila=registro.fila,
                campo="tipo_tarifa",
                severidad=Severidad.BLOQUEANTE,
                problema=(
                    f"el código '{registro.codigo}' se marcó como "
                    f"{registro.tipo_tarifa}"
                ),
                valor_original=registro.tipo_tarifa,
                regla=(
                    "los propios y los traslados nunca llevan SOAT: "
                    "se cargan como PRO"
                ),
                sugerencia="cambiar el tipo a PRO y definir el valor",
            )
        )


def _texto_regla_codigo(tipo_cargue: str) -> str:
    return {
        rules.CARGUE_CUPS: (
            "el CUPS tiene 6 caracteres (dígitos o letras mayúsculas, "
            "ej. 129M01) o es un propio PRO####"
        ),
        rules.CARGUE_CUMS: "el CUMS es expediente-consecutivo (ej. 20048691-1)",
        rules.CARGUE_INS: "el código de insumo no admite espacios ni signos",
    }[tipo_cargue]


# ------------------------------------------------------------
# Descripción
# ------------------------------------------------------------

def _procesar_descripcion(
    registro: Registro,
    fila: dict[str, object],
    tipo_cargue: str,
) -> None:
    # CUPS no lleva descripción en el TXT, pero igual se lee para el reporte.
    original = parsing.texto_de_celda(fila.get("descripcion"))
    registro.descripcion_original = original

    saneada, cambios = sanitizer.sanear_descripcion(original)
    registro.descripcion = saneada

    if tipo_cargue == rules.CARGUE_CUPS:
        return

    if saneada == "":
        registro.agregar(
            Hallazgo(
                fila=registro.fila,
                campo="descripcion",
                severidad=Severidad.BLOQUEANTE,
                problema="la descripción está vacía",
                regla=f"{tipo_cargue} exige descripción",
                sugerencia="completar la descripción en el anexo",
            )
        )
        return

    for cambio in cambios:
        registro.agregar(
            Hallazgo(
                fila=registro.fila,
                campo="descripcion",
                severidad=Severidad.CORRECCION,
                problema=cambio,
                valor_original=original,
                valor_final=saneada,
                regla="tabla de caracteres del cargue GEMANET",
            )
        )

    pendientes = sanitizer.caracteres_no_soportados(saneada)
    if pendientes:
        detalle = ", ".join(sanitizer.describir_caracter(c) for c in pendientes)
        registro.agregar(
            Hallazgo(
                fila=registro.fila,
                campo="descripcion",
                severidad=Severidad.BLOQUEANTE,
                problema=f"quedan caracteres sin regla de reemplazo: {detalle}",
                valor_original=original,
                valor_final=saneada,
                regla="la descripción debe quedar en ASCII",
                sugerencia=(
                    "definir el reemplazo y agregarlo a "
                    "rules.REEMPLAZOS_DE_CARACTERES"
                ),
            )
        )

    if rules.SEPARADOR in saneada:
        registro.agregar(
            Hallazgo(
                fila=registro.fila,
                campo="descripcion",
                severidad=Severidad.BLOQUEANTE,
                problema="la descripción todavía contiene el separador ';'",
                valor_final=saneada,
                regla="el ';' rompe la estructura del TXT",
            )
        )


# ------------------------------------------------------------
# Tarifa, tipo y porcentaje
# ------------------------------------------------------------

def _procesar_tarifa(
    registro: Registro,
    fila: dict[str, object],
    tipo_cargue: str,
) -> None:
    tipo, problema_tipo = parsing.tipo_tarifa_de_celda(fila.get("tipo_tarifa"))
    codigo_ley = parsing.texto_de_celda(fila.get("codigo_ley"))
    codigo_ley = "" if codigo_ley.upper() in {"NA", "N/A", "NO APLICA"} else codigo_ley

    # Los insumos nunca se cargan regulados.
    if tipo_cargue in rules.CARGUES_SIEMPRE_PROPIOS:
        if tipo and tipo != rules.TARIFA_PROPIA:
            registro.agregar(
                Hallazgo(
                    fila=registro.fila,
                    campo="tipo_tarifa",
                    severidad=Severidad.BLOQUEANTE,
                    problema=f"el anexo marca el insumo como '{tipo}'",
                    valor_original=parsing.texto_de_celda(fila.get("tipo_tarifa")),
                    regla="los insumos siempre se cargan como tarifa propia",
                    sugerencia="confirmar con el área de contratación",
                )
            )
        registro.tipo_tarifa = rules.TARIFA_PROPIA
        registro.porcentaje = 0
        _asignar_valor(registro, fila)
        return

    if problema_tipo:
        registro.agregar(
            Hallazgo(
                fila=registro.fila,
                campo="tipo_tarifa",
                severidad=Severidad.BLOQUEANTE,
                problema=problema_tipo,
                valor_original=parsing.texto_de_celda(fila.get("tipo_tarifa")),
                regla=f"valores válidos: {', '.join(rules.TIPOS_DE_TARIFA_VALIDOS)}",
            )
        )
        return

    if tipo == "":
        # Sin columna de tipo, se asume propia solo si tampoco hay código ley.
        if codigo_ley:
            registro.agregar(
                Hallazgo(
                    fila=registro.fila,
                    campo="tipo_tarifa",
                    severidad=Severidad.BLOQUEANTE,
                    problema=(
                        f"hay código ley '{codigo_ley}' pero no se indica el "
                        "manual (UVB, UVR o UVT)"
                    ),
                    regla="una tarifa regulada necesita manual y código ley",
                )
            )
            return
        tipo = rules.TARIFA_PROPIA
        registro.agregar(
            Hallazgo(
                fila=registro.fila,
                campo="tipo_tarifa",
                severidad=Severidad.ADVERTENCIA,
                problema="el anexo no indica tipo de tarifa; se asume propia",
                valor_final=rules.TARIFA_PROPIA,
                regla="sin manual ni código ley, la tarifa es propia",
            )
        )

    registro.tipo_tarifa = tipo

    porcentaje, problema_pct, nota_pct = parsing.porcentaje_de_celda(
        fila.get("porcentaje")
    )
    registro.porcentaje = porcentaje

    if problema_pct:
        registro.agregar(
            Hallazgo(
                fila=registro.fila,
                campo="porcentaje",
                severidad=Severidad.BLOQUEANTE,
                problema=problema_pct,
                valor_original=parsing.texto_de_celda(fila.get("porcentaje")),
                regla="el porcentaje es un entero entre -100 y 100",
            )
        )
    elif nota_pct:
        registro.agregar(
            Hallazgo(
                fila=registro.fila,
                campo="porcentaje",
                severidad=Severidad.CORRECCION,
                problema=nota_pct,
                valor_original=parsing.texto_de_celda(fila.get("porcentaje")),
                valor_final=str(porcentaje),
                regla="el anexo usa fracción y GEMANET usa entero",
            )
        )

    if tipo == rules.TARIFA_PROPIA:
        if porcentaje != 0:
            registro.agregar(
                Hallazgo(
                    fila=registro.fila,
                    campo="porcentaje",
                    severidad=Severidad.ADVERTENCIA,
                    problema=(
                        f"tarifa propia con porcentaje {porcentaje}; "
                        "las propias van sin descuento"
                    ),
                    regla="tarifa propia -> porcentaje 0",
                )
            )
        _asignar_valor(registro, fila)
        return

    # --- Tarifa regulada: el campo 2 lleva el código ley, no el valor ---
    registro.codigo_ley = codigo_ley

    if codigo_ley == "":
        registro.agregar(
            Hallazgo(
                fila=registro.fila,
                campo="codigo_ley",
                severidad=Severidad.BLOQUEANTE,
                problema=f"tarifa {tipo} sin código ley en el anexo",
                regla="una tarifa regulada se carga con el código ley",
                sugerencia=(
                    "buscar el código en el SUPERHOMOLOGADOR y agregarlo "
                    "al anexo"
                ),
            )
        )
        return

    if not re.match(rules.PATRON_CODIGO_LEY, codigo_ley):
        registro.agregar(
            Hallazgo(
                fila=registro.fila,
                campo="codigo_ley",
                severidad=Severidad.BLOQUEANTE,
                problema=f"el código ley '{codigo_ley}' no tiene formato válido",
                valor_original=codigo_ley,
                regla="el código ley tiene entre 4 y 6 dígitos",
            )
        )

    # El valor se lee igual, para poder compararlo en el reporte.
    _asignar_valor(registro, fila, obligatorio=False)


def _asignar_valor(
    registro: Registro,
    fila: dict[str, object],
    *,
    obligatorio: bool = True,
) -> None:
    valor, problema, nota = parsing.valor_de_celda(fila.get("valor"))
    registro.valor = valor
    registro.valor_original = parsing.texto_de_celda(fila.get("valor"))

    if problema:
        registro.agregar(
            Hallazgo(
                fila=registro.fila,
                campo="valor",
                severidad=(
                    Severidad.BLOQUEANTE if obligatorio else Severidad.ADVERTENCIA
                ),
                problema=problema,
                valor_original=registro.valor_original,
                regla="la tarifa propia va en el TXT como entero",
                sugerencia="definir la tarifa o excluir el registro del cargue",
            )
        )
        return

    if nota:
        registro.agregar(
            Hallazgo(
                fila=registro.fila,
                campo="valor",
                severidad=Severidad.CORRECCION,
                problema=nota,
                valor_original=registro.valor_original,
                valor_final=str(valor),
                regla="el valor se redondea al peso",
            )
        )


# ============================================================
# VALIDACIONES ENTRE REGISTROS
# ============================================================

def validar_duplicados(registros: list[Registro]) -> None:
    """Marca los códigos repetidos.

    El sistema nunca decide cuál se queda: solo avisa. Es el caso de los
    CUPS adulto/pediátrico, que el equipo todavía no ha definido.
    """

    conteo = Counter(r.codigo for r in registros if r.codigo)

    for registro in registros:
        repeticiones = conteo.get(registro.codigo, 0)
        if repeticiones > 1:
            registro.agregar(
                Hallazgo(
                    fila=registro.fila,
                    campo="codigo",
                    severidad=Severidad.ADVERTENCIA,
                    problema=(
                        f"el código '{registro.codigo}' aparece "
                        f"{repeticiones} veces en el anexo"
                    ),
                    valor_original=registro.codigo,
                    regla="GEMANET no distingue dos registros con el mismo código",
                    sugerencia="decidir cuál se carga o crear un código propio",
                )
            )


def validar_descripciones_repetidas(registros: list[Registro]) -> None:
    """Avisa cuando dos códigos distintos comparten descripción."""

    conteo = Counter(
        r.descripcion for r in registros if r.descripcion
    )

    for registro in registros:
        if conteo.get(registro.descripcion, 0) > 1:
            registro.agregar(
                Hallazgo(
                    fila=registro.fila,
                    campo="descripcion",
                    severidad=Severidad.ADVERTENCIA,
                    problema="la descripción se repite en otro registro",
                    valor_final=registro.descripcion,
                    regla="descripciones iguales con códigos distintos",
                    sugerencia="verificar si son productos diferentes",
                )
            )
