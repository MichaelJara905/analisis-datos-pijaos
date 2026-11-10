"""Construcción y validación de los registros del cargue.

Cada fila cruda del anexo se convierte en un `Registro`. Todo lo que se
corrige queda registrado; todo lo que no se puede resolver con certeza se
marca para revisión en vez de adivinarse.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

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
    # El código se respeta tal cual viene. En insumos ni siquiera se recortan
    # los espacios de los extremos; en servicios y medicamentos sí (nunca los
    # llevan) y el cambio queda registrado.
    codigo, aviso = parsing.codigo_de_celda(
        fila.get("codigo"),
        conservar_espacios=tipo_cargue == rules.CARGUE_INS,
    )
    registro.codigo = codigo

    original = fila.get("codigo")
    if codigo and isinstance(original, str) and original != codigo:
        es_insumo = tipo_cargue == rules.CARGUE_INS
        registro.agregar(
            Hallazgo(
                fila=registro.fila,
                campo="codigo",
                severidad=Severidad.CORRECCION,
                problema=(
                    "se quitaron saltos de línea o tabulaciones al inicio o al final del código"
                    if es_insumo
                    else "se quitaron espacios sobrantes al inicio o al final del código"
                ),
                valor_original=original,
                valor_final=codigo,
                regla=(
                    "un salto de línea no cabe en el archivo ni es parte del código"
                    if es_insumo
                    else "los códigos de servicios y medicamentos no llevan espacios en los extremos"
                ),
            )
        )

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

    # Solo en servicios: allí los CUPS llevan ceros a la izquierda (053109) y
    # Excel los quita si la celda es numérica. Los códigos de insumos y
    # medicamentos no se rellenan con ceros: el aviso sería ruido.
    if aviso and tipo_cargue == rules.CARGUE_CUPS:
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
    if not re.fullmatch(patron, codigo):
        registro.agregar(
            Hallazgo(
                fila=registro.fila,
                campo="codigo",
                severidad=Severidad.BLOQUEANTE,
                problema=_problema_de_formato(codigo, tipo_cargue),
                valor_original=codigo,
                regla=_texto_regla_codigo(tipo_cargue),
                sugerencia=_sugerencia_codigo(codigo, tipo_cargue),
            )
        )

    # Insumos: el patrón es amplio a propósito (los códigos son del prestador),
    # así que además se descarta lo que claramente no es un código.
    if tipo_cargue == rules.CARGUE_INS and re.fullmatch(patron, codigo):
        motivo = _por_que_no_parece_codigo(codigo)
        if motivo:
            registro.agregar(
                Hallazgo(
                    fila=registro.fila,
                    campo="codigo",
                    severidad=Severidad.BLOQUEANTE,
                    problema=f"el código '{_visible(codigo)}' no es un código válido: {motivo}",
                    valor_original=codigo,
                    regla="la columna de código debe traer un código, no texto",
                    sugerencia="devolver al prestador para que informe el código correcto",
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


def _visible(codigo: str) -> str:
    """El código tal cual, pero con los saltos de línea a la vista."""

    return re.sub(r"\s*[\r\n]+\s*", " / ", codigo).strip()


def _problema_de_formato(codigo: str, tipo_cargue: str) -> str:
    """Dice POR QUÉ el código no cumple el formato, para devolverlo al prestador."""

    base = f"el código '{_visible(codigo)}' no cumple el formato de {tipo_cargue}"

    if re.search(r"[\r\n]", codigo):
        return f"{base}: tiene varios códigos en la misma celda (separados por saltos de línea)"
    if rules.SEPARADOR in codigo:
        return f"{base}: contiene el separador ';'"

    raros = sanitizer.caracteres_no_soportados(codigo)
    if raros:
        detalle = ", ".join(sanitizer.describir_caracter(c) for c in raros)
        return f"{base}: contiene caracteres que no son ASCII ({detalle})"

    return base


def _por_que_no_parece_codigo(codigo: str) -> str:
    """Motivo por el que un código de insumo es en realidad un texto; '' si parece válido."""

    limpio = codigo.strip()

    if limpio.upper() in rules.CODIGOS_DE_RELLENO:
        return "es un texto de relleno, no un código"
    if len(limpio) > rules.LARGO_MAXIMO_CODIGO_INS:
        return (
            f"tiene {len(limpio)} caracteres; parece un texto o varios códigos "
            f"juntos (el máximo habitual es {rules.LARGO_MAXIMO_CODIGO_INS})"
        )
    if limpio.count(" ") > rules.ESPACIOS_MAXIMOS_CODIGO_INS:
        return "tiene demasiados espacios; parece una frase, no un código"
    return ""


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
        rules.CARGUE_INS: (
            "el código de insumo no admite ';', saltos de línea ni "
            "caracteres fuera de ASCII"
        ),
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

MAXIMO_DE_FILAS_EN_EL_MENSAJE = 8


def _filas_repetidas(grupo: list[Registro]) -> str:
    filas = [str(r.fila) for r in grupo[:MAXIMO_DE_FILAS_EN_EL_MENSAJE]]
    return ", ".join(filas) + ("…" if len(grupo) > MAXIMO_DE_FILAS_EN_EL_MENSAJE else "")


def _agrupar(registros: list[Registro], clave) -> dict[str, list[Registro]]:
    grupos: dict[str, list[Registro]] = {}
    for registro in registros:
        valor = clave(registro)
        if valor:
            grupos.setdefault(valor, []).append(registro)
    return {v: g for v, g in grupos.items() if len(g) > 1}


def validar_duplicados(registros: list[Registro]) -> None:
    """Bloquea TODOS los registros de un código repetido.

    GEMANET no distingue dos registros con el mismo código, y el sistema no
    decide cuál se queda: se devuelven al prestador. Es el caso, por ejemplo,
    de dos filas con el mismo código y valores distintos.
    """

    for codigo, grupo in _agrupar(registros, lambda r: r.codigo.strip()).items():
        for registro in grupo:
            valores = sorted({str(r.valor_original) for r in grupo if r.valor_original})
            registro.agregar(
                Hallazgo(
                    fila=registro.fila,
                    campo="codigo",
                    severidad=Severidad.BLOQUEANTE,
                    problema=(
                        f"el código '{codigo}' aparece {len(grupo)} veces en el "
                        f"anexo (filas {_filas_repetidas(grupo)}"
                        + (f"; valores: {', '.join(valores)}" if len(valores) > 1 else "")
                        + ")"
                    ),
                    valor_original=registro.codigo,
                    regla="GEMANET no distingue dos registros con el mismo código",
                    sugerencia="devolver al prestador: debe quedar una sola fila por código",
                )
            )


def validar_descripciones_repetidas(registros: list[Registro]) -> None:
    """Bloquea los registros que comparten la misma descripción.

    Dos productos distintos no deben llamarse igual: no se sabría a cuál
    corresponde cada tarifa. Se comparan las descripciones ya saneadas.
    """

    for descripcion, grupo in _agrupar(registros, lambda r: r.descripcion).items():
        for registro in grupo:
            registro.agregar(
                Hallazgo(
                    fila=registro.fila,
                    campo="descripcion",
                    severidad=Severidad.BLOQUEANTE,
                    problema=(
                        f"la descripción se repite en {len(grupo)} registros "
                        f"(filas {_filas_repetidas(grupo)})"
                    ),
                    valor_final=registro.descripcion,
                    regla="no puede haber dos registros con la misma descripción",
                    sugerencia="devolver al prestador para que los diferencie",
                )
            )


def _sin_ceros(texto: str) -> str:
    return texto.strip().lstrip("0")


def validar_contra_homologador(
    registros: list[Registro],
    soat_por_cups: Mapping[str, Iterable[str]],
) -> int:
    """Cruza cada CUPS con los códigos SOAT que el homologador le asigna.

    - Tarifa propia cuyo valor es un SOAT homologado a ese CUPS: es el error
      de cargar el código ley como si fuera el valor. GEMANET lo acepta sin
      avisar, así que se bloquea aquí.
    - Tarifa regulada cuyo código ley no es uno de los homologados: el
      homólogo debe ser igual al del homologador.

    Un CUPS puede tener varios SOAT; basta con que coincida con uno.
    Los CUPS que el homologador no conoce no se marcan.

    Returns:
        Cantidad de registros cuyo CUPS no está en el homologador.
    """

    sin_cruce = 0

    for registro in registros:
        homologados = soat_por_cups.get(registro.codigo)
        if not homologados:
            if registro.codigo:
                sin_cruce += 1
            continue

        normalizados = {_sin_ceros(str(s)) for s in homologados}
        lista = ", ".join(sorted(str(s) for s in homologados))

        if not registro.es_regulado:
            if registro.valor is not None and _sin_ceros(str(registro.valor)) in normalizados:
                registro.agregar(
                    Hallazgo(
                        fila=registro.fila,
                        campo="valor",
                        severidad=Severidad.BLOQUEANTE,
                        problema=(
                            f"el valor {registro.valor} es un código SOAT "
                            f"homologado al CUPS {registro.codigo}"
                        ),
                        valor_original=str(registro.valor),
                        regla=(
                            "en tarifa PRO el campo 2 es el valor; un código "
                            "SOAT va con UVB, UVT o UVR"
                        ),
                        sugerencia=(
                            "si es regulado, indicar el manual; si es propio, "
                            "corregir el valor"
                        ),
                    )
                )
            continue

        if registro.codigo_ley and _sin_ceros(registro.codigo_ley) not in normalizados:
            registro.agregar(
                Hallazgo(
                    fila=registro.fila,
                    campo="codigo_ley",
                    severidad=Severidad.BLOQUEANTE,
                    problema=(
                        f"el código ley '{registro.codigo_ley}' no es un "
                        f"homologado del CUPS {registro.codigo}"
                    ),
                    valor_original=registro.codigo_ley,
                    regla="el homólogo debe ser igual al del SUPERHOMOLOGADOR",
                    sugerencia=f"homologados para este CUPS: {lista}",
                )
            )

    return sin_cruce
