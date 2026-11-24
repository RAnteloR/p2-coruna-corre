"""Descarga y lectura de la lista de inscritos del circuito (Issue #8, Hito 1).

Este archivo descarga todas las paginas de inscritos usando la funcion comun
de descarga, las guarda en datos/raw/inscritos/ y genera datos/interim/inscritos.csv
junto con un resumen en datos/interim/inscritos_resumen.json.
Nunca imprime nombres ni dorsales por pantalla, solo numeros de conteo.
"""

from __future__ import annotations

import json
import re
import unicodedata
import warnings
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pandas as pd
from bs4 import BeautifulSoup

from src.config import DIR_INTERIM, DIR_RAW
from src.obtencion import descargar

URL_BASE_INSCRITOS = "https://corunacorre.com/gl/web/inscripcion/listado/"
CARPETA_RAW_INSCRITOS = DIR_RAW / "inscritos"
RUTA_CSV_INSCRITOS = DIR_INTERIM / "inscritos.csv"
RUTA_RESUMEN_INSCRITOS = DIR_INTERIM / "inscritos_resumen.json"
MAX_PAGINAS = 200

# Aceptamos las cabeceras tanto en castellano como en gallego por si la web cambia
EQUIVALENCIAS_COLUMNAS = {
    "nombre": "nome",
    "nome": "nome",
    "apellidos": "apelidos",
    "apelidos": "apelidos",
    "dorsal": "dorsal",
    "pagado": "pagado",
    "estado": "estado",
}
COLUMNAS_SALIDA = ["nome", "apelidos", "dorsal", "pagado", "estado"]
COLUMNAS_OBLIGATORIAS = {"nome", "apelidos", "dorsal"}


def _limpiar_texto_cabecera(texto: str) -> str:
    """Pasa una cabecera a minusculas, sin tildes ni simbolos raros (como flechas)."""
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z]", "", sin_tildes.lower())


def _leer_estado_celda(celda) -> str:
    """Saca el estado aunque venga como un icono en vez de texto."""
    texto = celda.get_text(strip=True)
    if texto:
        return texto

    # En la web real el estado es un icono <i> de FontAwesome (por ejemplo fa-check-circle-o)
    icono = celda.find("i")
    if icono is None:
        return ""

    clases_icono = icono.get("class", [])
    for clase in clases_icono:
        if "check" in clase:
            return "confirmado"

    # Si sale cualquier otro icono distinto al tick, guardamos su nombre para verlo luego
    clases_utiles = [clase for clase in clases_icono if clase != "fa"]
    return " ".join(clases_utiles)


def extraer_total_web(html_bytes: bytes) -> int | None:
    """Lee el numero total de inscritos que sale en la cabecera de la web."""
    sopa = BeautifulSoup(html_bytes, "html.parser")

    # Primero buscamos dentro del bloque de cabecera exacto y si no en cualquier h1
    etiqueta_contador = sopa.select_one("div.page-header-web h1 span.badge")
    if etiqueta_contador is None:
        etiqueta_contador = sopa.select_one("h1 span.badge")

    if etiqueta_contador is None:
        return None

    # Quitamos puntos o espacios por si el numero viene escrito como "2.345"
    solo_digitos = re.sub(r"[^\d]", "", etiqueta_contador.get_text(strip=True))
    return int(solo_digitos) if solo_digitos else None


def parsear_pagina_inscritos(html_bytes: bytes) -> list[dict[str, str]]:
    """Lee el HTML de una pagina y saca las filas buscando cada columna por su cabecera."""
    sopa = BeautifulSoup(html_bytes, "html.parser")
    tabla = sopa.find("table")
    if tabla is None:
        return []

    # Sacamos las cabeceras de la tabla para saber en que posicion esta cada dato
    cabeceras_html = tabla.find_all("th")
    mapa_columnas: dict[str, int] = {}
    for indice, th in enumerate(cabeceras_html):
        clave_limpia = _limpiar_texto_cabecera(th.get_text(" ", strip=True))
        nombre_columna = EQUIVALENCIAS_COLUMNAS.get(clave_limpia)
        if nombre_columna is not None:
            mapa_columnas[nombre_columna] = indice

    # Si faltan cabeceras basicas, avisamos con error para no mezclar datos a ciegas
    faltantes = COLUMNAS_OBLIGATORIAS - set(mapa_columnas.keys())
    if faltantes:
        raise ValueError(f"Faltan cabeceras obligatorias en la tabla de inscritos: {sorted(faltantes)}")

    # Si la tabla tiene tbody cogemos las filas de ahi para saltarnos la fila de cabeceras
    cuerpo = tabla.find("tbody")
    filas_html = cuerpo.find_all("tr") if cuerpo else tabla.find_all("tr")[1:]

    lista_inscritos = []
    for fila in filas_html:
        celdas = fila.find_all("td")
        if not celdas:
            continue

        registro: dict[str, str] = {}
        for columna in COLUMNAS_SALIDA:
            posicion = mapa_columnas.get(columna)
            if posicion is None or posicion >= len(celdas):
                registro[columna] = ""
            elif columna == "estado":
                registro[columna] = _leer_estado_celda(celdas[posicion])
            else:
                registro[columna] = celdas[posicion].get_text(strip=True)

        lista_inscritos.append(registro)

    return lista_inscritos


def tiene_pagina_siguiente(html_bytes: bytes, pagina_actual: int) -> bool:
    """Funciona como un hasNext(): comprueba si existe el numero exacto de la pagina siguiente."""
    sopa = BeautifulSoup(html_bytes, "html.parser")
    pagina_buscada = pagina_actual + 1

    for enlace in sopa.find_all("a", href=True):
        # Sacamos los parametros de la URL (?page=2) para comparar el numero exacto
        parametros = parse_qs(urlsplit(enlace["href"]).query)
        for valor in parametros.get("page", []):
            if valor.isdigit() and int(valor) == pagina_buscada:
                return True

    return False


def comprobar_total_inscritos(total_descargado: int, total_en_web: int | None) -> list[str]:
    """Comprueba si las filas descargadas cuadran con la web y lanza aviso si no coinciden."""
    avisos = []

    if total_en_web is None:
        mensaje = "No se pudo leer el total de inscritos anunciado en la web."
        warnings.warn(mensaje, UserWarning, stacklevel=2)
        avisos.append(mensaje)
    elif total_descargado != total_en_web:
        mensaje = (
            f"El total descargado ({total_descargado}) no coincide con "
            f"el anunciado en la web ({total_en_web})."
        )
        warnings.warn(mensaje, UserWarning, stacklevel=2)
        avisos.append(mensaje)

    return avisos


def descargar_inscritos(
    forzar: bool = False,
    max_paginas: int = MAX_PAGINAS,
) -> list[Path]:
    """Recorre todas las paginas de inscritos y guarda cada HTML en datos/raw/inscritos/."""
    CARPETA_RAW_INSCRITOS.mkdir(parents=True, exist_ok=True)
    rutas_guardadas = []
    numero_pagina = 1

    while numero_pagina <= max_paginas:
        # La pagina 1 es la URL base, a partir de la 2 ponemos ?page=N
        if numero_pagina == 1:
            url_pagina = URL_BASE_INSCRITOS
        else:
            url_pagina = f"{URL_BASE_INSCRITOS}?page={numero_pagina}"

        ruta_destino = CARPETA_RAW_INSCRITOS / f"pagina_{numero_pagina:03d}.html"
        html_bytes = descargar(url_pagina, destino=ruta_destino, forzar=forzar)
        rutas_guardadas.append(ruta_destino)

        # Corte de seguridad por si la pagina viene vacia
        filas = parsear_pagina_inscritos(html_bytes)
        if len(filas) == 0:
            break

        # Si no hay enlace exacto a la pagina siguiente, hemos llegado al final
        if not tiene_pagina_siguiente(html_bytes, numero_pagina):
            break

        numero_pagina += 1
    else:
        warnings.warn(
            f"Se alcanzo el limite maximo de {max_paginas} paginas al descargar inscritos.",
            UserWarning,
            stacklevel=2,
        )

    return rutas_guardadas


def construir_inscritos_csv(
    rutas_paginas: list[Path] | None = None,
    ruta_csv: Path = RUTA_CSV_INSCRITOS,
    ruta_resumen: Path = RUTA_RESUMEN_INSCRITOS,
) -> pd.DataFrame:
    """Lee todos los HTML guardados, crea inscritos.csv, comprueba el total y guarda el resumen JSON."""
    if rutas_paginas is None:
        rutas_paginas = sorted(CARPETA_RAW_INSCRITOS.glob("pagina_*.html"))

    todos_los_inscritos = []
    total_en_web = None

    for indice, ruta in enumerate(rutas_paginas):
        html_bytes = ruta.read_bytes()
        # El contador total de la web lo leemos de la primera pagina
        if indice == 0:
            total_en_web = extraer_total_web(html_bytes)

        filas_pagina = parsear_pagina_inscritos(html_bytes)
        todos_los_inscritos.extend(filas_pagina)

    tabla_inscritos = pd.DataFrame(todos_los_inscritos, columns=COLUMNAS_SALIDA)

    ruta_csv.parent.mkdir(parents=True, exist_ok=True)
    tabla_inscritos.to_csv(ruta_csv, index=False)

    # Comprobamos si cuadran las filas y guardamos el resumen de la ejecucion en JSON
    avisos = comprobar_total_inscritos(len(tabla_inscritos), total_en_web)
    resumen = {
        "fecha_ejecucion": datetime.now().isoformat(timespec="seconds"),
        "url_fuente": URL_BASE_INSCRITOS,
        "paginas_descargadas": len(rutas_paginas),
        "total_anunciado_web": total_en_web,
        "total_descargado": len(tabla_inscritos),
        "coincide_total": len(avisos) == 0,
        "avisos": avisos,
    }
    ruta_resumen.parent.mkdir(parents=True, exist_ok=True)
    ruta_resumen.write_text(json.dumps(resumen, indent=2, ensure_ascii=False), encoding="utf-8")

    return tabla_inscritos


if __name__ == "__main__":
    print("Descargando paginas de inscritos desde /gl/ (tarda ~2-3 min la primera vez)...")
    paginas = descargar_inscritos()
    tabla = construir_inscritos_csv(paginas)
    print(f"Paginas descargadas: {len(paginas)}")
    print(f"Total de inscritos guardados en {RUTA_CSV_INSCRITOS}: {len(tabla)}")
    print(f"Dorsales unicos: {tabla['dorsal'].nunique()}")
    print("Recuento por estado:")
    print(tabla["estado"].value_counts(dropna=False).to_string())
    print(f"Resumen de comprobacion guardado en: {RUTA_RESUMEN_INSCRITOS}")