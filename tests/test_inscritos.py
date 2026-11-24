"""Tests para la descarga y lectura de la lista de inscritos."""

from src.inscritos import parsear_pagina_inscritos, tiene_pagina_siguiente

HTML_EJEMPLO_CON_SIGUIENTE = b"""
<html>
  <body>
    <table>
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
          <td>ANA</td>
          <td>LOPEZ PEREZ</td>
          <td>101</td>
          <td>01/03/2026 10:00</td>
          <td>OK</td>
        </tr>
        <tr>
          <td>LUIS</td>
          <td>GOMEZ RUIZ</td>
          <td>202</td>
          <td>01/03/2026 10:05</td>
          <td>OK</td>
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

HTML_ULTIMA_PAGINA = b"""
<html>
  <body>
    <table>
      <tbody>
        <tr>
          <td>MARTA</td>
          <td>SILVA DIAZ</td>
          <td>303</td>
          <td>02/03/2026 12:00</td>
          <td>OK</td>
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

HTML_SIN_TABLA = b"<html><body><p>No hay datos aqui</p></body></html>"


def test_parsear_pagina_inscritos_saca_filas():
    # Probamos que lee bien las dos filas del HTML de prueba
    filas = parsear_pagina_inscritos(HTML_EJEMPLO_CON_SIGUIENTE)

    assert len(filas) == 2
    assert filas[0]["nome"] == "ANA"
    assert filas[0]["apelidos"] == "LOPEZ PEREZ"
    assert filas[0]["dorsal"] == "101"
    assert filas[1]["dorsal"] == "202"


def test_parsear_pagina_sin_tabla_devuelve_vacio():
    # Si la pagina no tiene tabla, tiene que devolver una lista vacia sin fallar
    filas = parsear_pagina_inscritos(HTML_SIN_TABLA)
    assert filas == []


def test_tiene_pagina_siguiente_detecta_el_final():
    # Si estamos en la pagina 1 y hay enlace a ?page=2, tiene que decir True
    assert tiene_pagina_siguiente(HTML_EJEMPLO_CON_SIGUIENTE, pagina_actual=1) is True

    # Si ya estamos en la pagina 2 y no hay enlace a ?page=3, tiene que decir False
    assert tiene_pagina_siguiente(HTML_ULTIMA_PAGINA, pagina_actual=2) is False