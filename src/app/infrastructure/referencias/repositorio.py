"""Lectura de los archivos de referencia del sistema.

Tres fuentes, tres propósitos:

    SUPERHOMOLOGADOR   tarifas reguladas (UVB, UVT, UVR) y la homologación
                       CUPS <-> código ley.
    CIRCULAR 022       precios regulados de medicamentos, por CUM.
    MÁXIMOS Y MÍNIMOS  rango histórico de tarifas propias del sistema.

Son archivos grandes: leer 'MÁXIMOS Y MÍNIMOS' con openpyxl toma cerca de
16 segundos. Por eso, la primera lectura deja una copia en caché dentro de
`.cache_referencias/` y las siguientes tardan milisegundos. La caché se
invalida sola cuando cambia la fecha o el tamaño del archivo original.

Los originales nunca se modifican.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path

from openpyxl import load_workbook

from src.app.domain.cargues.parsing import normalizar_encabezado, texto_de_celda

CARPETA_CACHE = ".cache_referencias"

# Se sube cuando cambia la forma en que se leen las fuentes: así una caché
# escrita por una versión anterior del código se descarta sola.
VERSION_CACHE = 1

# Cómo se reconoce cada archivo dentro de la carpeta de referencias.
PATRONES_DE_ARCHIVO = {
    "superhomologador": ("SUPERHOMOLOGADOR",),
    "circular": ("CIRCULAR", "MEDICAMENTO"),
    "maximos": ("MAXIMO",),
}

MANUALES = ("UVB", "UVT", "UVR")


class ReferenciaNoDisponible(Exception):
    """No se encontró o no se pudo leer un archivo de referencia."""


# ============================================================
# UBICACIÓN DE LOS ARCHIVOS
# ============================================================

@dataclass(frozen=True)
class Fuentes:
    """Rutas de los tres archivos de referencia."""

    carpeta: Path
    superhomologador: Path | None = None
    circular: Path | None = None
    maximos: Path | None = None

    def faltantes(self) -> list[str]:
        return [
            nombre
            for nombre in ("superhomologador", "circular", "maximos")
            if getattr(self, nombre) is None
        ]


def descubrir_fuentes(carpeta: str | Path) -> Fuentes:
    """Busca los archivos de referencia por su nombre dentro de la carpeta."""

    ruta = Path(carpeta)
    if not ruta.is_dir():
        raise ReferenciaNoDisponible(f"No existe la carpeta '{ruta}'.")

    encontrados: dict[str, Path] = {}

    for archivo in sorted(ruta.glob("*.xls*")):
        nombre = normalizar_encabezado(archivo.stem)
        for clave, patrones in PATRONES_DE_ARCHIVO.items():
            if clave in encontrados:
                continue
            if all(patron in nombre for patron in patrones):
                encontrados[clave] = archivo

    return Fuentes(carpeta=ruta, **encontrados)


# ============================================================
# CACHÉ EN DISCO
# ============================================================

def _huella(ruta: Path) -> dict[str, float]:
    estado = ruta.stat()
    return {
        "mtime": estado.st_mtime,
        "size": estado.st_size,
        "version": VERSION_CACHE,
    }


def _rutas_cache(ruta: Path, nombre: str) -> tuple[Path, Path]:
    carpeta = ruta.parent / CARPETA_CACHE
    return carpeta / f"{nombre}.csv", carpeta / f"{nombre}.json"


def _leer_cache(ruta: Path, nombre: str) -> list[dict[str, str]] | None:
    datos, meta = _rutas_cache(ruta, nombre)

    if not datos.exists() or not meta.exists():
        return None

    try:
        if json.loads(meta.read_text(encoding="utf-8")) != _huella(ruta):
            return None
        with datos.open(encoding="utf-8", newline="") as archivo:
            return list(csv.DictReader(archivo))
    except (OSError, ValueError):
        return None


def _escribir_cache(
    ruta: Path,
    nombre: str,
    filas: list[dict[str, str]],
) -> None:
    if not filas:
        return

    datos, meta = _rutas_cache(ruta, nombre)

    try:
        datos.parent.mkdir(parents=True, exist_ok=True)
        with datos.open("w", encoding="utf-8", newline="") as archivo:
            escritor = csv.DictWriter(archivo, fieldnames=list(filas[0].keys()))
            escritor.writeheader()
            escritor.writerows(filas)
        meta.write_text(json.dumps(_huella(ruta)), encoding="utf-8")
    except OSError:
        # Si la carpeta es de solo lectura se sigue sin caché: más lento,
        # pero nunca se rompe la consulta.
        pass


def _con_cache(ruta: Path, nombre: str, lector) -> list[dict[str, str]]:
    guardado = _leer_cache(ruta, nombre)
    if guardado is not None:
        return guardado

    filas = lector()
    _escribir_cache(ruta, nombre, filas)
    return filas


# ============================================================
# LECTURA DE HOJAS
# ============================================================

def _indices(fila: tuple, columnas: dict[str, tuple[str, ...]]) -> dict[str, int]:
    """Ubica las columnas de una hoja por el nombre del encabezado."""

    normalizados = {
        indice: normalizar_encabezado(valor)
        for indice, valor in enumerate(fila)
        if normalizar_encabezado(valor) != ""
    }

    encontrados: dict[str, int] = {}
    usadas: set[int] = set()

    # Dos pasadas, igual que el lector de anexos: primero coincidencia
    # exacta. Si no, 'PUNTAJE' se quedaría con 'PUNTAJE O GRUPO QX' y
    # 'UNIDAD DE MEDIDA' con 'CANTIDAD POR UNIDAD DE MEDIDA'.
    for exacta in (True, False):
        for campo, alias in columnas.items():
            if campo in encontrados:
                continue
            for alias_normalizado in (normalizar_encabezado(a) for a in alias):
                for indice, texto in normalizados.items():
                    if indice in usadas:
                        continue
                    coincide = (
                        texto == alias_normalizado
                        if exacta
                        else alias_normalizado in texto
                    )
                    if coincide:
                        encontrados[campo] = indice
                        usadas.add(indice)
                        break
                if campo in encontrados:
                    break

    return encontrados


def _leer_hoja(
    ruta: Path,
    hoja: str,
    fila_encabezado: int,
    columnas: dict[str, tuple[str, ...]],
    obligatorias: tuple[str, ...],
) -> list[dict[str, str]]:
    """Lee una hoja completa y devuelve filas con los campos pedidos."""

    libro = load_workbook(ruta, read_only=True, data_only=True)

    try:
        if hoja not in libro.sheetnames:
            raise ReferenciaNoDisponible(
                f"'{ruta.name}' no tiene la hoja '{hoja}'. "
                f"Hojas: {', '.join(libro.sheetnames)}"
            )

        pagina = libro[hoja]
        indices: dict[str, int] = {}
        filas: list[dict[str, str]] = []

        for numero, fila in enumerate(pagina.iter_rows(values_only=True), start=1):
            if numero < fila_encabezado:
                continue

            if numero == fila_encabezado:
                indices = _indices(fila, columnas)
                faltantes = [c for c in obligatorias if c not in indices]
                if faltantes:
                    disponibles = [str(v) for v in fila if v is not None]
                    raise ReferenciaNoDisponible(
                        f"En '{ruta.name}' / '{hoja}' faltan columnas: "
                        f"{', '.join(faltantes)}. "
                        f"Encabezados: {', '.join(disponibles)}"
                    )
                continue

            registro = {
                campo: texto_de_celda(
                    fila[indice] if indice < len(fila) else None
                )
                for campo, indice in indices.items()
            }

            if any(registro.get(campo) for campo in obligatorias):
                filas.append(registro)

        return filas
    finally:
        libro.close()


# ============================================================
# FUENTES
# ============================================================

@dataclass
class Manual:
    """Un manual tarifario regulado, indexado por código ley."""

    sigla: str
    unidad: float
    filas: dict[str, dict[str, str]] = field(default_factory=dict)


def _unidad_del_manual(ruta: Path, hoja: str) -> float:
    """Lee el valor de la unidad del año, que está sobre los encabezados."""

    libro = load_workbook(ruta, read_only=True, data_only=True)
    try:
        pagina = libro[hoja]
        for fila in pagina.iter_rows(max_row=1, values_only=True):
            for valor in fila:
                if isinstance(valor, (int, float)) and valor > 0:
                    return float(valor)
                texto = texto_de_celda(valor).replace(",", "")
                if texto.replace(".", "", 1).isdigit() and float(texto) > 0:
                    return float(texto)
        return 0.0
    finally:
        libro.close()


def cargar_manual(ruta: str | Path, sigla: str) -> Manual:
    """Carga una hoja tarifaria (UVB, UVT o UVR)."""

    archivo = Path(ruta)
    columnas = {
        "codigo_ley": ("CODIGO",),
        "descripcion": ("DESCRIPCION",),
        "puntaje": ("PUNTAJE",),
        "valor_calculado": ("VALOR CALCULADO",),
        "valor_resultante": ("VALOR RESULTANTE",),
    }

    filas = _con_cache(
        archivo,
        f"manual_{sigla.lower()}",
        lambda: _leer_hoja(archivo, sigla, 2, columnas, ("codigo_ley",)),
    )

    return Manual(
        sigla=sigla,
        unidad=_unidad_del_manual(archivo, sigla),
        filas={fila["codigo_ley"]: fila for fila in filas if fila["codigo_ley"]},
    )


def cargar_homologador(ruta: str | Path) -> list[dict[str, str]]:
    """Carga la equivalencia CUPS <-> código ley."""

    archivo = Path(ruta)
    columnas = {
        "cups": ("COD. CUPS RES. 2775", "COD. CUPS"),
        "codigo_ley": ("COD. SOAT",),
        "descripcion_ley": ("DESCRIPCION SOAT",),
        "descripcion": ("DESCRIPCION SERVICIO O PROCEDIMIENTO",),
        "cobertura": ("COBERTURA",),
    }

    return _con_cache(
        archivo,
        "homologador",
        lambda: _leer_hoja(archivo, "HOMOLOGADOR", 1, columnas, ("cups", "codigo_ley")),
    )


def cargar_circular(ruta: str | Path) -> list[dict[str, str]]:
    """Carga los precios regulados de medicamentos."""

    archivo = Path(ruta)
    columnas = {
        "cum": ("CUM/IUM",),
        "medicamento": ("MEDICAMENTO (PRESENTACION COMERCIAL)", "MEDICAMENTO"),
        "unidad_medida": ("UNIDAD DE MEDIDA",),
        "precio_presentacion": ("PRECIO MAX. VENTA INSTITUCIONAL (PRESENTACION COMPLETA)",),
        "precio_unidad": ("PRECIO MAX. VENTA INSTITUCIONAL POR UNIDAD",),
        "margen_presentacion": ("MARGEN PARA IPS (PRESENTACION COMPLETA)",),
        "margen_unidad": ("MARGEN PARA IPS POR UNIDAD",),
        "circular": ("CIRCULAR CNPMDM",),
        "vigencia": ("FECHA INICIO VIGENCIA",),
    }

    return _con_cache(
        archivo,
        "circular",
        lambda: _leer_hoja(archivo, "Precio por unidad", 1, columnas, ("cum",)),
    )


def cargar_maximos(ruta: str | Path) -> list[dict[str, str]]:
    """Carga el rango histórico de tarifas por código."""

    archivo = Path(ruta)
    columnas = {
        "tipo": ("TIPO SERVICIO",),
        "codigo": ("CODIGO SERVICIO",),
        "minimo": ("VALOR MINIMO DEL SERVICIO",),
        "maximo": ("VALOR MAXIMO DEL SERVICIO",),
        "promedio": ("VALOR PROMEDIO",),
        "promedio_incremento": ("PROMEDIO CON INCREMENTO",),
    }

    return _con_cache(
        archivo,
        "maximos_agrupado",
        lambda: _leer_hoja(
            archivo,
            "AGRUPADO_DE_SERVICIOS",
            1,
            columnas,
            ("tipo", "codigo"),
        ),
    )


def contratos_del_codigo(
    ruta: str | Path,
    codigo: str,
    *,
    limite: int = 50,
) -> list[dict[str, str]]:
    """Busca en el detalle histórico los contratos de un código.

    El detalle tiene más de 180.000 filas, así que se recorre en streaming
    y sin caché: se usa solo cuando alguien pide ver el desglose.
    """

    archivo = Path(ruta)
    columnas = {
        "vigencia": ("INICIO VIGENCIA",),
        "codigo": ("CODIGO SERVICIO",),
        "tipo": ("TIPO SERVICIO",),
        "valor": ("VALOR DEL SERVICIO",),
        "tipo_tarifario": ("TIPO TARIFARIO PACTADO",),
        "porcentaje": ("PORCENTAJE TARIFA PACTADA",),
        "prestador": ("NOMBRE DEL PRESTADOR",),
        "contrato": ("NUMERO DE CONTRATO",),
        "nombre_servicio": ("NOMBRE ORIGINAL DEL SERVICIO",),
    }

    libro = load_workbook(archivo, read_only=True, data_only=True)

    try:
        pagina = libro["DETALLE_DE_SERVICIOS"]
        indices: dict[str, int] = {}
        encontrados: list[dict[str, str]] = []

        for numero, fila in enumerate(pagina.iter_rows(values_only=True), start=1):
            if numero == 1:
                indices = _indices(fila, columnas)
                continue

            posicion = indices.get("codigo")
            if posicion is None or posicion >= len(fila):
                continue

            if texto_de_celda(fila[posicion]) != codigo:
                continue

            encontrados.append(
                {
                    campo: texto_de_celda(
                        fila[indice] if indice < len(fila) else None
                    )
                    for campo, indice in indices.items()
                }
            )

            if len(encontrados) >= limite:
                break

        return encontrados
    finally:
        libro.close()
