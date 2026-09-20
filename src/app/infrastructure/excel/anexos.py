"""Lectura de anexos tarifarios en Excel.

Los anexos no tienen un formato único: cambia la hoja, la fila donde
empiezan los encabezados, el nombre de las columnas y su orden. Por eso
el lector NO usa posiciones fijas:

    1. Recorre las hojas buscando una fila que parezca de encabezados.
    2. Mapea cada columna por el nombre del encabezado, usando los alias
       de `rules.ALIAS_DE_COLUMNAS`.
    3. Lee los datos desde la fila siguiente.

Si no logra identificar las columnas obligatorias, lanza `LecturaFallida`
con los encabezados que sí encontró, para poder mapearlos a mano.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from openpyxl import load_workbook

from src.app.domain.cargues import rules
from src.app.domain.cargues.parsing import normalizar_encabezado


class LecturaFallida(Exception):
    """No se pudo interpretar la estructura del anexo."""


@dataclass
class HojaDetectada:
    """Resultado de analizar una hoja del archivo."""

    nombre: str
    fila_encabezado: int
    columnas: dict[str, int]          # campo lógico -> índice de columna
    encabezados: dict[int, str]       # índice -> encabezado original
    reconocidas: int
    puntaje: int = 0


@dataclass
class AnexoLeido:
    """Filas crudas del anexo, con su origen."""

    hoja: str
    fila_encabezado: int
    mapeo: dict[str, str]             # campo lógico -> encabezado original
    filas: list[dict[str, object]]    # incluye "_fila" con el número real
    encabezados_disponibles: list[str]


# ============================================================
# DETECCIÓN
# ============================================================

def _mapear_encabezados(
    valores: list[object],
    alias_por_campo: dict[str, tuple[str, ...]],
) -> tuple[dict[str, int], dict[int, str], int]:
    """Empareja los encabezados de una fila con los campos lógicos.

    Trabaja en dos pasadas para evitar que un alias genérico se quede con
    una columna que le pertenece a otro campo:

        1. Coincidencia exacta de todos los campos.
        2. Coincidencia por contenido solo con lo que quedó libre.

    Sin esto, el alias 'CODIGO' de CUMS se apropiaba de la columna
    'CODIGO HOMOLOGO SOAT' de una hoja de servicios.

    Returns:
        (columnas, encabezados, puntaje)
    """

    normalizados = {
        indice: normalizar_encabezado(valor)
        for indice, valor in enumerate(valores)
        if normalizar_encabezado(valor) != ""
    }

    encabezados = {
        indice: str(valores[indice]).strip()
        for indice in normalizados
    }

    columnas: dict[str, int] = {}
    usadas: set[int] = set()
    puntaje = 0

    # Pasada 1: coincidencia exacta.
    for campo, alias in alias_por_campo.items():
        indice = _buscar_exacta(normalizados, alias, usadas)
        if indice is not None:
            columnas[campo] = indice
            usadas.add(indice)
            puntaje += rules.PUNTOS_COINCIDENCIA_EXACTA

    # Pasada 2: coincidencia por contenido.
    for campo, alias in alias_por_campo.items():
        if campo in columnas:
            continue
        indice = _buscar_parcial(normalizados, alias, usadas)
        if indice is not None:
            columnas[campo] = indice
            usadas.add(indice)
            puntaje += rules.PUNTOS_COINCIDENCIA_PARCIAL

    return columnas, encabezados, puntaje


def _buscar_exacta(
    normalizados: dict[int, str],
    alias: tuple[str, ...],
    usadas: set[int],
) -> int | None:
    """Encabezado idéntico a alguno de los alias."""

    for alias_normalizado in (normalizar_encabezado(a) for a in alias):
        for indice, texto in normalizados.items():
            if indice not in usadas and texto == alias_normalizado:
                return indice
    return None


def _buscar_parcial(
    normalizados: dict[int, str],
    alias: tuple[str, ...],
    usadas: set[int],
) -> int | None:
    """Encabezado que contiene el alias.

    Sirve para casos como 'TARIFA OFERTADA (% DE DESCUENTO)', que contiene
    'TARIFA OFERTADA'.
    """

    for alias_normalizado in (normalizar_encabezado(a) for a in alias):
        for indice, texto in normalizados.items():
            if indice not in usadas and alias_normalizado in texto:
                return indice
    return None


def _puntaje_por_nombre(nombre_hoja: str, tipo_cargue: str) -> int:
    """Premia la hoja cuyo nombre corresponde al tipo de cargue."""

    nombre = normalizar_encabezado(nombre_hoja)
    puntaje = 0

    for tipo, pistas in rules.PISTAS_DE_HOJA.items():
        if not any(pista in nombre for pista in pistas):
            continue
        if tipo == tipo_cargue:
            puntaje += rules.PUNTOS_PISTA_DE_HOJA
        else:
            puntaje -= rules.PUNTOS_PISTA_DE_HOJA

    return puntaje


def detectar_hojas(
    libro,
    tipo_cargue: str,
) -> list[HojaDetectada]:
    """Analiza todas las hojas y devuelve las que sirven, mejor primero."""

    alias = rules.ALIAS_DE_COLUMNAS[tipo_cargue]
    obligatorias = rules.COLUMNAS_OBLIGATORIAS[tipo_cargue]
    candidatas: list[HojaDetectada] = []

    for hoja in libro.worksheets:
        mejor: HojaDetectada | None = None

        bono = _puntaje_por_nombre(hoja.title, tipo_cargue)

        for numero, fila in enumerate(
            hoja.iter_rows(
                max_row=rules.MAXIMO_FILAS_PARA_ENCABEZADO,
                values_only=True,
            ),
            start=1,
        ):
            valores = list(fila)
            columnas, encabezados, puntaje = _mapear_encabezados(valores, alias)

            if len(columnas) < rules.MINIMO_COLUMNAS_RECONOCIDAS:
                continue
            if not all(campo in columnas for campo in obligatorias):
                continue

            detectada = HojaDetectada(
                nombre=hoja.title,
                fila_encabezado=numero,
                columnas=columnas,
                encabezados=encabezados,
                reconocidas=len(columnas),
                puntaje=puntaje + bono,
            )
            if mejor is None or detectada.puntaje > mejor.puntaje:
                mejor = detectada

        if mejor is not None:
            candidatas.append(mejor)

    return sorted(candidatas, key=lambda h: h.puntaje, reverse=True)


def _encabezados_vistos(libro) -> list[str]:
    """Encabezados de texto del archivo, para ayudar a diagnosticar."""

    vistos: list[str] = []
    for hoja in libro.worksheets:
        for fila in hoja.iter_rows(
            max_row=rules.MAXIMO_FILAS_PARA_ENCABEZADO,
            values_only=True,
        ):
            for valor in fila:
                if isinstance(valor, str) and valor.strip():
                    etiqueta = f"{hoja.title}: {valor.strip()}"
                    if etiqueta not in vistos:
                        vistos.append(etiqueta)
    return vistos[:80]


# ============================================================
# LECTURA
# ============================================================

def leer_anexo(
    origen: str | Path | BinaryIO,
    tipo_cargue: str,
    *,
    hoja: str | None = None,
    fila_encabezado: int | None = None,
    mapeo_manual: dict[str, str] | None = None,
) -> AnexoLeido:
    """Lee un anexo y devuelve sus filas crudas.

    Args:
        origen: Ruta del archivo o archivo binario ya abierto.
        tipo_cargue: CUMS, INS o CUPS.
        hoja: Nombre de la hoja, si se quiere forzar una.
        fila_encabezado: Fila de encabezados (base 1), si se quiere forzar.
        mapeo_manual: Campo lógico -> encabezado exacto, para los casos en
            que la detección automática no alcanza.

    Raises:
        LecturaFallida: si no se puede identificar la estructura.
    """

    if tipo_cargue not in rules.TIPOS_DE_CARGUE:
        raise LecturaFallida(f"Tipo de cargue no soportado: {tipo_cargue}")

    libro = load_workbook(origen, data_only=True, read_only=True)

    try:
        seleccion = _seleccionar_hoja(
            libro,
            tipo_cargue,
            hoja,
            fila_encabezado,
            mapeo_manual,
        )
        filas = _extraer_filas(libro[seleccion.nombre], seleccion)
    finally:
        libro.close()

    mapeo = {
        campo: seleccion.encabezados.get(indice, f"columna {indice + 1}")
        for campo, indice in seleccion.columnas.items()
    }

    return AnexoLeido(
        hoja=seleccion.nombre,
        fila_encabezado=seleccion.fila_encabezado,
        mapeo=mapeo,
        filas=filas,
        encabezados_disponibles=sorted(seleccion.encabezados.values()),
    )


def _seleccionar_hoja(
    libro,
    tipo_cargue: str,
    hoja: str | None,
    fila_encabezado: int | None,
    mapeo_manual: dict[str, str] | None,
) -> HojaDetectada:
    """Decide con qué hoja y qué fila de encabezados se va a trabajar."""

    if hoja is not None and fila_encabezado is not None:
        if hoja not in libro.sheetnames:
            raise LecturaFallida(
                f"La hoja '{hoja}' no existe. Hojas: "
                f"{', '.join(libro.sheetnames)}"
            )
        return _detectar_en_fila(
            libro[hoja],
            tipo_cargue,
            fila_encabezado,
            mapeo_manual,
        )

    candidatas = detectar_hojas(libro, tipo_cargue)

    if hoja is not None:
        candidatas = [c for c in candidatas if c.nombre == hoja]

    if not candidatas:
        obligatorias = ", ".join(rules.COLUMNAS_OBLIGATORIAS[tipo_cargue])
        raise LecturaFallida(
            "No se identificaron las columnas obligatorias "
            f"({obligatorias}) para un cargue {tipo_cargue}.\n"
            "Indica la hoja, la fila de encabezados y el mapeo manual, "
            "o agrega el alias en rules.ALIAS_DE_COLUMNAS.\n"
            "Encabezados encontrados en el archivo:\n - "
            + "\n - ".join(_encabezados_vistos(libro))
        )

    return candidatas[0]


def _detectar_en_fila(
    hoja,
    tipo_cargue: str,
    fila_encabezado: int,
    mapeo_manual: dict[str, str] | None,
) -> HojaDetectada:
    """Construye el mapeo usando una fila de encabezados específica."""

    valores: list[object] = []
    for numero, fila in enumerate(hoja.iter_rows(values_only=True), start=1):
        if numero == fila_encabezado:
            valores = list(fila)
            break

    if not valores:
        raise LecturaFallida(
            f"La fila {fila_encabezado} de la hoja '{hoja.title}' está vacía."
        )

    columnas, encabezados, puntaje = _mapear_encabezados(
        valores,
        rules.ALIAS_DE_COLUMNAS[tipo_cargue],
    )

    if mapeo_manual:
        for campo, encabezado in mapeo_manual.items():
            buscado = normalizar_encabezado(encabezado)
            for indice, texto in encabezados.items():
                if normalizar_encabezado(texto) == buscado:
                    columnas[campo] = indice
                    break
            else:
                raise LecturaFallida(
                    f"El encabezado '{encabezado}' indicado para '{campo}' "
                    f"no está en la fila {fila_encabezado}."
                )

    faltantes = [
        campo
        for campo in rules.COLUMNAS_OBLIGATORIAS[tipo_cargue]
        if campo not in columnas
    ]
    if faltantes:
        raise LecturaFallida(
            f"Faltan columnas obligatorias: {', '.join(faltantes)}. "
            f"Encabezados de la fila {fila_encabezado}: "
            + ", ".join(encabezados.values())
        )

    return HojaDetectada(
        nombre=hoja.title,
        fila_encabezado=fila_encabezado,
        columnas=columnas,
        encabezados=encabezados,
        reconocidas=len(columnas),
        puntaje=puntaje,
    )


def _extraer_filas(hoja, seleccion: HojaDetectada) -> list[dict[str, object]]:
    """Lee los datos desde la fila siguiente a los encabezados.

    Se detiene tras una racha de filas vacías, porque los archivos de Excel
    suelen declarar un rango mucho mayor que los datos reales.
    """

    filas: list[dict[str, object]] = []
    vacias_seguidas = 0
    indices = seleccion.columnas

    for numero, fila in enumerate(hoja.iter_rows(values_only=True), start=1):
        if numero <= seleccion.fila_encabezado:
            continue

        valores = list(fila)
        registro: dict[str, object] = {"_fila": numero}
        hay_datos = False

        for campo, indice in indices.items():
            valor = valores[indice] if indice < len(valores) else None
            registro[campo] = valor
            if valor is not None and str(valor).strip() != "":
                hay_datos = True

        if not hay_datos:
            vacias_seguidas += 1
            if vacias_seguidas >= rules.FILAS_VACIAS_PARA_CORTAR:
                break
            continue

        vacias_seguidas = 0
        filas.append(registro)

    return filas
