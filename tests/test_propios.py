"""Pruebas de la creación de propios y de los candidatos a propio."""

from __future__ import annotations

import pytest
from openpyxl import Workbook

from src.app.application import cargues_service, cli_propios, propios_service
from src.app.domain.cargues import propios, rules
from src.app.domain.cargues.propios import SolicitudPropio
from src.app.infrastructure.excel.propios import (
    LecturaPropiosFallida,
    leer_solicitudes,
)


def _sol(fila, nombre, valor, cups):
    return SolicitudPropio(fila=fila, nombre=nombre, valor=valor, cups=cups)


# ---------------- códigos ----------------

@pytest.mark.parametrize(
    ("texto", "esperado"),
    [("PRO5715", 5715), ("pro 5715", 5715), (5715, 5715), ("0007", 7)],
)
def test_numero_de_codigo(texto, esperado) -> None:
    assert propios.numero_de_codigo(texto) == esperado


def test_ultimo_codigo_invalido() -> None:
    with pytest.raises(propios.CodigoInvalido):
        propios.numero_de_codigo("ABC")


def test_consecutivo_sigue_el_orden() -> None:
    lista = propios.preparar_propios(
        [_sol(2, "A", 1000, "601T02"), _sol(3, "B", 2000, "129M01")], "PRO5715"
    )
    assert [p.codigo for p in lista] == ["PRO5716", "PRO5717"]


def test_bloqueados_no_consumen_numero() -> None:
    lista = propios.preparar_propios(
        [
            _sol(2, "A", 1000, "601T02"),
            _sol(3, "", 2000, "601T02"),          # sin nombre
            _sol(4, "C", "BAJO COTIZACION", "601T02"),
            _sol(5, "D", 3000, "601T02"),
        ],
        "PRO5715",
    )
    assert [p.codigo for p in lista] == ["PRO5716", "", "", "PRO5717"]


# ---------------- validación ----------------

def test_nombre_se_sanea_y_se_quita_el_separador() -> None:
    (p,) = propios.preparar_propios(
        [_sol(2, "TRASLADO | IBAGUÉ A BOGOTÁ Nº 2", 2880000, "601T02")], "PRO1"
    )
    assert p.nombre == "TRASLADO - IBAGUE A BOGOTA NRO 2"
    assert "|" not in p.nombre
    assert not p.bloqueado
    assert any(h.severidad.value == "CORRECCION" for h in p.hallazgos)


@pytest.mark.parametrize("cups", ["", "6012", "601t02", "PRO6212", "4413022"])
def test_cups_invalido_bloquea(cups) -> None:
    (p,) = propios.preparar_propios([_sol(2, "A", 1000, cups)], "PRO1")
    assert p.bloqueado


def test_valor_cero_o_negativo_bloquea() -> None:
    lista = propios.preparar_propios(
        [_sol(2, "A", 0, "601T02"), _sol(3, "B", -5, "601T02")], "PRO1"
    )
    assert all(p.bloqueado for p in lista)


def test_cups_desconocido_solo_advierte() -> None:
    (p,) = propios.preparar_propios(
        [_sol(2, "A", 1000, "999999")], "PRO1", cups_conocidos={"601T02"}
    )
    assert not p.bloqueado
    assert any(h.severidad.value == "ADVERTENCIA" for h in p.hallazgos)


def test_nombres_repetidos_avisan_pero_no_bloquean() -> None:
    lista = propios.preparar_propios(
        [_sol(2, "IGUAL", 1000, "601T02"), _sol(3, "IGUAL", 2000, "601T02")], "PRO1"
    )
    assert all(not p.bloqueado for p in lista)
    assert all(p.hallazgos for p in lista)


# ---------------- archivos ----------------

def test_reproduce_la_plantilla_real_y_no_termina_en_salto() -> None:
    lista = propios.preparar_propios(
        [
            _sol(2, "TRASLADO ASISTENCIAL BASICO DOBLE DESDE IBAGUE HASTA BOGOTA", 2880000, "601T02"),
            _sol(3, "OTRO", 1500, "601T01"),
        ],
        "PRO6211",
    )

    creacion = propios.construir_bytes_creacion(lista)
    carga = propios.construir_bytes_carga(lista)

    assert creacion == (
        b"TRASLADO ASISTENCIAL BASICO DOBLE DESDE IBAGUE HASTA BOGOTA|PRO6212|2880000|601T02"
        b"\r\n"
        b"OTRO|PRO6213|1500|601T01"
    )
    assert carga == b"PRO6212;2880000;PRO;0;0;\r\nPRO6213;1500;PRO;0;0;"
    assert not creacion.endswith(b"\r\n") and not carga.endswith(b"\r\n")


def test_generar_salidas_escribe_los_cuatro_archivos(tmp_path) -> None:
    lista = propios.preparar_propios(
        [_sol(2, "A", 1000, "601T02"), _sol(3, "", 1, "601T02")], "PRO1"
    )

    rutas = propios_service.generar_salidas(lista, tmp_path, prefijo="P")

    assert set(rutas) == {"creacion", "carga", "asignacion", "hallazgos"}
    assert rutas["creacion"].read_bytes() == b"A|PRO0002|1000|601T02"


# ---------------- lectura y CLI ----------------

def _excel(tmp_path, filas, nombre="propios.xlsx"):
    libro = Workbook()
    hoja = libro.active
    hoja.append(["LISTA DE PROPIOS"])
    for fila in filas:
        hoja.append(fila)
    ruta = tmp_path / nombre
    libro.save(ruta)
    return ruta


def test_lee_excel_con_encabezado_desplazado(tmp_path) -> None:
    ruta = _excel(tmp_path, [["CUPS", "Nombre", "Valor"], ["601T02", "RUTA", 1000]])

    (s,) = leer_solicitudes(ruta)

    assert (s.nombre, s.valor, s.cups) == ("RUTA", 1000, "601T02")


def test_lectura_sin_columnas_falla_claro(tmp_path) -> None:
    ruta = _excel(tmp_path, [["ALFA", "BETA"], [1, 2]])
    with pytest.raises(LecturaPropiosFallida):
        leer_solicitudes(ruta)


def test_cli_genera_archivos_y_no_toca_el_original(tmp_path, capsys) -> None:
    ruta = _excel(tmp_path, [["NOMBRE", "VALOR", "CUPS"], ["RUTA", 1000, "601T02"]])
    antes = ruta.read_bytes()

    codigo = cli_propios.main(
        [str(ruta), "--ultimo-pro", "PRO5715", "--salida", str(tmp_path / "out")]
    )

    assert codigo == 0
    assert "PRO5716" in capsys.readouterr().out
    assert ruta.read_bytes() == antes
    assert list((tmp_path / "out").glob("*_creacion.txt"))


# ---------------- candidatos a propio ----------------

def test_candidatos_separa_crear_propio_y_traslados(tmp_path) -> None:
    libro = Workbook()
    hoja = libro.active
    hoja.title = "SERVICIOS"
    hoja.append(["CUPS", "DESCRIPCION", "VALOR"])
    hoja.append(["810116", "CONSULTA", 50000])
    hoja.append(["", "TRASLADO RUTA X - CREAR PROPIO", 300000])
    hoja.append(["601T02", "TRASLADO", 35456])
    ruta = tmp_path / "anexo.xlsx"
    libro.save(ruta)

    resultado = cargues_service.procesar_anexo(ruta, rules.CARGUE_CUPS)
    candidatos = cargues_service.candidatos_a_propio(resultado)

    assert [c["fila"] for c in candidatos] == [3, 4]
    assert "crear propio" in candidatos[0]["motivo"]
    assert "traslado" in candidatos[1]["motivo"]
    assert cargues_service.generar_salidas(resultado, tmp_path / "s")["propios_pendientes"].exists()
