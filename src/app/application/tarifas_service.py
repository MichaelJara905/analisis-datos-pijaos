"""Casos de uso del análisis de tarifas.

Orquesta: lee con infrastructure, normaliza con domain y devuelve los
DataFrames que la interfaz pinta. No contiene Streamlit.
"""

from __future__ import annotations

import re
from typing import BinaryIO

import polars as pl
from rapidfuzz import fuzz, process

from src.app.domain.tarifas.text import (
    ALLOWED_DESCRIPTION_PATTERN,
    normalize_description_for_matching,
    sanitize_text,
)
from src.app.infrastructure.excel.workbook import (
    REQUIRED_COLUMNS,
    create_excel_download,
    create_template,
    read_template,
)

__all__ = [
    "REQUIRED_COLUMNS",
    "analyze_descriptions",
    "compare_sources",
    "create_excel_download",
    "create_template",
    "duplicate_codes",
    "find_description_matches",
    "get_basic_metrics",
    "get_column_summary",
    "get_tariff_metrics",
    "load_excel",
    "normalize_description_column",
    "normalize_tariff_types",
    "pivot_sources",
    "sanitize_text_column",
]
NUMERIC_TOKEN_PATTERN = re.compile(r"\d+(?:\.\d+)?")


def _extract_numeric_tokens(value: str) -> list[str]:
    """Extrae números normalizados, incluidos decimales y medidas compuestas."""

    return NUMERIC_TOKEN_PATTERN.findall(value)


# ============================================================
# CARGA
# ============================================================

def load_excel(uploaded_file: BinaryIO) -> pl.DataFrame:
    """Carga la plantilla de tarifas y normaliza sus tipos.

    La lectura del archivo vive en infrastructure; aquí solo se aplica la
    regla de negocio: los códigos se tratan como texto para conservar los
    ceros a la izquierda.
    """

    return normalize_tariff_types(read_template(uploaded_file))


def normalize_tariff_types(df: pl.DataFrame) -> pl.DataFrame:
    """Normaliza tipos y espacios sin cambiar el significado de los datos."""

    return df.with_columns(
        pl.col("codigo_servicio").cast(pl.String, strict=False).str.strip_chars(),
        pl.col("descripcion").cast(pl.String, strict=False).str.strip_chars(),
        pl.col("valor_servicio").cast(pl.Float64, strict=False),
    )


# ============================================================
# METRICS
# ============================================================

def get_basic_metrics(
    df: pl.DataFrame,
) -> dict[str, int]:
    """Obtiene indicadores generales del DataFrame."""

    numeric_columns = sum(
        1
        for dtype in df.dtypes
        if dtype.is_numeric()
    )

    text_columns = sum(
        1
        for dtype in df.dtypes
        if dtype == pl.String
    )

    return {
        "rows": df.height,
        "columns": df.width,
        "numeric_columns": numeric_columns,
        "text_columns": text_columns,
    }


def get_tariff_metrics(df: pl.DataFrame) -> dict[str, int | float]:
    """Calcula indicadores orientados al control de tarifas."""

    codes = df.get_column("codigo_servicio")
    descriptions = df.get_column("descripcion")
    values = df.get_column("valor_servicio")
    duplicate_rows = int(codes.len() - codes.n_unique())
    return {
        "rows": df.height,
        "unique_codes": codes.n_unique(),
        "duplicate_rows": max(duplicate_rows, 0),
        "missing_codes": int(codes.is_null().sum() + (codes == "").sum()),
        "missing_descriptions": int(
            descriptions.is_null().sum() + (descriptions == "").sum()
        ),
        "invalid_values": int(values.is_null().sum()),
    }


def duplicate_codes(df: pl.DataFrame) -> pl.DataFrame:
    """Devuelve todos los registros cuyo código aparece más de una vez."""

    counts = df.group_by("codigo_servicio").agg(pl.len().alias("repeticiones"))
    return (
        df.join(counts.filter(pl.col("repeticiones") > 1), on="codigo_servicio")
        .sort("codigo_servicio")
    )


def compare_sources(
    source_a: pl.DataFrame,
    source_b: pl.DataFrame,
    *,
    match_column: str = "codigo_servicio",
    join_type: str = "full",
    difference_scope: str = "todos",
    value_tolerance: float = 0.0,
) -> dict[str, pl.DataFrame]:
    """Cruza dos fuentes con estrategia de unión y criterio configurables."""

    valid_columns = {"codigo_servicio", "descripcion"}
    valid_joins = {"inner", "left", "right", "full"}
    valid_scopes = {"todos", "valor_servicio", "descripcion"}
    if match_column not in valid_columns:
        raise ValueError(f"Campo de cruce no soportado: {match_column}")
    if join_type not in valid_joins:
        raise ValueError(f"Tipo de cruce no soportado: {join_type}")
    if difference_scope not in valid_scopes:
        raise ValueError(f"Criterio de diferencia no soportado: {difference_scope}")

    a = normalize_tariff_types(source_a.select(REQUIRED_COLUMNS))
    b = normalize_tariff_types(source_b.select(REQUIRED_COLUMNS))
    a_keys = a.select(match_column).unique()
    b_keys = b.select(match_column).unique()
    only_a_keys = a_keys.join(b_keys, on=match_column, how="anti")
    only_b_keys = b_keys.join(a_keys, on=match_column, how="anti")
    joined = a.join(b, on=match_column, how="inner", suffix="_b")
    value_difference = (pl.col("valor_servicio") - pl.col("valor_servicio_b")).abs() > value_tolerance
    # La columna usada como clave queda una sola vez en el resultado del join.
    # Por eso no existe `descripcion_b` cuando la descripción es el campo de cruce.
    description_difference = (
        pl.lit(False)
        if match_column == "descripcion"
        else pl.col("descripcion") != pl.col("descripcion_b")
    )
    if difference_scope == "valor_servicio":
        differences = joined.filter(value_difference)
    elif difference_scope == "descripcion":
        differences = joined.filter(description_difference)
    else:
        differences = joined.filter(value_difference | description_difference)

    matched = {
        "inner": joined,
        "left": a.join(b, on=match_column, how="left", suffix="_b"),
        "right": b.join(a, on=match_column, how="left", suffix="_a"),
        "full": a.join(b, on=match_column, how="full", suffix="_b"),
    }[join_type]
    return {
        "only_a": a.filter(pl.col(match_column).is_in(only_a_keys[match_column].implode())),
        "only_b": b.filter(pl.col(match_column).is_in(only_b_keys[match_column].implode())),
        "matched": matched,
        "differences": differences,
        "duplicates_a": duplicate_codes(a),
        "duplicates_b": duplicate_codes(b),
    }


def find_description_matches(
    source_a: pl.DataFrame,
    source_b: pl.DataFrame,
    *,
    threshold: float = 0.8,
    limit_per_description: int = 10,
) -> pl.DataFrame:
    """
    Encuentra las descripciones más similares entre dos fuentes.

    Utiliza RapidFuzz para buscar candidatos sin comparar manualmente
    cada fila de A contra cada fila de B. Las descripciones se normalizan
    una sola vez por fuente.

    ``token_sort_ratio`` conserva las palabras adicionales y los tokens
    numéricos, pero permite que el orden de las palabras no afecte el score.

    Args:
        source_a: Primera fuente.
        source_b: Segunda fuente.
        threshold: Umbral mínimo de similitud entre 0 y 1.
        limit_per_description: Máximo de coincidencias por descripción A.
    """

    if not 0 <= threshold <= 1:
        raise ValueError("El umbral debe estar entre 0 y 1.")
    if limit_per_description <= 0:
        raise ValueError("limit_per_description debe ser mayor que cero.")

    a = (
        normalize_tariff_types(
            source_a.select(REQUIRED_COLUMNS)
        )
        .select(["codigo_servicio", "descripcion"])
        .drop_nulls("descripcion")
        .unique()
    )

    b = (
        normalize_tariff_types(
            source_b.select(REQUIRED_COLUMNS)
        )
        .select(["codigo_servicio", "descripcion"])
        .drop_nulls("descripcion")
        .unique()
    )

    a = a.with_columns(
        pl.col("descripcion")
        .map_elements(normalize_description_for_matching, return_dtype=pl.String)
        .fill_null("")
        .alias("descripcion_normalizada")
    )

    b = b.with_columns(
        pl.col("descripcion")
        .map_elements(normalize_description_for_matching, return_dtype=pl.String)
        .fill_null("")
        .alias("descripcion_normalizada")
    )

    a_records = a.filter(pl.col("descripcion_normalizada") != "").to_dicts()
    b_records = b.filter(pl.col("descripcion_normalizada") != "").to_dicts()
    choices = [row["descripcion_normalizada"] for row in b_records]
    rows: list[dict[str, str | float]] = []
    score_cutoff = threshold * 100

    for row_a in a_records:
        description_a = row_a["descripcion_normalizada"]
        matches = process.extract(
            description_a,
            choices,
            scorer=fuzz.token_sort_ratio,
            score_cutoff=score_cutoff,
            limit=limit_per_description,
        )

        numeric_a = tuple(_extract_numeric_tokens(description_a))
        for matched_description, score, index in matches:
            row_b = b_records[index]
            numeric_b = tuple(_extract_numeric_tokens(matched_description))
            score = float(score)
            if numeric_a != numeric_b:
                # Incluso si el scorer redondeara la similitud a 100, dos
                # medidas distintas nunca deben presentarse como equivalentes.
                score = min(score, 99.99)
            rows.append(
                {
                    "codigo_servicio_a": row_a["codigo_servicio"],
                    "descripcion_a": row_a["descripcion"],
                    "codigo_servicio_b": row_b["codigo_servicio"],
                    "descripcion_b": row_b["descripcion"],
                    "similitud_porcentaje": round(score, 2),
                }
            )

    if not rows:
        return pl.DataFrame(
            schema={
                "codigo_servicio_a": pl.String,
                "descripcion_a": pl.String,
                "codigo_servicio_b": pl.String,
                "descripcion_b": pl.String,
                "similitud_porcentaje": pl.Float64,
            }
        )

    return (
        pl.DataFrame(rows)
        .sort(
            "similitud_porcentaje",
            descending=True,
        )
    )

def pivot_sources(
    joined: pl.DataFrame,
    *,
    group_columns: list[str] | None = None,
    value_columns: list[str] | None = None,
) -> pl.DataFrame:
    """
    Construye una vista pivot a partir de un DataFrame ya cruzado.

    Agrupa el resultado por ``group_columns`` y, para cada columna del
    DataFrame, añade un contador de valores no nulos (``n_<columna>``).
    Las columnas numéricas adicionales de ``value_columns`` se suman
    dentro de cada grupo (``sum_<columna>``).

    Args:
        joined: Resultado del cruce (por ejemplo ``matched`` de
            ``compare_sources``).
        group_columns: Columnas por las que se agrupa. Si no se indica
            usa todas las columnas no numéricas presentes.
        value_columns: Columnas numéricas que se suman en el grupo.

    Returns:
        DataFrame pivotado con las agregaciones solicitadas.
    """

    if group_columns is None:
        group_columns = [
            c for c in joined.columns if not joined.schema[c].is_numeric()
        ]
    valid_group = [c for c in group_columns if c in joined.columns]
    if not valid_group:
        valid_group = ["__total__"]

    if value_columns is None:
        value_columns = [
            c for c in joined.columns if joined.schema[c].is_numeric()
        ]
    valid_values = [c for c in value_columns if c in joined.columns]

    expressions: list[pl.Expr] = [
        pl.col(c).len().alias(f"n_{c}")
        for c in joined.columns
        if c not in valid_group
    ]
    expressions += [
        pl.col(c).sum().alias(f"sum_{c}")
        for c in valid_values
    ]

    return (
        joined.group_by(valid_group)
        .agg(expressions)
        .sort(valid_group)
    )


# ============================================================
# COLUMN SUMMARY
# ============================================================

def get_column_summary(
    df: pl.DataFrame,
) -> pl.DataFrame:
    """
    Genera un resumen básico de las columnas.
    """

    rows = []

    for column in df.columns:

        series = df[column]

        rows.append(
            {
                "Columna": column,
                "Tipo": str(series.dtype),
                "Registros": df.height,
                "Nulos": series.null_count(),
                "Únicos": series.n_unique(),
            }
        )

    return pl.DataFrame(rows)


# ============================================================
# DESCRIPCIONES
# ============================================================

def sanitize_text_column(
    df: pl.DataFrame,
    column_name: str,
) -> pl.DataFrame:
    """
    Sanitiza una columna de texto sin modificar
    el DataFrame original.
    """

    if column_name not in df.columns:
        raise ValueError(
            f"La columna '{column_name}' "
            "no existe."
        )

    if df[column_name].dtype != pl.String:
        raise ValueError(
            f"La columna '{column_name}' "
            "no es de tipo texto."
        )

    return df.with_columns(
        pl.col(column_name)
        .map_elements(
            sanitize_text,
            return_dtype=pl.String,
        )
        .alias(column_name)
    )


def analyze_descriptions(df: pl.DataFrame) -> pl.DataFrame:
    """Marca descripciones vacías, con caracteres no permitidos y normalizables."""

    return df.with_columns(
        pl.col("descripcion").is_null().alias("descripcion_vacia"),
        (~pl.col("descripcion").fill_null("").str.contains(ALLOWED_DESCRIPTION_PATTERN))
        .alias("tiene_simbolos_no_permitidos"),
        pl.col("descripcion")
        .fill_null("")
        .map_elements(sanitize_text, return_dtype=pl.String)
        .alias("descripcion_normalizada"),
    ).with_columns(
        (
            pl.col("descripcion").fill_null("").str.strip_chars() != pl.col("descripcion_normalizada")
        ).alias("requiere_normalizacion")
    )


def normalize_description_column(df: pl.DataFrame) -> pl.DataFrame:
    """Reemplaza la descripción por su versión segura para carga en DB."""

    return df.with_columns(
        pl.col("descripcion")
        .map_elements(sanitize_text, return_dtype=pl.String)
        .alias("descripcion")
    )
