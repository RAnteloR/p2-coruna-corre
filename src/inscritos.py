"""Descarga y lectura de la lista de inscritos del circuito (Issue #8, Hito 1).

Este archivo descarga todas las paginas de inscritos usando la funcion comun
de descarga, las guarda en datos/raw/inscritos/ y genera datos/interim/inscritos.csv.
Nunca imprime nombres ni dorsales por pantalla, solo numeros de conteo.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

from src.config import DIR_INTERIM, DIR_RAW
from src.obtencion import descargar

URL_BASE_INSCRITOS = "https://corunacorre.com/es/web/inscripcion/listado/"
CARPETA_RAW_INSCRITOS = DIR_RAW / "inscritos"
RUTA_CSV_INSCRITOS = DIR_INTERIM / "inscritos.csv"


def parsear_pagina_inscritos(html_bytes: bytes) -> list[dict[str, str]]:
    """Lee el HTML de una pagina y saca las filas de la tabla de inscritos."""
    sopa = BeautifulSoup(html_bytes, "html.parser")
    tabla = sopa.find("table")
    if tabla is None:
        return []

    # Si la tabla tiene tbody cogemos las filas de ahi para saltarnos la cabecera
    cuerpo = tabla.find("tbody")
    filas_html = cuerpo.find_all("tr") if cuerpo else tabla.find_all("tr")[1:]

    lista_inscritos = []
    for fila in filas_html:
        celdas = fila.find_all("td")
        # Comprobamos que la fila tenga al menos nombre, apellidos y dorsal
        if len(celdas) < 3:
            continue

        # Usamos nome, apelidos y dorsal para que coincidan con el contrato de datos
        registro = {
            "nome": celdas[0].get_text(strip=True),
            "apelidos": celdas[1].get_text(strip=True),
            "dorsal": celdas[2].get_text(strip=True),
            "pagado": celdas[3].get_text(strip=True) if len(celdas) > 3 else "",
        }
        lista_inscritos.append(registro)

    return lista_inscritos


def tiene_pagina_siguiente(html_bytes: bytes, pagina_actual: int) -> bool:
    """Funciona como un hasNext(): mira si hay un enlace a la pagina siguiente."""
    sopa = BeautifulSoup(html_bytes, "html.parser")
    texto_siguiente = f"page={pagina_actual + 1}"

    for enlace in sopa.find_all("a", href=True):
        if texto_siguiente in enlace["href"]:
            return True

    return False


def descargar_inscritos(forzar: bool = False) -> list[Path]:
    """Recorre todas las paginas de inscritos y guarda cada HTML en datos/raw/inscritos/."""
    CARPETA_RAW_INSCRITOS.mkdir(parents=True, exist_ok=True)
    rutas_guardadas = []
    numero_pagina = 1

    while True:
        # La pagina 1 es la URL base, a partir de la 2 añadimos ?page=N
        if numero_pagina == 1:
            url_pagina = URL_BASE_INSCRITOS
        else:
            url_pagina = f"{URL_BASE_INSCRITOS}?page={numero_pagina}"

        ruta_destino = CARPETA_RAW_INSCRITOS / f"pagina_{numero_pagina:03d}.html"
        html_bytes = descargar(url_pagina, destino=ruta_destino, forzar=forzar)
        rutas_guardadas.append(ruta_destino)

        # Comprobamos si la pagina viene vacia para cortar por seguridad
        filas = parsear_pagina_inscritos(html_bytes)
        if len(filas) == 0:
            break

        # Si no hay enlace a la pagina siguiente, ya hemos llegado al final
        if not tiene_pagina_siguiente(html_bytes, numero_pagina):
            break

        numero_pagina += 1

    return rutas_guardadas


def construir_inscritos_csv(rutas_paginas: list[Path] | None = None) -> pd.DataFrame:
    """Lee todos los HTML guardados, crea inscritos.csv y devuelve la tabla."""
    if rutas_paginas is None:
        rutas_paginas = sorted(CARPETA_RAW_INSCRITOS.glob("pagina_*.html"))

    todos_los_inscritos = []
    for ruta in rutas_paginas:
        html_bytes = ruta.read_bytes()
        filas_pagina = parsear_pagina_inscritos(html_bytes)
        todos_los_inscritos.extend(filas_pagina)

    tabla_inscritos = pd.DataFrame(
        todos_los_inscritos,
        columns=["nome", "apelidos", "dorsal", "pagado"],
    )

    DIR_INTERIM.mkdir(parents=True, exist_ok=True)
    tabla_inscritos.to_csv(RUTA_CSV_INSCRITOS, index=False)

    return tabla_inscritos


if __name__ == "__main__":
    print("Descargando paginas de inscritos (puede tardar unos 2-3 minutos la primera vez)...")
    paginas = descargar_inscritos()
    tabla = construir_inscritos_csv(paginas)
    print(f"Paginas descargadas: {len(paginas)}")
    print(f"Total de inscritos guardados en {RUTA_CSV_INSCRITOS}: {len(tabla)}")
    print(f"Dorsales unicos: {tabla['dorsal'].nunique()}")