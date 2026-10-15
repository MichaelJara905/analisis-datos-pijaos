"""Caso de uso: consultar las tres fuentes de referencia desde un solo sitio.

Reemplaza el trabajo manual de abrir el SUPERHOMOLOGADOR, la Circular 022 y
Máximos y Mínimos para revisar un código.

Qué responde cada consulta:

    Servicio (CUPS)     códigos ley homologados, tarifa UVB/UVT/UVR con su
                        puntaje, simulación de descuento y rango histórico.
    Medicamento (CUM)   precio regulado por unidad, margen IPS y rango.
    Insumo              rango histórico (los insumos nunca son regulados).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from src.app.domain.cargues import rules
from src.app.domain.tarifas.text import normalize_description_for_matching
from src.app.infrastructure.referencias import repositorio
from src.app.infrastructure.referencias.repositorio import (
    Fuentes,
    ReferenciaNoDisponible,
)

# Tipo de servicio de Máximos y Mínimos según el cargue consultado.
TIPO_HISTORICO = {
    rules.CARGUE_CUPS: ("CUP", "PAQ", "PRO"),
    rules.CARGUE_CUMS: ("MED", "MOS"),
    rules.CARGUE_INS: ("INS", "APM"),
}


# ============================================================
# ÍNDICE EN MEMORIA
# ============================================================

@dataclass
class Referencias:
    """Las tres fuentes ya cargadas e indexadas para consultar."""

    fuentes: Fuentes
    manuales: dict[str, repositorio.Manual] = field(default_factory=dict)
    homologos_por_cups: dict[str, list[dict[str, str]]] = field(default_factory=dict)
    circular_por_cum: dict[str, dict[str, str]] = field(default_factory=dict)
    historico: dict[tuple[str, str], dict[str, str]] = field(default_factory=dict)

    def disponibles(self) -> dict[str, bool]:
        return {
            "superhomologador": bool(self.manuales),
            "circular": bool(self.circular_por_cum),
            "maximos": bool(self.historico),
        }


def cargar_referencias(carpeta: str | Path) -> Referencias:
    """Carga las fuentes disponibles en la carpeta indicada.

    Si falta un archivo no se cae: se devuelve lo que sí esté, y la interfaz
    avisa qué fuente no se pudo consultar.
    """

    fuentes = repositorio.descubrir_fuentes(carpeta)
    referencias = Referencias(fuentes=fuentes)

    if fuentes.superhomologador is not None:
        for sigla in repositorio.MANUALES:
            referencias.manuales[sigla] = repositorio.cargar_manual(
                fuentes.superhomologador,
                sigla,
            )

        for fila in repositorio.cargar_homologador(fuentes.superhomologador):
            referencias.homologos_por_cups.setdefault(fila["cups"], []).append(fila)

    if fuentes.circular is not None:
        for fila in repositorio.cargar_circular(fuentes.circular):
            referencias.circular_por_cum.setdefault(fila["cum"], fila)

    if fuentes.maximos is not None:
        for fila in repositorio.cargar_maximos(fuentes.maximos):
            referencias.historico[(fila["tipo"], fila["codigo"])] = fila

    return referencias


def cargar_soat_por_cups(carpeta: str | Path) -> dict[str, frozenset[str]]:
    """Solo el homologador: CUPS -> códigos SOAT que le corresponden.

    Es la parte liviana de las referencias; no abre la Circular ni Máximos
    y Mínimos. Lo usa la validación de los cargues CUPS.

    Raises:
        ReferenciaNoDisponible: si la carpeta no tiene el SUPERHOMOLOGADOR.
    """

    fuentes = repositorio.descubrir_fuentes(carpeta)
    if fuentes.superhomologador is None:
        raise ReferenciaNoDisponible(
            f"No hay un archivo SUPERHOMOLOGADOR en '{carpeta}'."
        )

    acumulado: dict[str, set[str]] = {}
    for fila in repositorio.cargar_homologador(fuentes.superhomologador):
        acumulado.setdefault(fila["cups"], set()).add(fila["codigo_ley"])

    return {cups: frozenset(leyes) for cups, leyes in acumulado.items()}


# ============================================================
# CONSULTAS
# ============================================================

def _numero(texto: str | None) -> float | None:
    if not texto:
        return None
    try:
        return float(str(texto).replace(",", ""))
    except ValueError:
        return None


def _redondear(valor: float) -> int:
    return int(Decimal(str(valor)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def tarifas_reguladas(
    referencias: Referencias,
    codigo_ley: str,
    *,
    porcentaje: int = 0,
) -> list[dict[str, object]]:
    """Valor del código ley en cada manual, con el descuento aplicado."""

    resultado: list[dict[str, object]] = []

    for sigla, manual in referencias.manuales.items():
        fila = manual.filas.get(codigo_ley)
        if fila is None:
            continue

        base = _numero(fila.get("valor_resultante")) or _numero(
            fila.get("valor_calculado")
        )
        con_descuento = (
            _redondear(base * (1 + porcentaje / 100)) if base is not None else None
        )

        resultado.append(
            {
                "manual": sigla,
                "unidad": manual.unidad,
                "descripcion": fila.get("descripcion", ""),
                "puntaje": _numero(fila.get("puntaje")),
                "valor_manual": _redondear(base) if base is not None else None,
                "porcentaje": porcentaje,
                "valor_con_descuento": con_descuento,
            }
        )

    return resultado


def rango_historico(
    referencias: Referencias,
    codigo: str,
    tipo_cargue: str,
) -> list[dict[str, object]]:
    """Mínimo, máximo y promedio históricos del código.

    Sirve como alerta, no como regla: la fuente tiene datos sucios, con
    mínimos de dos pesos, y su vigencia más reciente es 2024.
    """

    filas: list[dict[str, object]] = []

    for tipo in TIPO_HISTORICO.get(tipo_cargue, ()):
        fila = referencias.historico.get((tipo, codigo))
        if fila is None:
            continue

        filas.append(
            {
                "tipo": tipo,
                "minimo": _numero(fila.get("minimo")),
                "maximo": _numero(fila.get("maximo")),
                "promedio": _numero(fila.get("promedio")),
                "promedio_incremento": _numero(fila.get("promedio_incremento")),
            }
        )

    return filas


def consultar_servicio(
    referencias: Referencias,
    cups: str,
    *,
    porcentaje: int = 0,
) -> dict[str, object]:
    """Todo lo que se sabe de un CUPS."""

    codigo = str(cups).strip()
    homologos = referencias.homologos_por_cups.get(codigo, [])

    tarifas: list[dict[str, object]] = []
    for homologo in homologos:
        for tarifa in tarifas_reguladas(
            referencias,
            homologo["codigo_ley"],
            porcentaje=porcentaje,
        ):
            tarifa["codigo_ley"] = homologo["codigo_ley"]
            tarifas.append(tarifa)

    return {
        "codigo": codigo,
        "tipo": rules.CARGUE_CUPS,
        "homologos": homologos,
        "ambiguo": len({h["codigo_ley"] for h in homologos}) > 1,
        "tarifas": tarifas,
        "historico": rango_historico(referencias, codigo, rules.CARGUE_CUPS),
    }


def consultar_medicamento(referencias: Referencias, cum: str) -> dict[str, object]:
    """Precio regulado de un medicamento, si la Circular 022 lo incluye."""

    codigo = str(cum).strip()
    fila = referencias.circular_por_cum.get(codigo)

    regulado = None
    if fila is not None:
        precio = _numero(fila.get("precio_unidad"))
        margen = _numero(fila.get("margen_unidad"))
        regulado = {
            "medicamento": fila.get("medicamento", ""),
            "unidad_medida": fila.get("unidad_medida", ""),
            "precio_unidad": precio,
            "margen_unidad": margen,
            "costo_total_unidad": (
                None if precio is None else _redondear(precio + (margen or 0))
            ),
            "circular": fila.get("circular", ""),
            "vigencia": fila.get("vigencia", ""),
        }

    return {
        "codigo": codigo,
        "tipo": rules.CARGUE_CUMS,
        "regulado": regulado,
        "historico": rango_historico(referencias, codigo, rules.CARGUE_CUMS),
    }


def consultar_insumo(referencias: Referencias, codigo: str) -> dict[str, object]:
    """Un insumo solo tiene historial: nunca lleva tarifa regulada."""

    limpio = str(codigo).strip()

    return {
        "codigo": limpio,
        "tipo": rules.CARGUE_INS,
        "historico": rango_historico(referencias, limpio, rules.CARGUE_INS),
        "nota": "Los insumos siempre se cargan como tarifa propia (PRO).",
    }


def consultar(
    referencias: Referencias,
    codigo: str,
    tipo_cargue: str,
    *,
    porcentaje: int = 0,
) -> dict[str, object]:
    """Punto único de consulta."""

    if tipo_cargue == rules.CARGUE_CUPS:
        return consultar_servicio(referencias, codigo, porcentaje=porcentaje)
    if tipo_cargue == rules.CARGUE_CUMS:
        return consultar_medicamento(referencias, codigo)
    if tipo_cargue == rules.CARGUE_INS:
        return consultar_insumo(referencias, codigo)

    raise ValueError(f"Tipo de consulta no soportado: {tipo_cargue}")


# ============================================================
# BÚSQUEDA POR TEXTO
# ============================================================

def buscar_por_texto(
    referencias: Referencias,
    texto: str,
    tipo_cargue: str,
    *,
    limite: int = 25,
) -> list[dict[str, str]]:
    """Busca por descripción cuando no se tiene el código a la mano.

    Compara con la descripción normalizada, así que no importan las tildes
    ni las mayúsculas. Los insumos no tienen fuente con descripciones, por
    eso solo se puede buscar servicios y medicamentos.
    """

    buscado = normalize_description_for_matching(texto) or ""
    if len(buscado) < 3:
        return []

    palabras = buscado.split()
    resultados: list[dict[str, str]] = []

    def coincide(valor: str) -> bool:
        normalizado = normalize_description_for_matching(valor) or ""
        return all(palabra in normalizado for palabra in palabras)

    if tipo_cargue == rules.CARGUE_CUPS:
        for filas in referencias.homologos_por_cups.values():
            for fila in filas:
                if coincide(fila.get("descripcion", "")) or coincide(
                    fila.get("descripcion_ley", "")
                ):
                    resultados.append(
                        {
                            "codigo": fila["cups"],
                            "codigo_ley": fila["codigo_ley"],
                            "descripcion": fila.get("descripcion", ""),
                            "cobertura": fila.get("cobertura", ""),
                        }
                    )
                if len(resultados) >= limite:
                    return resultados

    elif tipo_cargue == rules.CARGUE_CUMS:
        for fila in referencias.circular_por_cum.values():
            if coincide(fila.get("medicamento", "")):
                resultados.append(
                    {
                        "codigo": fila["cum"],
                        "descripcion": fila.get("medicamento", ""),
                        "unidad_medida": fila.get("unidad_medida", ""),
                        "precio_unidad": fila.get("precio_unidad", ""),
                    }
                )
            if len(resultados) >= limite:
                return resultados

    return resultados


__all__ = [
    "Referencias",
    "ReferenciaNoDisponible",
    "buscar_por_texto",
    "cargar_referencias",
    "consultar",
    "consultar_insumo",
    "consultar_medicamento",
    "consultar_servicio",
    "rango_historico",
    "tarifas_reguladas",
]
