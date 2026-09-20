import plotly.express as px
import polars as pl
import streamlit as st


def render_bar_chart(
    df: pl.DataFrame,
    x: str,
    y: str,
    title: str,
    *,
    color: str | None = None,
    orientation: str = "v",
    height: int = 400,
) -> None:
    """
    Renderiza un gráfico de barras a partir de un DataFrame Polars.

    Parameters
    ----------
    df:
        DataFrame que contiene los datos.

    x:
        Columna para el eje X.

    y:
        Columna para el eje Y.

    title:
        Título del gráfico.

    color:
        Columna opcional para segmentar por color.

    orientation:
        'v' para vertical o 'h' para horizontal.

    height:
        Altura del gráfico en píxeles.
    """

    if df.is_empty():
        st.info("No existen datos para mostrar.")
        return

    required_columns = {x, y}

    if color:
        required_columns.add(color)

    missing_columns = (
        required_columns
        - set(df.columns)
    )

    if missing_columns:
        raise ValueError(
            "Columnas no encontradas: "
            + ", ".join(sorted(missing_columns))
        )

    chart_df = df.to_pandas()

    fig = px.bar(
        chart_df,
        x=x,
        y=y,
        color=color,
        orientation=orientation,
        title=title,
    )

    fig.update_layout(
        height=height,
        margin={
            "l": 20,
            "r": 20,
            "t": 60,
            "b": 20,
        },
        hovermode="x unified",
    )

    st.plotly_chart(
        fig,
        use_container_width=True,
    )
