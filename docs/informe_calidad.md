# Informe de calidad de los datos

Issue #9 · Datos: Absoluta de las 6 carreras disputadas del circuito Coruña Corre 2026 (5.390 filas en total).
El perfil completo está en `notebooks/B_01_limpieza_calidad.ipynb` y los recuentos en `docs/perfil_calidad.csv`.

## Cómo se hizo
1. Se cargaron las 6 carreras de `datos/interim/` tal como vienen de la web (todo como texto).
2. Con la función `perfil()` se contaron los problemas de cada carrera, agrupados en las cinco dimensiones de calidad: completitud, validez, consistencia, exactitud y unicidad.
3. Los casos raros se inspeccionaron mostrando solo columnas sin datos personales (puesto, puesto por sexo, puesto por categoría y tiempo).
4. Se limpiaron las carreras con `limpiar_carrera()` (`src/limpieza.py`) sin borrar ninguna fila, y se comprobó que el número de filas no cambia.

## Problemas encontrados

| # | Problema | Dimensión | Carreras | Filas | Cómo se detectó | Qué se decidió |
|---|---|---|---|---|---|---|
| 1 | Personas sin sexo ni categoría (`NO-n` y `—`) | Completitud | 01, 02, 03, 05 | 17 | Perfil: no encajan con `M-3` / `MS2M-1` | Se conservan como `SIN_CATEGORIA`, sin sexo |
| 2 | Tiempos de más de 10 h | Exactitud | 05 | 3 | `marcar_tiempo()`: más de 1 h | Marcados `imposible`, no se corrigen |
| 3 | Categoría especial `ESP` | Validez | 01, 05, 06 | 3 | Recuento de categorías | Se mantiene como categoría propia |
| 4 | Volta a Oza sin regulamento | Completitud | 05 | 659 | Al buscar las distancias | Límites generales: 12 min y 1 h |
| 5 | Carreras de distinta distancia | Consistencia | Todas | — | Regulamentos específicos (art. 3) | Mínimo según la distancia |
| 6 | Códigos distintos en carreras y circuito | Consistencia | Todas | — | Comparando las dos webs | `categorias.csv` guarda los dos |
| 7 | No hay categoría de discapacidad | Completitud | Todas | 0 | Recuento de categorías | Se anota; no afecta |

### Detalle de cada problema

**1. Personas sin sexo ni categoría.** En puesto por categoría aparecen como `NO-1`, `NO-2`… y en puesto por sexo como `—`. Hay 3 en carrera_01, 6 en carrera_02, 5 en carrera_03 y 3 en carrera_05. Se conservan porque corrieron y cuentan para la participación, pero quedan fuera de los análisis por sexo o categoría.

**2. Tiempos de más de 10 horas.** Son 10:28:43, 10:39:57 y 10:42:58, los tres últimos puestos de Volta a Oza, y además son 3 de las filas `NO`. Hipótesis: se registró la hora de llegada (la carrera sale a las 10:00) en vez del tiempo. No se puede comprobar, así que no se inventa el tiempo: se marcan como `imposible` y quedan fuera de los análisis de tiempos.

**3. Categoría `ESP`.** Aparece como `ESPM` / `ESPF`. El regulamento no explica qué significa.

**4. Volta a Oza sin regulamento.** No se sabe su distancia ni su cierre de control. Se usan los límites generales por analogía con las demás carreras, que cierran el control 1 h después de la salida.

**5. Distancias distintas.** Las carreras miden entre 5.850 y 6.700 m. Por eso el tiempo mínimo creíble se calcula con la distancia (2:30 min/km, el ritmo del récord del mundo de 5 km). Para comparar el rendimiento entre carreras (pregunta 9) no se usarán los tiempos directamente.

**6. Códigos distintos.** La misma categoría se escribe distinto en las carreras y en la clasificación del circuito (`SNR`/`SN`, `MS1`/`M1`…). Se usará en la O4 para unir ambas tablas.

**7. Discapacidad.** El regulamento define esta categoría, pero no aparece en los datos de 2026.

## Comprobaciones sin problemas
En las 6 carreras dieron **0**: celdas vacías, puestos no numéricos o repetidos, dorsales repetidos, filas duplicadas, formatos de tiempo incorrectos, tiempos que faltan, categorías desconocidas y casos en los que el sexo del puesto por sexo no coincide con el de la categoría. También se confirmaron los códigos `SUB20` (72 filas) y `MS3` (590), que al principio solo se habían deducido.

## Resultado de la limpieza
- 6 ficheros `datos/interim/carrera_XX_limpia.csv` con las columnas de `docs/contrato_datos.md` (no se suben: llevan nombres).
- 5.390 filas, las mismas que en origen: no se ha borrado ni duplicado ninguna.
- `tempo_marca`: 5.387 `ok` y 3 `imposible`.
- Categorías: SNR 1.667 · MS1 1.382 · MS2 1.328 · MS3 590 · SUB23 186 · MS4 145 · SUB20 72 · SIN_CATEGORIA 17 · ESP 3.

## Otras observaciones
- **Carrera sin disputar:** Novo Mesoiro (22/11/2026) se excluye porque aún no se ha corrido. Si los datos se vuelven a descargar después de esa fecha, aparecería como `carrera_07`. Hay que decidir en grupo si se congela el análisis en 6 carreras.
- **Fallo encontrado durante el perfil:** al aplicar `marcar_tiempo()` a una columna de pandas, los tiempos vacíos llegaban como `NaN` en vez de `None` y salían como `ok`. Se corrigió para que cuenten como `faltante` y se añadió un test.