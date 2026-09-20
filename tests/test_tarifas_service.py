import polars as pl
import pytest

from src.app.application.tarifas_service import (
    compare_sources,
    find_description_matches,
    pivot_sources,
)
from src.app.domain.tarifas.text import (
    normalize_description_for_matching,
    sanitize_text,
)


def tariff_frame(codes: list[str], descriptions: list[str]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "codigo_servicio": codes,
            "descripcion": descriptions,
            "valor_servicio": [100.0] * len(codes),
        }
    )


def test_matches_identical_descriptions() -> None:
    source_a = tariff_frame(["A1"], ["CONSULTA MEDICA GENERAL"])
    source_b = tariff_frame(["B1"], ["CONSULTA MEDICA GENERAL"])

    result = find_description_matches(source_a, source_b)

    assert result.height == 1
    assert result["similitud_porcentaje"][0] == 100.0


def test_token_order_is_supported() -> None:
    source_a = tariff_frame(["A1"], ["CONSULTA MEDICA GENERAL"])
    source_b = tariff_frame(["B1"], ["GENERAL CONSULTA MEDICA"])

    result = find_description_matches(source_a, source_b)

    assert result.height == 1
    assert result["similitud_porcentaje"][0] >= 80.0


def test_different_description_does_not_match() -> None:
    source_a = tariff_frame(["A1"], ["CONSULTA MEDICA GENERAL"])
    source_b = tariff_frame(["B1"], ["CIRUGIA CARDIOVASCULAR"])

    result = find_description_matches(source_a, source_b)

    assert result.is_empty()


def test_threshold_uses_percentage_semantics() -> None:
    source_a = tariff_frame(["A1"], ["CONSULTA MEDICA GENERAL"])
    source_b = tariff_frame(["B1"], ["CONSULTA MEDICA GENERAL EXTRA"])

    result = find_description_matches(source_a, source_b, threshold=0.8)

    assert result.height == 1
    assert result["similitud_porcentaje"][0] >= 80.0


def test_duplicate_descriptions_keep_all_codes_until_limit() -> None:
    source_a = tariff_frame(["A1"], ["CONSULTA MEDICA"])
    source_b = tariff_frame(
        ["B1", "B2", "B3", "B4"],
        ["CONSULTA MEDICA"] * 4,
    )

    result = find_description_matches(source_a, source_b, limit_per_description=3)

    assert result.height == 3
    assert set(result["codigo_servicio_b"].to_list()).issubset(
        {"B1", "B2", "B3", "B4"}
    )


def test_empty_values_and_empty_sources_return_schema() -> None:
    source_a = tariff_frame(["A1", "A2"], [None, "!!!"])
    source_b = tariff_frame(["B1"], [" "])

    result = find_description_matches(source_a, source_b)

    assert result.is_empty()
    assert result.schema == {
        "codigo_servicio_a": pl.String,
        "descripcion_a": pl.String,
        "codigo_servicio_b": pl.String,
        "descripcion_b": pl.String,
        "similitud_porcentaje": pl.Float64,
    }


def test_validates_threshold_and_limit() -> None:
    source = tariff_frame(["A1"], ["CONSULTA"])

    with pytest.raises(ValueError):
        find_description_matches(source, source, threshold=1.1)
    with pytest.raises(ValueError):
        find_description_matches(source, source, limit_per_description=0)


def test_matching_normalization_preserves_measurements() -> None:
    assert sanitize_text("3.3*12 MM") == "3 3 12 MM"
    assert normalize_description_for_matching("3.3*12 MM") == "3.3*12 MM"


@pytest.mark.parametrize(
    "description_b, expected_score",
    [
        ("FRESA DIAMANTADA 3.0 MM", False),
        ("FRESA DIAMANTADA 3.3 MM", True),
        ("FRESA DIAMANTADA 3.5 MM", False),
        ("FRESA DIAMANTADA 9*3.0 MM", False),
        ("FRESA DIAMANTADA 12*3.0 MM", False),
        ("FRESA DIAMANTADA 18*3.0 MM", False),
        ("FRESA FOSFORO DIAMANTADA MI 12*3.5 MM", False),
    ],
)
def test_numeric_measurements_never_get_false_100_percent(
    description_b: str,
    expected_score: bool,
) -> None:
    source_a = tariff_frame(["A1"], ["FRESA DIAMANTADA 3.3 MM"])
    source_b = tariff_frame(["B1"], [description_b])

    result = find_description_matches(source_a, source_b, threshold=0.0)

    assert result.height == 1
    assert (result["similitud_porcentaje"][0] == 100.0) is expected_score


def test_pivot_sources_groups_and_sums_values() -> None:
    source_a = tariff_frame(["A1", "A2"], ["CONSULTA", "URGENCIAS"])
    source_b = tariff_frame(["A1", "B1"], ["CONSULTA", "OTRO"])

    result = compare_sources(source_a, source_b, match_column="codigo_servicio", join_type="full")
    pivot = pivot_sources(result["matched"], group_columns=["codigo_servicio"])

    assert "codigo_servicio" in pivot.columns
    assert "n_codigo_servicio_b" in pivot.columns
    assert "sum_valor_servicio" in pivot.columns
    assert "sum_valor_servicio_b" in pivot.columns
    assert pivot["codigo_servicio"].null_count() >= 1


def test_pivot_default_groups_by_non_numeric_columns() -> None:
    source_a = tariff_frame(["A1"], ["CONSULTA"])
    source_b = tariff_frame(["A1", "B1"], ["CONSULTA", "OTRO"])

    result = compare_sources(source_a, source_b, match_column="codigo_servicio", join_type="full")
    pivot = pivot_sources(result["matched"])

    assert {"codigo_servicio", "descripcion", "codigo_servicio_b", "descripcion_b"} <= set(pivot.columns)


def test_pivot_inner_join_only_keeps_matches() -> None:
    source_a = tariff_frame(["A1", "A2"], ["CONSULTA", "URGENCIAS"])
    source_b = tariff_frame(["A1", "B1"], ["CONSULTA", "OTRO"])

    result = compare_sources(source_a, source_b, match_column="codigo_servicio", join_type="inner")
    pivot = pivot_sources(result["matched"])

    assert pivot["codigo_servicio"].null_count() == 0
    assert "A2" not in pivot["codigo_servicio"].to_list()
