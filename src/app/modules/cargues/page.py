"""Interfaz del módulo de cargues GEMANET.

Flujo: subir anexo -> revisar cómo se interpretó -> corregir lo que haga
falta -> descargar el TXT. El archivo original nunca se modifica.
"""

from __future__ import annotations

import io

import polars as pl
import streamlit as st

from src.app.components.layout import render_header
from src.app.application import cargues_service, notificacion_service, referencias_service
from src.app.core.config import get_config
from src.app.domain.cargues import rules, txt_writer
from src.app.infrastructure.referencias.repositorio import ReferenciaNoDisponible
from src.app.domain.cargues.model import ResultadoCargue, Severidad
from src.app.infrastructure.excel.anexos import LecturaFallida
from src.app.infrastructure.excel.workbook import create_excel_download


def _tabla(filas: list[dict[str, object]]) -> pl.DataFrame:
    """Convierte las filas del reporte a Polars, como el resto de la app."""

    if not filas:
        return pl.DataFrame()

    # Todo a texto: las tablas son de lectura, no de cálculo, y así no se
    # pierde un código con ceros a la izquierda al inferir el tipo.
    return pl.DataFrame(
        [{clave: "" if valor is None else str(valor) for clave, valor in fila.items()}
         for fila in filas]
    )


def _mostrar(filas: list[dict[str, object]]) -> None:
    st.dataframe(_tabla(filas).to_pandas(), use_container_width=True, hide_index=True)


def _excel(filas: list[dict[str, object]], hoja: str) -> bytes:
    """Exporta a Excel con el mismo formato que usa el módulo de tarifas."""

    return create_excel_download(_tabla(filas), hoja)


@st.cache_resource(show_spinner=False)
def _soat_por_cups() -> dict[str, frozenset[str]] | None:
    """Homologador CUPS -> SOAT; None si no hay carpeta de referencias."""

    try:
        return referencias_service.cargar_soat_por_cups(
            get_config().referencias_path
        )
    except (ReferenciaNoDisponible, OSError, ValueError, KeyError):
        return None


@st.cache_data(show_spinner=False)
def cached_procesar_anexo(
    datos: bytes,
    nombre: str,
    tipo: str,
    hoja: str | None,
    fila_encabezado: int | None,
    _soat_por_cups: dict[str, frozenset[str]] | None = None,
) -> ResultadoCargue:
    """Cachea el análisis para no releer el Excel en cada rerun."""

    return cargues_service.procesar_anexo(
        io.BytesIO(datos),
        tipo,
        nombre_archivo=nombre,
        hoja=hoja,
        fila_encabezado=fila_encabezado,
        soat_por_cups=_soat_por_cups,
    )


def _firma(archivo, tipo: str, hoja: str, fila: int) -> str:
    return f"{archivo.name}:{archivo.size}:{tipo}:{hoja}:{fila}"


# ============================================================
# SECCIONES
# ============================================================

def render_carga() -> None:
    render_header(
        title="Cargues GEMANET",
        subtitle="Prepara y valida anexos tarifarios para el cargue masivo.",
    )
    st.title("Cargues GEMANET")
    st.write(
        "Prepara un anexo tarifario para el cargue masivo: revisa los datos, "
        "corrige lo que se puede corregir con seguridad, señala lo que hay "
        "que revisar y genera el archivo TXT."
    )
    st.info(
        "¿El prestador ya tiene códigos cargados en GEMANET? Usa **Conciliación "
        "GEMANET** con el reporte de su tarifario: hace este mismo análisis, "
        "descarta lo que ya está cargado y deja el TXT solo con lo que falta."
    )

    archivo = st.file_uploader(
        "Anexo tarifario (Excel)",
        type=["xlsx", "xlsm"],
        key="cargue_anexo",
    )

    columnas = st.columns(3)
    tipo = columnas[0].selectbox(
        "Tipo de cargue",
        rules.TIPOS_DE_CARGUE,
        help="PAQ todavía no está soportado: falta documentar su estructura.",
    )
    hoja = columnas[1].text_input(
        "Hoja (opcional)",
        help="Déjalo vacío para que el sistema la detecte.",
    )
    fila_encabezado = columnas[2].number_input(
        "Fila de encabezados (opcional)",
        min_value=0,
        value=0,
        help="0 = detección automática.",
    )

    if archivo is None:
        st.info("Sube el anexo para comenzar.")
        return

    if st.button("Analizar anexo", type="primary", use_container_width=True):
        _analizar(archivo, tipo, hoja, int(fila_encabezado))

    resultado = st.session_state.get("cargue_resultado")
    if resultado is None:
        st.info("Pulsa «Analizar anexo» para procesar el archivo.")
        return

    if st.session_state.get("cargue_firma") != _firma(
        archivo, tipo, hoja, int(fila_encabezado)
    ):
        st.warning("Cambiaron los parámetros. Vuelve a pulsar «Analizar anexo».")
        return

    render_interpretacion(resultado)
    render_resumen(resultado)
    render_detalle(resultado)
    render_descargas(resultado)


def _analizar(archivo, tipo: str, hoja: str, fila_encabezado: int) -> None:
    try:
        with st.spinner("Leyendo y validando el anexo..."):
            resultado = cached_procesar_anexo(
                archivo.getvalue(),
                archivo.name,
                tipo,
                hoja or None,
                fila_encabezado or None,
                _soat_por_cups() if tipo == rules.CARGUE_CUPS else None,
            )
    except LecturaFallida as error:
        st.session_state.pop("cargue_resultado", None)
        st.error("No se pudo interpretar la estructura del anexo.")
        st.code(str(error))
        st.caption(
            "Indica la hoja y la fila de encabezados, o agrega el nombre de "
            "la columna en rules.ALIAS_DE_COLUMNAS."
        )
        return

    st.session_state["cargue_resultado"] = resultado
    st.session_state["cargue_firma"] = _firma(archivo, tipo, hoja, fila_encabezado)


def render_interpretacion(resultado: ResultadoCargue) -> None:
    with st.container(border=True):
        st.markdown("**Cómo se interpretó el archivo**")
        st.caption(
            f"Hoja «{resultado.hoja}», encabezados en la fila "
            f"{resultado.fila_encabezado}."
        )
        _mostrar(
            [
                {"Campo del cargue": campo, "Columna del anexo": encabezado}
                for campo, encabezado in resultado.mapeo_columnas.items()
            ]
        )
        st.caption(
            "Si alguna columna quedó mal asignada, no sigas: corrige la hoja "
            "o la fila de encabezados y vuelve a analizar."
        )


def render_resumen(resultado: ResultadoCargue) -> None:
    resumen = resultado.resumen()

    tarjetas = st.columns(5)
    tarjetas[0].metric("Registros", resumen["registros_leidos"])
    tarjetas[1].metric("Listos", resumen["listos_para_cargue"])
    tarjetas[2].metric("Por revisar", resumen["con_advertencia"])
    tarjetas[3].metric("Bloqueados", resumen["bloqueados"])
    tarjetas[4].metric("Correcciones", resumen["correcciones"])

    if resumen["bloqueados"]:
        st.warning(
            f"{resumen['bloqueados']} registros no pueden ir al cargue. "
            "Revisa la pestaña «Bloqueados»."
        )
    elif resumen["con_advertencia"]:
        st.info(
            "Todos los registros pueden generarse, pero hay advertencias "
            "que conviene revisar antes de subir el archivo."
        )
    else:
        st.success("Todos los registros quedaron listos.")


def render_detalle(resultado: ResultadoCargue) -> None:
    detalle = cargues_service.filas_de_registros(resultado)
    hallazgos = cargues_service.filas_de_reporte(resultado)

    pestañas = st.tabs(
        ["Registros", "Bloqueados", "Por revisar", "Correcciones", "Vista previa del TXT"]
    )

    with pestañas[0]:
        _mostrar(detalle)

    with pestañas[1]:
        filas = [h for h in hallazgos if h["severidad"] == Severidad.BLOQUEANTE.value]
        if filas:
            _mostrar(filas)
        else:
            st.success("Sin registros bloqueados.")

    with pestañas[2]:
        filas = [h for h in hallazgos if h["severidad"] == Severidad.ADVERTENCIA.value]
        if filas:
            _mostrar(filas)
        else:
            st.success("Sin advertencias.")

    with pestañas[3]:
        filas = [h for h in hallazgos if h["severidad"] == Severidad.CORRECCION.value]
        st.caption(
            "Cada corrección automática queda registrada con su valor "
            "original y la regla aplicada."
        )
        if filas:
            _mostrar(filas)
        else:
            st.info("No hubo correcciones automáticas.")

    with pestañas[4]:
        if not resultado.listos:
            st.warning("No hay registros listos para generar.")
        else:
            vista = txt_writer.construir_contenido(
                resultado.listos[:20],
                resultado.tipo_cargue,
            )
            st.caption("Primeros 20 registros, tal como quedarían en el archivo.")
            st.code(vista, language="text")


def render_devolucion(resultado: ResultadoCargue, nombre: str) -> None:
    """Documento con lo bloqueado, para devolverlo al prestador."""

    por_corregir = notificacion_service.filas_por_corregir_de_registros(
        resultado.bloqueados, resultado.hoja
    )
    hoja_excel = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    st.markdown("**Para el prestador**")
    columnas = st.columns(2)

    devolucion = notificacion_service.excel_de_devolucion(por_corregir)
    if devolucion is not None:
        columnas[0].download_button(
            f"Devolver al prestador ({len(por_corregir)} bloqueados)",
            data=devolucion,
            file_name=f"{nombre}_devolucion_prestador.xlsx",
            mime=hoja_excel,
            help=(
                "CODIGO - DESCRIPCION - VALOR de lo bloqueado (repetidos, códigos "
                "inválidos...), con el motivo y la fila del anexo."
            ),
            type="primary",
            use_container_width=True,
        )
    else:
        columnas[0].success("No hay nada que devolver al prestador.")

    notificacion = notificacion_service.excel_de_notificacion(
        notificacion_service.filas_para_parametrizar(resultado.listos),
        por_corregir,
    )
    if notificacion is not None:
        columnas[1].download_button(
            "Notificar lo que se parametriza",
            data=notificacion,
            file_name=f"{nombre}_notificacion.xlsx",
            mime=hoja_excel,
            help="CODIGO - DESCRIPCION - VALOR de lo que se carga y, en otra hoja, lo que debe corregir.",
            use_container_width=True,
        )


def render_descargas(resultado: ResultadoCargue) -> None:
    st.subheader("Descargas")

    nombre = f"{resultado.tipo_cargue}_{resultado.archivo_origen.rsplit('.', 1)[0]}"

    if not resultado.listos:
        st.error("No se genera TXT porque ningún registro quedó listo.")
        render_devolucion(resultado, nombre)
        return

    columnas = st.columns(3)

    columnas[0].download_button(
        "Archivo TXT para GEMANET",
        data=txt_writer.construir_bytes(resultado.listos, resultado.tipo_cargue),
        file_name=f"{nombre}.txt",
        mime="text/plain",
        type="primary",
        use_container_width=True,
    )

    hoja_excel = (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    columnas[1].download_button(
        "Reporte de hallazgos",
        data=_excel(cargues_service.filas_de_reporte(resultado), "hallazgos"),
        file_name=f"{nombre}_hallazgos.xlsx",
        mime=hoja_excel,
        use_container_width=True,
    )

    columnas[2].download_button(
        "Detalle de registros",
        data=_excel(cargues_service.filas_de_registros(resultado), "registros"),
        file_name=f"{nombre}_registros.xlsx",
        mime=hoja_excel,
        use_container_width=True,
    )

    render_devolucion(resultado, nombre)

    st.caption(
        "El TXT incluye únicamente los registros listos. Los bloqueados "
        "quedan por fuera a propósito."
    )


render_carga()
