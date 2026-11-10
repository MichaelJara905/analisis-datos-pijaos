"""Pruebas de la conciliación anexo vs GEMANET (fase 1: solo informes)."""

from __future__ import annotations

import pytest
from openpyxl import Workbook

from src.app.application import cargues_service, cli_conciliar, conciliacion_service
from src.app.domain.cargues import rules
from src.app.domain.cargues.conciliacion import RegistroGemanet, clave_codigo, conciliar
from src.app.domain.cargues.model import Registro
from src.app.infrastructure.excel.anexos import LecturaFallida, leer_anexo
from src.app.infrastructure.excel.gemanet import (
    LecturaGemanetFallida,
    leer_reporte,
)


# ============================================================
# CLAVES
# ============================================================

@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("898015.0", "898015"),
        (898015.0, "898015"),
        ("53109.0", "053109"),
        ("129m01", "129M01"),
        ("20097544-1", "20097544-1"),
        ("INS0020179", "INS0020179"),
        (None, ""),
    ],
)
def test_clave_codigo(entrada, esperado) -> None:
    assert clave_codigo(entrada) == esperado


# ============================================================
# DOMINIO
# ============================================================

def _reg(codigo, **campos) -> Registro:
    base = {"fila": 2, "codigo": codigo, "valor": 1000, "tipo_tarifa": "PRO", "hoja": "H"}
    base.update(campos)
    return Registro(**base)


def _gema(codigo, valor=1000.0, tipo="PRO", porcentaje="0") -> RegistroGemanet:
    return RegistroGemanet(
        codigo=clave_codigo(codigo), valor=valor, tipo=tipo,
        porcentaje=porcentaje, descripcion="", activo="Si", fila=2,
    )


def test_pro_con_igual_valor_coincide_y_con_otro_valor_difiere() -> None:
    resultado = conciliar(
        [_reg("111111"), _reg("222222", valor=5000)],
        {"111111": _gema("111111"), "222222": _gema("222222", valor=4000.0)},
        rules.CARGUE_CUPS,
    )
    assert [f["codigo"] for f in resultado.coinciden] == ["111111"]
    assert "valor distinto" in resultado.diferencias[0]["motivo"]


def test_regulado_contra_gemanet_vacio_no_compara_valor() -> None:
    registro = _reg("333333", tipo_tarifa="UVB", codigo_ley="39143", valor=79100)
    resultado = conciliar(
        [registro], {"333333": _gema("333333", valor=79006.0, tipo="")}, rules.CARGUE_CUPS
    )
    assert len(resultado.coinciden) == 1 and not resultado.diferencias


def test_tipo_distinto_se_reporta() -> None:
    resultado = conciliar(
        [_reg("444444", tipo_tarifa="UVB", codigo_ley="39143")],
        {"444444": _gema("444444", tipo="PRO")},
        rules.CARGUE_CUPS,
    )
    assert "tipo distinto" in resultado.diferencias[0]["motivo"]


def test_repetido_no_se_decide_y_va_a_inconsistencias() -> None:
    resultado = conciliar(
        [_reg("555555", fila=2), _reg("555555", fila=9, valor=2000)],
        {},
        rules.CARGUE_CUPS,
    )
    assert not resultado.faltan_listos
    # Cada fila repetida va al informe, con dónde está cada una y los valores.
    assert [f["fila"] for f in resultado.faltan_con_error] == [2, 9]
    motivo = resultado.faltan_con_error[0]["motivo"]
    assert "decidir cuál se carga" in motivo and "fila 2" in motivo and "fila 9" in motivo
    assert "valores: 1000, 2000" in motivo
    assert resultado.inconsistencias[0]["tipo"] == "código repetido"
    assert "1000" in resultado.inconsistencias[0]["detalle"]
    assert "2000" in resultado.inconsistencias[0]["detalle"]


def test_solo_en_gemanet() -> None:
    resultado = conciliar([], {"666666": _gema("666666")}, rules.CARGUE_CUPS)
    assert resultado.solo_gemanet[0]["codigo"] == "666666"


# ============================================================
# LECTURA DE ENCABEZADOS REALES
# ============================================================

def _libro(tmp_path, hojas: dict[str, list[list]], nombre="anexo.xlsx"):
    libro = Workbook()
    libro.remove(libro.active)
    for titulo, filas in hojas.items():
        hoja = libro.create_sheet(titulo)
        for fila in filas:
            hoja.append(fila)
    ruta = tmp_path / nombre
    libro.save(ruta)
    return ruta


def test_encabezados_del_anexo_de_servicios(tmp_path) -> None:
    ruta = _libro(
        tmp_path,
        {
            "SERVICIOS ": [
                ["x"],
                [
                    "No", "CUPS/ PROPIO", "2707/2025", "CÓDIGO CLINALSOFT",
                    "DESCRIPCION CUPS", "NOMBRE TARIFA", "VALOR SOAT VIGENTE",
                    "% TARIFA DSCTO", "VALOR CON DESCUENTO", "INCLUSIONES",
                    "CÓDIGO SOAT HOMOLOGO",
                ],
                [1, "937001", "937001", "C-937001", "TERAPIA", "SOAT VIGENTE UVB",
                 35119, 0, 35100, None, "29114"],
            ]
        },
    )

    anexo = leer_anexo(ruta, rules.CARGUE_CUPS, hoja="SERVICIOS ", fila_encabezado=2)

    assert anexo.mapeo["valor"] == "VALOR CON DESCUENTO"
    assert anexo.mapeo["porcentaje"] == "% TARIFA DSCTO"
    assert anexo.mapeo["tipo_tarifa"] == "NOMBRE TARIFA"
    assert anexo.mapeo["codigo_ley"] == "CÓDIGO SOAT HOMOLOGO"
    assert anexo.mapeo["codigo_interno"] == "CÓDIGO CLINALSOFT"


def test_encabezados_de_medicamentos_e_insumos(tmp_path) -> None:
    ruta = _libro(
        tmp_path,
        {
            "MEDICAMENTOS": [
                ["ANEXO"],
                ["IDSERVICIO", "CUMS", "CODIGO MIPRES", "DESCRIPCION CUMS", "CLASIFICACION", "OFERTA 2026"],
                ["R03", "20107595-1", None, "BUDESONIDA", "REGULADO", 1148],
            ],
            " INSUMOS": [
                ["ANEXO"],
                ["IDSERVICIO", "COD INS", "SERVICIO", "OFERTA 2026", "OBSERVACIONES"],
                ["INS0020287", "PERISFERICOS", "CATETER", 1056029, None],
            ],
        },
    )

    cums = leer_anexo(ruta, rules.CARGUE_CUMS, hoja="MEDICAMENTOS", fila_encabezado=2)
    ins = leer_anexo(ruta, rules.CARGUE_INS, hoja=" INSUMOS", fila_encabezado=2)

    assert cums.mapeo["valor"] == "OFERTA 2026"
    assert cums.mapeo["codigo"] == "CUMS"
    assert ins.mapeo["codigo"] == "IDSERVICIO"
    assert ins.mapeo["descripcion"] == "SERVICIO"
    assert ins.filas[0]["codigo"] == "INS0020287"


# ============================================================
# LECTOR DE GEMANET
# ============================================================

def _reporte(tmp_path, filas, nombre="GEMA_CUPS.xlsx", extra=False):
    encabezado = ["CÓDIGO", "VALOR PACTADO", "TIPO TARIFARIO", "PORCENTAJE TARIFA", "DESCRIPCIÓN", "ACTIVO"]
    return _libro(tmp_path, {"DATOS": [encabezado] + filas}, nombre)


def test_lee_codigos_numericos_y_tipo_vacio(tmp_path) -> None:
    ruta = _reporte(
        tmp_path,
        [[898015.0, 12600.0, "PRO", 0, "ESTUDIO", "Si"], [53109.0, 7000.0, None, 0, "REG", "Si"]],
    )

    reporte = leer_reporte(ruta)

    assert set(reporte.registros) == {"898015", "053109"}
    assert reporte.registros["053109"].es_regulado
    assert not reporte.registros["898015"].es_regulado


def test_reporta_columnas_corridas_y_repetidos(tmp_path) -> None:
    ruta = _reporte(
        tmp_path,
        [
            ["111111", 100.0, "PRO", 0, "DESC", " TRANSFERENCIAS MUSCULOTENDINOSAS"],
            ["222222", 100.0, "PRO", 0, "A", "Si"],
            ["222222", 100.0, "PRO", 0, "A", "Si"],
        ],
    )

    tipos = {a["tipo"] for a in leer_reporte(ruta).anomalias}

    assert tipos == {"columnas corridas", "código repetido"}


def test_reporte_sin_columnas_falla_claro(tmp_path) -> None:
    ruta = _libro(tmp_path, {"DATOS": [["ALFA", "BETA"], [1, 2]]}, "malo.xlsx")
    with pytest.raises(LecturaGemanetFallida):
        leer_reporte(ruta)


# ============================================================
# MULTI-HOJA Y CONCILIACIÓN COMPLETA
# ============================================================

def _anexo_cups(tmp_path):
    cab = ["No", "CUPS/ PROPIO", "CÓDIGO CLINALSOFT", "DESCRIPCION CUPS", "NOMBRE TARIFA",
           "VALOR CON DESCUENTO", "% TARIFA DSCTO", "CÓDIGO SOAT HOMOLOGO"]
    return _libro(
        tmp_path,
        {
            "SERVICIOS ": [
                ["PRESTADOR DE PRUEBA"],
                cab,
                [1, "937001", "C-1", "TERAPIA", "PROPIA", 35100, 0, None],
                [2, "890271", "C-2", "CONSULTA", "SOAT VIGENTE UVB", 79100, 0, "39143"],
                [3, "053109", "C-3", "BLOQUEO", "PROPIA", 10000, 0, None],
                [4, "TEXTO LIBRE", "C-4", "NO ES CODIGO", "PROPIA", 500, 0, None],
                [5, "815601", "C-5", "PROTESIS", "PROPIA", 4508200, 0, None],
            ],
            "TABLA FISH": [
                ["ANEXO 3"],
                ["CUPS", "CUPS CLINALSOFT", "DESCRIPCIÓN", "TARIFA"],
                ["908424", "C-908424-18", "ESTUDIO", 1362200],
                ["908424", "C-908424-19", "ESTUDIO", 1362200],
                ["908424", "C-908424-20", "ESTUDIO", 1362200],
            ],
            "LISTA ": [["Baja Complejidad"], ["Alta Complejidad"]],
        },
    )


def _gema_cups(tmp_path):
    return _reporte(
        tmp_path,
        [
            [890271.0, 79006.0, None, 0, "CONSULTA", "Si"],
            [53109.0, 12000.0, "PRO", 0, "BLOQUEO", "Si"],
            [815601.0, 4508200.0, "PRO", 0, "PROTESIS", "Si"],
            [908424.0, 444300.0, "PRO", 0, "ESTUDIO", "Si"],
            [999999.0, 1.0, "PRO", 0, "SOLO GEMA", "Si"],
        ],
    )


def test_multihoja_usa_las_hojas_reconocidas_y_omite_el_resto(tmp_path) -> None:
    procesado = cargues_service.procesar_anexo_multihoja(_anexo_cups(tmp_path), rules.CARGUE_CUPS)

    assert procesado.hojas_usadas == ["SERVICIOS", "TABLA FISH"]
    assert procesado.hojas_omitidas == ["LISTA"]
    assert {r.hoja for r in procesado.registros} == {"SERVICIOS", "TABLA FISH"}


def test_multihoja_con_hoja_inexistente_falla_claro(tmp_path) -> None:
    with pytest.raises(LecturaFallida) as error:
        cargues_service.procesar_anexo_multihoja(
            _anexo_cups(tmp_path), rules.CARGUE_CUPS, hojas=["NO EXISTE"]
        )
    assert "NO EXISTE" in str(error.value)


def test_en_insumos_solo_entran_las_hojas_que_lo_dicen(tmp_path) -> None:
    ruta = _libro(
        tmp_path,
        {
            " INSUMOS": [["A"], ["IDSERVICIO", "SERVICIO", "OFERTA 2026"], ["INS1", "GASA", 1500]],
            "IMAGENOLOGIA": [["A"], ["CUPS", "DESCRIPCION", "VALOR"], ["883910", "RM", 863000]],
        },
    )

    procesado = cargues_service.procesar_anexo_multihoja(ruta, rules.CARGUE_INS)

    assert procesado.hojas_usadas == ["INSUMOS"]


def test_conciliacion_completa(tmp_path) -> None:
    resultado, procesado, _ = conciliacion_service.conciliar_anexo(
        _anexo_cups(tmp_path), rules.CARGUE_CUPS, _gema_cups(tmp_path)
    )

    assert [f["codigo"] for f in resultado.coinciden] == ["890271", "815601"]
    assert [f["codigo"] for f in resultado.faltan_listos] == ["937001"]
    assert resultado.faltan_listos[0]["linea_txt"] == "937001;35100;PRO;0;0;"
    assert [f["codigo"] for f in resultado.faltan_con_error] == ["TEXTO LIBRE"]
    assert [f["codigo"] for f in resultado.diferencias] == ["053109"]
    assert [f["codigo"] for f in resultado.solo_gemanet] == ["999999"]
    assert [i["codigo"] for i in resultado.inconsistencias] == ["908424"]
    assert "C-908424-18" in resultado.inconsistencias[0]["detalle"]


def test_txt_lleva_solo_lo_que_falta_y_es_valido(tmp_path) -> None:
    resultado, procesado, reporte = conciliacion_service.conciliar_anexo(
        _anexo_cups(tmp_path), rules.CARGUE_CUPS, _gema_cups(tmp_path)
    )

    rutas = conciliacion_service.generar_informes(
        resultado, procesado, tmp_path / "out", reporte=reporte
    )
    contenido = rutas["txt"].read_bytes()

    # Solo 937001: 890271, 053109 y 815601 ya están; 908424 está repetido;
    # "TEXTO LIBRE" tiene error.
    assert contenido == b"937001;35100;PRO;0;0;"
    assert not contenido.endswith(b"\r\n")


def test_el_txt_nunca_trae_un_codigo_que_ya_esta_en_gemanet(tmp_path) -> None:
    resultado, procesado, reporte = conciliacion_service.conciliar_anexo(
        _anexo_cups(tmp_path), rules.CARGUE_CUPS, _gema_cups(tmp_path)
    )

    for linea in conciliacion_service.construir_txt(resultado).decode("ascii").split("\r\n"):
        assert clave_codigo(linea.split(";")[0]) not in reporte.registros


def test_la_verificacion_final_detecta_repetidos_y_ya_cargados() -> None:
    gema = {"111111": _gema("111111")}
    contenido = b"111111;1;PRO;0;0;\r\n222222;1;PRO;0;0;\r\n222222;2;PRO;0;0;"

    problemas = conciliacion_service.verificar_txt(contenido, gema)

    assert any("ya está en GEMANET" in p for p in problemas)
    assert any("se repite" in p for p in problemas)


def test_si_la_verificacion_falla_no_se_escribe_el_txt(tmp_path, monkeypatch) -> None:
    resultado, procesado, reporte = conciliacion_service.conciliar_anexo(
        _anexo_cups(tmp_path), rules.CARGUE_CUPS, _gema_cups(tmp_path)
    )
    resultado.a_cargar.append(resultado.a_cargar[0])     # fuerza un repetido

    with pytest.raises(conciliacion_service.TxtInconsistente):
        conciliacion_service.generar_informes(resultado, procesado, tmp_path / "out", reporte=reporte)

    assert not list((tmp_path / "out").glob("*.txt"))


def test_sin_nada_que_cargar_no_hay_txt(tmp_path) -> None:
    anexo = _libro(tmp_path, {"SERVICIOS": [["x"], ["CUPS", "VALOR"], ["890271", 79100]]})
    gema = _reporte(tmp_path, [[890271.0, 79100.0, "PRO", 0, "C", "Si"]])
    resultado, procesado, reporte = conciliacion_service.conciliar_anexo(anexo, rules.CARGUE_CUPS, gema)

    rutas = conciliacion_service.generar_informes(resultado, procesado, tmp_path / "out", reporte=reporte)

    assert "txt" not in rutas


def test_en_insumos_el_tipo_vacio_de_gemanet_no_es_regulado() -> None:
    insumo = _reg("INS-1", valor=44030, tipo_tarifa="PRO")
    sin_tipo = _gema("INS-1", valor=44030.0, tipo="")

    como_insumo = conciliar([insumo], {"INS-1": sin_tipo}, rules.CARGUE_INS)
    como_servicio = conciliar([insumo], {"INS-1": sin_tipo}, rules.CARGUE_CUPS)

    assert len(como_insumo.coinciden) == 1 and not como_insumo.diferencias
    assert "tipo distinto" in como_servicio.diferencias[0]["motivo"]


def test_en_insumos_el_valor_distinto_si_se_reporta() -> None:
    resultado = conciliar(
        [_reg("INS-1", valor=50000)], {"INS-1": _gema("INS-1", valor=44030.0, tipo="")}, rules.CARGUE_INS
    )
    assert "valor distinto" in resultado.diferencias[0]["motivo"]


def test_cargado_pero_inactivo_se_reporta_como_diferencia() -> None:
    resultado = conciliar(
        [_reg("111111")],
        {"111111": RegistroGemanet(codigo="111111", valor=1000.0, tipo="PRO", porcentaje="0",
                                   descripcion="", activo="No", fila=2)},
        rules.CARGUE_CUPS,
    )
    assert "INACTIVO" in resultado.diferencias[0]["motivo"]
    assert not resultado.a_cargar


def test_informes_y_cli_no_tocan_los_originales(tmp_path, capsys) -> None:
    anexo, gema = _anexo_cups(tmp_path), _gema_cups(tmp_path)
    antes = (anexo.read_bytes(), gema.read_bytes())

    codigo = cli_conciliar.main(
        [str(anexo), "--tipo", "CUPS", "--gemanet", str(gema), "--salida", str(tmp_path / "out"),
         "--solo-informes"]
    )

    salida = capsys.readouterr().out
    assert codigo == 0
    assert "no se generó ningún TXT" in salida
    assert (anexo.read_bytes(), gema.read_bytes()) == antes
    nombres = {p.name.split("_", 3)[-1] for p in (tmp_path / "out").glob("*.csv")}
    assert {"faltantes.csv", "diferencias.csv", "solo_en_gemanet.csv", "inconsistencias.csv", "resumen.csv"} <= nombres
    assert not list((tmp_path / "out").glob("*.txt"))


def test_cli_por_defecto_genera_el_txt(tmp_path, capsys) -> None:
    anexo, gema = _anexo_cups(tmp_path), _gema_cups(tmp_path)

    codigo = cli_conciliar.main(
        [str(anexo), "--tipo", "CUPS", "--gemanet", str(gema), "--salida", str(tmp_path / "out")]
    )

    (txt,) = (tmp_path / "out").glob("*_para_cargar.txt")
    assert codigo == 0
    assert txt.read_bytes() == b"937001;35100;PRO;0;0;"
    assert "1 líneas" in capsys.readouterr().out
