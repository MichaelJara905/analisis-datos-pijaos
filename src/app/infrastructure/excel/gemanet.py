"""Lectura de los reportes que se exportan de GEMANET.

Hay un reporte por tipo (medicamentos, insumos, servicios) con las columnas
CÓDIGO, VALOR PACTADO, TIPO TARIFARIO, PORCENTAJE TARIFA, DESCRIPCIÓN y
ACTIVO (medicamentos agrega REGULADO).

Particularidades de la exportación, vistas en los reportes reales:
    - Los CUPS vienen como número (898015.0): se pierden los ceros iniciales.
    - TIPO TARIFARIO vacío = tarifa regulada (confirmado por el equipo).
    - Una descripción con coma corre las columnas siguientes: la fila se
      conserva y se reporta como anomalía.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from openpyxl import load_workbook

from src.app.domain.cargues.conciliacion import RegistroGemanet, clave_codigo
from src.app.domain.cargues.parsing import normalizar_encabezado, texto_de_celda

COLUMNAS = {
    "codigo": "CODIGO",
    "valor": "VALOR PACTADO",
    "tipo": "TIPO TARIFARIO",
    "porcentaje": "PORCENTAJE TARIFA",
    "descripcion": "DESCRIPCION",
    "activo": "ACTIVO",
}
OBLIGATORIAS = ("codigo", "valor")
VALORES_DE_ACTIVO = {"", "SI", "NO"}


class LecturaGemanetFallida(Exception):
    """No se pudo interpretar el reporte de GEMANET."""


@dataclass
class ReporteGemanet:
    archivo: str
    registros: dict[str, RegistroGemanet] = field(default_factory=dict)
    repetidos: dict[str, list[int]] = field(default_factory=dict)
    anomalias: list[dict[str, object]] = field(default_factory=list)


def _a_numero(texto: str) -> float | None:
    try:
        return float(texto.replace(",", ""))
    except ValueError:
        return None


def leer_reporte(origen: str | Path, *, completar_ceros: bool = True) -> ReporteGemanet:
    """Lee el reporte. `completar_ceros` solo para servicios (ver `clave_codigo`)."""

    ruta = Path(origen)
    libro = load_workbook(ruta, data_only=True, read_only=True)

    try:
        hoja = libro["DATOS"] if "DATOS" in libro.sheetnames else libro.worksheets[0]
        filas = hoja.iter_rows(values_only=True)

        encabezado = next(filas, None)
        if encabezado is None:
            raise LecturaGemanetFallida(f"'{ruta.name}' está vacío.")

        normalizados = {
            normalizar_encabezado(valor): indice
            for indice, valor in enumerate(encabezado)
            if valor is not None
        }
        indices = {
            campo: normalizados[nombre]
            for campo, nombre in COLUMNAS.items()
            if nombre in normalizados
        }
        faltantes = [c for c in OBLIGATORIAS if c not in indices]
        if faltantes:
            raise LecturaGemanetFallida(
                f"'{ruta.name}' no tiene las columnas {', '.join(faltantes)}. "
                f"Encabezados: {', '.join(str(v) for v in encabezado if v)}"
            )

        reporte = ReporteGemanet(archivo=ruta.name)
        posiciones: dict[str, list[int]] = {}

        def celda(fila: tuple, campo: str) -> str:
            indice = indices.get(campo)
            return "" if indice is None or indice >= len(fila) else texto_de_celda(fila[indice])

        for numero, fila in enumerate(filas, start=2):
            codigo = celda(fila, "codigo")
            if codigo == "":
                continue

            clave = clave_codigo(codigo, completar_ceros=completar_ceros)
            registro = RegistroGemanet(
                codigo=clave,
                valor=_a_numero(celda(fila, "valor")),
                tipo=celda(fila, "tipo").upper(),
                porcentaje=celda(fila, "porcentaje"),
                descripcion=celda(fila, "descripcion"),
                activo=celda(fila, "activo"),
                fila=numero,
            )

            if normalizar_encabezado(registro.activo) not in VALORES_DE_ACTIVO:
                reporte.anomalias.append(
                    {
                        "origen": "gemanet",
                        "tipo": "columnas corridas",
                        "codigo": clave,
                        "detalle": (
                            "ACTIVO trae texto de la descripción; probable "
                            "coma dentro de la descripción"
                        ),
                        "ubicacion": f"{ruta.name} fila {numero}",
                        "en_gemanet": "sí",
                    }
                )

            posiciones.setdefault(clave, []).append(numero)
            reporte.registros.setdefault(clave, registro)

        reporte.repetidos = {c: f for c, f in posiciones.items() if len(f) > 1}
        for clave, filas_repetidas in reporte.repetidos.items():
            reporte.anomalias.append(
                {
                    "origen": "gemanet",
                    "tipo": "código repetido",
                    "codigo": clave,
                    "detalle": f"{len(filas_repetidas)} veces en el reporte",
                    "ubicacion": f"{ruta.name} filas {', '.join(map(str, filas_repetidas[:8]))}",
                    "en_gemanet": "sí",
                }
            )

        return reporte
    finally:
        libro.close()
