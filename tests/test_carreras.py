"""Tests de src/carreras.py. No hacen peticiones reales.

- Las páginas índice (portada, edición, eventos, categorías y fichas) están guardadas en
  tests/fixtures/ y NO contienen personas.
- Las páginas de resultados se escriben a mano con nombres inventados.

Ejecutar desde la raíz del repo:  python -m pytest
"""

from datetime import date
from pathlib import Path

import pytest

from src import carreras as c

FIX = Path(__file__).parent / "fixtures"
BASE = "https://corunacorre.com"
URL_EDICION = BASE + "/gl/web/resultado/edicion-63"
URL_EVENTOS = URL_EDICION + "/eventos"


def fixture(nombre: str) -> bytes:
    return (FIX / nombre).read_bytes()


# --------------------------------------------------------------------------------------
# Parte 1: páginas índice
# --------------------------------------------------------------------------------------

def test_edicion_actual_desde_la_portada():
    url = c.parsear_url_edicion_actual(fixture("portada_resultados.html"), c.URL_RESULTADOS)
    assert url == URL_EDICION


def test_enlace_por_evento():
    assert c.parsear_url_eventos(fixture("edicion.html"), URL_EDICION) == URL_EVENTOS


def test_anho_de_la_edicion():
    assert c.parsear_anho_edicion(fixture("eventos.html")) == 2026


def test_eventos_con_resultados_en_orden():
    eventos = c.parsear_eventos_con_resultados(fixture("eventos.html"), URL_EVENTOS)
    assert [e["evento_id"] for e in eventos] == [3210, 3211, 3212, 3213, 3214, 3215]
    assert eventos[0]["url_resultados"] == BASE + "/gl/web/resultado/evento-3210"


def test_menu_incluye_la_carrera_sin_correr():
    menu = c.parsear_eventos_del_menu(fixture("eventos.html"), URL_EVENTOS)
    assert [e["evento_id"] for e in menu][-1] == 3216


def test_absoluta_por_texto():
    url = c.parsear_url_absoluta(fixture("resultados_evento.html"), BASE + "/gl/web/resultado/evento-3210")
    assert url == BASE + "/gl/web/resultado/competicion-17059"


def test_absoluta_no_depende_de_la_posicion_ni_de_mayusculas():
    html = b"""<ul>
      <li><a href="/gl/web/resultado/competicion-99">Absoluta (2008 e anteriores)</a></li>
      <li><a href="/gl/web/resultado/competicion-1">SUB10 M</a></li>
    </ul>"""
    assert c.parsear_url_absoluta(html, BASE) == BASE + "/gl/web/resultado/competicion-99"


def test_sin_absoluta_devuelve_none():
    html = b'<a href="/gl/web/resultado/competicion-1">SUB10 M</a>'
    assert c.parsear_url_absoluta(html, BASE) is None


def test_varias_absolutas_avisa_y_devuelve_la_primera():
    html = b"""<ul>
      <li><a href="/gl/web/resultado/competicion-99">ABSOLUTA</a></li>
      <li><a href="/gl/web/resultado/competicion-98">Absoluta (2008 e anteriores)</a></li>
    </ul>"""
    with pytest.warns(UserWarning, match="2 enlaces"):
        url = c.parsear_url_absoluta(html, BASE)
    assert url == BASE + "/gl/web/resultado/competicion-99"


def test_fecha_de_la_ficha():
    assert c.parsear_fecha_evento(fixture("ficha_disputada.html")) == date(2026, 3, 14)
    assert c.parsear_fecha_evento(fixture("ficha_futura.html")) == date(2026, 11, 22)


def test_fecha_ignora_otras_fechas_fuera_del_bloque_horarios():
    html = b"""<p>Inscripciones hasta el 15 de noviembre de 2026</p>
    <div id="horarios"><h3>Lugar e Horarios</h3><strong>22 de novembro de 2026 as 10:00</strong></div>"""
    assert c.parsear_fecha_evento(html) == date(2026, 11, 22)


def test_fecha_formato_numerico():
    assert c.parsear_fecha_evento(b"<div>14/3/2026 | 5 p.m.</div>") == date(2026, 3, 14)


def _web_falsa(eventos_html: bytes = None):
    """Simula la web con las páginas guardadas; registra las URLs pedidas."""
    pedidas = []

    def obtener(url: str) -> bytes:
        pedidas.append(url)
        if url == c.URL_RESULTADOS:
            return fixture("portada_resultados.html")
        if url == URL_EDICION:
            return fixture("edicion.html")
        if url == URL_EVENTOS:
            return eventos_html or fixture("eventos.html")
        if "/web/evento/3216" in url:
            return fixture("ficha_futura.html")
        if "/web/evento/" in url:
            return fixture("ficha_disputada.html")  # misma fecha para todas: vale para el test
        if "/resultado/evento-" in url:
            return fixture("resultados_evento.html")
        raise AssertionError(f"URL inesperada: {url}")

    return obtener, pedidas


def test_descubrir_carreras_excluye_la_ultima():
    obtener, pedidas = _web_falsa()
    tabla = c.descubrir_carreras(hoy=date(2026, 11, 17), obtener=obtener, verbose=False)

    assert list(tabla.columns[:4]) == ["carrera_id", "orden", "fecha", "url_absoluta"]
    assert list(tabla["evento_id"]) == [3210, 3211, 3212, 3213, 3214, 3215]
    assert list(tabla["orden"]) == [1, 2, 3, 4, 5, 6]
    assert tabla["carrera_id"].iloc[0] == "carrera_01"
    assert (tabla["url_absoluta"] == BASE + "/gl/web/resultado/competicion-17059").all()
    assert [e[0] for e in tabla.attrs["excluidas"]] == [3216]
    assert tabla.attrs["avisos"] == []
    # Se partió de la portada y se siguieron los enlaces
    assert pedidas[:3] == [c.URL_RESULTADOS, URL_EDICION, URL_EVENTOS]


def test_descubrir_excluye_por_fecha_aunque_tenga_enlace_de_resultados():
    extra = b'<a href="/gl/web/resultado/evento-3216">NOVO MESOIRO</a></body>'
    eventos = fixture("eventos.html").replace(b"</body>", extra)
    obtener, _ = _web_falsa(eventos)

    tabla = c.descubrir_carreras(URL_EDICION, hoy=date(2026, 11, 17), obtener=obtener, verbose=False)

    assert 3216 not in set(tabla["evento_id"])
    assert tabla.attrs["excluidas"][0][3] == "aún no se ha corrido"


def test_descubrir_no_se_corta_si_hay_varias_absolutas():
    obtener_base, _ = _web_falsa()
    extra = b'<a href="/gl/web/resultado/competicion-17060">ABSOLUTA BIS</a></body>'

    def obtener(url: str) -> bytes:
        html = obtener_base(url)
        if "/resultado/evento-3210" in url:
            return html.replace(b"</body>", extra)
        return html

    tabla = c.descubrir_carreras(hoy=date(2026, 11, 17), obtener=obtener, verbose=False)

    # La carrera sigue en la tabla con la primera Absoluta y el problema queda registrado
    assert list(tabla["evento_id"]) == [3210, 3211, 3212, 3213, 3214, 3215]
    assert tabla["url_absoluta"].iloc[0] == BASE + "/gl/web/resultado/competicion-17059"
    assert len(tabla.attrs["avisos"]) == 1
    assert tabla.attrs["avisos"][0].startswith("evento 3210")


# --------------------------------------------------------------------------------------
# Partes 2 y 3: páginas de resultados (nombres inventados)
# --------------------------------------------------------------------------------------

def _pagina(n: int, filas: int, total_paginas: int) -> bytes:
    """Página de resultados inventada con la misma estructura que la web."""
    trs = "".join(
        f"""<tr><td class="seleccionar"></td><td class="puesto">{(n - 1) * 3 + i + 1}</td>
        <td class="dorsal">{900 + i}</td><td class="nombre">PERSOA</td>
        <td class="apellidos">INVENTADA {n}-{i}</td><td class="get_puesto_sexo_display">M-{i}</td>
        <td class="get_puesto_categoria_display">MS-{i}</td><td class="tiempo_display">00:2{i}:00</td></tr>"""
        for i in range(filas)
    )
    paginas = "".join(f'<li class="page-item"><a href="?page={k}">{k}</a></li>'
                      for k in range(1, total_paginas + 1))
    seguinte = f'<li class="next"><a href="?page={n + 1}">Seguinte</a></li>' if n < total_paginas else ""
    return f"""<html><body><table><thead><tr><th></th><th>Puesto</th></tr></thead>
    <tbody>{trs}</tbody></table><ul class="pagination">{paginas}{seguinte}</ul></body></html>""".encode()


@pytest.fixture
def web_resultados():
    """3 páginas: 3 + 3 + 2 filas. Simula descargar(): guarda en destino y no repite."""
    paginas = {1: _pagina(1, 3, 3), 2: _pagina(2, 3, 3), 3: _pagina(3, 2, 3)}
    peticiones = []

    def obtener(url, destino):
        if destino.exists():
            return destino.read_bytes()
        peticiones.append(url)
        n = int(url.split("page=")[1])
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(paginas[n])
        return paginas[n]

    return obtener, peticiones


def test_parsear_filas_columnas_crudas():
    filas = c.parsear_filas(_pagina(1, 2, 1))
    assert len(filas) == 2
    assert list(filas[0]) == c.COLUMNAS
    assert filas[0]["posto_sexo"] == "M-0" and filas[1]["tempo"] == "00:21:00"


def test_url_pagina():
    assert c.url_pagina(BASE + "/gl/web/resultado/competicion-1", 3) == \
        BASE + "/gl/web/resultado/competicion-1?page=3"


def test_descarga_hasta_que_no_hay_siguiente_y_no_repite(tmp_path, web_resultados):
    obtener, peticiones = web_resultados
    url = BASE + "/gl/web/resultado/competicion-1"

    assert c.descargar_carrera("carrera_01", url, obtener=obtener, dir_raw=tmp_path) == 3
    assert sorted(p.name for p in (tmp_path / "carrera_01").iterdir()) == \
        ["pagina_1.html", "pagina_2.html", "pagina_3.html"]
    assert len(peticiones) == 3

    # Segunda ejecución: todo está en disco, ninguna petición nueva
    assert c.descargar_carrera("carrera_01", url, obtener=obtener, dir_raw=tmp_path) == 3
    assert len(peticiones) == 3


def test_para_si_la_pagina_viene_vacia(tmp_path):
    def obtener(url, destino):
        html = _pagina(1, 3, 5) if url.endswith("page=1") else b"<table><tbody></tbody></table>"
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(html)
        return html

    assert c.descargar_carrera("carrera_01", BASE + "/x", obtener=obtener, dir_raw=tmp_path) == 1
    assert not (tmp_path / "carrera_01" / "pagina_2.html").exists()


def test_interim_y_comprobacion_cuadran(tmp_path, web_resultados):
    obtener, _ = web_resultados
    c.descargar_carrera("carrera_01", BASE + "/x", obtener=obtener, dir_raw=tmp_path / "raw")

    df = c.construir_interim("carrera_01", tmp_path / "raw", tmp_path / "interim")
    csv = (tmp_path / "interim" / "carrera_01.csv").read_text(encoding="utf-8")
    assert csv.splitlines()[0] == ",".join(c.COLUMNAS)
    assert len(df) == 8

    r = c.comprobar_filas("carrera_01", df, tmp_path / "raw")
    assert r["paginas"] == 3 and r["filas"] == 8 and r["filas_por_pagina"] == 3
    assert r["ultima_pagina_web"] == 3 and r["filas_duplicadas"] == 0
    assert r["cuadra"] is True


def test_comprobacion_detecta_pagina_incompleta(tmp_path):
    raw = tmp_path / "raw" / "carrera_01"
    raw.mkdir(parents=True)
    (raw / "pagina_1.html").write_bytes(_pagina(1, 3, 3))
    (raw / "pagina_2.html").write_bytes(_pagina(2, 1, 3))  # le faltan filas
    (raw / "pagina_3.html").write_bytes(_pagina(3, 2, 3))

    df = c.construir_interim("carrera_01", tmp_path / "raw", tmp_path / "interim")
    r = c.comprobar_filas("carrera_01", df, tmp_path / "raw")
    assert r["paginas_incompletas"] == 1 and r["cuadra"] is False


def test_paginas_ordenadas_numericamente(tmp_path):
    raw = tmp_path / "carrera_01"
    raw.mkdir()
    for n in (1, 2, 10, 11):
        (raw / f"pagina_{n}.html").write_bytes(b"")
    assert [p.name for p in c.paginas_guardadas("carrera_01", tmp_path)] == \
        ["pagina_1.html", "pagina_2.html", "pagina_10.html", "pagina_11.html"]
