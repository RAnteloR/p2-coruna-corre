"""Tests para la descarga, lectura y comprobacion de la lista de inscritos."""

import json

import pandas as pd
import pytest

from src.inscritos import (
    comprobar_total_inscritos,
    construir_inscritos_csv,
    extraer_total_web,
    parsear_pagina_inscritos,
    tiene_pagina_siguiente,
)

# Trozo basado en la estructura HTML real de corunacorre.com pero con datos inventados
HTML_REAL_ANONIMIZADO = b"""
<html>
  <body>
    <div class="page-header-web">
      <h1>
        INSCRITOS EN XIII CIRCUITO DE CARREIRAS POPULARES CORUNA CORRE 2026
        <span class="badge">2</span>
      </h1>
    </div>
    <table class="table">
      <thead>
        <tr>
          <th>Nombre</th>
          <th>Apellidos</th>
          <th>Dorsal</th>
          <th>Pagado</th>
          <th>Estado</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>PERSONA UNO</td>
          <td>APELIDO PROBA A</td>
          <td class="dorsal">1001</td>
          <td>27/02/2026 11:46</td>
          <td class="get_pagado"><i aria-hidden="true" class="fa fa-check-circle-o"></i></td>
        </tr>
        <tr>
          <td>PERSONA DOUS</td>
          <td>APELIDO PROBA B</td>
          <td class="dorsal">1002</td>
          <td>27/02/2026 11:49</td>
          <td class="get_pagado"><i aria-hidden="true" class="fa fa-check-circle-o"></i></td>
        </tr>
      </tbody>
    </table>
    <div class="paginacion">
      <a href="?page=1">1</a>
      <a href="?page=2">2</a>
    </div>
  </body>
</html>
"""

# HTML con las columnas en otro orden y en gallego para probar que lee por cabecera
HTML_COLUMNAS_DESORDENADAS = b"""
<html>
  <body>
    <table>
      <thead>
        <tr>
          <th>Dorsal</th>
          <th>Estado</th>
          <th>Apelidos</th>
          <th>Nome</th>
          <th>Pagado</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>555</td>
          <td><i class="fa fa-clock-o"></i></td>
          <td>SILVA DIAZ</td>
          <td>MARTA</td>
          <td>02/03/2026 12:00</td>
        </tr>
      </tbody>
    </table>
  </body>
</html>
"""

# HTML que solo tiene ?page=20 para comprobar que NO se confunde con ?page=2
HTML_SOLO_PAGE_20 = b"""
<html>
  <body>
    <div class="paginacion">
      <a href="?page=1">1</a>
      <a href="?page=20">20</a>
    </div>
  </body>
</html>
"""

HTML_SIN_TABLA = b"<html><body><p>No hay datos aqui</p></body></html>"


def test_parsear_html_real_anonimizado():
    # Comprobamos que lee bien todas las columnas y traduce el icono de Estado
    filas = parsear_pagina_inscritos(HTML_REAL_ANONIMIZADO)

    assert len(filas) == 2
    assert filas[0] == {
        "nome": "PERSONA UNO",
        "apelidos": "APELIDO PROBA A",
        "dorsal": "1001",
        "pagado": "27/02/2026 11:46",
        "estado": "confirmado",
    }
    assert filas[1]["dorsal"] == "1002"
    assert filas[1]["estado"] == "confirmado"


def test_parsear_lee_por_cabecera_aunque_cambie_el_orden():
    # Aunque la web cambie el orden de las columnas o las ponga en gallego, sigue funcionando
    filas = parsear_pagina_inscritos(HTML_COLUMNAS_DESORDENADAS)

    assert len(filas) == 1
    assert filas[0]["nome"] == "MARTA"
    assert filas[0]["apelidos"] == "SILVA DIAZ"
    assert filas[0]["dorsal"] == "555"
    assert filas[0]["estado"] == "fa-clock-o"


def test_parsear_pagina_sin_tabla_devuelve_vacio():
    filas = parsear_pagina_inscritos(HTML_SIN_TABLA)
    assert filas == []


def test_extraer_total_web_lee_el_badge():
    assert extraer_total_web(HTML_REAL_ANONIMIZADO) == 2
    assert extraer_total_web(HTML_SIN_TABLA) is None


def test_tiene_pagina_siguiente_compara_numero_exacto():
    # En HTML_REAL_ANONIMIZADO existe ?page=2, asi que desde la 1 devuelve True
    assert tiene_pagina_siguiente(HTML_REAL_ANONIMIZADO, pagina_actual=1) is True
    # Desde la pagina 2 no existe ?page=3, devuelve False
    assert tiene_pagina_siguiente(HTML_REAL_ANONIMIZADO, pagina_actual=2) is False
    # En HTML_SOLO_PAGE_20 solo existe ?page=20: desde la pagina 1 NO debe confundirlo con page=2
    assert tiene_pagina_siguiente(HTML_SOLO_PAGE_20, pagina_actual=1) is False


def test_comprobar_total_inscritos_avisa_si_no_cuadra():
    # Si cuadran no hay avisos
    assert comprobar_total_inscritos(total_descargado=2345, total_en_web=2345) == []

    # Si no cuadran tiene que saltar un UserWarning y devolver el texto del aviso
    with pytest.warns(UserWarning, match="no coincide"):
        avisos = comprobar_total_inscritos(total_descargado=2340, total_en_web=2345)
    assert len(avisos) == 1


def test_construir_inscritos_csv_genera_csv_y_resumen(tmp_path):
    # Creamos una pagina HTML falsa en una carpeta temporal para no tocar datos reales
    pagina_1 = tmp_path / "pagina_001.html"
    pagina_1.write_bytes(HTML_REAL_ANONIMIZADO)

    ruta_csv = tmp_path / "inscritos.csv"
    ruta_resumen = tmp_path / "inscritos_resumen.json"

    tabla = construir_inscritos_csv(
        rutas_paginas=[pagina_1],
        ruta_csv=ruta_csv,
        ruta_resumen=ruta_resumen,
    )

    # Comprobamos que se creo el CSV con 2 filas y las 5 columnas
    assert ruta_csv.exists()
    tabla_leida = pd.read_csv(ruta_csv, dtype=str)
    assert len(tabla) == 2
    assert len(tabla_leida) == 2
    assert list(tabla_leida.columns) == ["nome", "apelidos", "dorsal", "pagado", "estado"]

    # Comprobamos que se creo el resumen JSON y dice que todo cuadra
    assert ruta_resumen.exists()
    resumen = json.loads(ruta_resumen.read_text(encoding="utf-8"))
    assert resumen["paginas_descargadas"] == 1
    assert resumen["total_anunciado_web"] == 2
    assert resumen["total_descargado"] == 2
    assert resumen["coincide_total"] is True
    assert resumen["avisos"] == []