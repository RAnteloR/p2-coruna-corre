"""Tests de las funciones de limpieza (issues #4 y #9). Datos inventados, sin nombres."""

from src.limpieza import (
    tiempo_a_segundos,
    marcar_tiempo,
    parsear_posto_sexo,
    parsear_posto_categoria,
    limpiar_carrera,
)
import pandas as pd


# --- Tiempos ------

def test_formato_hh_mm_ss():
    assert tiempo_a_segundos("00:28:36") == 1716


def test_formato_mm_ss():
    assert tiempo_a_segundos("28:36") == 1716


def test_quita_espacios():
    assert tiempo_a_segundos(" 00:28:36 ") == 1716


def test_vacio_devuelve_none():
    assert tiempo_a_segundos("") is None
    assert tiempo_a_segundos(None) is None
    assert tiempo_a_segundos(float("nan")) is None   # así llegan los vacíos desde pandas


def test_formato_raro_devuelve_none():
    assert tiempo_a_segundos("abc") is None
    assert tiempo_a_segundos("00:75:00") is None     # 75 minutos no es válido


def test_marcas():
    assert marcar_tiempo(1716) == "ok"
    assert marcar_tiempo(None) == "faltante"
    assert marcar_tiempo(0) == "imposible"
    assert marcar_tiempo(300) == "imposible"         # 5 min: menos que el récord del mundo
    assert marcar_tiempo(4000) == "imposible"        # + de 1 h: fuera del control


# --- Posto por sexo (M-3) ------

def test_posto_sexo():
    assert parsear_posto_sexo("M-3") == ("M", 3)
    assert parsear_posto_sexo("F-229") == ("F", 229)
    assert parsear_posto_sexo(" m-548 ") == ("M", 548)   # espacios y minus


def test_posto_sexo_raro():
    assert parsear_posto_sexo("") == (None, None)
    assert parsear_posto_sexo(None) == (None, None)
    assert parsear_posto_sexo("X-3") == (None, None)     # sexo desconocido
    assert parsear_posto_sexo("M3") == (None, None)      # sin guion


# --- Posto por categoría (MS2M-1) ------

def test_posto_categoria():
    assert parsear_posto_categoria("MS2M-1") == ("MS2", "M", 1)
    assert parsear_posto_categoria("SNRF-80") == ("SNR", "F", 80)
    assert parsear_posto_categoria("SUB23M-6") == ("SUB23", "M", 6)
    assert parsear_posto_categoria("M1M-2") == ("M1", "M", 2)   # formato de la clasificación del circuito


def test_posto_categoria_raro():
    assert parsear_posto_categoria("") == (None, None, None)
    assert parsear_posto_categoria(None) == (None, None, None)
    assert parsear_posto_categoria("MS2-1") == (None, None, None)   # falta el sexo


def test_categorias_especiales():
    assert parsear_posto_categoria("ESPM-1") == ("ESP", "M", 1)     # Especial
    assert parsear_posto_categoria("NO") == (None, None, None)      # sin categoría

def test_tiempo_negativo_es_imposible():
    assert tiempo_a_segundos("-5:00") == -300
    assert marcar_tiempo(tiempo_a_segundos("-5:00")) == "imposible"


def test_bordes_de_los_limites():
    assert marcar_tiempo(12 * 60) == "ok"              # justo 12:00 vale
    assert marcar_tiempo(12 * 60 - 1) == "imposible"
    assert marcar_tiempo(60 * 60) == "ok"              # justo 1:00:00 vale
    assert marcar_tiempo(60 * 60 + 1) == "imposible"

def test_minimo_segun_distancia():
    # Torre de Hércules: 6.625 m -> mínimo 6,625 x 150 = 993,75 s (unos 16:34)
    assert marcar_tiempo(15 * 60, distancia_m=6625) == "imposible"
    assert marcar_tiempo(20 * 60, distancia_m=6625) == "ok"


def test_sin_distancia_usa_12_min():
    assert marcar_tiempo(13 * 60) == "ok"
    assert marcar_tiempo(13 * 60, distancia_m=float("nan")) == "ok"   # Volta a Oza: sin distancia

def test_nan_es_faltante():
    # pandas convierte los None en NaN al usar .map() sobre una columna
    assert marcar_tiempo(float("nan")) == "faltante"



# --- Limpiar una carrera entera --------------------------------------------

def _carrera_inventada():
    return pd.DataFrame({
        "posto": ["1", "2", "3"],
        "dorsal": ["101", "102", "103"],
        "nome": ["ANA", "LUIS", "EVA"],
        "apelidos": ["PEREZ", "GOMEZ", "RUIZ"],
        "posto_sexo": ["F-1", "M-1", "—"],
        "posto_categoria": ["SNRF-1", "MS1M-1", "NO-1"],
        "tempo": ["00:25:00", "00:26:30", "10:28:43"],
    })


def test_limpiar_carrera_columnas_del_contrato():
    limpia = limpiar_carrera(_carrera_inventada(), "carrera_03", distancia_m=6395)
    assert list(limpia.columns) == [
        "carrera_id", "orden", "dorsal", "nome", "apelidos", "posto", "sexo",
        "posto_sexo", "categoria", "posto_categoria", "tempo_s", "tempo_marca",
    ]
    assert len(limpia) == 3                      # no se pierde ninguna fila
    assert (limpia["orden"] == 3).all()


def test_limpiar_carrera_separa_y_convierte():
    limpia = limpiar_carrera(_carrera_inventada(), "carrera_03", distancia_m=6395)
    assert limpia.loc[0, "sexo"] == "F"
    assert limpia.loc[0, "categoria"] == "SNR"
    assert limpia.loc[1, "posto_categoria"] == 1
    assert limpia.loc[0, "tempo_s"] == 1500
    assert limpia.loc[0, "tempo_marca"] == "ok"


def test_limpiar_carrera_fila_sin_categoria():
    limpia = limpiar_carrera(_carrera_inventada(), "carrera_03", distancia_m=6395)
    assert limpia.loc[2, "categoria"] == "SIN_CATEGORIA"
    assert pd.isna(limpia.loc[2, "sexo"])
    assert pd.isna(limpia.loc[2, "posto_categoria"])
    assert limpia.loc[2, "tempo_marca"] == "imposible"     # más de 10 h