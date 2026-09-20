import plotly.express as px
import polars as pl
import streamlit as st

from src.app.components.layout import render_header
from src.app.application.tarifas_service import (
    analyze_descriptions,
    compare_sources,
    create_excel_download,
    create_template,
    duplicate_codes,
    find_description_matches,
    get_tariff_metrics,
    load_excel,
    normalize_description_column,
    pivot_sources,
)


@st.cache_data(show_spinner=False)
def cached_description_matches(
    source_a: pl.DataFrame,
    source_b: pl.DataFrame,
    threshold: float,
    limit_per_description: int,
) -> pl.DataFrame:
    """Cachea el cálculo costoso entre reruns con los mismos archivos."""

    return find_description_matches(
        source_a,
        source_b,
        threshold=threshold,
        limit_per_description=limit_per_description,
    )


@st.cache_data(show_spinner=False)
def cached_load_excel(data: bytes, filename: str) -> pl.DataFrame:
    """Cachea la carga del Excel para no releer el archivo en cada rerun."""

    from io import BytesIO

    return load_excel(BytesIO(data))


def _load_source(file) -> pl.DataFrame | None:
    """Carga un archivo Excel usando caché y guardándolo en sesión."""

    if file is None:
        return None
    data = file.getvalue()
    return cached_load_excel(data, file.name)


def render() -> None:
    """Renderiza el módulo de control y saneamiento de tarifas."""

    render_header(
        title="Análisis de Tarifas",
        subtitle="Valida, cruza y prepara información de servicios para carga.",
    )
    st.title("Análisis de Tarifas")
    st.write(
        "Usa la plantilla con las columnas `codigo_servicio`, `descripcion` y "
        "`valor_servicio`. El código se trata como texto para no perder ceros iniciales."
    )

    st.download_button(
        "Descargar plantilla Excel",
        data=create_template(),
        file_name="plantilla_tarifas.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
    )

    source_a_file = st.file_uploader(
        "Fuente A (obligatoria)", type=["xlsx", "xls"], key="tarifas_source_a"
    )
    source_b_file = st.file_uploader(
        "Fuente B (opcional para cruce)", type=["xlsx", "xls"], key="tarifas_source_b"
    )

    if source_a_file is None:
        st.info("Descarga la plantilla, diligénciala y cárgala como Fuente A para comenzar.")
        return

    # Se carga la fuente una única vez y se conserva en sesión para no
    # recomputar en cada interacción. La carga es barata (cacheada), pero
    # el análisis derivado se ejecuta solo cuando el usuario lo pide.
    try:
        source_a = _load_source(source_a_file)
        source_b = _load_source(source_b_file)
    except (ValueError, RuntimeError) as exc:
        st.error(f"No fue posible procesar el archivo: {exc}")
        return

    if source_a.is_empty():
        st.warning("La Fuente A no contiene registros.")
        return

    reset_if_source_changed(source_a_file, source_b_file)

    render_welcome()
    render_quality_overview(source_a)
    render_source_analysis(source_a)

    if source_b is not None:
        render_comparison(source_a, source_b)

    render_sanitization(source_a)


def reset_if_source_changed(source_a_file, source_b_file) -> None:
    """Limpia los resultados derivados cuando cambian los archivos cargados."""

    signature = (
        f"{source_a_file.name}:{source_a_file.size}:"
        + (f"{source_b_file.name}:{source_b_file.size}" if source_b_file else "none")
    )
    if st.session_state.get("tarifas_source_signature") != signature:
        st.session_state["tarifas_source_signature"] = signature
        for key in [
            "tarifas_metrics",
            "tarifas_source_analysis",
            "tarifas_source_duplicates",
            "tarifas_sanitized",
            "tarifas_comparison",
            "tarifas_match_column",
            "tarifas_join",
            "tarifas_scope",
            "tarifas_tolerance",
        ]:
            st.session_state.pop(key, None)
        for key in list(st.session_state.keys()):
            if key.startswith("pivot_"):
                st.session_state.pop(key, None)


def render_welcome() -> None:
    """Muestra las acciones disponibles antes de ejecutar ningún cálculo."""

    with st.container(border=True):
        st.markdown("**Acciones disponibles**")
        st.caption(
            "Los cálculos se ejecutan únicamente al pulsar cada botón, con indicador "
            "de progreso. Esto evita recargar el módulo completo en cada interacción."
        )


def render_quality_overview(df: pl.DataFrame) -> None:
    st.subheader("Indicadores de calidad")

    if st.button(
        "Analizar calidad de la Fuente A",
        key="run_quality",
        type="secondary",
        use_container_width=True,
    ):
        with st.spinner("Analizando indicadores de calidad..."):
            metrics = get_tariff_metrics(df)
            st.session_state["tarifas_metrics"] = metrics

    metrics = st.session_state.get("tarifas_metrics")
    if metrics is None:
        st.info("Pulsa el botón para calcular los indicadores de calidad.")
        return

    cards = st.columns(6)
    labels = [
        ("Registros", "rows"),
        ("Códigos únicos", "unique_codes"),
        ("Filas duplicadas", "duplicate_rows"),
        ("Códigos vacíos", "missing_codes"),
        ("Descripciones vacías", "missing_descriptions"),
        ("Valores inválidos", "invalid_values"),
    ]
    for card, (label, key) in zip(cards, labels):
        card.metric(label, f"{metrics[key]:,}")

    chart_data = pl.DataFrame(
        {"Indicador": ["Válidos", "Con problemas"], "Registros": [
            max(df.height - metrics["duplicate_rows"] - metrics["invalid_values"], 0),
            metrics["duplicate_rows"] + metrics["invalid_values"],
        ]}
    )
    fig = px.bar(chart_data.to_pandas(), x="Indicador", y="Registros", color="Indicador")
    fig.update_layout(height=300, margin={"l": 20, "r": 20, "t": 30, "b": 20}, showlegend=False)
    st.plotly_chart(fig, use_container_width=True)


def render_source_analysis(df: pl.DataFrame) -> None:
    st.subheader("Revisión de la Fuente A")

    run = st.button(
        "Analizar estructura y descripciones",
        key="run_source_analysis",
        type="secondary",
        use_container_width=True,
    )
    if run:
        with st.spinner("Revisando datos, duplicados y descripciones..."):
            analyzed = analyze_descriptions(df)
            duplicates = duplicate_codes(df)
        st.session_state["tarifas_source_analysis"] = analyzed
        st.session_state["tarifas_source_duplicates"] = duplicates

    analyzed = st.session_state.get("tarifas_source_analysis")
    if analyzed is None:
        st.info("Pulsa el botón para revisar los datos de la Fuente A.")
        return
    duplicates = st.session_state.get("tarifas_source_duplicates")

    tab_data, tab_duplicates, tab_descriptions = st.tabs(
        ["Datos", "Códigos duplicados", "Descripciones"]
    )
    with tab_data:
        st.dataframe(df.to_pandas(), use_container_width=True, hide_index=True)
    with tab_duplicates:
        if duplicates is not None and not duplicates.is_empty():
            st.warning(f"Se encontraron {duplicates.height:,} filas con códigos repetidos.")
            st.dataframe(duplicates.to_pandas(), use_container_width=True, hide_index=True)
        else:
            st.success("No se encontraron códigos duplicados.")
    with tab_descriptions:
        flagged = analyzed.filter(
            pl.col("descripcion_vacia") | pl.col("tiene_simbolos_no_permitidos")
        )
        st.caption("Se marcan tildes, caracteres especiales, descripciones vacías y cambios de formato.")
        if flagged.is_empty():
            st.success("Las descripciones no presentan hallazgos.")
        else:
            st.warning(f"{flagged.height:,} descripciones requieren revisión.")
            st.dataframe(
                flagged.select([
                    "codigo_servicio", "descripcion", "descripcion_normalizada",
                    "descripcion_vacia", "tiene_simbolos_no_permitidos",
                    "requiere_normalizacion",
                ]).to_pandas(),
                use_container_width=True,
                hide_index=True,
            )


def render_comparison(source_a: pl.DataFrame, source_b: pl.DataFrame) -> None:
    st.subheader("Cruce de fuentes A y B")

    match_options = {
        "Código de servicio": "codigo_servicio",
        "Descripción": "descripcion",
    }

    with st.container(border=True):
        st.markdown("**Configuración del cruce**")
        match_label = st.selectbox("Campo para cruzar", list(match_options))
        fuzzy_description = False
        threshold = 0.8
        limit_per_description = 10

        if match_options[match_label] == "descripcion":
            fuzzy_description = st.checkbox(
                "Buscar descripciones similares",
                help="Compara las descripciones aun cuando no sean idénticas.",
            )
            if fuzzy_description:
                threshold = st.slider(
                    "Similitud mínima (%)", min_value=50, max_value=100, value=80
                ) / 100
                limit_per_description = st.number_input(
                    "Máximo por descripción", min_value=1, max_value=100, value=10
                )
            if st.button(
                "Buscar coincidencias",
                key="run_fuzzy",
                type="primary",
                use_container_width=True,
            ):
                render_fuzzy_comparison(source_a, source_b, threshold, limit_per_description)
            else:
                st.info("Configura la búsqueda y pulsa «Buscar coincidencias».")
            return

        if st.button(
            "Ejecutar cruce",
            key="run_cross",
            type="primary",
            use_container_width=True,
        ):
            st.session_state["tarifas_match_column"] = match_options[match_label]
            st.session_state.pop("tarifas_comparison", None)
            st.session_state["tarifas_join"] = "full"
            st.session_state["tarifas_scope"] = "todos"
            st.session_state["tarifas_tolerance"] = 0.0

    # Si aún no se ejecutó el cruce con este campo, se muestra el aviso.
    if st.session_state.get("tarifas_match_column") != match_options[match_label]:
        st.info("Configura el cruce y pulsa «Ejecutar cruce» para ver los resultados.")
        return

    join_options = {
        "Todos los registros (FULL)": "full",
        "Coincidencias (INNER)": "inner",
        "Conservar todos de A (LEFT)": "left",
        "Conservar todos de B (RIGHT)": "right",
    }
    scope_options = {
        "Valor o descripción": "todos",
        "Solo valor del servicio": "valor_servicio",
        "Solo descripción": "descripcion",
    }

    with st.container(border=True):
        st.markdown("**Unir y filtrar**")
        controls = st.columns(3)
        join_label = controls[0].selectbox(
            "Tipo de cruce",
            list(join_options),
            index=list(join_options.values()).index(
                st.session_state.get("tarifas_join", "full")
            ),
            key="pivot_join",
        )
        scope_label = controls[1].selectbox(
            "Qué considerar diferencia",
            list(scope_options),
            index=list(scope_options.values()).index(
                st.session_state.get("tarifas_scope", "todos")
            ),
            key="pivot_scope",
        )
        tolerance = controls[2].number_input(
            "Tolerancia del valor",
            min_value=0.0,
            value=st.session_state.get("tarifas_tolerance", 0.0),
            step=0.01,
            help="Permite ignorar diferencias pequeñas de precio.",
            key="pivot_tolerance",
        )

    new_join = join_options[join_label]
    new_scope = scope_options[scope_label]
    new_tol = float(tolerance)
    config_changed = (
        new_join != st.session_state.get("tarifas_join", new_join)
        or new_scope != st.session_state.get("tarifas_scope", new_scope)
        or new_tol != st.session_state.get("tarifas_tolerance", new_tol)
    )
    need_recompute = (
        config_changed
        or st.session_state.get("tarifas_comparison") is None
    )
    if config_changed:
        st.session_state["tarifas_join"] = new_join
        st.session_state["tarifas_scope"] = new_scope
        st.session_state["tarifas_tolerance"] = new_tol

    if need_recompute:
        with st.spinner("Cruzando fuentes A y B..."):
            result = compare_sources(
                source_a,
                source_b,
                match_column=match_options[match_label],
                join_type=new_join,
                difference_scope=new_scope,
                value_tolerance=new_tol,
            )
            st.session_state["tarifas_comparison"] = result
    else:
        result = st.session_state["tarifas_comparison"]

    render_cross_metrics(result)
    render_pivot_view(result)


def render_cross_metrics(result: dict[str, pl.DataFrame]) -> None:
    cards = st.columns(4)
    cards[0].metric("Solo en A", result["only_a"].height)
    cards[1].metric("Solo en B", result["only_b"].height)
    cards[2].metric("Diferencias", result["differences"].height)
    cards[3].metric("Duplicados A/B", result["duplicates_a"].height + result["duplicates_b"].height)


def render_pivot_view(result: dict[str, pl.DataFrame]) -> None:
    st.markdown("#### Exploración interactiva del cruce")

    view_options = {
        "Coincidencias (matched)": "matched",
        "Solo en A": "only_a",
        "Solo en B": "only_b",
        "Diferencias": "differences",
        "Duplicados de A": "duplicates_a",
        "Duplicados de B": "duplicates_b",
    }
    view_label = st.selectbox(
        "Conjunto del cruce a explorar",
        list(view_options),
        key="pivot_base_view",
    )
    joined = result[view_options[view_label]]
    available = list(joined.columns)

    with st.container(border=True):
        st.markdown("**Configurar vista pivot**")
        controls = st.columns(2)
        group_cols = controls[0].multiselect(
            "Agrupar por columnas",
            options=available,
            default=[c for c in ("codigo_servicio", "codigo_servicio_b") if c in available],
            key="pivot_group_cols",
        )
        numeric_cols = [c for c in available if joined.schema[c].is_numeric()]
        value_cols = controls[1].multiselect(
            "Sumar valores (numéricas)",
            options=numeric_cols,
            default=[c for c in ("valor_servicio", "valor_servicio_b") if c in numeric_cols],
            key="pivot_value_cols",
        )

    # Filtros por valores: permite reducir el conjunto antes de agrupar.
    filterable = [
        c for c in ("codigo_servicio", "description", "descripcion", "codigo_servicio_b")
        if c in joined.columns
    ]
    for col in filterable[:2]:
        unique_values = sorted(
            joined[col].drop_nulls().unique().cast(pl.String).to_list()
        )
        if not unique_values:
            continue
        selected = st.multiselect(
            f"Filtrar por {col}",
            options=unique_values,
            key=f"pivot_filter_{col}",
        )
        if selected:
            joined = joined.filter(pl.col(col).cast(pl.String).is_in(selected))

    with st.spinner("Construyendo vista pivot..."):
        aggregated = pivot_sources(
            joined,
            group_columns=group_cols,
            value_columns=value_cols,
        )

    visible = st.multiselect(
        "Columnas visibles",
        options=list(aggregated.columns),
        default=list(aggregated.columns),
        key="pivot_visible_cols",
    )
    display = aggregated if not visible else aggregated.select(visible)

    tabs = st.tabs(["Vista pivot", "Detalle del cruce"])
    with tabs[0]:
        if display.is_empty():
            st.info("La vista pivot quedó vacía con la configuración actual.")
        else:
            st.dataframe(display.to_pandas(), use_container_width=True, hide_index=True)
            st.download_button(
                "Descargar vista pivot",
                data=create_excel_download(display, "pivot_cruce"),
                file_name="vista_pivot_cruce.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
    with tabs[1]:
        if joined.is_empty():
            st.success("No se encontraron registros en este conjunto.")
        else:
            st.dataframe(joined.to_pandas(), use_container_width=True, hide_index=True)


def render_fuzzy_comparison(
    source_a: pl.DataFrame,
    source_b: pl.DataFrame,
    threshold: float,
    limit_per_description: int,
) -> None:
    with st.spinner("Buscando descripciones similares..."):
        matches = cached_description_matches(
            source_a,
            source_b,
            threshold,
            limit_per_description,
        )
    metric_columns = st.columns(2)
    metric_columns[0].metric("Coincidencias encontradas", matches.height)
    metric_columns[1].metric("Similitud mínima", f"{threshold:.0%}")
    st.caption(
        "Se usa la descripción normalizada para comparar, pero se muestran los textos originales. "
        "Las coincidencias están ordenadas de mayor a menor similitud."
    )
    if matches.is_empty():
        st.info("No se encontraron descripciones que superen el umbral seleccionado.")
    else:
        st.dataframe(matches.to_pandas(), use_container_width=True, hide_index=True)
        st.download_button(
            "Descargar coincidencias de descripción",
            data=create_excel_download(matches, "coincidencias"),
            file_name="coincidencias_descripcion.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


def render_sanitization(df: pl.DataFrame) -> None:
    st.subheader("Saneamiento y exportación")
    st.caption("La normalización elimina tildes y símbolos no compatibles, compacta espacios y convierte a mayúsculas.")

    if st.button(
        "Sanear y exportar",
        key="run_sanitization",
        type="secondary",
        use_container_width=True,
    ):
        with st.spinner("Saneando descripciones..."):
            sanitized = normalize_description_column(df)
        st.session_state["tarifas_sanitized"] = sanitized

    sanitized = st.session_state.get("tarifas_sanitized")
    if sanitized is None:
        st.info("Pulsa el botón para sanear las descripciones y exportarlas.")
        return

    changed = sanitized.filter(pl.col("descripcion") != df["descripcion"])
    st.metric("Descripciones modificadas", changed.height)
    st.dataframe(
        pl.DataFrame({
            "Original": df["descripcion"].head(20),
            "Normalizada": sanitized["descripcion"].head(20),
        }).to_pandas(),
        use_container_width=True,
        hide_index=True,
    )
    st.download_button(
        "Descargar fuente saneada",
        data=create_excel_download(sanitized, "tarifas_saneadas"),
        file_name="tarifas_saneadas.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


render()
