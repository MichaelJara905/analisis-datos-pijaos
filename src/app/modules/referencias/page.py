"""Consulta de las tres fuentes de referencia desde una sola pantalla.

Evita tener que abrir el SUPERHOMOLOGADOR, la Circular 022 y Máximos y
Mínimos a mano cada vez que hay que revisar un código.
"""

from __future__ import annotations

import polars as pl
import streamlit as st

from src.app.application import referencias_service
from src.app.components.layout import render_header
from src.app.core.config import get_config
from src.app.domain.cargues import rules
from src.app.infrastructure.referencias.repositorio import ReferenciaNoDisponible

TIPOS = {
    "Servicio (CUPS)": rules.CARGUE_CUPS,
    "Medicamento (CUM)": rules.CARGUE_CUMS,
    "Insumo": rules.CARGUE_INS,
}


@st.cache_resource(show_spinner=False)
def cargar(carpeta: str) -> referencias_service.Referencias:
    """Carga las fuentes una vez por sesión del servidor.

    La primera lectura tarda (son más de 300.000 filas entre los tres
    archivos); después queda en memoria y en caché de disco.
    """

    return referencias_service.cargar_referencias(carpeta)


def _tabla(filas: list[dict]) -> None:
    if not filas:
        return
    st.dataframe(
        pl.DataFrame(
            [
                {k: "" if v is None else str(v) for k, v in fila.items()}
                for fila in filas
            ]
        ).to_pandas(),
        use_container_width=True,
        hide_index=True,
    )


def _pesos(valor) -> str:
    return "-" if valor is None else f"${valor:,.0f}".replace(",", ".")


# ============================================================
# SECCIONES
# ============================================================

def render() -> None:
    render_header(
        title="Consulta de referencias",
        subtitle="Superhomologador, Circular 022 y Máximos y Mínimos en un solo sitio.",
    )
    st.title("Consulta de referencias")

    carpeta = st.text_input(
        "Carpeta de los archivos de referencia",
        value=str(getattr(get_config(), "referencias_path", "referencias")),
        help=(
            "Debe contener el SUPERHOMOLOGADOR, la Circular 022 y Máximos y "
            "Mínimos. Se reconocen por el nombre del archivo."
        ),
    )

    try:
        with st.spinner("Cargando fuentes de referencia..."):
            referencias = cargar(carpeta)
    except ReferenciaNoDisponible as error:
        st.error(str(error))
        return

    render_estado(referencias)
    render_consulta(referencias)
    render_busqueda(referencias)


def render_estado(referencias: referencias_service.Referencias) -> None:
    disponibles = referencias.disponibles()
    etiquetas = {
        "superhomologador": "Superhomologador",
        "circular": "Circular 022",
        "maximos": "Máximos y Mínimos",
    }

    columnas = st.columns(3)
    for columna, (clave, etiqueta) in zip(columnas, etiquetas.items()):
        if disponibles[clave]:
            columna.success(f"{etiqueta}: cargado")
        else:
            columna.warning(f"{etiqueta}: no encontrado")

    if referencias.manuales:
        unidades = ", ".join(
            f"{sigla} {manual.unidad:,.0f}".replace(",", ".")
            for sigla, manual in referencias.manuales.items()
        )
        st.caption(f"Unidades del año: {unidades}")

    st.caption(
        "Máximos y Mínimos llega hasta la vigencia 2024 y tiene datos "
        "sucios: úsalo como referencia, no como regla."
    )


def render_consulta(referencias: referencias_service.Referencias) -> None:
    st.subheader("Consultar un código")

    columnas = st.columns([2, 2, 1])
    etiqueta = columnas[0].selectbox("Tipo", list(TIPOS))
    codigo = columnas[1].text_input("Código", placeholder="441302")
    porcentaje = columnas[2].number_input(
        "% descuento",
        min_value=-100,
        max_value=100,
        value=0,
        help="Simula el descuento pactado sobre la tarifa regulada.",
    )

    if not codigo:
        st.info("Escribe un código para consultarlo.")
        return

    resultado = referencias_service.consultar(
        referencias,
        codigo,
        TIPOS[etiqueta],
        porcentaje=int(porcentaje),
    )

    if TIPOS[etiqueta] == rules.CARGUE_CUPS:
        render_servicio(resultado)
    elif TIPOS[etiqueta] == rules.CARGUE_CUMS:
        render_medicamento(resultado)
    else:
        st.info(resultado["nota"])

    render_historico(resultado["historico"])


def render_servicio(resultado: dict) -> None:
    homologos = resultado["homologos"]

    if not homologos:
        st.warning(
            "El CUPS no está en el homologador. Si su tarifa es regulada, "
            "el código ley hay que confirmarlo con contratación."
        )
    else:
        if resultado["ambiguo"]:
            st.warning(
                "Este CUPS tiene más de un código ley. El sistema no elige: "
                "hay que definir cuál aplica."
            )
        _tabla(homologos)

    if resultado["tarifas"]:
        st.markdown("**Tarifa por manual**")
        _tabla(
            [
                {
                    "Manual": t["manual"],
                    "Código ley": t["codigo_ley"],
                    "Puntaje": t["puntaje"],
                    "Unidad del año": _pesos(t["unidad"]),
                    "Valor del manual": _pesos(t["valor_manual"]),
                    f"Con {t['porcentaje']}%": _pesos(t["valor_con_descuento"]),
                }
                for t in resultado["tarifas"]
            ]
        )
        st.caption(
            "El manual redondea a la centena; el TXT del cargue va al peso."
        )


def render_medicamento(resultado: dict) -> None:
    regulado = resultado["regulado"]

    if regulado is None:
        st.info(
            "El medicamento no aparece en la Circular 022, así que no tiene "
            "precio regulado: se carga como tarifa propia."
        )
        return

    st.markdown(f"**{regulado['medicamento']}**")

    columnas = st.columns(3)
    columnas[0].metric("Precio por unidad", _pesos(regulado["precio_unidad"]))
    columnas[1].metric("Margen IPS", _pesos(regulado["margen_unidad"]))
    columnas[2].metric("Costo total", _pesos(regulado["costo_total_unidad"]))

    st.caption(
        f"Unidad: {regulado['unidad_medida']} · {regulado['circular']} · "
        f"vigencia {regulado['vigencia']}. La hoja de precio por unidad es "
        "derivada: verifica kits, combos y multidosis contra el texto oficial."
    )


def render_historico(historico: list[dict]) -> None:
    st.markdown("**Rango histórico del sistema**")

    if not historico:
        st.info("El código no tiene historial registrado.")
        return

    for fila in historico:
        columnas = st.columns(4)
        columnas[0].metric(f"Mínimo ({fila['tipo']})", _pesos(fila["minimo"]))
        columnas[1].metric("Máximo", _pesos(fila["maximo"]))
        columnas[2].metric("Promedio", _pesos(fila["promedio"]))
        columnas[3].metric("Promedio + incremento", _pesos(fila["promedio_incremento"]))


def render_busqueda(referencias: referencias_service.Referencias) -> None:
    st.subheader("Buscar por descripción")
    st.caption(
        "Para cuando no se tiene el código. Los insumos no tienen una fuente "
        "con descripciones, así que solo se buscan servicios y medicamentos."
    )

    columnas = st.columns([1, 3])
    etiqueta = columnas[0].selectbox(
        "Buscar en",
        ["Servicio (CUPS)", "Medicamento (CUM)"],
        key="referencias_tipo_busqueda",
    )
    texto = columnas[1].text_input(
        "Descripción",
        placeholder="esofagogastroduodenoscopia",
        key="referencias_texto",
    )

    if len(texto.strip()) < 3:
        return

    resultados = referencias_service.buscar_por_texto(
        referencias,
        texto,
        TIPOS[etiqueta],
    )

    if not resultados:
        st.info("Sin coincidencias.")
        return

    st.caption(f"{len(resultados)} coincidencias (máximo 25).")
    _tabla(resultados)


render()
