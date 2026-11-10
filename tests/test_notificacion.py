"""Pruebas del documento para notificar al prestador y del respeto a los códigos."""

from __future__ import annotations

from io import BytesIO

import pytest
from openpyxl import Workbook, load_workbook

from src.app.application import (
    cargues_service,
    conciliacion_service,
    notificacion_service,
)
from src.app.domain.cargues import rules, txt_writer
from src.app.domain.cargues.conciliacion import RegistroGemanet, clave_codigo, conciliar
from src.app.domain.cargues.model import Registro, Severidad
from src.app.domain.cargues.validators import construir_registro


def _reg(codigo, descripcion="TORNILLO", valor=1000, **campos) -> Registro:
    return Registro(
        fila=2, codigo=codigo, descripcion=descripcion, descripcion_original=descripcion,
        valor=valor, tipo_tarifa="PRO", **campos,
    )


def _leer(excel: bytes):
    return load_workbook(BytesIO(excel))


# ============================================================
# DOCUMENTO DE NOTIFICACIÓN
# ============================================================

def test_hoja_con_codigo_descripcion_y_valor_y_codigos_como_texto() -> None:
    excel = notificacion_service.excel_de_notificacion(
        notificacion_service.filas_para_parametrizar(
            [_reg("000123", "TORNILLO 3.5 MM", 315000), _reg("107-210/41", "COPA", 7227500)]
        )
    )

    hoja = _leer(excel)["Para parametrizar"]

    assert [c.value for c in hoja[1]] == ["CODIGO", "DESCRIPCION", "VALOR"]
    assert hoja["A2"].value == "000123"            # los ceros iniciales se conservan
    assert hoja["A2"].number_format == "@"
    assert hoja["A3"].value == "107-210/41"
    assert hoja["B2"].value == "TORNILLO 3.5 MM"
    assert hoja["C2"].value == 315000


def test_la_segunda_hoja_trae_lo_que_el_prestador_debe_corregir() -> None:
    excel = notificacion_service.excel_de_notificacion(
        [["1", "A", 10]],
        [["2", "B", 20, "código repetido 2 veces en el anexo"]],
    )

    libro = _leer(excel)

    assert libro.sheetnames == ["Para parametrizar", "Por corregir"]
    assert [c.value for c in libro["Por corregir"][1]] == ["CODIGO", "DESCRIPCION", "VALOR", "MOTIVO"]
    assert libro["Por corregir"]["D2"].value == "código repetido 2 veces en el anexo"


def test_sin_nada_que_notificar_no_hay_documento() -> None:
    assert notificacion_service.excel_de_notificacion([], []) is None


def test_el_valor_vacio_no_rompe_el_documento() -> None:
    excel = notificacion_service.excel_de_notificacion(
        notificacion_service.filas_para_parametrizar([_reg("1", valor=None)])
    )
    assert _leer(excel)["Para parametrizar"]["C2"].value in (None, "")


def test_el_cargue_genera_el_documento_de_notificacion(tmp_path) -> None:
    libro = Workbook()
    hoja = libro.active
    hoja.title = "INSUMOS"
    hoja.append(["COD INTERNO IPS", "DESCRIPCION", "TARIFA OFERTADA"])
    hoja.append(["000123", "TORNILLO ÁÉÍ", 315000])
    hoja.append(["", "SIN CODIGO", 10])
    ruta = tmp_path / "anexo.xlsx"
    libro.save(ruta)

    resultado = cargues_service.procesar_anexo(ruta, rules.CARGUE_INS)
    rutas = cargues_service.generar_salidas(resultado, tmp_path / "salidas")

    libro = load_workbook(rutas["notificacion"])
    assert libro["Para parametrizar"]["A2"].value == "000123"
    assert libro["Para parametrizar"]["B2"].value == "TORNILLO AEI"      # la descripción saneada
    assert libro["Por corregir"]["D2"].value == "el código está vacío"


def test_la_conciliacion_genera_el_documento_de_notificacion(tmp_path) -> None:
    resultado = conciliar([_reg("1", valor=500)], {}, rules.CARGUE_INS, linea=lambda r: "")

    excel = conciliacion_service.construir_notificacion(resultado)

    assert _leer(excel)["Para parametrizar"]["A2"].value == "1"


# ============================================================
# LOS CÓDIGOS NO SE CAMBIAN
# ============================================================

def _ins(codigo, **campos):
    fila = {"_fila": 3, "codigo": codigo, "descripcion": "TORNILLO", "valor": 1000}
    fila.update(campos)
    return construir_registro(fila, rules.CARGUE_INS)


@pytest.mark.parametrize("codigo", ["000123", "00103", "0201361", "CS-093 ", " 107-210/41", "PER 11-14-S", "abc-Ñ".replace("Ñ", "n")])
def test_el_codigo_de_insumo_queda_exactamente_como_viene(codigo) -> None:
    registro = _ins(codigo)

    assert registro.codigo == codigo
    assert not registro.bloqueado
    assert txt_writer.construir_linea(registro, rules.CARGUE_INS).startswith(f"{codigo};")


def test_un_codigo_de_insumo_numerico_no_avisa_por_ceros() -> None:
    registro = _ins(1455.0)

    assert registro.codigo == "1455"
    assert not registro.tiene_advertencias


def test_en_servicios_se_conservan_los_ceros_y_se_avisa_si_la_celda_es_numerica() -> None:
    con_ceros = construir_registro({"_fila": 2, "codigo": "053109", "descripcion": "X", "valor": 1}, rules.CARGUE_CUPS)
    numerico = construir_registro({"_fila": 3, "codigo": 53109.0, "descripcion": "X", "valor": 1}, rules.CARGUE_CUPS)

    def avisos_del_codigo(registro):
        return [
            h for h in registro.hallazgos
            if h.campo == "codigo" and h.severidad is Severidad.ADVERTENCIA
        ]

    assert con_ceros.codigo == "053109" and not avisos_del_codigo(con_ceros)
    assert avisos_del_codigo(numerico)         # Excel pudo haberle quitado el cero


def test_en_servicios_los_espacios_de_los_extremos_se_quitan_y_queda_registrado() -> None:
    registro = construir_registro({"_fila": 2, "codigo": " 890271 ", "descripcion": "X", "valor": 1}, rules.CARGUE_CUPS)

    assert registro.codigo == "890271"
    assert any(
        h.severidad is Severidad.CORRECCION and "espacios" in h.problema for h in registro.hallazgos
    )
    assert not registro.bloqueado


def test_un_codigo_de_insumo_con_salto_de_linea_adentro_se_bloquea() -> None:
    assert _ins("107-210\n41").bloqueado
    assert _ins("REF 8120 \nREF 8121").bloqueado


def test_los_saltos_de_linea_de_los_extremos_se_quitan_pero_los_espacios_no() -> None:
    registro = _ins("CS-093 \n")

    assert registro.codigo == "CS-093 "
    assert not registro.bloqueado
    assert any(
        h.severidad is Severidad.CORRECCION and "saltos de línea" in h.problema
        for h in registro.hallazgos
    )


def test_la_conciliacion_ignora_los_espacios_de_los_extremos_para_comparar() -> None:
    registro = _reg("CS-093 ")
    gema = RegistroGemanet(codigo=clave_codigo("CS-093"), valor=1000.0, tipo="PRO", porcentaje="0",
                           descripcion="", activo="Si", fila=2)

    resultado = conciliar([registro], {clave_codigo("CS-093"): gema}, rules.CARGUE_INS)

    assert len(resultado.coinciden) == 1 and not resultado.a_cargar
