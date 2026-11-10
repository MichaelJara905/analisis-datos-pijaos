"""Creación de propios para GEMANET.

Un propio es un servicio nuevo que se crea con la estructura

    nombre|PRO####|valor|CUPS

y después se carga como un CUPS normal (`PRO####;valor;PRO;0;0;`). Los dos
archivos salen de las mismas solicitudes, así que no pueden desalinearse.

Reglas confirmadas por el equipo:
    - El consecutivo sigue el orden: después de PRO5715 va PRO5716.
    - El cuarto campo siempre es un CUPS.
    - El nombre no tiene reglas de negocio; solo restricciones técnicas
      (ASCII, sin '|' ni saltos de línea).
    - El archivo no termina en salto de línea.

El sistema nunca decide qué ítems necesitan un propio: solo asigna código a
las solicitudes que se le entregan.
"""

from __future__ import annotations

import re
from collections.abc import Collection
from dataclasses import dataclass, field

from src.app.domain.cargues import parsing, rules, sanitizer, txt_writer
from src.app.domain.cargues.model import Hallazgo, Registro, Severidad


class CodigoInvalido(ValueError):
    """El último código usado no se puede interpretar."""


@dataclass(frozen=True)
class SolicitudPropio:
    """Lo que se pide crear: tal como viene, sin interpretar."""

    fila: int
    nombre: object
    valor: object
    cups: object


@dataclass
class Propio:
    fila: int
    nombre: str = ""
    nombre_original: str = ""
    codigo: str = ""
    valor: int | None = None
    cups: str = ""
    hallazgos: list[Hallazgo] = field(default_factory=list)

    @property
    def bloqueado(self) -> bool:
        return any(h.severidad is Severidad.BLOQUEANTE for h in self.hallazgos)


# ============================================================
# CÓDIGOS
# ============================================================

def numero_de_codigo(texto: object) -> int:
    """'PRO5715', 'pro 5715' o 5715 -> 5715."""

    limpio = str(texto).strip().upper().replace(" ", "")
    coincidencia = re.fullmatch(rf"(?:{rules.PREFIJO_CODIGO_PROPIO})?(\d+)", limpio)
    if coincidencia is None:
        raise CodigoInvalido(
            f"No se entiende el último código usado: '{texto}'. "
            "Debe ser como PRO5715 o 5715."
        )
    return int(coincidencia.group(1))


def formatear_codigo(numero: int) -> str:
    return f"{rules.PREFIJO_CODIGO_PROPIO}{numero:0{rules.DIGITOS_CODIGO_PROPIO}d}"


# ============================================================
# PREPARACIÓN
# ============================================================

def _hallazgo(fila: int, campo: str, severidad: Severidad, problema: str, **extra) -> Hallazgo:
    return Hallazgo(fila=fila, campo=campo, severidad=severidad, problema=problema, **extra)


def _preparar_nombre(propio: Propio, crudo: object) -> None:
    original = parsing.texto_de_celda(crudo)
    propio.nombre_original = original

    saneado, cambios = sanitizer.sanear_descripcion(original)

    if rules.SEPARADOR_PROPIOS in saneado:
        saneado = saneado.replace(
            rules.SEPARADOR_PROPIOS, rules.REEMPLAZO_SEPARADOR_PROPIOS
        )
        cambios.append(
            f"{rules.SEPARADOR_PROPIOS} -> {rules.REEMPLAZO_SEPARADOR_PROPIOS}"
        )

    saneado = saneado.strip()
    propio.nombre = saneado

    if saneado == "":
        propio.hallazgos.append(
            _hallazgo(
                propio.fila, "nombre", Severidad.BLOQUEANTE,
                "el nombre está vacío",
                regla="todo propio necesita nombre",
            )
        )
        return

    for cambio in cambios:
        propio.hallazgos.append(
            _hallazgo(
                propio.fila, "nombre", Severidad.CORRECCION, cambio,
                valor_original=original, valor_final=saneado,
                regla="el nombre del propio queda en ASCII y sin separador",
            )
        )

    pendientes = sanitizer.caracteres_no_soportados(saneado)
    if pendientes:
        detalle = ", ".join(sanitizer.describir_caracter(c) for c in pendientes)
        propio.hallazgos.append(
            _hallazgo(
                propio.fila, "nombre", Severidad.BLOQUEANTE,
                f"quedan caracteres sin regla de reemplazo: {detalle}",
                valor_original=original, valor_final=saneado,
                regla="el nombre debe quedar en ASCII",
            )
        )


def _preparar_valor(propio: Propio, crudo: object) -> None:
    valor, problema, nota = parsing.valor_de_celda(crudo)
    propio.valor = valor

    if problema or valor is None:
        propio.hallazgos.append(
            _hallazgo(
                propio.fila, "valor", Severidad.BLOQUEANTE,
                problema or "la tarifa está vacía",
                valor_original=parsing.texto_de_celda(crudo),
                regla="el valor del propio es un entero en pesos",
            )
        )
        return

    if valor <= 0:
        propio.hallazgos.append(
            _hallazgo(
                propio.fila, "valor", Severidad.BLOQUEANTE,
                "el valor debe ser mayor que cero",
                valor_original=str(valor),
                regla="un propio no se crea sin valor",
            )
        )

    if nota:
        propio.hallazgos.append(
            _hallazgo(
                propio.fila, "valor", Severidad.CORRECCION, nota,
                valor_original=parsing.texto_de_celda(crudo),
                valor_final=str(valor), regla="el valor se redondea al peso",
            )
        )


def _preparar_cups(
    propio: Propio,
    crudo: object,
    cups_conocidos: Collection[str] | None,
) -> None:
    cups = parsing.texto_de_celda(crudo)
    propio.cups = cups

    if not re.fullmatch(r"[0-9A-Z]{6}", cups):
        propio.hallazgos.append(
            _hallazgo(
                propio.fila, "cups", Severidad.BLOQUEANTE,
                f"'{cups}' no es un CUPS válido",
                valor_original=cups,
                regla="el cuarto campo siempre es un CUPS de 6 caracteres",
                sugerencia="corregir el CUPS de la solicitud",
            )
        )
        return

    if cups_conocidos is not None and cups not in cups_conocidos:
        propio.hallazgos.append(
            _hallazgo(
                propio.fila, "cups", Severidad.ADVERTENCIA,
                f"el CUPS {cups} no está en el homologador",
                valor_original=cups,
                regla="solo se valida lo que el homologador conoce",
                sugerencia="verificar el CUPS manualmente",
            )
        )


def preparar_propios(
    solicitudes: list[SolicitudPropio],
    ultimo_usado: object,
    *,
    cups_conocidos: Collection[str] | None = None,
) -> list[Propio]:
    """Valida las solicitudes y asigna el consecutivo a las que quedan listas.

    Las solicitudes bloqueadas no consumen número: no dejan huecos.

    Raises:
        CodigoInvalido: si `ultimo_usado` no se puede interpretar.
    """

    siguiente = numero_de_codigo(ultimo_usado) + 1
    propios: list[Propio] = []

    for solicitud in solicitudes:
        propio = Propio(fila=solicitud.fila)
        _preparar_nombre(propio, solicitud.nombre)
        _preparar_valor(propio, solicitud.valor)
        _preparar_cups(propio, solicitud.cups, cups_conocidos)
        propios.append(propio)

    for propio in propios:
        if propio.bloqueado:
            continue
        propio.codigo = formatear_codigo(siguiente)
        siguiente += 1

    repetidos = {}
    for propio in propios:
        if propio.nombre:
            repetidos.setdefault(propio.nombre, []).append(propio)
    for nombre, grupo in repetidos.items():
        if len(grupo) > 1:
            for propio in grupo:
                propio.hallazgos.append(
                    _hallazgo(
                        propio.fila, "nombre", Severidad.ADVERTENCIA,
                        f"el nombre se repite en {len(grupo)} solicitudes",
                        valor_final=nombre,
                        regla="nombres iguales generan propios duplicados",
                        sugerencia="verificar si realmente son dos propios",
                    )
                )

    return propios


# ============================================================
# ARCHIVOS
# ============================================================

def construir_linea_creacion(propio: Propio) -> str:
    return rules.SEPARADOR_PROPIOS.join(
        [propio.nombre, propio.codigo, str(propio.valor), propio.cups]
    )


def construir_linea_carga(propio: Propio) -> str:
    """La misma línea que produce el cargue CUPS para un servicio propio."""

    registro = Registro(
        fila=propio.fila,
        codigo=propio.codigo,
        valor=propio.valor,
        tipo_tarifa=rules.TARIFA_PROPIA,
    )
    return txt_writer.construir_linea(registro, rules.CARGUE_CUPS)


def _unir(lineas: list[str]) -> bytes:
    # Sin salto de línea al final: el archivo debe quedar sin espacios.
    return rules.FIN_DE_LINEA.join(lineas).encode(rules.CODIFICACION)


def construir_bytes_creacion(propios: list[Propio]) -> bytes:
    return _unir([construir_linea_creacion(p) for p in propios])


def construir_bytes_carga(propios: list[Propio]) -> bytes:
    return _unir([construir_linea_carga(p) for p in propios])
