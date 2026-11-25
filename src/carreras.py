"""Obtención de las carreras reales del circuito (issue #7, HITO 1).

Tres pasos, cada uno con su función principal:

1. descubrir_carreras(): parte de la página de la edición y sigue los enlaces
   edición -> eventos (carreras) -> categorías, localiza la Absoluta por el TEXTO del
   enlace y excluye las carreras que aún no se han corrido. Devuelve la tabla
   carrera_id, orden, fecha, url_absoluta (+ evento_id y nombre de la carrera).
2. descargar_carrera(): recorre todas las páginas de la Absoluta de una carrera sin
   saber cuántas hay, guardando cada una en bytes en datos/raw/<carrera_id>/pagina_N.html.
3. construir_interim() + comprobar_filas(): pasa cada carrera a
   datos/interim/<carrera_id>.csv con las columnas crudas y comprueba que el número de
   filas es coherente con el número de páginas.

Todas las peticiones pasan por src.obtencion.descargar (User-Agent, pausa, sin repetir).
Las funciones parsear_* trabajan con bytes y no hacen peticiones: así se prueban con HTML
guardado (tests/fixtures/).

Este módulo NUNCA imprime nombres ni dorsales: solo recuentos.
"""

from __future__ import annotations

import re
import unicodedata
import warnings
from datetime import date
from pathlib import Path
from typing import Callable
from urllib.parse import urljoin, urlsplit

import pandas as pd
from bs4 import BeautifulSoup

from src.config import DIR_DOCS, DIR_INTERIM, DIR_RAW
from src.obtencion import descargar

URL_BASE = "https://corunacorre.com"
URL_RESULTADOS = URL_BASE + "/web/resultado/"  # portada de resultados (enlaza la edición actual)

# Columnas crudas de interim/ y la clase de la celda <td> de la web de la que salen.
COLUMNAS_TD = {
    "posto": "puesto",
    "dorsal": "dorsal",
    "nome": "nombre",
    "apelidos": "apellidos",
    "posto_sexo": "get_puesto_sexo_display",
    "posto_categoria": "get_puesto_categoria_display",
    "tempo": "tiempo_display",
}
COLUMNAS = list(COLUMNAS_TD)

# Meses en galego y castellano (la web mezcla los dos).
MESES = {
    "xaneiro": 1, "enero": 1, "febreiro": 2, "febrero": 2, "marzo": 3, "abril": 4,
    "maio": 5, "mayo": 5, "xuño": 6, "junio": 6, "xullo": 7, "julio": 7,
    "agosto": 8, "setembro": 9, "septiembre": 9, "outubro": 10, "octubre": 10,
    "novembro": 11, "noviembre": 11, "decembro": 12, "diciembre": 12,
}

Obtener = Callable[[str], bytes]


# --------------------------------------------------------------------------------------
# Utilidades de parseo
# --------------------------------------------------------------------------------------

def _sopa(html: bytes) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


def _normalizar(texto: str) -> str:
    """Mayúsculas, sin tildes y sin espacios repetidos (para comparar textos de enlaces)."""
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", sin_tildes).strip().upper()


def _enlaces(html: bytes) -> list[tuple[str, str]]:
    """Lista de (texto, href) de todos los enlaces de la página, en orden."""
    return [(a.get_text(" ", strip=True), a["href"]) for a in _sopa(html).find_all("a", href=True)]


# --------------------------------------------------------------------------------------
# Parte 1: descubrir las carreras y su Absoluta
# --------------------------------------------------------------------------------------

def parsear_url_edicion_actual(html: bytes, url: str = URL_RESULTADOS) -> str:
    """En la portada de resultados, devuelve la URL del enlace «Edición Actual»."""
    for texto, href in _enlaces(html):
        if _normalizar(texto) == "EDICION ACTUAL" and "/edicion-" in href:
            return urljoin(url, href)
    raise ValueError("No se encontró el enlace «Edición Actual» en la portada de resultados.")


def parsear_url_eventos(html: bytes, url: str) -> str:
    """En la página de una edición, devuelve la URL del enlace «Por evento»."""
    for texto, href in _enlaces(html):
        if _normalizar(texto) == "POR EVENTO":
            return urljoin(url, href)
    raise ValueError("No se encontró el enlace «Por evento» en la página de la edición.")


def parsear_anho_edicion(html: bytes) -> int | None:
    """Año de la edición, sacado del <title> de la página (p. ej. «... edición 2026 ...»)."""
    sopa = _sopa(html)
    titulo = sopa.title.get_text(" ", strip=True) if sopa.title else ""
    anhos = re.findall(r"\b(20\d\d)\b", titulo)
    return int(anhos[-1]) if anhos else None


def parsear_eventos_con_resultados(html: bytes, url: str) -> list[dict]:
    """Carreras que tienen enlace de resultados en la página de eventos, en el orden de la web.

    Devuelve dicts con evento_id, nombre y url_resultados.
    """
    vistos: dict[int, dict] = {}
    for texto, href in _enlaces(html):
        m = re.search(r"/resultado/evento-(\d+)/?$", href)
        if m and int(m.group(1)) not in vistos:
            vistos[int(m.group(1))] = {
                "evento_id": int(m.group(1)),
                "nombre": texto,
                "url_resultados": urljoin(url, href),
            }
    return list(vistos.values())


def parsear_eventos_del_menu(html: bytes, url: str) -> list[dict]:
    """Todas las carreras del menú «Eventos» (incluidas las que aún no se han corrido).

    Devuelve dicts con evento_id, nombre y url_ficha.
    """
    vistos: dict[int, dict] = {}
    for texto, href in _enlaces(html):
        m = re.search(r"/web/evento/(\d+)/?$", href)
        if m and int(m.group(1)) not in vistos:
            vistos[int(m.group(1))] = {
                "evento_id": int(m.group(1)),
                "nombre": texto,
                "url_ficha": urljoin(url, href),
            }
    return list(vistos.values())


def parsear_url_absoluta(html: bytes, url: str) -> str | None:
    """En la página de resultados de un evento, devuelve el enlace de la categoría Absoluta.

    Se busca por el TEXTO del enlace (empieza por «ABSOLUTA»), no por su posición ni por el
    número de competición, que cambian de una carrera a otra. Devuelve None si no hay.

    Si hay más de un enlace «Absoluta» no se corta la ejecución: se avisa con
    warnings.warn (para revisarlo a mano) y se devuelve el primero.
    """
    candidatas = [
        urljoin(url, href)
        for texto, href in _enlaces(html)
        if _normalizar(texto).startswith("ABSOLUTA") and "/resultado/competicion-" in href
    ]
    candidatas = list(dict.fromkeys(candidatas))  # sin repetidos, manteniendo el orden
    if len(candidatas) > 1:
        warnings.warn(
            f"Hay {len(candidatas)} enlaces «Absoluta» en {url}; se usa el primero (revisar a mano).",
            UserWarning,
            stacklevel=2,
        )
    return candidatas[0] if candidatas else None


def parsear_fecha_evento(html: bytes) -> date | None:
    """Fecha de la carrera desde su ficha (/gl/web/evento/<id>/).

    Solo lee el bloque «Lugar e Horarios» (<div id="horarios">), para no coger otras fechas
    de la ficha (p. ej. «inscripciones hasta el 15 de noviembre»). Dentro del bloque busca
    «14 de marzo de 2026» y, si no está, la primera fecha d/m/aaaa. Si la página no tiene
    ese bloque (HTML sin estructura de ficha), se usa la página entera.
    """
    sopa = _sopa(html)
    for etiqueta in sopa(["script", "style"]):
        etiqueta.decompose()
    bloque = sopa.find(id="horarios")
    texto = (bloque or sopa).get_text(" ", strip=True)

    m = re.search(r"\b(\d{1,2}) de ([A-Za-zÀ-ÿ]+) de (\d{4})\b", texto)
    if m and m.group(2).lower() in MESES:
        return date(int(m.group(3)), MESES[m.group(2).lower()], int(m.group(1)))

    m = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", texto)
    if m:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    return None


def descubrir_carreras(
    url_edicion: str | None = None,
    hoy: date | None = None,
    obtener: Obtener = descargar,
    verbose: bool = True,
) -> pd.DataFrame:
    """Devuelve las carreras YA DISPUTADAS de una edición, con la URL de su Absoluta.

    - url_edicion: página de la edición (p. ej. .../gl/web/resultado/edicion-63). Si es None,
      se parte de la portada de resultados y se sigue el enlace «Edición Actual».
    - hoy: fecha de referencia para decidir qué carreras ya se corrieron (por defecto, hoy).
    - obtener: función que da los bytes de una URL (en los tests se cambia por una falsa).

    Una carrera se excluye (y se dice por qué) si:
      * su fecha es hoy o posterior (aún no se ha corrido; normalmente la última), o
      * no tiene enlace de resultados en la página de eventos, o
      * su página de resultados no tiene categoría Absoluta.

    Columnas: carrera_id, orden, fecha, url_absoluta, evento_id, nombre.

    Los avisos menores (p. ej. varias categorías Absoluta en una carrera) no cortan la
    ejecución: se guardan en tabla.attrs["avisos"] y se imprimen si verbose=True.
    """
    hoy = hoy or date.today()

    if url_edicion is None:
        url_edicion = parsear_url_edicion_actual(obtener(URL_RESULTADOS), URL_RESULTADOS)
    html_edicion = obtener(url_edicion)
    url_eventos = parsear_url_eventos(html_edicion, url_edicion)
    html_eventos = obtener(url_eventos)
    anho = parsear_anho_edicion(html_eventos) or parsear_anho_edicion(html_edicion)

    con_resultados = {e["evento_id"]: e for e in parsear_eventos_con_resultados(html_eventos, url_eventos)}
    # El menú tiene TODAS las carreras de la edición actual, también la que aún no se corrió.
    del_menu = {e["evento_id"]: e for e in parsear_eventos_del_menu(html_eventos, url_eventos)}

    candidatos = list(con_resultados) + [i for i in del_menu if i not in con_resultados]

    filas, excluidas, avisos = [], [], []
    for evento_id in candidatos:
        url_ficha = (
            del_menu[evento_id]["url_ficha"] if evento_id in del_menu
            else urljoin(url_eventos, f"/gl/web/evento/{evento_id}/")
        )
        fecha = parsear_fecha_evento(obtener(url_ficha))
        nombre = (con_resultados.get(evento_id) or del_menu[evento_id])["nombre"]

        # El menú es común a toda la web: si estamos en otra edición, sus carreras no cuentan.
        if evento_id not in con_resultados and anho and fecha and fecha.year != anho:
            continue

        if fecha is not None and fecha >= hoy:
            excluidas.append((evento_id, nombre, fecha, "aún no se ha corrido"))
            continue
        if evento_id not in con_resultados:
            excluidas.append((evento_id, nombre, fecha, "sin enlace de resultados"))
            continue

        url_res = con_resultados[evento_id]["url_resultados"]
        with warnings.catch_warnings(record=True) as capturados:
            warnings.simplefilter("always")
            url_absoluta = parsear_url_absoluta(obtener(url_res), url_res)
        avisos.extend(f"evento {evento_id} ({nombre}): {w.message}" for w in capturados)
        if url_absoluta is None:
            excluidas.append((evento_id, nombre, fecha, "sin categoría Absoluta"))
            continue

        filas.append({"evento_id": evento_id, "nombre": nombre, "fecha": fecha,
                      "url_absoluta": url_absoluta})

    tabla = pd.DataFrame(filas, columns=["evento_id", "nombre", "fecha", "url_absoluta"])
    # Orden cronológico (a igual fecha, el de la web).
    tabla = tabla.sort_values("fecha", kind="stable").reset_index(drop=True)
    tabla.insert(0, "orden", range(1, len(tabla) + 1))
    tabla.insert(0, "carrera_id", [f"carrera_{n:02d}" for n in tabla["orden"]])
    tabla = tabla[["carrera_id", "orden", "fecha", "url_absoluta", "evento_id", "nombre"]]

    if verbose:
        print(f"Carreras disputadas: {len(tabla)} · excluidas: {len(excluidas)}")
        for evento_id, nombre, fecha, motivo in excluidas:
            print(f"  - excluida evento {evento_id} ({nombre}, {fecha}): {motivo}")
        for aviso in avisos:
            print(f"  ! aviso {aviso}")
    tabla.attrs["excluidas"] = excluidas
    tabla.attrs["avisos"] = avisos
    return tabla


# --------------------------------------------------------------------------------------
# Parte 2: descargar todas las páginas de cada Absoluta
# --------------------------------------------------------------------------------------

def parsear_filas(html: bytes) -> list[dict]:
    """Filas de la tabla de resultados de una página, con las columnas crudas (texto)."""
    tabla = _sopa(html).find("table")
    if tabla is None:
        return []
    cuerpo = tabla.find("tbody") or tabla
    filas = []
    for tr in cuerpo.find_all("tr"):
        celdas = {
            clase: td.get_text(" ", strip=True)
            for td in tr.find_all("td")
            for clase in (td.get("class") or [])
        }
        if not celdas:
            continue  # fila de cabecera o vacía
        filas.append({col: celdas.get(clase, "") for col, clase in COLUMNAS_TD.items()})
    return filas


def parsear_hay_siguiente(html: bytes) -> bool:
    """True si la paginación tiene un enlace «Seguinte»/«Siguiente» activo."""
    sopa = _sopa(html)
    for li in sopa.select("ul.pagination li"):
        clases = li.get("class") or []
        if "next" in clases and "disabled" not in clases and li.find("a", href=True):
            return True
    return False


def parsear_ultima_pagina(html: bytes) -> int:
    """Número de página más alto que aparece en la paginación (1 si no hay paginación)."""
    numeros = [
        int(a.get_text(strip=True))
        for a in _sopa(html).select("ul.pagination li a")
        if a.get_text(strip=True).isdigit()
    ]
    return max(numeros, default=1)


def url_pagina(url_absoluta: str, n: int) -> str:
    """URL de la página n de una clasificación (?page=n)."""
    partes = urlsplit(url_absoluta)
    return partes._replace(query=f"page={n}", fragment="").geturl()


def ruta_pagina(carrera_id: str, n: int, dir_raw: Path = DIR_RAW) -> Path:
    return dir_raw / carrera_id / f"pagina_{n}.html"


def descargar_carrera(
    carrera_id: str,
    url_absoluta: str,
    obtener: Callable[..., bytes] = descargar,
    dir_raw: Path = DIR_RAW,
    max_paginas: int = 500,
) -> int:
    """Descarga todas las páginas de la Absoluta de una carrera. Devuelve cuántas hay.

    No se sabe de antemano cuántas páginas hay: se sigue pidiendo la siguiente mientras la
    página tenga filas y un enlace «siguiente». Cada página se guarda en bytes en
    datos/raw/<carrera_id>/pagina_N.html; si ya existe se lee del disco (sin petición), así
    que una segunda ejecución no hace peticiones nuevas.
    """
    n = 1
    while n <= max_paginas:
        html = obtener(url_pagina(url_absoluta, n), destino=ruta_pagina(carrera_id, n, dir_raw))
        if not parsear_filas(html):
            # Página vacía: no cuenta (solo puede pasar si la web cambia el paginado).
            ruta_pagina(carrera_id, n, dir_raw).unlink(missing_ok=True)
            return n - 1
        if not parsear_hay_siguiente(html):
            return n
        n += 1
    raise RuntimeError(f"{carrera_id}: más de {max_paginas} páginas; ¿bucle en la paginación?")


def descargar_todas(carreras: pd.DataFrame, **kwargs) -> pd.Series:
    """Descarga todas las carreras de la tabla de descubrir_carreras(). Devuelve páginas por carrera."""
    paginas = {}
    for fila in carreras.itertuples():
        paginas[fila.carrera_id] = descargar_carrera(fila.carrera_id, fila.url_absoluta, **kwargs)
        print(f"{fila.carrera_id}: {paginas[fila.carrera_id]} páginas")
    return pd.Series(paginas, name="paginas")


# --------------------------------------------------------------------------------------
# Parte 3: tablas por carrera en interim/ y comprobación de filas
# --------------------------------------------------------------------------------------

def paginas_guardadas(carrera_id: str, dir_raw: Path = DIR_RAW) -> list[Path]:
    """Páginas guardadas de una carrera, ordenadas por número (1, 2, ..., 10, 11)."""
    rutas = (dir_raw / carrera_id).glob("pagina_*.html")
    return sorted(rutas, key=lambda p: int(p.stem.split("_")[1]))


def construir_interim(
    carrera_id: str, dir_raw: Path = DIR_RAW, dir_interim: Path = DIR_INTERIM
) -> pd.DataFrame:
    """Une las páginas de una carrera en datos/interim/<carrera_id>.csv (columnas crudas, texto)."""
    filas = []
    for ruta in paginas_guardadas(carrera_id, dir_raw):
        n = int(ruta.stem.split("_")[1])
        filas += [{**f, "_pagina": n} for f in parsear_filas(ruta.read_bytes())]
    df = pd.DataFrame(filas, columns=COLUMNAS + ["_pagina"])
    dir_interim.mkdir(parents=True, exist_ok=True)
    df[COLUMNAS].to_csv(dir_interim / f"{carrera_id}.csv", index=False, encoding="utf-8")
    return df


def comprobar_filas(carrera_id: str, df: pd.DataFrame, dir_raw: Path = DIR_RAW) -> dict:
    """Comprueba que el número de filas cuadra con el número de páginas. Solo recuentos.

    Con un tamaño de página T (filas de la página 1) y N páginas, todas las páginas salvo la
    última deben tener T filas y el total debe estar entre (N-1)*T + 1 y N*T. Además se
    comprueba que N es la última página que anuncia la paginación de la web y que no hay
    filas repetidas entre páginas (lo que pasaría si la web reordenase mientras se descarga).
    """
    rutas = paginas_guardadas(carrera_id, dir_raw)
    n_paginas = len(rutas)
    por_pagina = df.groupby("_pagina").size().reindex(range(1, n_paginas + 1), fill_value=0)
    tam = int(por_pagina.iloc[0]) if n_paginas else 0
    n_filas = len(df)
    ultima_web = parsear_ultima_pagina(rutas[-1].read_bytes()) if rutas else 0
    paginas_seguidas = [int(p.stem.split("_")[1]) for p in rutas] == list(range(1, n_paginas + 1))
    paginas_incompletas = int((por_pagina.iloc[:-1] != tam).sum()) if n_paginas > 1 else 0
    duplicadas = int(df.duplicated(subset=COLUMNAS).sum())

    cuadra = (
        n_paginas > 0
        and paginas_seguidas
        and (n_paginas - 1) * tam < n_filas <= n_paginas * tam
        and paginas_incompletas == 0
        and ultima_web == n_paginas
        and duplicadas == 0
    )
    return {
        "carrera_id": carrera_id,
        "paginas": n_paginas,
        "ultima_pagina_web": ultima_web,
        "filas_por_pagina": tam,
        "filas_ultima_pagina": int(por_pagina.iloc[-1]) if n_paginas else 0,
        "filas": n_filas,
        "filas_min_esperadas": (n_paginas - 1) * tam + 1 if n_paginas else 0,
        "filas_max_esperadas": n_paginas * tam,
        "paginas_incompletas": paginas_incompletas,
        "filas_duplicadas": duplicadas,
        "cuadra": bool(cuadra),
    }


def construir_todas(
    carreras: pd.DataFrame,
    dir_raw: Path = DIR_RAW,
    dir_interim: Path = DIR_INTERIM,
    destino_comprobacion: Path | None = DIR_DOCS / "comprobacion_filas.csv",
) -> pd.DataFrame:
    """Crea el CSV de interim/ de cada carrera y guarda la tabla de comprobación de filas.

    La comprobación solo tiene recuentos (sin nombres ni dorsales), así que se guarda en
    docs/ para que se pueda subir al repositorio.
    """
    resultados = []
    for fila in carreras.itertuples():
        df = construir_interim(fila.carrera_id, dir_raw, dir_interim)
        resultados.append({"orden": fila.orden, "fecha": fila.fecha,
                           **comprobar_filas(fila.carrera_id, df, dir_raw)})
    comprobacion = pd.DataFrame(resultados)
    comprobacion.insert(0, "carrera_id", comprobacion.pop("carrera_id"))
    if destino_comprobacion is not None:
        destino_comprobacion.parent.mkdir(parents=True, exist_ok=True)
        comprobacion.to_csv(destino_comprobacion, index=False, encoding="utf-8")
    return comprobacion
