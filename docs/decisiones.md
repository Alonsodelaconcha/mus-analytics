# Registro de decisiones

Cada entrada recoge qué se decidió y por qué. Las más recientes van al final.

## 2026-10-05 · Fase 1: reglas confirmadas con el usuario

| Tema | Decisión |
|---|---|
| Par | Solo cuenta el rango de la pareja; las cartas sueltas no importan. Empate → gana el más cercano a la mano. |
| Cuatro iguales | Son duples de ese rango (pareja alta = pareja baja). RRRR > RRCC; RR44 > 5555 porque se compara primero la pareja alta. |
| 31 real | Desactivada por defecto. Si se activa, solo cambia el orden (gana a cualquier otra 31) y puntúa 3. La composición es configurable; por defecto 7-7-7-Sota. |
| 4 reyes | Orden R > C > S > 7 > … > 3 > 2 > As; el 3 vale 3 y el 2 vale 2 (715 manos distintas). Basta con soportarla sin romper nada; la prioridad es 8 reyes. |
| Cobro de pares y juego | La pareja ganadora cobra las jugadas de **ambos** compañeros; la perdedora no cobra nada. |
| Entorno | Python 3.14 en `.venv`; estructura `src/mus` con `pyproject.toml`. |

## 2026-10-05 · Fase 1: diseño del motor

**Mano = vector de conteos por rango.** Como el palo no importa, una mano queda determinada por cuántas cartas tiene de cada rango. Esta representación es canónica (el orden de las cartas no importa), hashable e indexable. Su *código* (los conteos leídos en base 5) tiene una ventaja extra: es igual a la suma de `5**rango` de cada carta, así que en el Monte Carlo se obtiene sumando, sin contar.

**Rangos efectivos, no cartas físicas.** En 8 reyes, el 3 *es* un Rey a todos los efectos, así que la baraja se modela con 8 rangos, con 8 copias de R y de A. Los símbolos `3` y `2` se aceptan como alias al leer una mano. La variante de 4 reyes es simplemente otra baraja de 10 rangos.

**Una clave comparable por lance.** Cada lance tiene una función que devuelve una tupla en la que *mayor = mejor*, o `None` si la mano no participa. La chica niega los rangos para mantener ese criterio. Ventajas: un solo criterio de comparación, fácil de probar con casos concretos, y los empates de clave se resuelven aparte por posición. Alternativa descartada: funciones `compara(a, b)` por lance, más difíciles de vectorizar.

**Fuerza densa precalculada.** Para cada lance, la clave de cada una de las 330 manos se convierte en un entero denso (0 = no participa). Comparar fuerzas equivale exactamente a comparar claves, y hay un test que lo comprueba para todos los pares de manos. Con esto, el ganador de un lance en millones de repartos es un `argmax` de NumPy. Además, `argmax` devuelve el primer máximo, que coincide con la regla de desempate (gana el más cercano a la mano).

**Cálculo exacto por pesos combinatorios.** P(mano) = ∏ C(nᵣ, kᵣ) / C(40, 4). Se verifica contra una fuerza bruta independiente que recorre las 91 390 manos físicas sin usar ni la fórmula ni los evaluadores.

**Monte Carlo vectorizado por lotes.** Se usa `Generator.permuted` sobre una matriz (lote × 40). Se eligió frente a `argpartition` porque este no garantiza que el orden *dentro* de las cartas extraídas sea aleatorio, y ese orden decide qué cartas recibe cada jugador. El lote (250 000) limita la memoria. El rendimiento es de ~1 M manos/s.

**Intervalo de Wilson** en lugar del intervalo normal: no se sale de [0, 1] y funciona bien con proporciones pequeñas (P(juego 40) ≈ 0,02).

**Las métricas se definen una sola vez, como máscaras sobre la tabla.** El valor exacto y la estimación Monte Carlo usan la misma definición, así que la comparación valida el muestreo y los pesos. Los evaluadores se validan aparte, con tests de casos límite y con la fuerza bruta.

**Tests estadísticos deterministas.** Llevan semilla fija y un nivel del 99,9 % para que no fallen por azar. Además del test métrica a métrica, hay un χ² sobre las 330 frecuencias a la vez; el cuantil se aproxima con Wilson-Hilferty para no depender de SciPy.

**El punto exige un filtro aparte.** Su fuerza es 0 en las manos con juego, pero el lance solo se juega si *nadie* en la mesa tiene juego. `resolver_lance` lo gestiona en la versión escalar, y `ganadores_lance` en la vectorizada. Se añadió esta última al cerrar la fase, para que la Fase 2 no tenga que acordarse de aplicar el filtro. Un test comprueba con repartos reales que las dos versiones dan el mismo ganador en los cinco lances.

**Riesgo identificado: `lru_cache` y argumentos por defecto.** `f()` y `f(ReglasMus())` generaban dos entradas de caché distintas. Se resolvió con una función interna cacheada que siempre recibe las reglas explícitas.

## 2026-10-06 · Fase 2: equity

**Decisiones confirmadas con el usuario.** Cálculo exacto siempre que sea viable, con Monte Carlo como verificación cruzada. La información sobre otros jugadores es una condición genérica sobre su mano, no una lista cerrada de señas; las señas de cada zona se definirán encima. Los tantos esperados se calculan solo en paso (los envites son de la Fase 6). Se aceptan condiciones también sobre los rivales, en la API. La monotonía en la posición solo se exige a la equity **individual**.

**Equity exacta por programación dinámica sobre el mazo restante.** Fijada la mano del héroe, las otras tres se reparten de 36 cartas. Enumerar las 330³ ternas por mano sería caro, pero el peso de la última mano solo depende del mazo que queda tras quitar las dos anteriores, y hay pocos mazos distintos (≤ 6 435; 5 288 para R R C 5). Se precalcula `W3[mano, mazo]` y el resto son productos vectorizados. Los pesos son enteros: la suma total es exactamente C(36,4)·C(32,4)·C(28,4) ≈ 4,3·10¹³ < 2⁵³, así que en float64 las sumas son exactas, no aproximadas.

**El compañero se enumera primero.** El reparto es intercambiable, así que el orden de enumeración es libre. Con el compañero primero, "gana la pareja" se convierte en un producto de condiciones independientes sobre cada rival ("por debajo del mejor de nosotros dos, con el desempate por asiento"). Además, una condición sobre el compañero se aplica en ese mismo nivel.

**Umbrales con sumas acumuladas.** Las condiciones del tipo "fuerza del rival < umbral" se resuelven ordenando las manos por fuerza y precalculando sumas acumuladas. Así se evita recorrer los ~330 umbrales posibles.

**Tantos netos con una identidad.** Lo que cobran los rivales cuando ganan es E[jugadas rivales] − E[jugadas rivales · ganamos nosotros]. Esto funciona porque, si nadie tiene la jugada, sus tantos valen 0. Así todo se reduce a sumas con la misma estructura de producto.

**Rendimiento: limitado por la memoria, no por la CPU.** Se pasó de ~1 s a ~0,27 s por mano (4 posiciones × 5 lances), guardando W3 traspuesta para que la suma acumulada recorra filas contiguas. La tabla completa tarda 83 s con 1 proceso, 43 s con 4 y 45 s con 8: más procesos no ayudan porque se satura el ancho de banda de memoria. Por defecto se usan hasta 4. Una consulta suelta con condiciones tarda ~0,3 s. El usuario pidió no optimizar más.

**Caché en disco.** La tabla se guarda en `resultados/cache/equity_<hash>.npz`. El nombre incluye un hash de las reglas y de `VERSION_MOTOR`, de modo que cambiar una regla o el motor obliga a recalcular. Una vez generada, se carga en 0,1 s. Hubo una generación que tardó 6 078 s; repetida en condiciones controladas tardó 46 s y dio un resultado idéntico bit a bit. La causa más probable es que el equipo se suspendiera durante un corte de conexión, ya que `perf_counter` cuenta también el tiempo suspendido.

**Tres verificaciones independientes:**
1. **Fuerza bruta** (`tests/fuerza_bruta.py`): recorre todas las ternas en orden de asiento, en lugar de compañero primero, y decide los ganadores con `ganadores_lance`/`tantos_lance`, ya contrastadas con la resolución escalar. Coincide con el exacto a 1e-9.
2. **Monte Carlo** con muestreo por rechazo para las condiciones.
3. **Identidades exactas** sobre la tabla completa:
   - Σ posiciones P(gana) = P(se juega).
   - P(pareja 1) + P(pareja 2) = P(se juega).
   - Los tantos son de suma cero.
   - P(se juega juego) + P(se juega punto) = 1.
   - Monotonía individual en la posición.

**Corrección de Bonferroni en los tests de Monte Carlo.** Un test con ~63 comparaciones al 99,9 % tiene un ~6 % de probabilidad de fallar por azar, y le ocurrió a una con 3,5σ. La fuerza bruta confirmó que el exacto era correcto. Cambiar la semilla hasta que pasara habría sido trampa, así que se repartió el 0,1 % de error entre las 63 comparaciones (z ≈ 4,2 por comparación). En el uso normal de la CLI se mantiene el 95 %: allí que salga algún "FUERA" de vez en cuando es lo esperado.

**Tests lentos separados.** Se marcan con `@pytest.mark.slow`: fuerza bruta, Monte Carlo grandes y tabla completa. `pytest` ejecuta por defecto solo los rápidos (~10 s); los lentos se lanzan con `pytest -m slow`.

**La equity por pareja no es monótona en la posición.** Con una mano floja, a la pareja le va mejor si el compañero es mano, porque es él quien gana los empates. En grande pasa en 264 de las 330 manos: P(pareja) es mayor con el héroe en posición 3 que en posición 1. Hay un test que lo documenta con A A A A.

**Limitación conocida.** Todo supone manos del **reparto inicial** uniformes. En la mesa real los lances se juegan después del mus y los descartes, y cortar o no ya informa. Esto se corrige con la Fase 3.

## 2026-10-06 · Fase 3: reglas del mus confirmadas con el usuario

| Tema | Decisión |
|---|---|
| Descarte | Si hay mus, es obligatorio descartar al menos 1 carta (hasta 4). Quedarse servido equivale a cortar. |
| Información pública | Es público cuántas cartas pide cada uno; las descartadas no se enseñan. No se modela "mus visto". |
| Quién corta | Se habla en orden desde la mano y basta con que uno corte. No se modelan "mus corrido" ni otras variantes locales. |
| Mazo agotado | Configurable. Por defecto se barajan los descartes de rondas anteriores, se reparte en orden desde la mano y no hay límite de rondas. (En la primera ronda no puede agotarse: se piden como mucho 16 cartas y quedan 24.) |
| Objetivo de las políticas | Pesos por lance configurables, con los tantos en paso como valor por defecto. |
| Iteración 3b/3c | Si oscila, se amortigua mezclando la política nueva con la anterior antes de darla por no convergente. |

**Plan de la fase** (aprobado): 3a descarte de una mano aislada (exacto); 3b distribución de la mesa tras el mus (marginal exacta + equity con rivales reponderados, verificada con Monte Carlo de la ronda completa); 3c cortar o no, con el efecto de selección (solo llegan al descarte las manos con las que nadie corta) y recalculando la 3b.

## 2026-10-06 · Fase 3a: descarte de una mano aislada

**Opciones = sub-multiconjuntos distintos que se conservan.** Con rangos repetidos hay menos de 15 (R R C 5 tiene 11; R R R R, 4). En total hay 3 546 opciones para las 330 manos. Quedarse servido no es una opción si hay mus, porque equivale a cortar: solo se muestra como referencia.

**Distribución exacta por hipergeométrica multivariante.** Robar n cartas del mazo equivale, desde el punto de vista del jugador, a robarlas de las 36 que no ve: P(D) = ∏ C(U_r, d_r) / C(36, n), con U = copias − mano original (las descartadas no vuelven). Se verifica de tres formas:
- contra una enumeración de robos de cartas físicas, con fracciones exactas;
- contra valores calculados a mano (R C 5 4 tirando el 4: P(juego) = 22/36);
- contra Monte Carlo (χ²).

**Objetivos.** `tantos` son los tantos netos en paso de la pareja, con pesos por lance configurables (`--pesos "grande=2,punto=0"`; los lances no citados pesan 1). Los objetivos de un solo lance (`grande`, `chica`, `pares`, `juego`) maximizan P(gano yo ese lance): miden la fuerza de *mi* mano sin depender de lo que lleve el compañero.

**Valoración con la equity de la Fase 2.** Cada mano final se valora con la tabla del reparto inicial, en la que los rivales aún no se han descartado. Es la limitación principal de la 3a, y la que corrige la 3b. Por eso la "mejora" frente a la mano servida todavía no sirve para decidir si cortar: compara mi mano tras el mus con rivales que no se han descartado.

**Simplificación: mis descartes no se descuentan de las manos rivales.** La tabla de equity supone que las cartas que he tirado podrían estar en manos de los rivales. El efecto se medirá en la 3b, cuando la equity se recalcule contra la mesa tras el mus.

**Coste.** Las distribuciones de todas las manos y opciones se calculan en ~1 s usando una tabla de combinatorios indexada con NumPy (con listas de Python, la variante de 4 reyes tardaba 12 s). Valorar las opciones es un producto matriz-vector.

**Ajustes tras la revisión del usuario.**
- Las cartas pedidas se muestran también **ponderadas** por la probabilidad de cada mano, es decir, el % de repartos que se vería en la mesa. Ponderar cambia la imagen: las manos que piden 4 cartas son el 10,6 % de las manos distintas, pero solo el 6,5 % de los repartos.
- Dos opciones cuyo valor difiere menos de `UMBRAL_EQUIVALENCIA` = 0,005 (en las unidades del objetivo, configurable con `--umbral`) se marcan como **prácticamente equivalentes** (≈). Medio punto porcentual o media centésima de tanto no justifican presentar una opción como claramente mejor.

## 2026-10-06 · Fase 3b: la mesa después del mus

**Política de descarte como distribución.** Para cada posición y mano, una probabilidad por opción: array (4, manos, máx. opciones). Las políticas puras (mejor respuesta) son un caso particular. Las mixtas aparecen al amortiguar la iteración.

**Marginal exacta de cada asiento.** q_s = p0 · M_s, con M_s[h, h'] = Σ_o π_s(o | h) · P(h' | h, o). Es exacta aunque los cuatro roben del mismo mazo: desde el punto de vista de un jugador, lo que roba es un subconjunto uniforme de las 36 cartas que no ve, sea cual sea lo que hayan robado antes los demás. Se verifica con un χ² contra la simulación de la ronda completa en los cuatro asientos.

**Método descartado: reparto uniforme reponderado.** La idea era reutilizar el motor exacto de la Fase 2 reponderando el reparto uniforme con r_s(h) = q_s(h) / p0(h) en cada asiento (para ello, `equity` acepta ahora pesos por asiento, de los que las condiciones son un caso particular). La verificación contra la simulación de la ronda completa lo descartó:
- Errores de 0,3-0,6 tantos totales por mano.
- Solo 8 de 84 magnitudes de mesa dentro del IC.

El motivo: **el modelo no reproduce las marginales.** Comprobado el 2026-10-07 con la política de la 3a, comparando la simulación de 1 millón de rondas con el modelo (héroe en el asiento 1):

| Medida | Simulación real | Modelo reponderado |
|---|---|---|
| P(juego) de cada uno de los otros asientos | 60,4 % | **48,0 %** |
| P(compañero con juego), si yo tengo / no tengo juego | 0,559 / 0,671 | 0,442 / 0,538 |
| Correlación de "tener juego" entre dos asientos | −0,11 | también negativa |
| P(nadie tiene juego) | 0,0049 | 0,0258 |
| Producto de las marginales reales (como si fueran independientes) | 0,0246 | — |

- **La correlación real es negativa.** Las figuras son limitadas: si yo tengo juego, mi compañero lo tiene con menos frecuencia. Por eso P(nadie tiene juego) real queda muy por debajo del producto de marginales.
- **El fallo del modelo es de marginales, no de signo.** Bajo el reparto reponderado, la marginal de un asiento es ∝ p0(X)·r(X)·E[Π r_otros | X]. Ese último factor penaliza las manos ricas en figuras, porque dejan menos figuras a los demás asientos, cuyos pesos también las favorecen. Los cuatro pesos compiten por las mismas 16 figuras, y la marginal efectiva queda muy por debajo de q (48 % de juego frente a 60 %). En la mesa real esa competencia es menor porque las cartas bajas tiradas salen del juego y se reponen del mazo: las 16 cartas finales llevan 9,8 figuras de media, frente a 6,4 en el reparto inicial. Con menos juego para los rivales, el modelo sobrevaloraba el juego propio y el punto.
- Ajustar los pesos para cuadrar las marginales (ajuste proporcional iterativo) podría reducir el error, pero no garantiza que la estructura condicional sea la real, y la simulación ya es precisa y rápida.

*Corrección:* una versión anterior de esta nota atribuía el fallo a una correlación positiva del juego tras el mus. El usuario señaló que eso no casaba con los números, y los datos lo confirman: la correlación es negativa. Las cifras que se citaban entonces (0,0078 / 0,028 / 0,031) venían de otra política y se han sustituido por las de la tabla.

Los pesos por asiento se mantienen en `equity`: los necesitará la 3c para condicionar a "este jugador ha dado mus" con políticas mixtas.

**Equity tras el mus por simulación de la ronda completa.** La tabla de equity tras el mus se estima simulando rondas completas (4 millones por vuelta) y agrupando por la mano final de cada asiento, con su error típico. Las manos finales que no salen nunca (probabilidad despreciable) toman el valor de la Fase 2 como respaldo. Verificación contra una simulación independiente (otra semilla, 2 millones de rondas):
- 84/84 magnitudes de mesa dentro del IC al 99,9 %.
- Todas las manos frecuentes coinciden mano a mano dentro de su error combinado.

**Valoración de una mano concreta con la ronda simulada** (`valorar_opciones_simuladas`). Para decidir el descarte de una mano dada, se simula la ronda con esa mano fija y se prueban todas las opciones sobre los mismos repartos (números aleatorios comunes). Así se recogen mis propios descartes, que salen del juego, y la conjunta real de los rivales, y la diferencia entre opciones parecidas se estima con un intervalo varias veces más estrecho que el de cada valor por separado. La tabla agrupada por mano final ignora mis descartes: en 10 manos típicas × 2 posiciones la diferencia de valor llega a 0,25 tantos, pero el descarte recomendado coincide en los 20 casos.

**Punto fijo con amortiguación y criterio de explotabilidad.**
- Se parte de la política de la 3a. En cada vuelta: simulación → tabla → nueva mejor respuesta.
- Todas las vueltas usan la misma semilla, para que el ruido no haga cambiar decisiones de una vuelta a otra.
- Si la mejor respuesta vuelve a una política ya vista (un ciclo), se amortigua mezclando con la anterior. El peso de la nueva se reduce a la mitad en cada ciclo, como pidió el usuario.
- Criterio de parada: **explotabilidad media** < 0,001 tantos por mano. Es lo que ganaría de media un jugador que se desviara de forma óptima, ponderado por la probabilidad de cada mano.

Dos criterios previos fallaron:
1. **Que la mejor respuesta coincida con la política.** Con decisiones en el filo entre dos opciones casi iguales, el equilibrio es mixto y la iteración oscila sin fin.
2. **Que la ganancia máxima sea pequeña en todas las manos.** En manos rarísimas (7 4 4 4, P ≈ 0,0002), el valor de tirar las cuatro depende de manos finales que casi no salen en la simulación. Su ruido mantiene una ganancia máxima espuria de ~0,01-0,14 aunque nada relevante cambie.

Resultado: converge en 3 vueltas, con una explotabilidad media de 0,00004. Las tablas de cada vuelta se guardan en caché, así que repetir la iteración es instantáneo.

**Simulador de la ronda completa** (`simular_ronda_mus`): reparto, descarte en orden desde la mano, robo del mazo y los cinco lances en paso, todo vectorizado (~250 000 rondas/s). Comprobaciones:
- Con la política "quedarse servido" (solo existe con `minimo = 0`), reproduce las probabilidades exactas de la Fase 2.
- Con cualquier política, reproduce las marginales exactas.

**Sin efecto de selección.** En la 3b todos dan mus siempre. La comparación justa para "¿mejora dar mus?" es:
- valor tras el mus, con los cuatro descartándose;
- frente al valor de cortar, con nadie descartándose (equity del reparto inicial).

`descarte --tras-mus` presenta exactamente esa comparación. Con `--n`, la hace simulando la ronda con la mano fija.

**Resultado del caso testigo R R C S de mano** (tantos en paso, sin selección):
- En la 3a, dar mus mejoraba +0,73.
- Con los rivales también descartándose, dar mus *empeora* −0,34 [−0,35, −0,32]: cortar es mejor.
- Siendo postre empeora −1,09.

**Limitación conocida (anotada a petición del usuario): coordinación de pareja.** El modelo decide cortar o dar mus mano a mano, sin comunicación con el compañero. Un jugador real puede dar mus con una mano dudosa para que hable el compañero, o preguntarle con señas antes de decidir. Es una mejora futura. En la 3c se aproxima solo en el caso testigo de A A 4 5 de postre, condicionando a dos tipos de mano del compañero.

En general, cuando los rivales también mejoran, el mus vale bastante menos. Solo las manos realmente malas (R C 5 4, R 7 6 4) siguen ganando claramente con él, y al postre le favorece menos que a la mano.
