"""Pruebas del módulo de cargues GEMANET.

Los casos de referencia salen de archivos TXT que cargaron correctamente
en GEMANET: si estas pruebas pasan, el generador reproduce byte a byte lo
que el sistema aceptó.
"""

from __future__ import annotations

import pytest
from openpyxl import Workbook

from src.app.application import cargues_service
from src.app.domain.cargues import parsing, rules, sanitizer, txt_writer
from src.app.domain.cargues.model import Registro, Severidad
from src.app.domain.cargues.validators import (
    construir_registro,
    validar_duplicados,
)
from src.app.infrastructure.excel.anexos import LecturaFallida, leer_anexo


# ============================================================
# SANEAMIENTO
# ============================================================

def test_conserva_parentesis_guiones_y_comas() -> None:
    """La referencia de un insumo no se puede tocar: GEMANET la acepta así."""

    original = (
        "SISTEMA DE BALON 5,5 CM DILATADOR BILIAR CON CATETER 8 FR "
        "X 240 CM G51798 (REF HBD-W-18-19-20)"
    )

    saneada, cambios = sanitizer.sanear_descripcion(original)

    assert saneada == original
    assert cambios == []


def test_grados_pegado_a_ene_es_numero() -> None:
    saneada, _ = sanitizer.sanear_descripcion("PUNCION N° 22")
    assert saneada == "PUNCION NRO 22"


def test_grados_suelto_se_traduce() -> None:
    saneada, _ = sanitizer.sanear_descripcion("TEMPERATURA 37° C")
    assert saneada == "TEMPERATURA 37 GRADOS C"


def test_punto_y_coma_se_vuelve_coma() -> None:
    saneada, cambios = sanitizer.sanear_descripcion("SESION; INCLUYE: PROFILAXIS")
    assert ";" not in saneada
    assert saneada == "SESION, INCLUYE: PROFILAXIS"
    assert any("," in cambio for cambio in cambios)


def test_tildes_y_ene() -> None:
    saneada, _ = sanitizer.sanear_descripcion("PINZA CUERPO EXTRAÑO ÁÉÍÓÚ")
    assert saneada == "PINZA CUERPO EXTRANO AEIOU"


def test_simbolos_de_la_tabla() -> None:
    saneada, _ = sanitizer.sanear_descripcion("CATETER Ø 3 MM MARCA® TEST™ 1ª")
    assert saneada == "CATETER D 3 MM MARCA(R) TEST(TM) 1A"


def test_no_convierte_a_mayusculas() -> None:
    saneada, _ = sanitizer.sanear_descripcion("DIPEPTIVEN 200mg/ml")
    assert saneada == "DIPEPTIVEN 200mg/ml"


def test_reporta_caracteres_sin_regla() -> None:
    saneada, _ = sanitizer.sanear_descripcion("PRODUCTO ∑ ESPECIAL")
    assert sanitizer.caracteres_no_soportados(saneada) == ["∑"]


# ============================================================
# CONVERSIÓN DE CELDAS
# ============================================================

@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        (527340.248, 527340),
        (188674.7, 188675),
        (2511460, 2511460),
        (0.5, 1),          # redondeo tipo Excel: 0,5 sube
        (1.5, 2),          # Python por defecto daría 2
        (2.5, 3),          # Python por defecto daría 2
        ("$ 1.234.567", 1234567),
        ("1.234.567,89", 1234568),
    ],
)
def test_valor_redondeado_al_peso(entrada, esperado) -> None:
    valor, problema, _ = parsing.valor_de_celda(entrada)
    assert problema == ""
    assert valor == esperado


def test_bajo_cotizacion_no_es_valor() -> None:
    valor, problema, _ = parsing.valor_de_celda("BAJO COTIZACION")
    assert valor is None
    assert "no tiene tarifa" in problema


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [(-0.1, -10), (0.15, 15), (-10, -10), (0, 0), (None, 0), ("-5%", -5)],
)
def test_porcentaje_se_vuelve_entero(entrada, esperado) -> None:
    porcentaje, problema, _ = parsing.porcentaje_de_celda(entrada)
    assert problema == ""
    assert porcentaje == esperado


def test_codigo_numerico_avisa_por_ceros_perdidos() -> None:
    codigo, aviso = parsing.codigo_de_celda(451201.0)
    assert codigo == "451201"
    assert "ceros a la izquierda" in aviso


def test_soat_solo_no_alcanza() -> None:
    tipo, problema = parsing.tipo_tarifa_de_celda("SOAT")
    assert tipo == ""
    assert "UVB" in problema


def test_evento_es_tarifa_propia() -> None:
    tipo, problema = parsing.tipo_tarifa_de_celda("EVENTO")
    assert tipo == rules.TARIFA_PROPIA
    assert problema == ""


# ============================================================
# GENERACIÓN DEL TXT
# ============================================================

def _registro(**campos) -> Registro:
    base = {
        "fila": 11,
        "codigo": "0201361",
        "descripcion": "INSUMO DE PRUEBA",
        "valor": 2511460,
        "tipo_tarifa": rules.TARIFA_PROPIA,
    }
    base.update(campos)
    return Registro(**base)


def test_linea_insumo_reproduce_el_txt_real() -> None:
    registro = _registro(
        descripcion=(
            "SISTEMA DE BALON 5,5 CM DILATADOR BILIAR CON CATETER 8 FR "
            "X 240 CM G51798 (REF HBD-W-18-19-20)"
        )
    )

    linea = txt_writer.construir_linea(registro, rules.CARGUE_INS)

    assert linea == (
        "0201361;2511460;PRO;0;SISTEMA DE BALON 5,5 CM DILATADOR BILIAR "
        "CON CATETER 8 FR X 240 CM G51798 (REF HBD-W-18-19-20);0;"
    )


def test_linea_medicamento_reproduce_el_txt_real() -> None:
    registro = _registro(
        codigo="20048691-1",
        valor=43820,
        descripcion="KETAMINA (KETAMAX) 500 MG X 10 ML (50MG/ML) SOLUCION INYECTABLE",
    )

    linea = txt_writer.construir_linea(registro, rules.CARGUE_CUMS)

    assert linea == (
        "20048691-1;43820;PRO;0;KETAMINA (KETAMAX) 500 MG X 10 ML "
        "(50MG/ML) SOLUCION INYECTABLE;0;"
    )


def test_linea_servicio_no_lleva_descripcion() -> None:
    registro = _registro(codigo="441302", valor=527340)
    assert txt_writer.construir_linea(registro, rules.CARGUE_CUPS) == "441302;527340;PRO;0;0;"


def test_servicio_regulado_lleva_codigo_ley_en_vez_de_valor() -> None:
    registro = _registro(
        codigo="998706",
        valor=188675,
        tipo_tarifa="UVB",
        codigo_ley="39143",
        porcentaje=-10,
    )

    assert txt_writer.construir_linea(registro, rules.CARGUE_CUPS) == "998706;39143;UVB;-10;0;"


def test_archivo_usa_crlf_y_no_termina_en_salto() -> None:
    registros = [_registro(), _registro(codigo="0205125", valor=5849742)]

    contenido = txt_writer.construir_bytes(registros, rules.CARGUE_INS)

    assert contenido.count(b"\r\n") == 1
    assert not contenido.endswith(b"\r\n")
    assert contenido.endswith(b";")
    assert b"  " not in contenido.split(b";")[0]


def test_regulado_sin_codigo_ley_no_genera_linea() -> None:
    registro = _registro(tipo_tarifa="UVR", codigo_ley="")

    with pytest.raises(txt_writer.GeneracionFallida):
        txt_writer.construir_linea(registro, rules.CARGUE_CUPS)


# ============================================================
# VALIDACIONES
# ============================================================

def test_insumo_regulado_queda_bloqueado() -> None:
    fila = {
        "_fila": 11,
        "codigo": "0201361",
        "descripcion": "INSUMO",
        "valor": 1000,
        "tipo_tarifa": "UVB",
    }

    registro = construir_registro(fila, rules.CARGUE_INS)

    assert registro.bloqueado
    assert any("insumo" in h.problema for h in registro.hallazgos)


def test_cups_regulado_sin_codigo_ley_queda_bloqueado() -> None:
    fila = {
        "_fila": 43,
        "codigo": "998706",
        "descripcion": "INTENSIFICADOR DE IMAGENES",
        "valor": 188674.7,
        "tipo_tarifa": "UVB",
        "codigo_ley": None,
        "porcentaje": -0.1,
    }

    registro = construir_registro(fila, rules.CARGUE_CUPS)

    assert registro.bloqueado
    assert any("sin código ley" in h.problema for h in registro.hallazgos)


def test_cups_de_cinco_digitos_queda_bloqueado() -> None:
    fila = {"_fila": 12, "codigo": "44130", "descripcion": "X", "valor": 100}
    assert construir_registro(fila, rules.CARGUE_CUPS).bloqueado


def test_bajo_cotizacion_queda_bloqueado() -> None:
    fila = {
        "_fila": 33,
        "codigo": "434501",
        "descripcion": "MUCOSECTOMIA",
        "valor": "BAJO COTIZACION",
    }
    assert construir_registro(fila, rules.CARGUE_CUPS).bloqueado


def test_codigos_repetidos_se_bloquean_todos_y_dicen_donde_estan() -> None:
    filas = [
        {"_fila": 11, "codigo": "441302", "descripcion": "EGD", "valor": 527340},
        {"_fila": 12, "codigo": "441302", "descripcion": "EGD PEDIATRICA", "valor": 1028969},
        {"_fila": 13, "codigo": "441303", "descripcion": "OTRO", "valor": 1000},
    ]
    registros = [construir_registro(f, rules.CARGUE_CUPS) for f in filas]

    validar_duplicados(registros)

    assert registros[0].bloqueado and registros[1].bloqueado
    assert not registros[2].bloqueado
    problema = next(h.problema for h in registros[0].hallazgos if "aparece" in h.problema)
    assert "2 veces" in problema and "11, 12" in problema
    assert "527340" in problema and "1028969" in problema      # los valores distintos


def test_el_repetido_se_detecta_aunque_difiera_el_espacio_final() -> None:
    registros = [_ins("CS-093"), _ins("CS-093 ")]

    validar_duplicados(registros)

    assert all(r.bloqueado for r in registros)


def test_descripcion_con_punto_y_coma_se_corrige_y_no_bloquea() -> None:
    fila = {
        "_fila": 20,
        "codigo": "0205125",
        "descripcion": "SESION; INCLUYE PROFILAXIS",
        "valor": 1000,
    }

    registro = construir_registro(fila, rules.CARGUE_INS)

    assert not registro.bloqueado
    assert ";" not in registro.descripcion
    assert any(h.severidad is Severidad.CORRECCION for h in registro.hallazgos)


# ============================================================
# LECTURA DE ANEXOS
# ============================================================

def _crear_anexo(tmp_path, nombre_hoja: str, encabezados: list[str], filas: list[list]):
    """Crea un anexo de prueba con cabecera de prestador antes de los datos."""

    libro = Workbook()
    hoja = libro.active
    hoja.title = nombre_hoja

    hoja.append(["PORTAFOLIO DE SERVICIOS"])
    hoja.append([])
    hoja.append(["NOMBRE DEL PRESTADOR:", "PRESTADOR DE PRUEBA"])
    hoja.append([])
    hoja.append(encabezados)
    for fila in filas:
        hoja.append(fila)

    ruta = tmp_path / "anexo.xlsx"
    libro.save(ruta)
    return ruta


def test_lector_encuentra_los_encabezados_aunque_no_esten_en_la_fila_uno(tmp_path) -> None:
    ruta = _crear_anexo(
        tmp_path,
        "INSUMOS",
        ["COD INVIMA", "COD INTERNO IPS", "DESCRIPCIÓN ", "TARIFA OFERTADA"],
        [["2018DM-1", "0201361", "CATETER", 2511460]],
    )

    anexo = leer_anexo(ruta, rules.CARGUE_INS)

    assert anexo.fila_encabezado == 5
    assert anexo.mapeo["codigo"] == "COD INTERNO IPS"
    assert anexo.filas[0]["codigo"] == "0201361"


def test_lector_acepta_nombres_alternativos_de_columna(tmp_path) -> None:
    ruta = _crear_anexo(
        tmp_path,
        "MATERIALES",
        ["CODIGO INTERNO", "NOMBRE DEL INSUMO", "VALOR UNITARIO"],
        [["A-100", "GASA", 1500]],
    )

    anexo = leer_anexo(ruta, rules.CARGUE_INS)

    assert anexo.mapeo["valor"] == "VALOR UNITARIO"


def test_lector_explica_cuando_no_reconoce_el_anexo(tmp_path) -> None:
    ruta = _crear_anexo(
        tmp_path,
        "HOJA1",
        ["ALFA", "BETA", "GAMMA"],
        [["a", "b", "c"]],
    )

    with pytest.raises(LecturaFallida) as error:
        leer_anexo(ruta, rules.CARGUE_INS)

    assert "ALFA" in str(error.value)


def test_lector_ignora_el_rango_inflado_del_archivo(tmp_path) -> None:
    filas = [["INV", f"020{numero:04d}", f"INSUMO {numero}", 1000] for numero in range(5)]
    ruta = _crear_anexo(
        tmp_path,
        "INSUMOS",
        ["COD INVIMA", "COD INTERNO IPS", "DESCRIPCION", "TARIFA OFERTADA"],
        filas,
    )

    anexo = leer_anexo(ruta, rules.CARGUE_INS)

    assert len(anexo.filas) == 5


# ============================================================
# PROCESO COMPLETO
# ============================================================

def test_proceso_completo_genera_txt_y_reportes(tmp_path) -> None:
    ruta = _crear_anexo(
        tmp_path,
        "INSUMOS",
        ["COD INTERNO IPS", "DESCRIPCION", "TARIFA OFERTADA"],
        [
            ["0201361", "CATETER 8 FR (REF HBD-W-18)", 2511460.4],
            ["0205125", "CLIP PADLOCK N° 2", 5849742],
            ["", "SIN CODIGO", 1000],
        ],
    )

    resultado = cargues_service.procesar_anexo(ruta, rules.CARGUE_INS)
    resumen = resultado.resumen()

    assert resumen["registros_leidos"] == 3
    assert resumen["listos_para_cargue"] == 2
    assert resumen["bloqueados"] == 1

    rutas = cargues_service.generar_salidas(resultado, tmp_path / "salidas")
    contenido = rutas["txt"].read_bytes()

    assert contenido == (
        b"0201361;2511460;PRO;0;CATETER 8 FR (REF HBD-W-18);0;"
        b"\r\n"
        b"0205125;5849742;PRO;0;CLIP PADLOCK NRO 2;0;"
    )
    assert rutas["reporte"].exists()
    assert rutas["detalle"].exists()


def test_el_anexo_original_no_se_modifica(tmp_path) -> None:
    ruta = _crear_anexo(
        tmp_path,
        "INSUMOS",
        ["COD INTERNO IPS", "DESCRIPCION", "TARIFA OFERTADA"],
        [["0201361", "CATETER", 2511460]],
    )
    antes = ruta.read_bytes()

    resultado = cargues_service.procesar_anexo(ruta, rules.CARGUE_INS)
    cargues_service.generar_salidas(resultado, tmp_path / "salidas")

    assert ruta.read_bytes() == antes


# ============================================================
# CÓDIGOS CUPS ALFANUMÉRICOS, PROPIOS Y TRASLADOS
# ============================================================

def _cups(codigo, **campos):
    fila = {"_fila": 11, "codigo": codigo, "descripcion": "X", "valor": 1000}
    fila.update(campos)
    return construir_registro(fila, rules.CARGUE_CUPS)


@pytest.mark.parametrize("codigo", ["810116", "129M01", "601T02", "A12345", "PRO6212"])
def test_cups_validos_alfanumericos_y_propios(codigo) -> None:
    assert not _cups(codigo).bloqueado


@pytest.mark.parametrize("codigo", ["44130", "4413022", "129m01", "441-02", "PRO12"])
def test_cups_con_formato_invalido_bloquea(codigo) -> None:
    assert _cups(codigo).bloqueado


def test_cinco_digitos_sugiere_el_cero_inicial() -> None:
    registro = _cups("53109")
    sugerencias = " ".join(h.sugerencia for h in registro.hallazgos)
    assert registro.bloqueado
    assert "053109" in sugerencias


def test_el_cups_alfanumerico_no_cambia_el_txt() -> None:
    registro = _registro(codigo="129M01", valor=362100)
    assert (
        txt_writer.construir_linea(registro, rules.CARGUE_CUPS)
        == "129M01;362100;PRO;0;0;"
    )


@pytest.mark.parametrize("codigo", ["601T01", "602T01", "602T02", "PRO6212"])
def test_traslado_o_propio_regulado_queda_bloqueado(codigo) -> None:
    from src.app.domain.cargues.validators import validar_codigos_propios_y_traslados

    registro = _cups(codigo, tipo_tarifa="UVB", codigo_ley="39601")
    validar_codigos_propios_y_traslados([registro])
    assert any("nunca llevan SOAT" in h.regla for h in registro.hallazgos)
    assert registro.bloqueado


HOMOLOGADOS = {
    "441302": frozenset({"18300"}),
    "129M02": frozenset({"38122", "38123", "38124"}),
}


def test_pro_con_valor_igual_al_soat_queda_bloqueado() -> None:
    from src.app.domain.cargues.validators import validar_contra_homologador

    registro = _cups("441302", tipo_tarifa="PRO", valor=18300)
    validar_contra_homologador([registro], HOMOLOGADOS)

    assert registro.bloqueado
    assert any("código SOAT" in h.problema for h in registro.hallazgos)


def test_pro_con_valor_normal_no_se_marca() -> None:
    from src.app.domain.cargues.validators import validar_contra_homologador

    registro = _cups("441302", tipo_tarifa="PRO", valor=527340)
    validar_contra_homologador([registro], HOMOLOGADOS)

    assert not registro.bloqueado


def test_regulado_con_soat_distinto_al_homologado_bloquea() -> None:
    from src.app.domain.cargues.validators import validar_contra_homologador

    registro = _cups("441302", tipo_tarifa="UVB", codigo_ley="18301")
    validar_contra_homologador([registro], HOMOLOGADOS)

    assert registro.bloqueado
    assert any("18300" in h.sugerencia for h in registro.hallazgos)


@pytest.mark.parametrize("ley", ["38122", "38124"])
def test_regulado_con_uno_de_varios_homologados_pasa(ley) -> None:
    from src.app.domain.cargues.validators import validar_contra_homologador

    registro = _cups("129M02", tipo_tarifa="UVB", codigo_ley=ley)
    validar_contra_homologador([registro], HOMOLOGADOS)

    assert not registro.bloqueado


def test_cups_fuera_del_homologador_no_se_marca_y_se_cuenta() -> None:
    from src.app.domain.cargues.validators import validar_contra_homologador

    registro = _cups("999999", tipo_tarifa="UVB", codigo_ley="1234")
    sin_cruce = validar_contra_homologador([registro], HOMOLOGADOS)

    assert sin_cruce == 1
    assert not registro.bloqueado


def test_servicio_avisa_cuando_no_hay_homologador(tmp_path) -> None:
    ruta = _crear_anexo(
        tmp_path, "SERVICIOS", ["CUPS", "VALOR"], [["441302", 527340]]
    )

    resultado = cargues_service.procesar_anexo(ruta, rules.CARGUE_CUPS)

    assert any(
        "homologador" in h.problema for h in resultado.hallazgos_generales
    )


def test_servicio_bloquea_con_homologador(tmp_path) -> None:
    ruta = _crear_anexo(
        tmp_path, "SERVICIOS", ["CUPS", "VALOR"], [["441302", 18300], ["902216", 12000]]
    )

    resultado = cargues_service.procesar_anexo(
        ruta, rules.CARGUE_CUPS, soat_por_cups=HOMOLOGADOS
    )

    assert resultado.resumen()["bloqueados"] == 1
    assert len(resultado.listos) == 1


def test_traslado_propio_no_se_bloquea() -> None:
    from src.app.domain.cargues.validators import validar_codigos_propios_y_traslados

    registro = _cups("601T02", tipo_tarifa="PRO", valor=35456)
    validar_codigos_propios_y_traslados([registro])
    assert not registro.bloqueado


# ============================================================
# CÓDIGOS DE INSUMO DEL PRESTADOR Y CARACTERES EQUIVALENTES
# ============================================================

def _ins(codigo):
    return construir_registro(
        {"_fila": 5, "codigo": codigo, "descripcion": "TORNILLO", "valor": 1000},
        rules.CARGUE_INS,
    )


@pytest.mark.parametrize(
    "codigo",
    ["128-822/02", "MPF-BT 50 35-S", "PER 11-14-S", "241.021412", "INS0020179", "107-210/41", "CS-093 "],
)
def test_codigos_de_insumo_del_prestador_con_barra_y_espacios_son_validos(codigo) -> None:
    assert not _ins(codigo).bloqueado


@pytest.mark.parametrize("codigo", ["AB;12", "107-210\n41", "CÓDIGO-1"])
def test_codigo_de_insumo_que_rompe_el_archivo_se_bloquea(codigo) -> None:
    assert _ins(codigo).bloqueado


def test_el_codigo_de_insumo_no_se_recorta() -> None:
    """Los códigos de insumo se respetan tal cual, incluso con espacios al final."""

    registro = _ins("CS-093 ")
    assert registro.codigo == "CS-093 "


@pytest.mark.parametrize(
    ("original", "esperado"),
    [
        ("PLACA TIPO Ⅱ", "PLACA TIPO II"),
        ("TORNILLO （3.5）", "TORNILLO (3.5)"),
        ("SUTURA ½ CIRCULO", "SUTURA 1/2 CIRCULO"),
    ],
)
def test_caracteres_equivalentes_pasan_a_ascii(original, esperado) -> None:
    saneada, cambios = sanitizer.sanear_descripcion(original)
    assert saneada == esperado
    assert cambios and not sanitizer.caracteres_no_soportados(saneada)


@pytest.mark.parametrize(
    ("original", "esperado"),
    [
        ("TORNILLO Φ 3.5 MM", "TORNILLO 3.5 MM"),
        ("GUIA φ1.2 MM NITINOL", "GUIA 1.2 MM NITINOL"),
        ("Φ 2.7 MM", "2.7 MM"),
    ],
)
def test_phi_griega_se_elimina_y_queda_registrada(original, esperado) -> None:
    saneada, cambios = sanitizer.sanear_descripcion(original)
    assert saneada == esperado
    assert any("(eliminado)" in cambio for cambio in cambios)


@pytest.mark.parametrize(
    ("original", "esperado"),
    [
        ("Broca calibrada de Ø 7.5 / 2.8 mm CHARFIX₂", "Broca calibrada de D 7.5 / 2.8 mm CHARFIX2"),
        ("Anillo en Ω Ω110mm  S", "Anillo en OMEGA OMEGA110mm  S"),
    ],
)
def test_subindice_dos_y_omega_pasan_a_ascii(original, esperado) -> None:
    saneada, cambios = sanitizer.sanear_descripcion(original)
    assert saneada == esperado
    assert not sanitizer.caracteres_no_soportados(saneada)
    assert cambios


def test_phi_ya_no_bloquea_el_registro() -> None:
    registro = construir_registro(
        {"_fila": 9, "codigo": "INS1", "descripcion": "TORNILLO Φ 3.5 MM", "valor": 1000},
        rules.CARGUE_INS,
    )
    assert not registro.bloqueado
    assert registro.descripcion == "TORNILLO 3.5 MM"
