"""Tests para el cruce de participaciones de carreras con la lista de inscritos."""

import json

import pandas as pd
import pytest

from src.cruce import (
    buscar_archivos_carreras,
    clasificar_cruce,
    ejecutar_cruce_carreras,
    marcar_inscritos,
    resumir_cruce_carrera,
)


def _tabla_inscritos_ejemplo() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"nome": "MARIA-JOSE", "apelidos": "NUNEZ PEREZ", "dorsal": "1001"},
            {"nome": "CARLOS", "apelidos": "GOMEZ LOPEZ", "dorsal": "1002"},
            {"nome": "ANA", "apelidos": "SILVA DIAZ", "dorsal": "1003"},
        ]
    )


def _tabla_carrera_ejemplo() -> pd.DataFrame:
    return pd.DataFrame(
        [
            # Coincide nombre (con tildes, minusculas y espacio en vez de guion) y dorsal -> ambos
            {"nome": "  María José ", "apelidos": "Núñez Pérez", "dorsal": "1001"},
            # Coincide nombre pero llevo otro dorsal ese dia -> solo_nombre
            {"nome": "Carlos", "apelidos": "Gómez López", "dorsal": "9999"},
            # Coincide el dorsal 1003 pero es otra persona -> solo_dorsal (debe ser False)
            {"nome": "Pedro", "apelidos": "Castro Blanco", "dorsal": "1003"},
            # No coincide ni nombre ni dorsal -> ninguno (debe ser False)
            {"nome": "Lucia", "apelidos": "Vidal Rey", "dorsal": "8888"},
        ]
    )


def test_clasificar_cruce_separa_los_cuatro_grupos():
    resultado = clasificar_cruce(_tabla_carrera_ejemplo(), _tabla_inscritos_ejemplo())

    assert list(resultado["tipo_cruce"]) == ["ambos", "solo_nombre", "solo_dorsal", "ninguno"]
    assert list(resultado["inscrito_circuito"]) == [True, True, False, False]


def test_clasificar_cruce_modo_estricto_solo_ambos():
    resultado = clasificar_cruce(
        _tabla_carrera_ejemplo(),
        _tabla_inscritos_ejemplo(),
        incluir_solo_nombre=False,
    )

    assert list(resultado["tipo_cruce"]) == ["ambos", "solo_nombre", "solo_dorsal", "ninguno"]
    assert list(resultado["inscrito_circuito"]) == [True, False, False, False]


def test_marcar_inscritos_solo_anade_columna_oficial_y_no_toca_original():
    carrera = _tabla_carrera_ejemplo()
    columnas_antes = list(carrera.columns)

    marcada = marcar_inscritos(carrera, _tabla_inscritos_ejemplo())

    # La tabla original no debe cambiar
    assert list(carrera.columns) == columnas_antes
    # La salida tiene las columnas originales mas inscrito_circuito (sin tipo_cruce)
    assert list(marcada.columns) == columnas_antes + ["inscrito_circuito"]
    assert marcada["inscrito_circuito"].dtype == bool


def test_cruce_limpia_dorsales_numericos_y_ignora_vacios():
    inscritos = pd.DataFrame(
        [
            {"nome": "MARIA", "apelidos": "PAZ", "dorsal": 1001.0},
            {"nome": "", "apelidos": "", "dorsal": None},
        ]
    )
    carrera = pd.DataFrame(
        [
            # Dorsal leido como entero 1001 debe coincidir con 1001.0
            {"nome": "Maria", "apelidos": "Paz", "dorsal": 1001},
            # Fila vacia nunca debe dar falso positivo contra otra fila vacia
            {"nome": None, "apelidos": None, "dorsal": None},
        ]
    )

    resultado = clasificar_cruce(carrera, inscritos)
    assert list(resultado["tipo_cruce"]) == ["ambos", "ninguno"]
    assert list(resultado["inscrito_circuito"]) == [True, False]


def test_clasificar_cruce_avisa_si_inscritos_vacio_y_falla_si_faltan_columnas():
    inscritos_vacios = pd.DataFrame(columns=["nome", "apelidos", "dorsal"])
    with pytest.warns(UserWarning, match="vacia"):
        resultado = clasificar_cruce(_tabla_carrera_ejemplo(), inscritos_vacios)
    assert list(resultado["inscrito_circuito"]) == [False, False, False, False]

    carrera_mal = pd.DataFrame([{"nome": "Ana", "dorsal": "10"}])
    with pytest.raises(ValueError, match="apelidos"):
        clasificar_cruce(carrera_mal, _tabla_inscritos_ejemplo())


def test_buscar_archivos_carreras_prefiere_tablas_limpias(tmp_path):
    (tmp_path / "inscritos.csv").write_text("nome,apelidos,dorsal\n", encoding="utf-8")
    (tmp_path / "carrera_01.csv").write_text("nome,apelidos,dorsal\n", encoding="utf-8")
    (tmp_path / "carrera_02.csv").write_text("nome,apelidos,dorsal\n", encoding="utf-8")

    # Sin archivos limpios, devuelve los base de carrera
    assert [r.name for r in buscar_archivos_carreras(tmp_path)] == ["carrera_01.csv", "carrera_02.csv"]

    # Si ya existen las tablas limpias de Persona B, las elige primero
    (tmp_path / "carrera_01_limpia.csv").write_text("nome,apelidos,dorsal\n", encoding="utf-8")
    assert [r.name for r in buscar_archivos_carreras(tmp_path)] == ["carrera_01_limpia.csv"]


def test_ejecutar_cruce_carreras_genera_resumen_json(tmp_path):
    ruta_inscritos = tmp_path / "inscritos.csv"
    ruta_carrera = tmp_path / "carrera_01.csv"
    ruta_resumen = tmp_path / "cruce_resumen.json"

    _tabla_inscritos_ejemplo().to_csv(ruta_inscritos, index=False)
    _tabla_carrera_ejemplo().to_csv(ruta_carrera, index=False)

    tabla_resumen = ejecutar_cruce_carreras(
        carpeta_interim=tmp_path,
        ruta_inscritos=ruta_inscritos,
        ruta_resumen=ruta_resumen,
    )

    assert len(tabla_resumen) == 1
    assert resumen_fila_ok(tabla_resumen.iloc[0])

    assert ruta_resumen.exists()
    datos_json = json.loads(ruta_resumen.read_text(encoding="utf-8"))
    assert datos_json["carreras_analizadas"] == 1
    assert datos_json["totales"]["ambos"] == 1
    assert datos_json["totales"]["solo_nombre"] == 1
    assert datos_json["totales"]["solo_dorsal"] == 1
    assert datos_json["totales"]["ninguno"] == 1
    assert datos_json["totales"]["inscritos_true"] == 2
    assert datos_json["totales"]["porcentaje_inscritos"] == 50.0


def resumen_fila_ok(fila) -> bool:
    return (
        fila["carrera_id"] == "carrera_01"
        and fila["total"] == 4
        and fila["inscritos_true"] == 2
        and fila["inscritos_false"] == 2
    )