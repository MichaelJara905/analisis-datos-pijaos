"""Consulta de documentos: una pestaña por documento de referencia.

Circular 022, Trazabilidad 2706, Listado CUM (INVIMA) y SuperHomologador.
Cada pestaña carga solo su archivo y responde su pregunta específica.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from src.app.application import consulta_service, referencias_service
from src.app.components.layout import render_header
from src.app.core.config import get_config
from src.app.infrastructure.referencias import repositorio
from src.app.infrastructure.referencias.repositorio import ReferenciaNoDisponible

# La caché queda en una carpeta local del proyecto, no junto a los
# originales (que suelen estar en el Drive).
repositorio.DIRECTORIO_CACHE = Path(".cache_referencias")


def _pesos(valor, decimales: int = 0) -> str:
    if valor is None or valor == "":
        return "-"
    texto = f"{float(valor):,.{decimales}f}"
    return "$" + texto.replace(",", "X").replace(".", ",").replace("X", ".")


def _tabla(filas: list[dict]) -> None:
    if filas:
        st.dataframe(
            [{k: "" if v is None else str(v) for k, v in f.items()} for f in filas],
            width="stretch",
            hide_index=True,
        )


# ============================================================
# CARGA (una vez por archivo y versión)
# ============================================================

@st.cache_resource(show_spinner=False)
def _cargar_circular(carpeta: str, firma: tuple):
    return consulta_service.cargar_circular(carpeta)


@st.cache_resource(show_spinner=False)
def _cargar_trazabilidad(carpeta: str, firma: tuple):
    return consulta_service.cargar_trazabilidad(carpeta)


@st.cache_resource(show_spinner=False)
def _cargar_listado(carpeta: str, firma: tuple):
    return consulta_service.cargar_listado(carpeta)


@st.cache_resource(show_spinner=False)
def _cargar_superhomologador(carpeta: str, firma: tuple):
    return consulta_service.cargar_superhomologador(carpeta)


CARGADORES = {
    "circular": (_cargar_circular, "Leyendo la Circular 022..."),
    "trazabilidad": (_cargar_trazabilidad, "Leyendo la trazabilidad 2706..."),
    "listado_cum": (_cargar_listado, "Leyendo el Listado CUM (la primera vez tarda)..."),
    "superhomologador": (_cargar_superhomologador, "Leyendo el SuperHomologador..."),
}


def _documento(carpeta: str, nombre: str):
    """Carga un documento; si falta, lo dice y devuelve None."""

    cargador, mensaje = CARGADORES[nombre]
    try:
        firma = consulta_service.firma_de_fuente(carpeta, nombre)
        with st.spinner(mensaje):
            return cargador(carpeta, firma)
    except ReferenciaNoDisponible as error:
        st.error(str(error))
    except (OSError, ValueError, KeyError) as error:
        st.error(f"No se pudo leer el archivo: {error}")
    return None


# ============================================================
# PESTAÑAS
# ============================================================

def _pestana_circular(carpeta: str) -> None:
    st.caption(
        "Tope que no puede superar la IPS: PMV de la presentación + margen IPS, "
        "dividido por la unidad mínima de dispensación (columna amarilla del libro)."
    )
    circular = _documento(carpeta, "circular")
    if circular is None:
        return

    st.caption(f"Archivo: {circular.archivo}")
    texto = st.text_input(
        "CUM o nombre del medicamento",
        placeholder="20081132-1  ·  triumeq  ·  imatinib",
        key="consulta_circular_texto",
    )
    if not texto.strip():
        return

    fichas = consulta_service.consultar_circular(circular, texto)
    if not fichas:
        st.info(
            "Sin resultados. Si buscas por CUM, debe ser exacto; un medicamento "
            "que no está en la Circular no tiene precio regulado."
        )
        return

    if len(fichas) > 1:
        st.caption(f"{len(fichas)} coincidencias. Elige una para ver el detalle.")
        _tabla(
            [
                {"CUM": f["cum"], "Medicamento": f["medicamento"], "Tope por unidad": _pesos(f["tope"], 2)}
                for f in fichas
            ]
        )
        elegido = st.selectbox("Detalle de", [f["cum"] for f in fichas], key="consulta_circular_elegido")
        ficha = next(f for f in fichas if f["cum"] == elegido)
    else:
        ficha = fichas[0]

    st.markdown(f"**{ficha['medicamento']}**")
    columnas = st.columns(3)
    columnas[0].metric("TOPE a parametrizar (por unidad)", _pesos(ficha["tope"], 2))
    columnas[1].metric("PMV por unidad (sin margen)", _pesos(ficha["pmv_por_umd"], 2))
    columnas[2].metric("Margen IPS por unidad", _pesos(ficha["margen_por_umd"], 2))

    detalle = {
        "CUM": ficha["cum"],
        "Mercado relevante": ficha["mercado"],
        "Unidad de medida": ficha["unidad_medida"],
        "Unidades por presentación": ficha["umd_presentacion"],
        "PMV presentación completa": _pesos(ficha["pmv_presentacion"]),
        "% margen IPS aplicado": "-" if ficha["porcentaje_margen"] is None else f"{ficha['porcentaje_margen']}%",
        "Criterio": ficha["criterio"],
        "Fundamento": ficha["fundamento"],
        "Circular": ficha["circular"],
        "Inicio de vigencia": ficha["vigencia"],
    }
    _tabla([detalle])

    if ficha["alerta"]:
        st.warning(f"Alerta de revisión: {ficha['alerta']}")

    st.markdown("**Verificar un valor**")
    oferta = st.number_input(
        "Valor por unidad ofrecido",
        min_value=0.0,
        value=0.0,
        step=1.0,
        key="consulta_circular_oferta",
    )
    if oferta > 0:
        veredicto = consulta_service.evaluar_valor(ficha["tope"], oferta)
        if veredicto["estado"] == "SUPERA EL TOPE":
            st.error(
                f"SUPERA EL TOPE por {_pesos(veredicto['diferencia'], 2)} "
                f"({veredicto['porcentaje']}%). GEMANET lo rechaza como valor regulado."
            )
        elif veredicto["estado"] == "DENTRO DEL TOPE":
            st.success("Dentro del tope. Los porcentajes son 'hasta': un valor menor es válido.")
        else:
            st.info("No hay tope para comparar.")

    st.caption(
        "Libro de apoyo derivado de la Circular 022 de 2026: no sustituye el texto oficial. "
        "Verifica kits, combos y multidosis."
    )


def _pestana_trazabilidad(carpeta: str) -> None:
    st.caption(
        "Un CUPS que no está en la Resolución 2706 (vigencia 2026) no se puede "
        "autorizar ni parametrizar."
    )
    trazabilidad = _documento(carpeta, "trazabilidad")
    if trazabilidad is None:
        return

    st.caption(f"Archivo: {trazabilidad.archivo} · {len(trazabilidad.vigentes):,} CUPS vigentes".replace(",", "."))
    texto = st.text_input(
        "Código CUPS (nuevo o anterior) o descripción",
        placeholder="441302  ·  129M01  ·  esofagogastroduodenoscopia",
        key="consulta_traza_texto",
    )
    if not texto.strip():
        return

    resultado = consulta_service.consultar_trazabilidad(trazabilidad, texto)

    if resultado["modo"] == "texto":
        if not resultado["coincidencias"]:
            st.info("Sin coincidencias.")
            return
        _tabla(
            [
                {"Código": c["codigo"], "Estado": c["estado"], "Descripción": c["descripcion"]}
                for c in resultado["coincidencias"]
            ]
        )
        st.caption("Escribe el código completo para ver el detalle.")
        return

    ficha = resultado["ficha"]
    if ficha["puede_autorizarse"]:
        st.success(f"{ficha['codigo']}: {ficha['estado']} — se puede autorizar y parametrizar.")
    elif ficha["estado"] == consulta_service.ESTADO_NO_VIGENTE:
        st.error(f"{ficha['codigo']}: ya no existe con este código — no se puede autorizar ni parametrizar.")
    else:
        st.error(f"{ficha['codigo']}: {ficha['estado']} — no se puede autorizar ni parametrizar.")

    if ficha["descripcion"]:
        st.markdown(f"**{ficha['descripcion']}**")
    if ficha["trazabilidad"]:
        st.caption(
            f"Trazabilidad {ficha['trazabilidad']}: "
            f"{ficha['significado'] or 'ver la hoja Convenciones del libro'}"
        )
    if ficha["viene_de"]:
        st.info(f"Reemplaza al código anterior: {', '.join(ficha['viene_de'])}")
    if ficha["reemplazos"]:
        st.markdown("**Reemplazo en la Resolución 2706**")
        _tabla(
            [
                {"Código nuevo": r["codigo"], "Descripción": r["descripcion"], "Trazabilidad": r["trazabilidad"]}
                for r in ficha["reemplazos"]
            ]
        )
    elif ficha["estado"] == consulta_service.ESTADO_NO_VIGENTE:
        st.warning("El libro no indica un código nuevo: el procedimiento se eliminó o se agrupó.")


def _pestana_listado(carpeta: str) -> None:
    st.caption(
        "Listado único de medicamentos vigentes del INVIMA. Sin registro en el "
        "listado, el medicamento se considera inactivo."
    )
    listado = _documento(carpeta, "listado_cum")
    if listado is None:
        return

    st.caption(f"Archivo: {listado.archivo} · {listado.generado or 'sin fecha de generación'}")
    texto = st.text_input(
        "CUM, expediente, producto, principio activo, titular o ATC",
        placeholder="20097544-1  ·  20097544  ·  tadalafilo  ·  G04BE08",
        key="consulta_listado_texto",
    )
    if not texto.strip():
        return

    resultado = consulta_service.consultar_listado(listado, texto)
    fichas = resultado["fichas"]
    if not fichas:
        st.info("Sin coincidencias.")
        return

    if len(fichas) > 1:
        st.caption(f"{len(fichas)} coincidencias (máximo {consulta_service.LIMITE_DE_RESULTADOS}).")
        _tabla(
            [
                {
                    "CUM": f["cum"],
                    "Estado": f["estado"],
                    "Producto": f.get("producto", ""),
                    "Principio activo": f.get("principio_activo", ""),
                    "Titular": f.get("titular", ""),
                }
                for f in fichas
            ]
        )
        elegido = st.selectbox("Detalle de", [f["cum"] for f in fichas], key="consulta_listado_elegido")
        ficha = next(f for f in fichas if f["cum"] == elegido)
    else:
        ficha = fichas[0]

    if ficha["estado"] == consulta_service.ESTADO_ACTIVO:
        st.success(f"{ficha['cum']}: ACTIVO")
    else:
        st.error(f"{ficha['cum']}: {ficha['estado']}")

    if ficha.get("nota"):
        st.info(ficha["nota"])
        return

    if ficha["registro_vencido"]:
        st.warning(
            f"La fecha de vencimiento del registro ({ficha['fecha_vencimiento']}) ya pasó, "
            "aunque el listado aún lo muestra vigente."
        )

    _tabla(
        [
            {
                "Producto": ficha["producto"],
                "Descripción comercial": ficha["descripcion_comercial"],
                "Principio activo": ficha["principio_activo"],
                "Concentración": ficha["concentracion"],
                "Forma": ficha["forma"],
                "Vía": ficha["via"],
                "ATC": ficha["atc"],
                "Titular": ficha["titular"],
                "Registro sanitario": ficha["registro_sanitario"],
                "Estado del registro": ficha["estado_registro"],
                "Expedición": ficha["fecha_expedicion"],
                "Vencimiento": ficha["fecha_vencimiento"],
                "Activo desde": ficha["fecha_activo"],
                "Inactivo desde": ficha["fecha_inactivo"],
                "Muestra médica": ficha["muestra_medica"],
                "IUM": ficha["ium"],
            }
        ]
    )

    if resultado["mismo_expediente"]:
        st.markdown("**Otras presentaciones del mismo expediente**")
        _tabla(
            [
                {"CUM": f["cum"], "Estado": f["estado"], "Descripción": f["descripcion"]}
                for f in resultado["mismo_expediente"]
            ]
        )


def _pestana_superhomologador(carpeta: str) -> None:
    st.caption(
        "Homólogo SOAT de cada CUPS y su tarifa en UVB, UVT y UVR. El valor del manual "
        "va sin el descuento que la hoja trae incorporado."
    )
    referencias = _documento(carpeta, "superhomologador")
    if referencias is None:
        return

    unidades = ", ".join(
        f"{sigla} {_pesos(manual.unidad)}" for sigla, manual in referencias.manuales.items()
    )
    st.caption(f"Unidades del año: {unidades}")

    columnas = st.columns([3, 1])
    texto = columnas[0].text_input(
        "CUPS, código SOAT o descripción",
        placeholder="441302  ·  18300  ·  esofagogastroduodenoscopia",
        key="consulta_super_texto",
    )
    porcentaje = columnas[1].number_input(
        "% descuento",
        min_value=-100,
        max_value=100,
        value=0,
        key="consulta_super_pct",
        help="Simula el descuento pactado sobre el valor del manual.",
    )
    if not texto.strip():
        return

    resultados = consulta_service.buscar_homologador(referencias, texto)
    if not resultados:
        st.warning(
            "Sin coincidencias. Si el CUPS no está en el homologador y su tarifa es "
            "regulada, el código ley hay que confirmarlo."
        )
        return

    cups = sorted({f["cups"] for f in resultados})
    if len(cups) > 1:
        st.caption(f"{len(resultados)} coincidencias.")
        _tabla(
            [
                {
                    "CUPS": f["cups"],
                    "Código SOAT": f["codigo_ley"],
                    "Descripción": f.get("descripcion", ""),
                    "Cobertura": f.get("cobertura", ""),
                }
                for f in resultados
            ]
        )
        elegido = st.selectbox("Detalle de", cups, key="consulta_super_elegido")
    else:
        elegido = cups[0]

    ficha = referencias_service.consultar_servicio(referencias, elegido, porcentaje=int(porcentaje))
    st.markdown(f"**CUPS {elegido}**")
    if ficha["ambiguo"]:
        st.warning("Este CUPS tiene más de un código SOAT. El sistema no elige: hay que definir cuál aplica.")
    _tabla(
        [
            {"Código SOAT": h["codigo_ley"], "Descripción SOAT": h.get("descripcion_ley", ""),
             "Descripción CUPS": h.get("descripcion", ""), "Cobertura": h.get("cobertura", "")}
            for h in ficha["homologos"]
        ]
    )

    if ficha["tarifas"]:
        st.markdown("**Tarifa por manual**")
        _tabla(
            [
                {
                    "Manual": t["manual"],
                    "Código SOAT": t["codigo_ley"],
                    "Puntaje": t["puntaje"],
                    "Valor del manual (sin descuento)": _pesos(t["valor_manual"]),
                    f"Con {t['porcentaje']}%": _pesos(t["valor_con_descuento"]),
                    "Valor que muestra la hoja": _pesos(t["valor_hoja"]),
                }
                for t in ficha["tarifas"]
            ]
        )
        st.caption(
            "El manual redondea a la centena; el TXT del cargue va al peso. "
            "La hoja UVT trae un -8% incorporado: aquí se informa aparte."
        )


# ============================================================
# PÁGINA
# ============================================================

def render() -> None:
    render_header(
        title="Consulta de documentos",
        subtitle="Circular 022, Trazabilidad 2706, Listado CUM y SuperHomologador.",
    )
    st.title("Consulta de documentos")

    columnas = st.columns([4, 1])
    carpeta = columnas[0].text_input(
        "Carpeta con los documentos",
        value=str(getattr(get_config(), "referencias_path", "referencias")),
        help="Cada archivo se reconoce por su nombre. Si cambia un archivo, se vuelve a leer solo.",
    )
    columnas[1].write("")
    if columnas[1].button("Actualizar", help="Vuelve a leer los archivos desde la carpeta."):
        st.cache_resource.clear()

    try:
        estado = consulta_service.estado_de_fuentes(carpeta)
    except ReferenciaNoDisponible as error:
        st.error(str(error))
        return

    tarjetas = st.columns(len(estado))
    for tarjeta, datos in zip(tarjetas, estado.values()):
        if datos["archivo"]:
            tarjeta.success(f"{datos['etiqueta']}\n\n{datos['archivo']}\n\nModificado: {datos['modificado']}")
        else:
            tarjeta.warning(f"{datos['etiqueta']}: no encontrado")

    pestanas = st.tabs(
        ["Circular 022", "Trazabilidad 2706", "Listado CUM", "SuperHomologador"]
    )
    with pestanas[0]:
        _pestana_circular(carpeta)
    with pestanas[1]:
        _pestana_trazabilidad(carpeta)
    with pestanas[2]:
        _pestana_listado(carpeta)
    with pestanas[3]:
        _pestana_superhomologador(carpeta)


render()
