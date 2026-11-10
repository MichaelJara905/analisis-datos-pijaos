"""Pruebas de la consulta de referencias.

Se construyen archivos sintéticos con la misma estructura de los reales
(fila de unidad sobre los encabezados, nombres de columna con acentos y
saltos de línea), para no depender de los archivos de producción.
"""

from __future__ import annotations

import json

import pytest
from openpyxl import Workbook

from src.app.application import referencias_service
from src.app.domain.cargues import rules
from src.app.infrastructure.referencias import repositorio


# ============================================================
# ARCHIVOS DE PRUEBA
# ============================================================

def _superhomologador(carpeta):
    libro = Workbook()

    for indice, (sigla, unidad, puntaje) in enumerate(
        [("UVB", 12110, 126.87), ("UVT", 52374, 29.52), ("UVR", 58364, 33.65)]
    ):
        hoja = libro.active if indice == 0 else libro.create_sheet()
        hoja.title = sigla
        hoja.append([f"UNIDAD DE VALOR BÁSICO 2026:", None, None, None, None, unidad])
        hoja.append(
            [
                "CÓDIGO",
                "Descripción",
                "FACTOR CONV.\nUVB",
                "PUNTAJE O GRUPO QX",
                "PUNTAJE",
                "VALOR CALCULADO PUNTAJE*UVB",
                0,
                "DESCUENTO",
                "VALOR RESULTANTE (APROX CENTESIMA MAS CERCANA Y SIN DECIMALES)",
            ]
        )
        hoja.append(
            [
                18300,
                "ESOFAGOGASTRODUODENOSCOPIA",
                9,
                "GRUPO",
                puntaje,
                puntaje * unidad,
                0,
                puntaje * unidad,
                round(puntaje * unidad, -2),
            ]
        )

    homologador = libro.create_sheet("HOMOLOGADOR")
    homologador.append(
        [
            "COD. CUPS  RES. 2775",
            "COD. SOAT",
            "Descripcion SOAT",
            "COD. CUPS",
            "DESCRIPCION SERVICIO O PROCEDIMIENTO",
            "COBERTURA",
        ]
    )
    homologador.append(
        ["441302", 18300, "ESOFAGOGASTRODUODENOSCOPIA", "441302", "EGD", "PBS"]
    )
    homologador.append(
        ["902216", 19646, "GLUCOSA EN SUERO", "902216", "GLUCOSA", "PBS"]
    )
    homologador.append(
        ["902216", 19642, "GLUCOSA PRE Y POST", "902216", "GLUCOSA", "PBS"]
    )

    ruta = carpeta / "SUPERHOMOLOGADOR-2026.xlsx"
    libro.save(ruta)
    return ruta


def _circular(carpeta):
    libro = Workbook()
    hoja = libro.active
    hoja.title = "Precio por unidad"
    hoja.append(
        [
            "No.",
            "CUM/IUM",
            "Medicamento (presentación comercial)",
            "Cantidad por unidad de medida",
            "Unidad de medida",
            "Precio máx. venta Institucional\n(presentación completa)",
            "Precio máx. venta Institucional\nPOR UNIDAD",
            "Margen para IPS\n(presentación completa)",
            "Margen para IPS\nPOR UNIDAD",
            "Circular CNPMDM",
            "Fecha inicio vigencia",
        ]
    )
    hoja.append(
        [
            1,
            "19939438-1",
            "GLIVEC - Imatinib 400 mg",
            12000,
            "mg",
            2477040,
            82568,
            0,
            1200,
            "Circular 04 de 2016",
            "2017-01-22",
        ]
    )

    ruta = carpeta / "CIRCULAR 022 DE 2026 PRECIO MEDICAMENTOS.xlsx"
    libro.save(ruta)
    return ruta


def _maximos(carpeta):
    libro = Workbook()

    agrupado = libro.active
    agrupado.title = "AGRUPADO_DE_SERVICIOS"
    agrupado.append(
        [
            " TIPO SERVICIO",
            " CÓDIGO SERVICIO",
            " VALOR MINIMO DEL SERVICIO",
            " VALOR MAXIMO DEL SERVICIO",
            "\tVALOR PROMEDIO",
            "PROMEDIO CON INCREMENTO",
        ]
    )
    agrupado.append(["CUP", "441302", 132012, 1319900, 830675, 873039.425])
    agrupado.append(["INS", "0201361", 900000, 3000000, 2100000, 2205000])

    detalle = libro.create_sheet("DETALLE_DE_SERVICIOS")
    detalle.append(
        [
            " INICIO VIGENCIA",
            " CÓDIGO SERVICIO",
            " TIPO SERVICIO",
            " VALOR DEL SERVICIO",
            " TIPO TARIFARIO PACTADO",
            " PORCENTAJE TARIFA PACTADA",
            " NOMBRE ORIGINAL DEL SERVICIO",
            " NOMBRE DEL PRESTADOR",
            " NUMERO DE  CONTRATO",
        ]
    )
    detalle.append(
        [2024, "441302", "CUP", 527340, "PROPIA", 0, "EGD", "PRESTADOR X", "41-2024-1"]
    )

    ruta = carpeta / "MAXIMOS Y MINIMOS DEL SISTEMA.xlsx"
    libro.save(ruta)
    return ruta


@pytest.fixture
def carpeta_referencias(tmp_path):
    _superhomologador(tmp_path)
    _circular(tmp_path)
    _maximos(tmp_path)
    return tmp_path


# ============================================================
# DESCUBRIMIENTO Y CARGA
# ============================================================

def test_reconoce_los_tres_archivos(carpeta_referencias) -> None:
    fuentes = repositorio.descubrir_fuentes(carpeta_referencias)

    assert fuentes.faltantes() == []


def test_avisa_cuando_falta_un_archivo(tmp_path) -> None:
    _circular(tmp_path)

    fuentes = repositorio.descubrir_fuentes(tmp_path)

    assert "superhomologador" in fuentes.faltantes()
    assert fuentes.circular is not None


def test_carga_parcial_no_se_cae(tmp_path) -> None:
    _circular(tmp_path)

    referencias = referencias_service.cargar_referencias(tmp_path)

    assert referencias.disponibles() == {
        "superhomologador": False,
        "circular": True,
        "maximos": False,
    }


# ============================================================
# CONSULTAS
# ============================================================

def test_servicio_cruza_manual_y_rango(carpeta_referencias) -> None:
    referencias = referencias_service.cargar_referencias(carpeta_referencias)

    resultado = referencias_service.consultar_servicio(
        referencias,
        "441302",
        porcentaje=-10,
    )

    manuales = {t["manual"]: t for t in resultado["tarifas"]}
    assert set(manuales) == {"UVB", "UVT", "UVR"}
    assert manuales["UVB"]["codigo_ley"] == "18300"
    assert manuales["UVB"]["puntaje"] == 126.87
    assert manuales["UVB"]["valor_manual"] == 1536400
    assert manuales["UVB"]["valor_con_descuento"] == 1382760
    assert resultado["historico"][0]["maximo"] == 1319900


def test_cups_con_dos_codigos_ley_se_marca_ambiguo(carpeta_referencias) -> None:
    referencias = referencias_service.cargar_referencias(carpeta_referencias)

    resultado = referencias_service.consultar_servicio(referencias, "902216")

    assert resultado["ambiguo"] is True


def test_medicamento_regulado_suma_el_margen(carpeta_referencias) -> None:
    referencias = referencias_service.cargar_referencias(carpeta_referencias)

    resultado = referencias_service.consultar_medicamento(referencias, "19939438-1")

    assert resultado["regulado"]["precio_unidad"] == 82568
    assert resultado["regulado"]["costo_total_unidad"] == 83768
    assert resultado["regulado"]["unidad_medida"] == "mg"


def test_medicamento_no_regulado(carpeta_referencias) -> None:
    referencias = referencias_service.cargar_referencias(carpeta_referencias)

    resultado = referencias_service.consultar_medicamento(referencias, "20048691-1")

    assert resultado["regulado"] is None


def test_insumo_solo_tiene_historial(carpeta_referencias) -> None:
    referencias = referencias_service.cargar_referencias(carpeta_referencias)

    resultado = referencias_service.consultar(referencias, "0201361", rules.CARGUE_INS)

    assert resultado["historico"][0]["promedio"] == 2100000
    assert "propia" in resultado["nota"]


def test_busqueda_por_descripcion_ignora_tildes(carpeta_referencias) -> None:
    referencias = referencias_service.cargar_referencias(carpeta_referencias)

    resultados = referencias_service.buscar_por_texto(
        referencias,
        "esofagogastroduodenoscopía",
        rules.CARGUE_CUPS,
    )

    assert resultados and resultados[0]["codigo"] == "441302"


def test_contratos_del_codigo(carpeta_referencias) -> None:
    fuentes = repositorio.descubrir_fuentes(carpeta_referencias)

    contratos = repositorio.contratos_del_codigo(fuentes.maximos, "441302")

    assert len(contratos) == 1
    assert contratos[0]["prestador"] == "PRESTADOR X"


def test_soat_por_cups_agrupa_los_homologados(carpeta_referencias) -> None:
    mapa = referencias_service.cargar_soat_por_cups(carpeta_referencias)

    assert mapa["441302"] == frozenset({"18300"})
    assert mapa["902216"] == frozenset({"19646", "19642"})


def test_soat_por_cups_sin_homologador_falla_claro(tmp_path) -> None:
    _circular(tmp_path)

    with pytest.raises(referencias_service.ReferenciaNoDisponible):
        referencias_service.cargar_soat_por_cups(tmp_path)


# ============================================================
# CACHÉ
# ============================================================

def test_la_cache_se_crea_y_se_reutiliza(carpeta_referencias) -> None:
    referencias_service.cargar_referencias(carpeta_referencias)

    cache = carpeta_referencias / repositorio.CARPETA_CACHE
    assert (cache / "homologador.csv").exists()

    # Segunda carga: mismos datos, ya sin abrir el Excel.
    referencias = referencias_service.cargar_referencias(carpeta_referencias)
    assert referencias.homologos_por_cups["441302"][0]["codigo_ley"] == "18300"


def test_la_cache_se_invalida_al_cambiar_de_version(carpeta_referencias) -> None:
    referencias_service.cargar_referencias(carpeta_referencias)

    meta = carpeta_referencias / repositorio.CARPETA_CACHE / "homologador.json"
    guardado = json.loads(meta.read_text(encoding="utf-8"))
    guardado["version"] = repositorio.VERSION_CACHE - 1
    meta.write_text(json.dumps(guardado), encoding="utf-8")

    fuentes = repositorio.descubrir_fuentes(carpeta_referencias)
    assert repositorio._leer_cache(fuentes.superhomologador, "homologador") is None
