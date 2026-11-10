"""Pruebas de la consulta por documento.

Los libros de prueba imitan la estructura de los reales (fila de
encabezados desplazada, encabezados con saltos de línea y tildes, filas
repetidas por rol en el listado) sin depender de los archivos de producción.
"""

from __future__ import annotations

from datetime import date

import pytest
from openpyxl import Workbook

from src.app.application import consulta_service
from src.app.infrastructure.referencias import repositorio
from src.app.infrastructure.referencias.repositorio import ReferenciaNoDisponible


# ============================================================
# LIBROS DE PRUEBA
# ============================================================

def _guardar(libro: Workbook, carpeta, nombre: str):
    ruta = carpeta / nombre
    libro.save(ruta)
    return ruta


def _circular_nueva(carpeta):
    libro = Workbook()
    hoja = libro.active
    hoja.title = "Precio por unidad"
    hoja.append(
        [
            "No.", "ID MR", "Mercado Relevante", "CUM/IUM",
            "Medicamento (presentación comercial)", "Cantidad por unidad de medida",
            "Unidad de medida", "UMD por presentación\n(extraído de la descripción)",
            "PMV Institucional\n(presentación completa)", "PMV Institucional\nPOR UMD\n= I ÷ H",
            "Margen máx. IPS\n(presentación completa)", "Margen máx. IPS\nPOR UMD\n= K ÷ H",
            "VALOR UNITARIO CON MARGEN IPS\n(tope)", "Circular CNPMDM", "Fecha inicio vigencia",
            "% margen IPS aplicado\n(según PMV)", "Criterio de margen",
            "Fundamento normativo del margen", "PMV presentación + margen IPS",
            "Alerta de revisión",
        ]
    )
    hoja.append(
        [1, 5, "Abacavir + Dolutegravir + Lamivudina - Sólido - Oral", "20081132-1",
         "TRIUMEQ - Abacavir 600mg + Dolutegravir 50mg - Sólido - Oral x 30 - GLAXOSMITHKLINE",
         30, "U", 30, 395640, 13188, 27694.8, 923.16, 14111.16, "Circular 22 de 2026", 46000,
         0.07, "Regla general: PMV ≤ umbral", "Art. 11 Circ. 018/2024", 423334.8, None]
    )
    hoja.append(
        [2, 91, "Imatinib - Sólido - Oral", "19939438-1", "GLIVEC - Imatinib 400 mg x 30",
         12000, "mg", 30, 2477040, 82568, 0, 0, 82568, "Circular 04 de 2016", 42757,
         0, "Excepción expresa", "Circ. 04/2016 art. 5", 2477040, "PMV de otra circular"]
    )
    return _guardar(libro, carpeta, "Precios por unidad Circular 022_2026.xlsx")


def _circular_anterior(carpeta):
    libro = Workbook()
    hoja = libro.active
    hoja.title = "Precio por unidad"
    hoja.append(
        [
            "No.", "CUM/IUM", "Medicamento (presentación comercial)", "Unidad de medida",
            "Precio máx. venta Institucional\n(presentación completa)",
            "Precio máx. venta Institucional\nPOR UNIDAD",
            "Margen para IPS\n(presentación completa)", "Margen para IPS\nPOR UNIDAD",
            "Circular CNPMDM", "Fecha inicio vigencia",
        ]
    )
    hoja.append([1, "19939438-1", "GLIVEC", "mg", 2477040, 82568, 0, 1200, "Circular 04 de 2016", "2017-01-22"])
    return _guardar(libro, carpeta, "CIRCULAR 022 DE 2026 MEDICAMENTOS.xlsx")


ENCABEZADO_LISTADO = [
    "CUMS", "EXPEDIENTE", "PRODUCTO", "TITULAR", "REGISTRO SANITARIO", "FECHA EXPEDICION",
    "FECHA VENCIMIENTO", "ESTADO REGISTRO", "EXPEDIENTE CUM", "CONSECUTIVO", "CANTIDAD CUM",
    "DESCRIPCIÓN COMERCIAL", "ESTADO CUM", "FECHA ACTIVO", "FECHA INACTIVO", "MUESTRA MÉDICA",
    "UNIDAD", "ATC", "DESCRIPCIÓN_ATC", "VÍA ADMINISTRACIÓN", "CONCENTRACIÓN",
    "PRINCIPIO ACTIVO", "UNIDAD MEDIDA", "CANTIDAD", "UNIDAD REFERENCIA",
    "FORMA FARMACÉUTICA", "NOMBRE ROL", "TIPO ROL", "MODALIDAD", "IUM",
]


def _fila_listado(cums, expediente, producto, estado, vencimiento="3000-01-01", rol="Titular"):
    fila = [None] * len(ENCABEZADO_LISTADO)
    valores = {
        "CUMS": cums, "EXPEDIENTE": expediente, "PRODUCTO": producto,
        "TITULAR": "LAB X", "REGISTRO SANITARIO": "INVIMA 2021M-1",
        "FECHA EXPEDICION": "1999-12-20", "FECHA VENCIMIENTO": vencimiento,
        "ESTADO REGISTRO": "Vigente", "DESCRIPCIÓN COMERCIAL": "CAJA X 30",
        "ESTADO CUM": estado, "FECHA ACTIVO": "2011-02-08", "MUESTRA MÉDICA": "No",
        "ATC": "G04BE08", "DESCRIPCIÓN_ATC": "tadalafilo", "VÍA ADMINISTRACIÓN": "ORAL",
        "CONCENTRACIÓN": "5 MG", "PRINCIPIO ACTIVO": "TADALAFILO",
        "FORMA FARMACÉUTICA": "TABLETA", "NOMBRE ROL": rol, "IUM": "1C100",
    }
    for nombre, valor in valores.items():
        fila[ENCABEZADO_LISTADO.index(nombre)] = valor
    return fila


def _listado(carpeta):
    libro = Workbook()
    hoja = libro.active
    hoja.title = "Vigentes"
    for _ in range(4):
        hoja.append([])
    hoja.append([None, None, "Fecha de Generación: 16 de Septiembre de 2026"])
    hoja.append([])
    hoja.append(ENCABEZADO_LISTADO)
    hoja.append(_fila_listado("3521-1", "3521", "ALERCET JARABE", "Inactivo"))
    hoja.append(_fila_listado("3521-3", "3521", "ALERCET JARABE", "Activo"))
    hoja.append(_fila_listado("20098922-12", "20098922", "LUDIKA TABLETAS", "Activo", "2020-01-01", "Fabricante"))
    hoja.append(_fila_listado("20098922-12", "20098922", "LUDIKA TABLETAS", "Activo", "2020-01-01", "Importador"))
    return _guardar(libro, carpeta, "ListadoCodigoUnicoVigentesSeptiembre2026.xlsx")


def _trazabilidad(carpeta):
    libro = Workbook()
    hoja = libro.active
    hoja.title = "Trazabilidad"
    for _ in range(5):
        hoja.append([])
    hoja.append(
        ["Anexo", "Código sin puntos ()", "Código con puntos (.)",
         "DESCRIPCIÓN RES 2641 DE 2024", "TRAZABILIDAD", "Anexo",
         "Código sin puntos ()", "Código con puntos (.)", "DESCRIPCIÓN RESOLUCIÓN 2706 DE 2025"]
    )
    hoja.append(["Anexo 2", "Sección 00 PROCEDIMIENTOS", "x", "x", "1", "Anexo 2", "Sección 00 PROCEDIMIENTOS", "x", "x"])
    hoja.append(["Anexo 2", "44", "44.", "GRUPO", "1", "Anexo 2", "44", "44.", "GRUPO"])
    hoja.append(["Anexo 2", "441302", "44.1.3.02", "EGD", "1", "Anexo 2", "441302", "44.1.3.02", "EGD CON O SIN BIOPSIA"])
    hoja.append(["Anexo 2", "920203", "92.0.2.03", "RECORRIDO CORPORAL I-131", "3 y 4",
                 "Anexo 2", "921304", "92.1.3.04", "RECORRIDO CORPORAL RASTREO DE METASTASIS"])
    hoja.append(["Anexo 2", "921304", "92.1.3.04", "RASTREO", "1", "Anexo 2", "921304", "92.1.3.04", "RECORRIDO CORPORAL RASTREO DE METASTASIS"])
    hoja.append(["Anexo 2", "936101", "93.6.1.01", "TRATAMIENTO MANIPULATIVO", "5", None, None, None, None])
    hoja.append(["Anexo 4", "601T02", "601T02", "TRASLADO SECUNDARIO", "1", "Anexo 4", "601T02", "601T02", "TRASLADO ASISTENCIAL BASICO TERRESTRE SECUNDARIO"])
    hoja.append(["Anexo 2", "053109", "05.3.1.09", "BLOQUEO DE NERVIOS PUDENDOS", "1", "Anexo 2", "053109", "05.3.1.09", "BLOQUEO DE NERVIOS PUDENDOS"])

    conv = libro.create_sheet("Convenciones")
    for _ in range(9):
        conv.append([])
    conv.append(["Trazabilidad o calificación de ajuste", "Tipo de Modificación"])
    conv.append(["1", "SE MANTIENE IGUAL"])
    conv.append(["3 y 4", "DESCRIPCIÓN MODIFICADA Y REUBICADO"])
    conv.append(["5", "SE ELIMINA POR ESTAR CONTENIDO EN OTRO PROCEDIMIENTO"])
    return _guardar(libro, carpeta, "Trazabilidad  Resolución 2706 de 2025_23122025.xlsx")


def _superhomologador(carpeta):
    libro = Workbook()
    for indice, (sigla, unidad, calculado, resultante) in enumerate(
        [
            ("UVB", 12110, 1536395.7, 1536400),
            ("UVT", 52374, 1546080.48, 1422400),   # la hoja trae -8% incorporado
            ("UVR", 58364, 1963948.6, 1963900),
        ]
    ):
        hoja = libro.active if indice == 0 else libro.create_sheet()
        hoja.title = sigla
        hoja.append(["UNIDAD", None, None, None, None, unidad])
        hoja.append(
            ["CÓDIGO", "Descripción", "FACTOR CONV.\nUVB", "PUNTAJE O GRUPO QX", "PUNTAJE",
             "VALOR CALCULADO PUNTAJE*UVB", -0.08 if sigla == "UVT" else 0, "DESCUENTO",
             "VALOR RESULTANTE (APROX CENTESIMA MAS CERCANA Y SIN DECIMALES)"]
        )
        hoja.append([18300, "ESOFAGOGASTRODUODENOSCOPIA", 6, "GRUPO", 126.87, calculado, 0, calculado, resultante])

    homologador = libro.create_sheet("HOMOLOGADOR")
    homologador.append(
        ["COD. CUPS  RES. 2775", "COD. SOAT", "Descripcion SOAT", "COD. CUPS",
         "DESCRIPCION SERVICIO O PROCEDIMIENTO", "COBERTURA"]
    )
    homologador.append(["441302", 18300, "ESOFAGOGASTRODUODENOSCOPIA", "441302", "EGD CON O SIN BIOPSIA", "PBS"])
    homologador.append(["902216", 19646, "LEUCOCITOS TOTAL", "902216", "LEUCOGRAMA", "PBS"])
    homologador.append(["902216", 19642, "LEUCOCITOS DIFERENCIAL", "902216", "LEUCOGRAMA", "PBS"])
    return _guardar(libro, carpeta, "SUPERHOMOLOGADOR-2026.xlsx")


@pytest.fixture
def carpeta(tmp_path):
    _circular_nueva(tmp_path)
    _listado(tmp_path)
    _trazabilidad(tmp_path)
    _superhomologador(tmp_path)
    return tmp_path


# ============================================================
# DESCUBRIMIENTO
# ============================================================

def test_reconoce_los_cuatro_documentos(carpeta) -> None:
    fuentes = repositorio.descubrir_fuentes(carpeta)

    assert fuentes.circular.name.startswith("Precios por unidad")
    assert fuentes.listado_cum is not None
    assert fuentes.trazabilidad is not None
    assert fuentes.superhomologador is not None


def test_prefiere_la_circular_nueva_sobre_la_anterior(carpeta) -> None:
    _circular_anterior(carpeta)

    fuentes = repositorio.descubrir_fuentes(carpeta)

    assert fuentes.circular.name == "Precios por unidad Circular 022_2026.xlsx"


def test_encuentra_los_documentos_en_subcarpetas(tmp_path) -> None:
    for subcarpeta, crear in (
        ("CIRCULARES", _circular_nueva),
        ("MEDICAMENTOS", _listado),
        ("CUPS 2026", _trazabilidad),
    ):
        destino = tmp_path / subcarpeta
        destino.mkdir()
        crear(destino)
    _superhomologador(tmp_path)

    fuentes = repositorio.descubrir_fuentes(tmp_path)

    assert fuentes.circular.parent.name == "CIRCULARES"
    assert fuentes.listado_cum.parent.name == "MEDICAMENTOS"
    assert fuentes.trazabilidad.parent.name == "CUPS 2026"
    assert fuentes.superhomologador.parent == tmp_path


def test_prefiere_el_archivo_mas_cercano_a_la_carpeta(tmp_path) -> None:
    viejo = tmp_path / "copias"
    viejo.mkdir()
    _listado(viejo)
    _listado(tmp_path)

    assert repositorio.descubrir_fuentes(tmp_path).listado_cum.parent == tmp_path


def test_no_entra_a_las_carpetas_ocultas_ni_a_la_cache(tmp_path) -> None:
    oculta = tmp_path / ".cache_referencias"
    oculta.mkdir()
    _listado(oculta)

    assert repositorio.descubrir_fuentes(tmp_path).listado_cum is None


def test_estado_de_fuentes_informa_lo_que_falta(tmp_path) -> None:
    _listado(tmp_path)

    estado = consulta_service.estado_de_fuentes(tmp_path)

    assert estado["listado_cum"]["archivo"] is not None
    assert estado["circular"]["archivo"] is None


def test_documento_ausente_falla_claro(tmp_path) -> None:
    with pytest.raises(ReferenciaNoDisponible):
        consulta_service.cargar_listado(tmp_path)


# ============================================================
# CIRCULAR 022
# ============================================================

def test_circular_busca_por_cum_y_muestra_el_tope(carpeta) -> None:
    circular = consulta_service.cargar_circular(carpeta)

    (ficha,) = consulta_service.consultar_circular(circular, "20081132-1")

    assert ficha["tope"] == pytest.approx(14111.16)
    assert ficha["pmv_por_umd"] == 13188
    assert ficha["margen_por_umd"] == pytest.approx(923.16)
    assert ficha["porcentaje_margen"] == 7.0
    assert ficha["umd_presentacion"] == "30"
    assert ficha["vigencia"] == "2025-12-09"  # serie de Excel 46000


def test_circular_busca_por_nombre_sin_tildes(carpeta) -> None:
    circular = consulta_service.cargar_circular(carpeta)

    fichas = consulta_service.consultar_circular(circular, "dolutegravir sólido")

    assert [f["cum"] for f in fichas] == ["20081132-1"]


def test_circular_excepcion_conserva_alerta_y_criterio(carpeta) -> None:
    circular = consulta_service.cargar_circular(carpeta)

    (ficha,) = consulta_service.consultar_circular(circular, "19939438-1")

    assert ficha["tope"] == 82568
    assert ficha["criterio"] == "Excepción expresa"
    assert ficha["alerta"] == "PMV de otra circular"


def test_circular_anterior_calcula_el_tope_sumando_el_margen(tmp_path) -> None:
    _circular_anterior(tmp_path)
    circular = consulta_service.cargar_circular(tmp_path)

    (ficha,) = consulta_service.consultar_circular(circular, "19939438-1")

    assert ficha["tope"] == 82568 + 1200


@pytest.mark.parametrize(
    ("valor", "estado"),
    [(14111.16, "DENTRO DEL TOPE"), (10000, "DENTRO DEL TOPE"), (14200, "SUPERA EL TOPE"), (None, "SIN DATOS")],
)
def test_evaluar_valor_contra_el_tope(valor, estado) -> None:
    assert consulta_service.evaluar_valor(14111.16, valor)["estado"] == estado


def test_evaluar_valor_informa_la_diferencia() -> None:
    veredicto = consulta_service.evaluar_valor(1000, 1100)
    assert veredicto["diferencia"] == 100
    assert veredicto["porcentaje"] == 10.0


# ============================================================
# LISTADO CUM
# ============================================================

def test_listado_deja_un_registro_por_cum(carpeta) -> None:
    listado = consulta_service.cargar_listado(carpeta)

    assert set(listado.por_cums) == {"3521-1", "3521-3", "20098922-12"}
    assert "16 de Septiembre de 2026" in listado.generado


def test_estado_activo_inactivo_y_ausente(carpeta) -> None:
    listado = consulta_service.cargar_listado(carpeta)
    hoy = date(2026, 11, 10)

    assert consulta_service.consultar_listado(listado, "3521-3", hoy=hoy)["fichas"][0]["estado"] == "ACTIVO"
    assert consulta_service.consultar_listado(listado, "3521-1", hoy=hoy)["fichas"][0]["estado"] == "INACTIVO"
    ausente = consulta_service.consultar_listado(listado, "99999-9", hoy=hoy)["fichas"][0]
    assert ausente["estado"] == "NO ESTÁ EN EL LISTADO"
    assert "inactivo" in ausente["nota"]


def test_listado_muestra_otras_presentaciones_del_expediente(carpeta) -> None:
    listado = consulta_service.cargar_listado(carpeta)

    resultado = consulta_service.consultar_listado(listado, "3521-3")

    assert [p["cum"] for p in resultado["mismo_expediente"]] == ["3521-1"]
    assert resultado["mismo_expediente"][0]["estado"] == "INACTIVO"


def test_listado_marca_el_registro_vencido(carpeta) -> None:
    listado = consulta_service.cargar_listado(carpeta)

    ficha = consulta_service.consultar_listado(listado, "20098922-12", hoy=date(2026, 11, 10))["fichas"][0]

    assert ficha["registro_vencido"] is True
    assert ficha["estado"] == "ACTIVO"


def test_listado_busca_por_expediente_y_por_texto(carpeta) -> None:
    listado = consulta_service.cargar_listado(carpeta)

    por_expediente = consulta_service.consultar_listado(listado, "3521")
    por_texto = consulta_service.consultar_listado(listado, "ludika")

    assert por_expediente["modo"] == "expediente"
    assert {f["cum"] for f in por_expediente["fichas"]} == {"3521-1", "3521-3"}
    assert [f["cum"] for f in por_texto["fichas"]] == ["20098922-12"]


# ============================================================
# TRAZABILIDAD 2706
# ============================================================

def test_trazabilidad_cups_vigente(carpeta) -> None:
    trazabilidad = consulta_service.cargar_trazabilidad(carpeta)

    ficha = consulta_service.consultar_trazabilidad(trazabilidad, "441302")["ficha"]

    assert ficha["estado"] == "VIGENTE 2026"
    assert ficha["puede_autorizarse"] is True
    assert ficha["significado"] == "SE MANTIENE IGUAL"


def test_trazabilidad_acepta_alfanumericos_y_ceros_perdidos(carpeta) -> None:
    trazabilidad = consulta_service.cargar_trazabilidad(carpeta)

    traslado = consulta_service.consultar_trazabilidad(trazabilidad, "601T02")["ficha"]
    sin_cero = consulta_service.consultar_trazabilidad(trazabilidad, "53109.0")["ficha"]

    assert traslado["puede_autorizarse"] is True
    assert sin_cero["codigo"] == "053109" and sin_cero["puede_autorizarse"] is True


def test_trazabilidad_codigo_anterior_muestra_el_reemplazo(carpeta) -> None:
    trazabilidad = consulta_service.cargar_trazabilidad(carpeta)

    ficha = consulta_service.consultar_trazabilidad(trazabilidad, "920203")["ficha"]

    assert ficha["estado"] == "NO VIGENTE"
    assert ficha["puede_autorizarse"] is False
    assert ficha["reemplazos"][0]["codigo"] == "921304"
    assert "REUBICADO" in ficha["significado"]


def test_trazabilidad_codigo_vigente_indica_de_cual_viene(carpeta) -> None:
    trazabilidad = consulta_service.cargar_trazabilidad(carpeta)

    ficha = consulta_service.consultar_trazabilidad(trazabilidad, "921304")["ficha"]

    assert ficha["puede_autorizarse"] is True
    assert ficha["viene_de"] == ["920203"]


def test_trazabilidad_eliminado_no_tiene_reemplazo(carpeta) -> None:
    trazabilidad = consulta_service.cargar_trazabilidad(carpeta)

    ficha = consulta_service.consultar_trazabilidad(trazabilidad, "936101")["ficha"]

    assert ficha["estado"] == "NO VIGENTE"
    assert ficha["reemplazos"] == []


def test_trazabilidad_codigo_ausente_no_se_puede_autorizar(carpeta) -> None:
    trazabilidad = consulta_service.cargar_trazabilidad(carpeta)

    ficha = consulta_service.consultar_trazabilidad(trazabilidad, "111111")["ficha"]

    assert ficha["estado"] == "NO ESTÁ EN LA RESOLUCIÓN 2706"
    assert ficha["puede_autorizarse"] is False


def test_trazabilidad_solo_cuenta_codigos_de_seis_caracteres(carpeta) -> None:
    trazabilidad = consulta_service.cargar_trazabilidad(carpeta)

    assert "44" not in trazabilidad.vigentes
    assert "441302" in trazabilidad.vigentes


def test_trazabilidad_busca_por_descripcion(carpeta) -> None:
    trazabilidad = consulta_service.cargar_trazabilidad(carpeta)

    resultado = consulta_service.consultar_trazabilidad(trazabilidad, "rastreo de metastasis")

    assert resultado["modo"] == "texto"
    assert {c["codigo"] for c in resultado["coincidencias"]} == {"921304", "920203"}


# ============================================================
# SUPERHOMOLOGADOR
# ============================================================

def test_homologador_busca_por_cups_soat_y_descripcion(carpeta) -> None:
    referencias = consulta_service.cargar_superhomologador(carpeta)

    por_cups = consulta_service.buscar_homologador(referencias, "441302")
    por_soat = consulta_service.buscar_homologador(referencias, "18300")
    por_texto = consulta_service.buscar_homologador(referencias, "leucograma")

    assert [f["codigo_ley"] for f in por_cups] == ["18300"]
    assert [f["cups"] for f in por_soat] == ["441302"]
    assert {f["codigo_ley"] for f in por_texto} == {"19646", "19642"}


def test_tarifa_parte_del_valor_sin_el_descuento_de_la_hoja(carpeta) -> None:
    from src.app.application import referencias_service

    referencias = consulta_service.cargar_superhomologador(carpeta)

    tarifas = {t["manual"]: t for t in referencias_service.consultar_servicio(referencias, "441302")["tarifas"]}

    assert tarifas["UVB"]["valor_manual"] == 1536400
    assert tarifas["UVT"]["valor_manual"] == 1546100      # centena de 1.546.080,48
    assert tarifas["UVT"]["valor_hoja"] == 1422400        # con el -8% de la hoja


def test_descuento_del_usuario_no_se_suma_al_de_la_hoja(carpeta) -> None:
    from src.app.application import referencias_service

    referencias = consulta_service.cargar_superhomologador(carpeta)

    uvt = next(
        t for t in referencias_service.consultar_servicio(referencias, "441302", porcentaje=-10)["tarifas"]
        if t["manual"] == "UVT"
    )

    assert uvt["valor_con_descuento"] == 1391490           # 1.546.100 x 0,90


# ============================================================
# CACHÉ LOCAL
# ============================================================

def test_la_cache_local_no_escribe_junto_al_original(carpeta, tmp_path_factory, monkeypatch) -> None:
    destino = tmp_path_factory.mktemp("cache")
    monkeypatch.setattr(repositorio, "DIRECTORIO_CACHE", destino)

    consulta_service.cargar_listado(carpeta)

    assert list(destino.glob("*listado_cum.csv"))
    assert not (carpeta / repositorio.CARPETA_CACHE).exists()

    segunda = consulta_service.cargar_listado(carpeta)   # sale de la caché
    assert "3521-3" in segunda.por_cums


def test_la_firma_cambia_cuando_cambia_el_archivo(carpeta) -> None:
    antes = consulta_service.firma_de_fuente(carpeta, "listado_cum")
    ruta = carpeta / "ListadoCodigoUnicoVigentesSeptiembre2026.xlsx"
    contenido = ruta.read_bytes()
    ruta.write_bytes(contenido + b"\0")

    assert consulta_service.firma_de_fuente(carpeta, "listado_cum") != antes
