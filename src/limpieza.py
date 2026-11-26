"""Funciones de limpieza de los resultados (B, issue #4).

Separan las columnas que en la web mezclan varios datos ('M-3', 'MS2M-1')
y pasan los tiempos a segundos. Si un valor no tiene el formato esperado,
devuelven None para poder contarlo luego en el informe de calidad.
"""

import pandas as pd
import math
import re

TIEMPO_MIN_S = 12 * 60   # mínimo general si no sabemos la distancia
RITMO_MIN_S_KM = 150     # 2:30 min/km: ritmo del récord del mundo de 5 km (12:35)
TIEMPO_MAX_S = 60 * 60   # 1 h: cierre de control (art. 6 de los regulamentos específicos)

PATRON_SEXO = re.compile(r"^([MF])-(\d+)$")                    # M-3
# El '?' hace que la categoría coja lo minimo, para no comerse la letra del sexo
PATRON_CATEGORIA = re.compile(r"^([A-Z0-9]+?)([MF])-(\d+)$")   # MS2M-1


def tiempo_a_segundos(texto):
    """Convierte '00:28:36' o '28:36' a segundos. Si no hay tiempo o no se entiende, devuelve None."""
    # Los vacíos de pandas llegan como NaN
    if texto is None or (isinstance(texto, float) and math.isnan(texto)):
        return None
    texto = str(texto).strip()
    if texto == "":
        return None

    # Un tiempo negativo no es un tiempo que falta: lo convertimos y marcar_tiempo lo dará como imposible
    negativo = texto.startswith("-")
    if negativo:
        texto = texto[1:].strip()

    partes = texto.split(":")
    if len(partes) not in (2, 3) or not all(p.isdigit() for p in partes):
        return None

    numeros = [int(p) for p in partes]
    if len(numeros) == 2:          # mm:ss - añadimos 0 horas
        numeros = [0] + numeros
    h, m, s = numeros
    if m >= 60 or s >= 60:
        return None
    total = h * 3600 + m * 60 + s
    return -total if negativo else total


def marcar_tiempo(segundos, distancia_m=None):
    """Devuelve 'ok', 'faltante' o 'imposible'. No borra nada, solo marca.
    Si se pasa la distancia de la carrera, el mínimo es 2:30 min/km por la distancia.
    Si no se sabe (None o NaN), se usa el mínimo general de 12 min.
    """
    # pandas convierte los None en NaN al usar .map() sobre una columna
    if segundos is None or (isinstance(segundos, float) and math.isnan(segundos)):
        return "faltante"
    if distancia_m is None or (isinstance(distancia_m, float) and math.isnan(distancia_m)):
        minimo = TIEMPO_MIN_S
    else:
        minimo = distancia_m / 1000 * RITMO_MIN_S_KM
    if segundos < minimo or segundos > TIEMPO_MAX_S:
        return "imposible"
    return "ok"


def parsear_posto_sexo(texto):
    """'M-3' -> ('M', 3). Si no encaja con el formato, devuelve (None, None)."""
    if not isinstance(texto, str):
        return (None, None)
    m = PATRON_SEXO.match(texto.strip().upper())
    if not m:
        return (None, None)
    return (m.group(1), int(m.group(2)))


def parsear_posto_categoria(texto):
    """'MS2M-1' -> ('MS2', 'M', 1). Si no encaja con el formato, devuelve (None, None, None)."""
    if not isinstance(texto, str):
        return (None, None, None)
    m = PATRON_CATEGORIA.match(texto.strip().upper())
    if not m:
        return (None, None, None)
    return (m.group(1), m.group(2), int(m.group(3)))


def limpiar_carrera(df, carrera_id, distancia_m=None):
    """Pasa la tabla cruda de interim/ a la tabla limpia de docs/contrato_datos.md.

    No borra ninguna fila: los valores raros se marcan o quedan vacíos.
    """
    sexo = df["posto_sexo"].map(parsear_posto_sexo)
    cat = df["posto_categoria"].map(parsear_posto_categoria)
    segundos = df["tempo"].map(tiempo_a_segundos)
    # Filas sin categoría ni sexo: vienen como "NO-1", "NO-2"... con posto_sexo "—"
    sin_categoria = df["posto_categoria"].str.fullmatch(r"NO-\d+")

    return pd.DataFrame({
        "carrera_id": carrera_id,
        "orden": int(carrera_id.split("_")[1]),        # carrera_03 -> 3
        "dorsal": df["dorsal"],
        "nome": df["nome"],
        "apelidos": df["apelidos"],
        "posto": df["posto"].astype(int),
        "sexo": sexo.map(lambda t: t[0]),
        "posto_sexo": sexo.map(lambda t: t[1]).astype("Int64"),       # Int64 admite vacíos
        "categoria": cat.map(lambda t: t[0]).mask(sin_categoria, "SIN_CATEGORIA"),
        "posto_categoria": cat.map(lambda t: t[2]).astype("Int64"),
        "tempo_s": segundos.astype("Int64"),
        "tempo_marca": segundos.map(lambda s: marcar_tiempo(s, distancia_m)),
    })