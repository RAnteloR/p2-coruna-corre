"""Rutas y configuración comunes del proyecto.

Todos los notebooks y módulos importan las rutas desde aquí, para no escribirlas a mano:

    from src.config import DIR_RAW, DIR_INTERIM, DIR_CLEAN, leer_clave
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

# Raíz del repositorio: este fichero está en <repo>/src/config.py
RAIZ = Path(__file__).resolve().parents[1]

DIR_DATOS = RAIZ / "datos"
DIR_RAW = DIR_DATOS / "raw"            # páginas descargadas en bytes (no se suben)
DIR_INTERIM = DIR_DATOS / "interim"    # tablas extraídas, aún con nombres (no se suben)
DIR_CLEAN = DIR_DATOS / "clean"        # CSV finales pseudonimizados (no se suben)
DIR_EXTERNOS = DIR_DATOS / "externos"  # ficheros propios o de otras fuentes
DIR_OUTPUT = RAIZ / "output"           # entregas por destinatario
DIR_DOCS = RAIZ / "docs"

# Fecha de corte fija: el análisis usa las 6 carreras disputadas antes de Novo Mesoiro
# (22/11/2026). Se excluye toda carrera con fecha >= FECHA_CORTE, así el resultado no
# cambia según el día en que se ejecute.
FECHA_CORTE = date(2026, 11, 22)

load_dotenv(RAIZ / ".env")


def leer_clave() -> bytes:
    """Devuelve la clave HMAC del grupo (variable CHAVE del fichero .env).

    La clave nunca está en el código ni en el repositorio: cada persona la pone en su
    propio .env (ver .env.example). Si falta, se para con un error claro.
    """
    clave = os.getenv("CHAVE", "").strip()
    if not clave:
        raise RuntimeError(
            "Falta CHAVE: copia .env.example como .env y pon la clave común del grupo."
        )
    return clave.encode("utf-8")
