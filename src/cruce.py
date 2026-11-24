"""Cruce de participaciones de las carreras con la lista de inscritos (Issue #8, Parte 2).

Usa las mismas funciones de normalizacion de nombres de src/ligazon.py para marcar
en cada carrera quien esta inscrito en el circuito (columna inscrito_circuito) y
sacar un diagnostico de los 4 grupos posibles sin mostrar nombres ni dorsales.
"""

from __future__ import annotations

import json
import warnings
from datetime import datetime
from pathlib import Path

import pandas as pd

from src.config import DIR_INTERIM
from src.inscritos import RUTA_CSV_INSCRITOS
from src.ligazon import nombre_completo, normalizar_nombre

RUTA_RESUMEN_CRUCE = DIR_INTERIM / "cruce_resumen.json"
COLUMNAS_NECESARIAS = {"nome", "apelidos", "dorsal"}


def _limpiar_texto(valor) -> str:
    """Convierte un valor de celda a texto limpio y pasa vacios (NaN/None) a cadena vacia."""
    if pd.isna(valor):
        return ""
    return str(valor).strip()


def _limpiar_dorsal(valor) -> str:
    """Deja el dorsal como texto limpio, evitando el tipico '.0' si pandas lo leyo como decimal."""
    if pd.isna(valor):
        return ""
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))

    texto = str(valor).strip()
    if texto.endswith(".0") and texto[:-2].isdigit():
        return texto[:-2]
    return texto


def _comprobar_columnas(tabla: pd.DataFrame, nombre_tabla: str) -> None:
    """Avisa con error claro si a una tabla le falta nome, apelidos o dorsal."""
    faltantes = COLUMNAS_NECESARIAS - set(tabla.columns)
    if faltantes:
        raise ValueError(f"Faltan columnas obligatorias en {nombre_tabla}: {sorted(faltantes)}")


def buscar_archivos_carreras(carpeta_interim: Path = DIR_INTERIM) -> list[Path]:
    """Busca los CSV de carreras en interim/. Si ya existen los limpios de Persona B, usa esos."""
    archivos_limpios = sorted(carpeta_interim.glob("carrera_*_limpia.csv"))
    if archivos_limpios:
        return archivos_limpios

    # Si todavia no se generaron los limpios, cogemos los CSV base de carreras
    return [
        ruta
        for ruta in sorted(carpeta_interim.glob("carrera_*.csv"))
        if not ruta.name.endswith("_limpia.csv") and not ruta.name.endswith("_cruce.csv")
    ]


def clasificar_cruce(
    tabla_carrera: pd.DataFrame,
    tabla_inscritos: pd.DataFrame,
    incluir_solo_nombre: bool = True,
) -> pd.DataFrame:
    """Clasifica cada fila de una carrera en 4 grupos y anade la columna inscrito_circuito.

    Grupos en 'tipo_cruce':
    - ambos: coincide el nombre normalizado y el dorsal del circuito.
    - solo_nombre: coincide el nombre normalizado, pero el dorsal es distinto.
    - solo_dorsal: coincide el dorsal, pero el nombre no (se marca False).
    - ninguno: no coincide ni nombre ni dorsal (se marca False).
    """
    _comprobar_columnas(tabla_carrera, "tabla_carrera")
    _comprobar_columnas(tabla_inscritos, "tabla_inscritos")

    if len(tabla_inscritos) == 0:
        warnings.warn(
            "La tabla de inscritos esta vacia; todas las participaciones saldran como False.",
            UserWarning,
            stacklevel=2,
        )

    # Guardamos los inscritos en conjuntos (sets) porque buscar ahi es instantaneo
    pares_inscritos: set[tuple[str, str]] = set()
    nombres_inscritos: set[str] = set()
    dorsales_inscritos: set[str] = set()

    for fila in tabla_inscritos.itertuples(index=False):
        nombre_norm = normalizar_nombre(
            nombre_completo(_limpiar_texto(fila.nome), _limpiar_texto(fila.apelidos))
        )
        dorsal_limpio = _limpiar_dorsal(fila.dorsal)

        if nombre_norm != "":
            nombres_inscritos.add(nombre_norm)
        if dorsal_limpio != "":
            dorsales_inscritos.add(dorsal_limpio)
        if nombre_norm != "" and dorsal_limpio != "":
            pares_inscritos.add((nombre_norm, dorsal_limpio))

    tipos_cruce: list[str] = []
    marcas_inscrito: list[bool] = []

    for fila in tabla_carrera.itertuples(index=False):
        nombre_norm = normalizar_nombre(
            nombre_completo(_limpiar_texto(fila.nome), _limpiar_texto(fila.apelidos))
        )
        dorsal_limpio = _limpiar_dorsal(fila.dorsal)

        if nombre_norm != "" and dorsal_limpio != "" and (nombre_norm, dorsal_limpio) in pares_inscritos:
            tipo = "ambos"
        elif nombre_norm != "" and nombre_norm in nombres_inscritos:
            tipo = "solo_nombre"
        elif dorsal_limpio != "" and dorsal_limpio in dorsales_inscritos:
            tipo = "solo_dorsal"
        else:
            tipo = "ninguno"

        es_inscrito = tipo == "ambos" or (incluir_solo_nombre and tipo == "solo_nombre")
        tipos_cruce.append(tipo)
        marcas_inscrito.append(es_inscrito)

    # Devolvemos una copia para no modificar la tabla original por accidente
    resultado = tabla_carrera.copy()
    resultado["tipo_cruce"] = tipos_cruce
    resultado["inscrito_circuito"] = marcas_inscrito
    return resultado


def marcar_inscritos(
    tabla_carrera: pd.DataFrame,
    tabla_inscritos: pd.DataFrame,
    incluir_solo_nombre: bool = True,
) -> pd.DataFrame:
    """Devuelve la tabla de carrera con solo la columna oficial 'inscrito_circuito' del contrato."""
    tabla_clasificada = clasificar_cruce(
        tabla_carrera,
        tabla_inscritos,
        incluir_solo_nombre=incluir_solo_nombre,
    )
    return tabla_clasificada.drop(columns=["tipo_cruce"])


def resumir_cruce_carrera(tabla_clasificada: pd.DataFrame, carrera_id: str) -> dict:
    """Saca solo los conteos de una carrera ya clasificada (sin nombres ni dorsales)."""
    total = int(len(tabla_clasificada))
    conteos = tabla_clasificada["tipo_cruce"].value_counts()

    ambos = int(conteos.get("ambos", 0))
    solo_nombre = int(conteos.get("solo_nombre", 0))
    solo_dorsal = int(conteos.get("solo_dorsal", 0))
    ninguno = int(conteos.get("ninguno", 0))
    inscritos_true = int(tabla_clasificada["inscrito_circuito"].sum())
    inscritos_false = total - inscritos_true
    porcentaje_inscritos = round((inscritos_true / total) * 100, 2) if total > 0 else 0.0

    return {
        "carrera_id": carrera_id,
        "total": total,
        "ambos": ambos,
        "solo_nombre": solo_nombre,
        "solo_dorsal": solo_dorsal,
        "ninguno": ninguno,
        "inscritos_true": inscritos_true,
        "inscritos_false": inscritos_false,
        "porcentaje_inscritos": porcentaje_inscritos,
    }


def ejecutar_cruce_carreras(
    carpeta_interim: Path = DIR_INTERIM,
    ruta_inscritos: Path = RUTA_CSV_INSCRITOS,
    ruta_resumen: Path = RUTA_RESUMEN_CRUCE,
    incluir_solo_nombre: bool = True,
) -> pd.DataFrame:
    """Cruza todas las carreras disponibles en interim/ contra inscritos.csv y guarda un resumen JSON."""
    tabla_inscritos = pd.read_csv(ruta_inscritos, dtype=str).fillna("")
    archivos_carreras = buscar_archivos_carreras(carpeta_interim)

    if not archivos_carreras:
        warnings.warn(
            f"No se encontraron archivos de carreras en {carpeta_interim}.",
            UserWarning,
            stacklevel=2,
        )

    filas_resumen = []
    for archivo in archivos_carreras:
        carrera_id = archivo.stem.replace("_limpia", "")
        tabla_carrera = pd.read_csv(archivo, dtype=str).fillna("")
        tabla_clasificada = clasificar_cruce(
            tabla_carrera,
            tabla_inscritos,
            incluir_solo_nombre=incluir_solo_nombre,
        )
        filas_resumen.append(resumir_cruce_carrera(tabla_clasificada, carrera_id))

    tabla_resumen = pd.DataFrame(filas_resumen)

    totales = {
        "total": int(tabla_resumen["total"].sum()) if len(tabla_resumen) else 0,
        "ambos": int(tabla_resumen["ambos"].sum()) if len(tabla_resumen) else 0,
        "solo_nombre": int(tabla_resumen["solo_nombre"].sum()) if len(tabla_resumen) else 0,
        "solo_dorsal": int(tabla_resumen["solo_dorsal"].sum()) if len(tabla_resumen) else 0,
        "ninguno": int(tabla_resumen["ninguno"].sum()) if len(tabla_resumen) else 0,
        "inscritos_true": int(tabla_resumen["inscritos_true"].sum()) if len(tabla_resumen) else 0,
        "inscritos_false": int(tabla_resumen["inscritos_false"].sum()) if len(tabla_resumen) else 0,
    }
    totales["porcentaje_inscritos"] = (
        round((totales["inscritos_true"] / totales["total"]) * 100, 2)
        if totales["total"] > 0
        else 0.0
    )

    resumen_json = {
        "fecha_ejecucion": datetime.now().isoformat(timespec="seconds"),
        "criterio_inscrito": "ambos_y_solo_nombre" if incluir_solo_nombre else "solo_ambos",
        "carreras_analizadas": len(filas_resumen),
        "totales": totales,
        "por_carrera": filas_resumen,
    }
    ruta_resumen.parent.mkdir(parents=True, exist_ok=True)
    ruta_resumen.write_text(json.dumps(resumen_json, indent=2, ensure_ascii=False), encoding="utf-8")

    return tabla_resumen


if __name__ == "__main__":
    print("Ejecutando cruce de carreras contra inscritos.csv...")
    resumen = ejecutar_cruce_carreras()
    print(resumen.to_string(index=False))
    print(f"\nResumen guardado en: {RUTA_RESUMEN_CRUCE}")