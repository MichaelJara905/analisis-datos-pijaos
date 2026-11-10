"""Conciliación entre un anexo y lo que ya está cargado en GEMANET.

Responde, para UN prestador y UN anexo: qué ya está cargado, qué falta (y
si lo que falta se puede cargar o tiene error), qué está cargado con otro
valor o tipo, qué hay en GEMANET que el anexo no trae, y qué
inconsistencias tiene el anexo (códigos repetidos).

Es lógica pura: recibe registros ya validados y lo cargado en GEMANET, y
devuelve filas listas para exportar. No decide nada por su cuenta: los
casos dudosos (por ejemplo, un CUPS repetido) van a un reporte aparte.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from src.app.domain.cargues import rules
from src.app.domain.cargues.model import Registro, Severidad

TOLERANCIA_PESOS = 0.5


# ============================================================
# MODELO
# ============================================================

@dataclass(frozen=True)
class RegistroGemanet:
    """Una fila del reporte exportado de GEMANET."""

    codigo: str
    valor: float | None
    tipo: str            # "PRO", "UVB"... o "" cuando es regulado sin manual
    porcentaje: str
    descripcion: str
    activo: str
    fila: int

    @property
    def es_regulado(self) -> bool:
        return self.tipo != rules.TARIFA_PROPIA


@dataclass
class ResultadoConciliacion:
    tipo_cargue: str
    coinciden: list[dict[str, object]] = field(default_factory=list)
    faltan_listos: list[dict[str, object]] = field(default_factory=list)
    faltan_con_error: list[dict[str, object]] = field(default_factory=list)
    diferencias: list[dict[str, object]] = field(default_factory=list)
    solo_gemanet: list[dict[str, object]] = field(default_factory=list)
    inconsistencias: list[dict[str, object]] = field(default_factory=list)
    # Registros que no están en GEMANET y se pueden cargar, en el orden del anexo.
    a_cargar: list[Registro] = field(default_factory=list)

    def resumen(self) -> dict[str, int]:
        return {
            "ya_cargados_y_coinciden": len(self.coinciden),
            "faltan_y_se_pueden_cargar": len(self.faltan_listos),
            "faltan_con_error": len(self.faltan_con_error),
            "cargados_con_diferencias": len(self.diferencias),
            "solo_en_gemanet": len(self.solo_gemanet),
            "inconsistencias": len(self.inconsistencias),
        }


# ============================================================
# CLAVES Y COMPARACIÓN
# ============================================================

def clave_codigo(texto: object, *, completar_ceros: bool = True) -> str:
    """Forma comparable de un código (solo para comparar; el código no se toca).

    El reporte de GEMANET guarda los CUPS como número (898015.0) y pierde
    los ceros iniciales; el anexo los trae como texto. Se quita el '.0' y,
    solo en servicios (`completar_ceros`), los códigos numéricos cortos se
    completan a 6 dígitos. En insumos NO: '103' y '00103' son códigos distintos.
    """

    if texto is None:
        return ""
    limpio = re.sub(r"\.0+$", "", str(texto).strip().upper())
    if completar_ceros and limpio.isdigit() and len(limpio) < 6:
        return limpio.zfill(6)
    return limpio


def _porcentaje_entero(texto: str) -> int | None:
    try:
        numero = float(str(texto).strip().replace(",", ".").replace("%", ""))
    except ValueError:
        return None
    if numero != 0 and abs(numero) <= 1:
        numero *= 100
    return int(round(numero))


def _diferencias(registro: Registro, gema: RegistroGemanet, tipo_cargue: str) -> list[str]:
    motivos: list[str] = []

    if gema.activo.strip().upper() == "NO":
        motivos.append("está cargado pero INACTIVO en GEMANET")

    # Los insumos siempre son tarifa propia: en el reporte de GEMANET el tipo
    # puede venir vacío y eso NO significa regulado (a diferencia de los CUPS).
    gema_regulado = gema.es_regulado and tipo_cargue not in rules.CARGUES_SIEMPRE_PROPIOS

    if registro.es_regulado != gema_regulado:
        motivos.append(
            f"tipo distinto: anexo {registro.tipo_tarifa or 'PRO'}, "
            f"GEMANET {gema.tipo or 'regulado'}"
        )
        return motivos

    if not registro.es_regulado:
        if (
            registro.valor is not None
            and gema.valor is not None
            and abs(registro.valor - gema.valor) > TOLERANCIA_PESOS
        ):
            motivos.append(
                f"valor distinto: anexo {registro.valor}, GEMANET {gema.valor:g}"
            )
        return motivos

    # Ambos regulados: el valor lo calcula GEMANET desde el manual, así que
    # solo se comparan el manual (si GEMANET lo informa) y el porcentaje.
    if gema.tipo and gema.tipo != registro.tipo_tarifa:
        motivos.append(
            f"manual distinto: anexo {registro.tipo_tarifa}, GEMANET {gema.tipo}"
        )
    pct_gema = _porcentaje_entero(gema.porcentaje)
    if pct_gema is not None and pct_gema != registro.porcentaje:
        motivos.append(
            f"porcentaje distinto: anexo {registro.porcentaje}, GEMANET {pct_gema}"
        )
    return motivos


# ============================================================
# FILAS DE REPORTE
# ============================================================

def _fila(registro: Registro, estado: str, motivo: str = "", linea: str = "") -> dict[str, object]:
    return {
        "hoja": registro.hoja,
        "fila": registro.fila,
        "codigo": registro.codigo,
        "descripcion": registro.descripcion_original,
        "tipo_tarifa": registro.tipo_tarifa,
        "valor": "" if registro.valor is None else registro.valor,
        "codigo_ley": registro.codigo_ley,
        "porcentaje": registro.porcentaje,
        "estado": estado,
        "motivo": motivo,
        "linea_txt": linea,
    }


def _motivos_de_bloqueo(registro: Registro) -> str:
    return "; ".join(
        h.problema for h in registro.hallazgos if h.severidad is Severidad.BLOQUEANTE
    )


# ============================================================
# CONCILIACIÓN
# ============================================================

def conciliar(
    registros: list[Registro],
    gemanet: Mapping[str, RegistroGemanet],
    tipo_cargue: str,
    *,
    linea: Callable[[Registro], str] | None = None,
) -> ResultadoConciliacion:
    """Compara los registros del anexo con lo cargado en GEMANET.

    Args:
        registros: todos los registros del anexo (de todas sus hojas), ya
            validados.
        gemanet: lo cargado, indexado por `clave_codigo`.
        linea: función que devuelve la línea del TXT de un registro, para
            mostrar con qué estructura se cargaría lo que falta.
    """

    resultado = ResultadoConciliacion(tipo_cargue=tipo_cargue)
    linea = linea or (lambda _registro: "")

    completar_ceros = tipo_cargue == rules.CARGUE_CUPS
    grupos: dict[str, list[Registro]] = defaultdict(list)
    for registro in registros:
        if registro.codigo:
            grupos[clave_codigo(registro.codigo, completar_ceros=completar_ceros)].append(registro)

    # --- Códigos repetidos en el anexo: reporte aparte, sin decidir ---
    for clave, grupo in grupos.items():
        if len(grupo) < 2:
            continue
        valores = sorted({str(r.valor) for r in grupo if r.valor is not None})
        internos = sorted(
            {str(r.crudo.get("codigo_interno", "")) for r in grupo if r.crudo.get("codigo_interno")}
        )
        resultado.inconsistencias.append(
            {
                "origen": "anexo",
                "tipo": "código repetido",
                "codigo": grupo[0].codigo,
                "detalle": (
                    f"{len(grupo)} veces; valores: {', '.join(valores) or 'sin valor'}"
                    + (f"; códigos internos: {', '.join(internos[:6])}"
                       + ("…" if len(internos) > 6 else "") if internos else "")
                ),
                "ubicacion": "; ".join(f"{r.hoja} fila {r.fila}" for r in grupo[:8])
                + ("…" if len(grupo) > 8 else ""),
                "en_gemanet": "sí" if clave in gemanet else "no",
            }
        )

    # --- Registros sin código ---
    for registro in registros:
        if not registro.codigo:
            resultado.faltan_con_error.append(
                _fila(registro, "CON ERROR", _motivos_de_bloqueo(registro) or "sin código")
            )

    # --- Un registro por código distinto ---
    for clave, grupo in grupos.items():
        repetido = len(grupo) > 1
        registro = grupo[0]
        gema = gemanet.get(clave)

        if gema is None:
            if repetido:
                # Cada fila repetida va al informe (el prestador debe ver todas),
                # con dónde están y qué valores traen.
                ubicaciones = "; ".join(f"{r.hoja} fila {r.fila}" if r.hoja else f"fila {r.fila}" for r in grupo[:8])
                valores = sorted({str(r.valor) for r in grupo if r.valor is not None})
                base = (
                    f"código repetido {len(grupo)} veces en el anexo ({ubicaciones}"
                    + ("…" if len(grupo) > 8 else "")
                    + (f"; valores: {', '.join(valores)}" if len(valores) > 1 else "")
                    + "): decidir cuál se carga"
                )
                for repetida in grupo:
                    otros = [
                        h.problema
                        for h in repetida.hallazgos
                        if h.severidad is Severidad.BLOQUEANTE and "veces en el anexo" not in h.problema
                    ]
                    resultado.faltan_con_error.append(
                        _fila(repetida, "CON ERROR", "; ".join([base] + otros))
                    )
            elif registro.bloqueado:
                resultado.faltan_con_error.append(
                    _fila(registro, "CON ERROR", _motivos_de_bloqueo(registro))
                )
            else:
                resultado.faltan_listos.append(
                    _fila(registro, "LISTO PARA CARGAR", linea=linea(registro))
                )
                resultado.a_cargar.append(registro)
            continue

        if repetido:
            continue  # ya está en GEMANET; el repetido quedó en inconsistencias

        motivos = _diferencias(registro, gema, tipo_cargue)
        if motivos:
            fila = _fila(registro, "DIFERENTE", "; ".join(motivos))
            fila["valor_gemanet"] = "" if gema.valor is None else gema.valor
            fila["tipo_gemanet"] = gema.tipo or "regulado"
            resultado.diferencias.append(fila)
        else:
            resultado.coinciden.append(_fila(registro, "COINCIDE"))

    # --- Lo que GEMANET tiene y el anexo no ---
    for clave, gema in gemanet.items():
        if clave not in grupos:
            resultado.solo_gemanet.append(
                {
                    "codigo": gema.codigo,
                    "descripcion": gema.descripcion,
                    "tipo_tarifa": gema.tipo or "regulado",
                    "valor": "" if gema.valor is None else gema.valor,
                    "activo": gema.activo,
                }
            )

    return resultado
