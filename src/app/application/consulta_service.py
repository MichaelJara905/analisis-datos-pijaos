"""Consulta por documento: Circular 022, Trazabilidad 2706, Listado CUM y
SuperHomologador.

Cada documento tiene su propia carga y su propia búsqueda, para poder
responder la pregunta específica de cada uno sin cruzarlos:

    Circular 022      ¿cuál es el tope a parametrizar de un medicamento?
    Trazabilidad 2706 ¿el CUPS está vigente en 2026? (si no está, no se
                      puede autorizar ni parametrizar)
    Listado CUM       ¿el medicamento está activo? (sin registro en el
                      listado, se considera inactivo)
    SuperHomologador  homólogos SOAT y tarifas UVB, UVT y UVR

Los archivos originales no se modifican.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from src.app.application import referencias_service
from src.app.domain.cargues.parsing import normalizar_encabezado
from src.app.infrastructure.referencias import repositorio
from src.app.infrastructure.referencias.repositorio import ReferenciaNoDisponible

LIMITE_DE_RESULTADOS = 25
MINIMO_DE_LETRAS = 3
TOLERANCIA_PESOS = 0.5

ESTADO_ACTIVO = "ACTIVO"
ESTADO_INACTIVO = "INACTIVO"
ESTADO_AUSENTE = "NO ESTÁ EN EL LISTADO"

ESTADO_VIGENTE = "VIGENTE 2026"
ESTADO_NO_VIGENTE = "NO VIGENTE"
ESTADO_NO_ESTA = "NO ESTÁ EN LA RESOLUCIÓN 2706"

FUENTES = {
    "circular": "Circular 022",
    "trazabilidad": "Trazabilidad 2706",
    "listado_cum": "Listado CUM (INVIMA)",
    "superhomologador": "SuperHomologador",
}


# ============================================================
# AYUDAS
# ============================================================

def _numero(texto: object) -> float | None:
    if texto in (None, ""):
        return None
    try:
        return float(str(texto).replace(",", ""))
    except ValueError:
        return None


def _fecha(texto: str) -> str:
    """Fecha legible: acepta ISO y el número de serie de Excel."""

    texto = (texto or "").strip()
    if re.fullmatch(r"\d{5}(\.0+)?", texto):
        return (date(1899, 12, 30) + timedelta(days=int(float(texto)))).isoformat()
    return texto[:10]


def _palabras(texto: str) -> list[str]:
    return normalizar_encabezado(texto).split()


def _indexar(filas: list[dict[str, str]], campos: tuple[str, ...]) -> list[tuple[str, dict[str, str]]]:
    return [
        (normalizar_encabezado(" ".join(f.get(c, "") for c in campos)), f)
        for f in filas
    ]


def _buscar_texto(
    indice: list[tuple[str, dict[str, str]]],
    texto: str,
    limite: int,
) -> list[dict[str, str]]:
    palabras = _palabras(texto)
    if not palabras or sum(len(p) for p in palabras) < MINIMO_DE_LETRAS:
        return []

    resultados: list[dict[str, str]] = []
    for indexado, fila in indice:
        if all(p in indexado for p in palabras):
            resultados.append(fila)
            if len(resultados) >= limite:
                break
    return resultados


def clave_cups(texto: object) -> str:
    """Código CUPS comparable: sin '.0' final y completado a 6 dígitos."""

    limpio = re.sub(r"\.0+$", "", str(texto or "").strip().upper())
    return limpio.zfill(6) if limpio.isdigit() and len(limpio) < 6 else limpio


def _ruta_fuente(carpeta: str | Path, nombre: str) -> Path:
    fuentes = repositorio.descubrir_fuentes(carpeta)
    ruta = getattr(fuentes, nombre)
    if ruta is None:
        raise ReferenciaNoDisponible(
            f"No hay un archivo de {FUENTES[nombre]} en '{carpeta}'. "
            "Se reconoce por el nombre del archivo."
        )
    return ruta


def estado_de_fuentes(carpeta: str | Path) -> dict[str, dict[str, object]]:
    """Qué archivo se encontró para cada documento y de cuándo es."""

    fuentes = repositorio.descubrir_fuentes(carpeta)
    estado: dict[str, dict[str, object]] = {}
    for nombre, etiqueta in FUENTES.items():
        ruta = getattr(fuentes, nombre)
        estado[nombre] = {
            "etiqueta": etiqueta,
            "archivo": None if ruta is None else ruta.name,
            "modificado": (
                None if ruta is None
                else datetime.fromtimestamp(ruta.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            ),
        }
    return estado


def firma_de_fuente(carpeta: str | Path, nombre: str) -> tuple[str, float, int]:
    """Identifica la versión del archivo: cambia cuando el archivo cambia."""

    ruta = _ruta_fuente(carpeta, nombre)
    estado = ruta.stat()
    return str(ruta), estado.st_mtime, estado.st_size


# ============================================================
# CIRCULAR 022
# ============================================================

@dataclass
class Circular:
    archivo: str
    por_cum: dict[str, dict[str, str]]
    indice: list[tuple[str, dict[str, str]]]


def cargar_circular(carpeta: str | Path) -> Circular:
    ruta = _ruta_fuente(carpeta, "circular")
    filas = repositorio.cargar_circular(ruta)
    return Circular(
        archivo=ruta.name,
        por_cum={f["cum"].strip(): f for f in filas if f.get("cum")},
        indice=_indexar(filas, ("cum", "medicamento", "mercado")),
    )


def ficha_circular(fila: dict[str, str]) -> dict[str, object]:
    """Resume una fila de la Circular con el TOPE a parametrizar."""

    precio_unidad = _numero(fila.get("precio_unidad"))
    margen_unidad = _numero(fila.get("margen_unidad"))
    tope = _numero(fila.get("tope_unidad"))
    if tope is None and precio_unidad is not None:
        tope = precio_unidad + (margen_unidad or 0)

    porcentaje = _numero(fila.get("pct_margen"))

    return {
        "cum": fila.get("cum", ""),
        "medicamento": fila.get("medicamento", ""),
        "mercado": fila.get("mercado", ""),
        "unidad_medida": fila.get("unidad_medida", ""),
        "umd_presentacion": fila.get("umd_presentacion", ""),
        "pmv_presentacion": _numero(fila.get("precio_presentacion")),
        "pmv_por_umd": precio_unidad,
        "margen_por_umd": margen_unidad,
        "tope": tope,
        "porcentaje_margen": None if porcentaje is None else round(porcentaje * 100, 2),
        "criterio": fila.get("criterio", ""),
        "fundamento": fila.get("fundamento", ""),
        "alerta": fila.get("alerta", ""),
        "circular": fila.get("circular", ""),
        "vigencia": _fecha(fila.get("vigencia", "")),
    }


def consultar_circular(
    circular: Circular,
    texto: str,
    *,
    limite: int = LIMITE_DE_RESULTADOS,
) -> list[dict[str, object]]:
    """Por CUM exacto, o por nombre del medicamento o mercado relevante."""

    clave = (texto or "").strip()
    if clave in circular.por_cum:
        return [ficha_circular(circular.por_cum[clave])]
    return [ficha_circular(f) for f in _buscar_texto(circular.indice, clave, limite)]


def evaluar_valor(tope: float | None, valor: float | None) -> dict[str, object]:
    """Compara un valor ofrecido con el tope. Los porcentajes son 'hasta'."""

    if tope is None or valor is None:
        return {"estado": "SIN DATOS", "diferencia": None, "porcentaje": None}

    diferencia = round(valor - tope, 2)
    if diferencia > TOLERANCIA_PESOS:
        return {
            "estado": "SUPERA EL TOPE",
            "diferencia": diferencia,
            "porcentaje": round(diferencia / tope * 100, 2) if tope else None,
        }
    return {"estado": "DENTRO DEL TOPE", "diferencia": diferencia, "porcentaje": None}


# ============================================================
# LISTADO CUM (INVIMA)
# ============================================================

@dataclass
class Listado:
    archivo: str
    generado: str
    por_cums: dict[str, dict[str, str]]
    por_expediente: dict[str, list[str]]
    indice: list[tuple[str, dict[str, str]]]


def cargar_listado(carpeta: str | Path) -> Listado:
    ruta = _ruta_fuente(carpeta, "listado_cum")
    filas = repositorio.cargar_listado_cum(ruta)

    por_expediente: dict[str, list[str]] = {}
    for fila in filas:
        por_expediente.setdefault(fila.get("expediente", "").strip(), []).append(fila["cums"])

    return Listado(
        archivo=ruta.name,
        generado=repositorio.fecha_de_generacion_listado(ruta),
        por_cums={f["cums"].strip(): f for f in filas},
        por_expediente=por_expediente,
        indice=_indexar(
            filas,
            ("cums", "producto", "principio_activo", "titular", "atc", "descripcion_atc"),
        ),
    )


def estado_del_cum(fila: dict[str, str] | None) -> str:
    if fila is None:
        return ESTADO_AUSENTE
    return ESTADO_ACTIVO if fila.get("estado_cum", "").strip().lower() == "activo" else ESTADO_INACTIVO


def ficha_listado(fila: dict[str, str] | None, cum: str, *, hoy: date | None = None) -> dict[str, object]:
    hoy = hoy or date.today()

    if fila is None:
        return {
            "cum": cum,
            "estado": ESTADO_AUSENTE,
            "nota": "Sin registro en el listado de vigentes del INVIMA: se considera inactivo.",
        }

    vencimiento = _fecha(fila.get("fecha_vencimiento", ""))
    return {
        "cum": fila.get("cums", cum),
        "estado": estado_del_cum(fila),
        "producto": fila.get("producto", ""),
        "descripcion_comercial": fila.get("descripcion_comercial", ""),
        "principio_activo": fila.get("principio_activo", ""),
        "concentracion": fila.get("concentracion", ""),
        "forma": fila.get("forma", ""),
        "via": fila.get("via", ""),
        "atc": f"{fila.get('atc', '')} {fila.get('descripcion_atc', '')}".strip(),
        "titular": fila.get("titular", ""),
        "registro_sanitario": fila.get("registro_sanitario", ""),
        "estado_registro": fila.get("estado_registro", ""),
        "fecha_expedicion": _fecha(fila.get("fecha_expedicion", "")),
        "fecha_vencimiento": vencimiento,
        "registro_vencido": bool(vencimiento) and vencimiento < hoy.isoformat(),
        "fecha_activo": _fecha(fila.get("fecha_activo", "")),
        "fecha_inactivo": _fecha(fila.get("fecha_inactivo", "")),
        "muestra_medica": fila.get("muestra_medica", ""),
        "expediente": fila.get("expediente", ""),
        "ium": fila.get("ium", ""),
    }


def consultar_listado(
    listado: Listado,
    texto: str,
    *,
    hoy: date | None = None,
    limite: int = LIMITE_DE_RESULTADOS,
) -> dict[str, object]:
    """Por CUM (expediente-consecutivo), por expediente o por texto.

    Devuelve {"modo": ..., "fichas": [...]}. Un CUM aparece una sola vez,
    aunque el libro lo repita por rol del titular.
    """

    clave = (texto or "").strip()

    if clave in listado.por_cums:
        fila = listado.por_cums[clave]
        hermanos = [
            c for c in listado.por_expediente.get(fila.get("expediente", "").strip(), [])
            if c != clave
        ]
        return {
            "modo": "cum",
            "fichas": [ficha_listado(fila, clave, hoy=hoy)],
            "mismo_expediente": [
                {"cum": c, "estado": estado_del_cum(listado.por_cums[c]),
                 "descripcion": listado.por_cums[c].get("descripcion_comercial", "")}
                for c in hermanos[:limite]
            ],
        }

    if re.fullmatch(r"\d+-\d+", clave):
        return {"modo": "cum", "fichas": [ficha_listado(None, clave, hoy=hoy)], "mismo_expediente": []}

    if clave.isdigit() and clave in listado.por_expediente:
        cums = listado.por_expediente[clave]
        return {
            "modo": "expediente",
            "fichas": [ficha_listado(listado.por_cums[c], c, hoy=hoy) for c in cums[:limite]],
            "mismo_expediente": [],
        }

    return {
        "modo": "texto",
        "fichas": [ficha_listado(f, f["cums"], hoy=hoy) for f in _buscar_texto(listado.indice, clave, limite)],
        "mismo_expediente": [],
    }


# ============================================================
# TRAZABILIDAD 2706
# ============================================================

@dataclass
class Trazabilidad:
    archivo: str
    por_nuevo: dict[str, list[dict[str, str]]]
    por_anterior: dict[str, list[dict[str, str]]]
    vigentes: frozenset[str]
    convenciones: dict[str, str]
    indice: list[tuple[str, dict[str, str]]]


def cargar_trazabilidad(carpeta: str | Path) -> Trazabilidad:
    ruta = _ruta_fuente(carpeta, "trazabilidad")
    filas = repositorio.cargar_trazabilidad(ruta)

    por_nuevo: dict[str, list[dict[str, str]]] = {}
    por_anterior: dict[str, list[dict[str, str]]] = {}
    for fila in filas:
        if fila["codigo_nuevo"]:
            por_nuevo.setdefault(fila["codigo_nuevo"], []).append(fila)
        if fila["codigo_anterior"]:
            por_anterior.setdefault(fila["codigo_anterior"], []).append(fila)

    return Trazabilidad(
        archivo=ruta.name,
        por_nuevo=por_nuevo,
        por_anterior=por_anterior,
        vigentes=frozenset(c for c in por_nuevo if len(c) == 6),
        convenciones=repositorio.cargar_convenciones_trazabilidad(ruta),
        indice=_indexar(filas, ("codigo_nuevo", "codigo_anterior", "descripcion_nueva", "descripcion_anterior")),
    )


def significado_de_trazabilidad(trazabilidad: Trazabilidad, tipo: str) -> str:
    clave = re.sub(r"\s+", " ", (tipo or "").strip()).upper()
    return trazabilidad.convenciones.get(clave, "")


def ficha_trazabilidad(trazabilidad: Trazabilidad, codigo: str) -> dict[str, object]:
    clave = clave_cups(codigo)

    if clave in trazabilidad.vigentes:
        fila = trazabilidad.por_nuevo[clave][0]
        anteriores = [
            f["codigo_anterior"] for f in trazabilidad.por_nuevo[clave]
            if f["codigo_anterior"] and f["codigo_anterior"] != clave
        ]
        return {
            "codigo": clave,
            "estado": ESTADO_VIGENTE,
            "puede_autorizarse": True,
            "descripcion": fila["descripcion_nueva"],
            "anexo": fila["anexo_nuevo"],
            "trazabilidad": fila["trazabilidad"],
            "significado": significado_de_trazabilidad(trazabilidad, fila["trazabilidad"]),
            "descripcion_anterior": fila["descripcion_anterior"],
            "viene_de": sorted(set(anteriores)),
            "reemplazos": [],
        }

    if clave in trazabilidad.por_anterior:
        filas = trazabilidad.por_anterior[clave]
        return {
            "codigo": clave,
            "estado": ESTADO_NO_VIGENTE,
            "puede_autorizarse": False,
            "descripcion": filas[0]["descripcion_anterior"],
            "anexo": filas[0]["anexo_anterior"],
            "trazabilidad": filas[0]["trazabilidad"],
            "significado": significado_de_trazabilidad(trazabilidad, filas[0]["trazabilidad"]),
            "descripcion_anterior": filas[0]["descripcion_anterior"],
            "viene_de": [],
            "reemplazos": [
                {
                    "codigo": f["codigo_nuevo"],
                    "descripcion": f["descripcion_nueva"],
                    "trazabilidad": f["trazabilidad"],
                }
                for f in filas
                if f["codigo_nuevo"]
            ],
        }

    return {
        "codigo": clave,
        "estado": ESTADO_NO_ESTA,
        "puede_autorizarse": False,
        "descripcion": "",
        "anexo": "",
        "trazabilidad": "",
        "significado": "",
        "descripcion_anterior": "",
        "viene_de": [],
        "reemplazos": [],
    }


def consultar_trazabilidad(
    trazabilidad: Trazabilidad,
    texto: str,
    *,
    limite: int = LIMITE_DE_RESULTADOS,
) -> dict[str, object]:
    """Por código (nuevo o anterior) o por descripción."""

    clave = clave_cups(texto)

    if re.fullmatch(r"[0-9A-Z]{6}", clave):
        return {"modo": "codigo", "ficha": ficha_trazabilidad(trazabilidad, clave), "coincidencias": []}

    coincidencias = []
    vistos: set[str] = set()
    for fila in _buscar_texto(trazabilidad.indice, texto, limite * 2):
        # Un cambio de código aporta los dos: el nuevo (vigente) y el anterior.
        for codigo in (fila["codigo_nuevo"], fila["codigo_anterior"]):
            if not codigo or codigo in vistos or len(codigo) != 6:
                continue
            vistos.add(codigo)
            ficha = ficha_trazabilidad(trazabilidad, codigo)
            coincidencias.append(
                {
                    "codigo": codigo,
                    "estado": ficha["estado"],
                    "descripcion": ficha["descripcion"],
                    "trazabilidad": ficha["trazabilidad"],
                }
            )
        if len(coincidencias) >= limite:
            break

    return {"modo": "texto", "ficha": None, "coincidencias": coincidencias}


# ============================================================
# SUPERHOMOLOGADOR
# ============================================================

def cargar_superhomologador(carpeta: str | Path) -> referencias_service.Referencias:
    _ruta_fuente(carpeta, "superhomologador")
    return referencias_service.cargar_superhomologador(carpeta)


def buscar_homologador(
    referencias: referencias_service.Referencias,
    texto: str,
    *,
    limite: int = LIMITE_DE_RESULTADOS,
) -> list[dict[str, str]]:
    """Por CUPS, por código SOAT (ley) o por descripción."""

    clave = clave_cups(texto)
    todas = [f for filas in referencias.homologos_por_cups.values() for f in filas]

    if clave in referencias.homologos_por_cups:
        return referencias.homologos_por_cups[clave][:limite]

    soat = (texto or "").strip().lstrip("0")
    if soat.isdigit():
        coincidencias = [f for f in todas if f["codigo_ley"].lstrip("0") == soat]
        if coincidencias:
            return coincidencias[:limite]

    indice = _indexar(todas, ("cups", "codigo_ley", "descripcion", "descripcion_ley"))
    return _buscar_texto(indice, texto, limite)
