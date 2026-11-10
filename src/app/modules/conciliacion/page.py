"""Conciliación de un anexo con lo que ya está cargado en GEMANET.

Se sube el anexo del prestador y el reporte exportado de GEMANET del mismo
tipo. El sistema descarta lo que ya está cargado y deja el TXT solo con lo
que falta y es válido; lo demás sale en informes aparte.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import polars as pl
import streamlit as st

from src.app.application import conciliacion_service, referencias_service
from src.app.components.layout import render_header
from src.app.core.config import get_config
from src.app.domain.cargues import rules
from src.app.infrastructure.excel.anexos import LecturaFallida
from src.app.infrastructure.excel.gemanet import LecturaGemanetFallida
from src.app.infrastructure.excel.workbook import create_excel_download
from src.app.infrastructure.referencias.repositorio import ReferenciaNoDisponible

TIPOS = {
    "Servicios (CUPS)": rules.CARGUE_CUPS,
    "Medicamentos (CUMS)": rules.CARGUE_CUMS,
    "Insumos (INS)": rules.CARGUE_INS,
}
HOJA_EXCEL = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
LLAVE = "conciliacion_resultado"


def _tabla(filas: list[dict]) -> pl.DataFrame:
    if not filas:
        return pl.DataFrame()
    # Todo a texto: los códigos con ceros a la izquierda no se deben perder.
    return pl.DataFrame(
        [{k: "" if v is None else str(v) for k, v in fila.items()} for fila in filas]
    )


def _mostrar(filas: list[dict]) -> None:
    if filas:
        st.dataframe(_tabla(filas).to_pandas(), width="stretch", hide_index=True)


def _guardar(archivo, carpeta: Path) -> Path:
    ruta = carpeta / archivo.name
    ruta.write_bytes(archivo.getvalue())
    return ruta


@st.cache_resource(show_spinner=False)
def _soat_por_cups():
    try:
        return referencias_service.cargar_soat_por_cups(get_config().referencias_path)
    except (ReferenciaNoDisponible, OSError, ValueError, KeyError):
        return None


def _conciliar(anexo, reporte, tipo: str, hojas: str) -> dict | None:
    with tempfile.TemporaryDirectory() as temporal:
        carpeta = Path(temporal)
        ruta_anexo = _guardar(anexo, carpeta)
        ruta_reporte = _guardar(reporte, carpeta)

        resultado, procesado, gema = conciliacion_service.conciliar_anexo(
            ruta_anexo,
            tipo,
            ruta_reporte,
            hojas=[h for h in hojas.split(",") if h.strip()] or None,
            soat_por_cups=_soat_por_cups() if tipo == rules.CARGUE_CUPS else None,
        )

        prefijo = f"{tipo}_{Path(anexo.name).stem}"
        rutas = conciliacion_service.generar_informes(
            resultado, procesado, carpeta / "salida", prefijo=prefijo, reporte=gema
        )
        txt = rutas["txt"].read_bytes() if "txt" in rutas else b""

    return {
        "resultado": resultado,
        "procesado": procesado,
        "reporte": gema,
        "txt": txt,
        "notificacion": conciliacion_service.construir_notificacion(resultado),
        "devolucion": conciliacion_service.construir_devolucion(resultado),
        "nombre": prefijo,
    }


def render() -> None:
    render_header(
        title="Conciliación con GEMANET",
        subtitle="Descarta lo que ya está cargado y deja solo lo que hay que subir.",
    )
    st.title("Conciliación con GEMANET")
    st.write(
        "Es el proceso completo: valida el anexo, bloquea lo que no se debe cargar "
        "(repetidos, códigos inválidos...), descarta lo que ya está en GEMANET y "
        "deja el TXT **solo** con lo que falta y es válido. Sube el anexo del "
        "prestador y el reporte de su tarifario en GEMANET (del mismo tipo)."
    )
    st.caption(
        "Salidas: el TXT para subir, el documento para devolver al prestador "
        "(CODIGO - DESCRIPCION - VALOR de lo bloqueado) y los informes de diferencias."
    )

    columnas = st.columns([1, 2, 2])
    etiqueta = columnas[0].selectbox("Tipo", list(TIPOS))
    anexo = columnas[1].file_uploader("Anexo del prestador (Excel)", type=["xlsx", "xlsm"], key="conc_anexo")
    reporte = columnas[2].file_uploader(
        "Reporte de GEMANET (Excel)", type=["xlsx"], key="conc_reporte",
        help="El reporte exportado de GEMANET del mismo tipo y del mismo prestador.",
    )
    hojas = st.text_input(
        "Hojas del anexo (opcional)",
        help="Separadas por coma. Vacío = el sistema usa las hojas que reconoce para el tipo.",
    )

    if anexo is None or reporte is None:
        st.info("Sube los dos archivos para comenzar.")
        return

    if st.button("Conciliar", type="primary", width="stretch"):
        try:
            with st.spinner("Cruzando el anexo con GEMANET..."):
                st.session_state[LLAVE] = _conciliar(anexo, reporte, TIPOS[etiqueta], hojas)
        except (LecturaFallida, LecturaGemanetFallida) as error:
            st.session_state.pop(LLAVE, None)
            st.error("No se pudo leer alguno de los archivos.")
            st.code(str(error))
            return
        except conciliacion_service.TxtInconsistente as error:
            st.session_state.pop(LLAVE, None)
            st.error(f"No se generó el TXT: falló la verificación final. {error}")
            return

    datos = st.session_state.get(LLAVE)
    if datos is None:
        return

    resultado, procesado = datos["resultado"], datos["procesado"]

    st.caption(
        f"Hojas usadas: {', '.join(procesado.hojas_usadas)}. "
        f"Omitidas: {', '.join(procesado.hojas_omitidas) or '-'}. "
        f"Registros en GEMANET: {len(datos['reporte'].registros)}."
    )
    for hallazgo in procesado.hallazgos_generales:
        st.warning(f"{hallazgo.problema}. {hallazgo.sugerencia}")

    r = resultado.resumen()
    tarjetas = st.columns(5)
    tarjetas[0].metric("Ya cargados", r["ya_cargados_y_coinciden"])
    tarjetas[1].metric("Para cargar", r["faltan_y_se_pueden_cargar"])
    tarjetas[2].metric("Faltan con error", r["faltan_con_error"])
    tarjetas[3].metric("Con diferencias", r["cargados_con_diferencias"])
    tarjetas[4].metric("Inconsistencias", r["inconsistencias"])

    st.subheader("Archivo para subir")
    if datos["txt"]:
        st.download_button(
            f"Descargar TXT ({len(resultado.a_cargar)} líneas)",
            data=datos["txt"],
            file_name=f"{datos['nombre']}_para_cargar.txt",
            mime="text/plain",
            type="primary",
            width="stretch",
        )
        st.caption("Sin los que ya están en GEMANET, sin repetidos y sin errores.")
    else:
        st.success("No hay nada para cargar: todo lo válido del anexo ya está en GEMANET.")

    if datos["devolucion"]:
        st.download_button(
            f"Devolver al prestador ({len(resultado.faltan_con_error)} bloqueados)",
            data=datos["devolucion"],
            file_name=f"{datos['nombre']}_devolucion_prestador.xlsx",
            mime=HOJA_EXCEL,
            key="descarga_devolucion",
            type="primary",
            width="stretch",
        )
        st.caption(
            "CODIGO - DESCRIPCION - VALOR de lo bloqueado, con el motivo y la fila del anexo."
        )

    if datos["notificacion"]:
        st.download_button(
            "Documento para notificar lo que se parametriza (Excel)",
            data=datos["notificacion"],
            file_name=f"{datos['nombre']}_notificacion.xlsx",
            mime=HOJA_EXCEL,
            key="descarga_notificacion",
            width="stretch",
        )
        st.caption(
            "CODIGO - DESCRIPCION - VALOR de lo que se va a parametrizar y, en otra hoja, "
            "lo que el prestador debe corregir, con el motivo."
        )

    pestanas = st.tabs(
        ["Vista previa del TXT", "Faltan con error", "Con diferencias", "Inconsistencias", "Solo en GEMANET"]
    )
    informes = [
        (None, None),
        (resultado.faltan_con_error, "faltan_con_error"),
        (resultado.diferencias, "diferencias"),
        (resultado.inconsistencias, "inconsistencias"),
        (resultado.solo_gemanet, "solo_en_gemanet"),
    ]
    mensajes = [
        "",
        "No se pueden cargar así: se muestra el motivo de cada uno.",
        "Ya están en GEMANET con otro valor, tipo o inactivos: el cargue no los actualiza.",
        "Códigos repetidos en el anexo y anomalías del reporte de GEMANET: hay que decidirlos a mano.",
        "Están en GEMANET y el anexo no los trae.",
    ]

    with pestanas[0]:
        if datos["txt"]:
            st.code("\n".join(datos["txt"].decode("ascii").split("\r\n")[:30]), language="text")
            st.caption("Primeras 30 líneas, tal como quedan en el archivo.")
        else:
            st.info("Sin líneas para cargar.")

    for pestana, (filas, nombre), mensaje in zip(pestanas[1:], informes[1:], mensajes[1:]):
        with pestana:
            st.caption(mensaje)
            if not filas:
                st.success("Nada por aquí.")
                continue
            _mostrar(filas)
            st.download_button(
                "Descargar en Excel",
                data=create_excel_download(_tabla(filas), nombre[:30]),
                file_name=f"{datos['nombre']}_{nombre}.xlsx",
                mime=HOJA_EXCEL,
                key=f"descarga_{nombre}",
            )


render()
