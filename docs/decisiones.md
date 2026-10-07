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

## 2026-10-07 · Fase 3c: cortar o dar mus

**Casos testigo registrados antes de calcular** (`docs/casos_testigo.md`, commit propio). Solo sirven para validar; no se ha ajustado nada del modelo con ellos.

**Modelo.** Una política de corte κ_s(h) da la probabilidad de que el asiento s corte con la mano h si le toca hablar. En paso, los tantos solo dependen de las cartas, así que, para el asiento s (los anteriores han dado mus):
- cortar vale T_ini (los lances con las manos iniciales);
- dar mus vale w·T_mus + (1 − w)·T_ini, con w = Π_{k>s} (1 − κ_k) la probabilidad de que den mus todos los que hablan después. Si alguno corta, se juega con las manos iniciales, corte quien corte.

Simplificaciones: una sola ronda de mus, tantos en paso y sin comunicación entre compañeros.

**Efecto de selección con pesos de importancia.** En una misma simulación, para cada asiento y mano inicial se acumulan:
- el alcance, Π_{k<s} (1 − κ_k): la probabilidad de que los anteriores hayan dado mus;
- el valor de cortar;
- la ventaja del mus, w·(T_mus − T_ini).

La tabla de equity tras el mus se pondera por P(dan mus los cuatro). Usar pesos en vez de descartar repartos aprovecha todas las muestras. Los errores típicos usan el tamaño efectivo de Kish, (Σw)²/Σw².

**Verificación exacta del efecto de selección.** El valor de cortar es la equity del reparto inicial sabiendo que los anteriores dieron mus, y eso lo calcula exactamente el motor de la Fase 2 con pesos por asiento (1 − κ). Con una política de prueba ("cortar con juego"), la simulación coincide con el exacto en 9 de 9 combinaciones (|z| < 1,7), y hay un test que lo comprueba.

**El equilibrio del modelo es degenerado.** La iteración conjunta de corte y descarte se hizo con amortiguación 1/(t + 1) (*fictitious play*), porque sin ella oscilaba sin control. Converge a una mesa en la que casi nunca hay mus: P(hay mus) baja a ~1 % y sigue bajando, y la explotabilidad cae a la par. La causa:
- La ronda de mus da de media +0,28 tantos a la pareja de la mano (tras el mus casi siempre se juega el juego, y la mano gana los empates).
- La pareja 2-4 prefiere, por tanto, que no haya mus.
- Dar mus revela debilidad, y quien habla después lo explota cortando.
- En cuanto el postre corta casi siempre, las decisiones de los demás dejan de importar.

Nada del modelo frena esa espiral: en paso no hay envites que hagan valer más las jugadas que da el mus, ni marcador, ni coste de información al cortar. Es una limitación del modelo, que tiene su peso para la Fase 6.

**Escenario principal: rivales razonables (nivel 1).** Cada rival corta si, suponiendo que todos los demás dan mus, cortar le sale mejor, y se descarta con el equilibrio de la 3b. El jugador que decide responde de forma óptima a esos rivales, con el efecto de selección completo. Así razona un jugador que no anticipa que los demás también cortan. Resultado: P(hay mus) = 11,5 %. Los dos escenarios se muestran siempre juntos. La elección del principal se debe a que P(mus) → 0 no se parece a la mesa real, no a los casos testigo, que se calcularon después.

**Explotabilidad consciente del ruido.** En la 3c, la explotabilidad se mide **por reparto**: cada ganancia por desviarse se pondera por la probabilidad de llegar a esa decisión (hablar, o que haya mus). En el corte solo cuentan las ganancias estadísticamente significativas (|ventaja| > 2 errores típicos). En manos casi indiferentes, el signo de la ventaja es ruido de la simulación y daría ganancias ficticias. Tras 40 vueltas, la explotabilidad del corte es de 0,0033 tantos por reparto y la del descarte, < 0,0001.

**Sensibilidad a cuánto cortan los rivales.** Las decisiones dudosas dependen de la frecuencia de mus en la mesa, que el modelo no puede fijar por sí solo, porque el equilibrio es degenerado. Por eso se añade `--factor-corte λ`, que escala la probabilidad de corte de los rivales razonables. Ventaja de dar mus (en tantos):

| λ | P(hay mus) | R C 5 4 mano | R C 5 4 postre | A A 4 5 mano | A A 4 5 postre | A A 4 5 postre, compañero flojo | R R C S mano |
|---|---|---|---|---|---|---|---|
| 0 (nadie corta) | 1,00 | +1,46 | +0,63 | −0,31 | −0,26 | +1,10 | −0,33 |
| 0,5 | 0,40 | +0,47 | +0,28 | −0,27 | −0,47 | +0,61 | −0,33 |
| 0,75 | 0,23 | +0,15 | +0,09 | −0,25 | −0,54 | +0,27 | −0,31 |
| 1 (razonables) | 0,11 | −0,06 | −0,08 | −0,22 | −0,48 | −0,19 | −0,27 |

**Mecanismo.** Cuando los rivales cortan con sus buenas manos, el mus solo llega a producirse si ellos van flojos. En esos repartos, el mus les ayuda más a ellos que a mí, y jugar ya con las manos iniciales me favorece.

**Validación con los casos testigo** (`mus testigos`, 300 000 repartos por caso, IC 95 %):
- **12 de 12 "corto" coinciden** en los dos escenarios y con margen amplio: R R C S, R C S A, R R R A, R R A A, C S 6 5 y 7 7 7 S, de mano y de postre. De mano, la ventaja de cortar va de 0,27 a 0,60 tantos; de postre, de 1,7 a 4,0.
- **R C 5 4 (mano y postre): el usuario da mus; el modelo, con λ = 1, corta**, por −0,06 y −0,11 tantos por mano. La decisión cambia en λ ≈ 0,9 (P(hay mus) ≈ 15 %). Con mesas en las que el mus sea más frecuente, la del usuario es mejor, y por mucho (+1,46 si nadie corta). Valoración: la discrepancia viene del supuesto sobre los rivales, no de un error claro de ninguno de los dos. El modelo con λ = 1 probablemente infravalora la frecuencia de mus real.
- **Descarte de R C 5 4: el usuario se queda R, el modelo R C.** Pierde 0,05-0,10 tantos por mano en paso. Quedarse R es el mejor descarte si el objetivo es pares (3a, `--objetivo pares`). En paso los pares valen poco frente al juego, al que también ayuda el caballo, y con envites esa diferencia podría cambiar.
- **A A 4 5 de mano: el usuario duda y daría mus para que hable el compañero; el modelo corta** en todo el rango de λ (−0,21 a −0,31). Dar mus sin coordinación cuesta unos 0,2 tantos por mano. La razón del usuario (la coordinación de pareja) queda fuera del modelo. El caso de postre muestra que esa información vale mucho.
- **A A 4 5 de postre:**
  - sin información, cortar (−0,45);
  - con el compañero **"va bien"**, cortar (−1,23), igual que el usuario;
  - con el compañero **"flojo"**, el usuario daría mus. El modelo da mus mientras λ ≤ 0,75 (+0,27 a +1,10) y corta con λ = 1 (−0,19).

  Preguntar al compañero es justo lo que hace cambiar la decisión: es la limitación de coordinación anotada, y su valor queda medido.

Definiciones usadas para preguntar al compañero, sobre su mano inicial:
- "va bien": medias o duples, 31, o al menos dos reyes;
- "flojo": sin pares, sin juego y como mucho un rey.

## 2026-10-07 · Calibración de λ con partidas reales

**Qué se mide.** El usuario anota, en partidas reales contra personas, en qué proporción de manos hay mus en la primera ronda (`datos/mus_real.csv`, una fila por sesión). El modelo da esa misma proporción en función de λ: P(hay mus) baja de forma monótona desde el 100 % con λ = 0 hasta el 11 % con λ = 1. Por eso se puede invertir: se busca el λ que reproduce lo observado, interpolando una curva de 11 puntos.

**Incertidumbre.** El intervalo de λ sale de invertir el intervalo de Wilson de la proporción observada. Si parte del intervalo queda fuera de lo que da el modelo (menos del 11 % de mus), el extremo se recorta a 1 y se avisa.

**No cambia nada por sí solo.** A 2026-10-07 hay 7 manos, con mus en 2: un 29 %, con intervalo del 8 % al 64 %. Eso corresponde a λ ≈ 0,65, con un intervalo de 0,26 a 1. Es demasiado ancho para decidir. Con 40-50 manos se ejecutará `python -m mus calibrar` y se decidirá con el usuario si cambia el λ por defecto.

**Limitación.** λ resume en un único número cómo cortan los jugadores. Los jugadores reales no cortan exactamente como los rivales razonables escalados: influyen el marcador, las señas y el estilo. Es una calibración gruesa del escenario.

## 2026-10-07 · Fase 4: plan aprobado y respuestas del usuario

| Tema | Decisión |
|---|---|
| Señas | En el MVP solo cambian la probabilidad de ganar, no "¿mus o corto?". Que cuenten también ahí será lo primero de la versión 2. La web incluirá una chuleta con los gestos. |
| Tipos de mesa | Los tres niveles propuestos ("Se da mucho mus", "Normal", "Se corta mucho"), con "Normal" por defecto. |
| Variante | Solo 8 reyes. |
| Tecnología | React + TypeScript + Vite. Lo programa todo Claude, priorizando la calidad. |
| Nombre y repositorio | Mus Analytics. El usuario hará público el repositorio en el paso de publicación; hay que avisarle en ese momento. |
| Sin conexión | Instalable y usable sin conexión (PWA). |
| Idioma | Solo castellano. |

## 2026-10-07 · Fase 4: las señas

**Regla de la mesa del usuario.** Las señas son libres: el compañero puede hacer una, varias o ninguna. Cada seña significa "tengo al menos esto", y si hace varias, cumple todas: se combinan con "y". De las señas que **no** hace no se saca ninguna conclusión, porque puede tener la jugada y no haberla pasado. Por eso no hay opción "Ninguna seña": equivaldría a "sin información".

| Seña | Cartas (en 8 reyes, el 3 es rey y el 2 es as) | Gesto |
|---|---|---|
| Dos reyes | Exactamente dos reyes | Morderse el labio inferior |
| Tres reyes | Exactamente tres reyes, también el solomillo | Morderse el lateral del labio inferior |
| Dos ases | Exactamente dos ases | Sacar la punta de la lengua |
| Tres ases | Exactamente tres ases | Sacar la lengua de lado |
| Medias | Tres cartas iguales, también de reyes o de ases | Torcer la boca cerrada hacia un lado |
| Duples | Dos parejas o cuatro iguales | Levantar las cejas |
| 31 | Suma exactamente 31 | Guiñar un ojo |
| Solomillo | Tres reyes y un as | Dar un beso simulado |
| Ciego | Sin pares ni juego, con cualquier punto | Cerrar los ojos |
| 30 al punto | Sin pares ni juego, suma 30 | Levantar ambos hombros |
| 29 al punto | Sin pares ni juego, suma 29 | Levantar un hombro |

La primera versión que pasó el usuario tenía exclusiones ("tres reyes" sin solomillo, "medias" sin reyes ni ases, "ciego" sin 29 ni 30) para que el compañero hiciera solo la seña más concreta. Al listarle los solapamientos que quedaban (dos reyes y 31, duples y dos reyes o dos ases, medias y 31), decidió quitarlas todas y aplicar la regla de las señas libres. Interpretación de Claude, coherente con las reglas del juego: "medias" son exactamente tres iguales, porque cuatro iguales son duples.

**Consecuencia: 16 conjuntos de manos distintos.** Como la probabilidad de ganar condicionada solo depende del conjunto de manos que cumplen las señas, muchas combinaciones dan exactamente lo mismo. Hay 30 combinaciones posibles, pero solo 16 conjuntos distintos (`senas.grupos_de_senas`):
- las 11 señas sueltas;
- y 5 combinaciones: dos reyes + dos ases (solo R R A A), dos reyes + duples, dos reyes + 31, dos ases + duples y medias + 31.

El resto coinciden con uno de ellos. Por ejemplo, "tres reyes + medias" es "tres reyes", cualquier combinación con el solomillo es el solomillo y "ciego + 30 al punto" es "30 al punto". Las demás combinaciones son imposibles: ninguna mano cumple más de cuatro señas a la vez (R R R A cumple tres reyes, medias, 31 y solomillo).

**Por eso se precalculan todas, de forma exacta.** 16 tablas completas de equity con el motor de la Fase 2 (`calcular_tabla_equity(companero=...)`) cuestan una media hora, una sola vez. La alternativa era portar el motor exacto a TypeScript para calcular en el móvil (unos 50 MB de memoria y algunas décimas de segundo por consulta). Se descartó para el MVP: es la parte más delicada del motor, y con 16 conjuntos no hace falta.

**Idea para la versión 2, a petición del usuario: "modo torneo".** Señas obligatorias y completas, como en los reglamentos de Euskadi: con dos reyes y 31 hay que pasar la 31, y el ciego no se puede pasar con 29 ni con pares. En ese modo, que el compañero no haga una seña también da información, y entonces sí tiene sentido la opción "Ninguna seña".

## 2026-10-07 · Fase 4, paso 1: exportador de datos y ficheros de referencia

**`python -m mus exportar-web`** escribe dos cosas:
- `web/public/datos`: los datos que se publican con la web.
- `web/test/referencia`: los ficheros con los que se comprobará que el núcleo en TypeScript da lo mismo que Python.

Los datos se versionan en git, porque generarlos lleva más de media hora la primera vez y la publicación automática solo debe construir la web. `.gitattributes` los marca como generados.

| Fichero | Contenido | Cálculo |
|---|---|---|
| `equity/reparto.json` | Probabilidad de ganar cada lance y tantos esperados, por mano y posición, sin información | Exacto (Fase 2) |
| `equity/<señas>.json` (16) | Lo mismo sabiendo las señas del compañero | Exacto (Fase 2 con condición) |
| `mesa-<tipo>.json` (3) | ¿Mus o corto?, el valor de cada descarte si hay mus y la equity de la mesa tras el mus | Simulación (3c) |
| `manifiesto.json` | Versiones, reglas, escalas, orden de los arrays, señas con sus manos, tipos de mesa y huella SHA-256 de cada fichero | — |

**"¿Mus o corto?" mano a mano, no con la tabla agregada.** La propuesta era leer la decisión de la simulación de la mesa, que acumula la ventaja del mus por asiento y mano inicial. Su precisión depende de lo frecuente que sea la mano: 4 4 4 4 sale una vez de cada 91 390 repartos, así que en 20 millones de repartos tendría unos 200 casos por asiento, con un error típico de unos 0,2 tantos. En su lugar, cada mano y posición se simula con sus cartas fijas (`cortar.valorar_corte`, lo mismo que `python -m mus cortar`). Ventajas:
- la precisión no depende de lo rara que sea la mano;
- el descarte es la mejor respuesta de esa mano, con sus propios descartes fuera del mazo;
- la web dice exactamente lo mismo que la CLI.

Cuesta 1 320 simulaciones por tipo de mesa, en paralelo y una sola vez.

**Refinamiento en dos etapas.** Cada caso se simula con 100 000 repartos. Si la decisión queda indiferente (el IC 95 % de la ventaja contiene el 0), se repite **desde cero** con 400 000 y otra semilla, y se usa solo el segundo cálculo. Elegir qué casos se repiten mirando el primero no sesga el segundo, porque es independiente. Repetir solo lo dudoso concentra el cálculo donde la decisión está en el filo.

**El valor de cada descarte se da "sabiendo que hay mus".** `valorar_corte` valora cada descarte como valor de *dar mus*: incluye los repartos en que alguien corta después y se juega con las manos iniciales. Al descartarse, en cambio, el mus ya se ha dado. Por eso se añaden a cada opción `si_hay_mus` y `si_hay_mus_frente_a_la_mejor`: los mismos repartos, pesados por la probabilidad de que den mus todos (w·d en vez de w). El mejor descarte es el mismo, y la diferencia con el mejor es la anterior dividida por P(que den mus los que hablan después). Hay un test que comprueba esa identidad.

**Tipos de mesa por la frecuencia de mus, no por λ.** Lo que un jugador puede observar es cuántas manos acaban en mus, así que cada nivel se define por eso y su λ se obtiene invirtiendo la curva P(hay mus | λ) de la calibración:
- "Se da mucho mus": 60 %.
- "Normal": 30 %, como las primeras partidas del usuario.
- "Se corta mucho": λ = 1, los rivales razonables (11,5 %).

Cuando haya 40-50 manos anotadas, el 30 % de "Normal" se cambiará por el calibrado.

**Formato.**
- Enteros escalados: probabilidades ×10 000 y tantos ×1 000. Son más compactos que los decimales y conservan más precisión de la que se muestra.
- Arrays planos con el orden indicado en cada fichero. Las manos van en el orden canónico (por código), y el manifiesto incluye sus textos para que la web compruebe al cargar que su orden es el mismo. Las opciones de descarte van en el orden de `opciones_descarte`, con sus códigos en el manifiesto.
- `null` = no disponible (señas imposibles con la mano del héroe, o casos no calculados).
- La decisión se exporta como código (1 / −1 / 0) y no se deduce en la web de la ventaja y su radio, porque al redondear podría cambiar en los casos límite.
- `allow_nan=False`: un NaN olvidado hace fallar la exportación en vez de producir un JSON inválido.
- `web.FORMATO` versiona la estructura; `web.VERSION_DECISIONES`, el cálculo.

**Ficheros de referencia, comparables sin redondeos.**
- `evaluacion.json`: las 330 manos (conteos, código, combinaciones, suma, pares, tantos y fuerza en cada lance) y 36 entradas de texto, válidas e inválidas, con lo que hace Python al leerlas.
- `lances.json`: 12 repartos especiales (empates en todas las posiciones, nadie con pares o juego, punto, duples...) y 3 000 aleatorios. Se resuelven con `resolver_mano`, la versión escalar, que no usa las tablas.
- `descartes.json`: las 3 546 opciones de descarte en orden canónico. La distribución de la mano final se da con **numeradores enteros** sobre C(36, cartas pedidas), así que TypeScript tiene que acertar exactamente, no a 1e-9. Guardar la distribución completa de todas las opciones ocuparía varios MB. En su lugar, cada opción lleva los totales por jugada y dos **huellas**: Σ numerador · peso, con pesos pseudoaleatorios fijos. Cualquier diferencia en cualquier mano final cambia la huella. Los pesos son < 2²⁰, de modo que las sumas (< 2·10¹³) son exactas en la doble precisión de JavaScript. Además, para 22 manos (234 opciones) se da la distribución completa.

**Reproducible.** Cada caso usa una semilla propia derivada de la mano y la posición, así que el resultado no depende del número de procesos (hay un test que lo comprueba). Regenerar los datos da los mismos ficheros, salvo la fecha del manifiesto.

**`python -m mus consultar-web`** lee los ficheros exportados, sin usar el motor salvo para leer la mano, y enseña lo que verá la web para una mano, posición, mesa y señas. Sirve para comparar los datos con `mus equity` y `mus cortar`.

**Resultado de la exportación (2026-10-07).** 33 minutos con 6 procesos la primera vez; desde la caché, 3 segundos.

| Tipo de mesa | λ | P(hay mus) | Decisiones repetidas | Siguen indiferentes | IC 95 % medio |
|---|---|---|---|---|---|
| Se da mucho mus | 0,29 | 60,4 % | 32 de 1 320 | 12 (\|ventaja\| ≤ 0,014) | ±0,027 tantos |
| Normal | 0,63 | 30,1 % | 37 | 14 (≤ 0,018) | ±0,026 |
| Se corta mucho | 1 | 11,5 % | 34 | 13 (≤ 0,025) | ±0,035 |

Las que siguen indiferentes tras 400 000 repartos valen lo mismo en la práctica: la diferencia es de menos de 3 centésimas de tanto. Con R C 5 4 de mano, por ejemplo, la decisión cambia con la mesa: dar mus gana +0,82 con mucho mus y +0,28 en la normal, y cortar es mejor si se corta mucho (−0,07).

Tamaño: 21 ficheros, 2,9 MB sin comprimir y **682 KB con gzip** (la propuesta estimaba 1-2 MB sin comprimir; las señas combinables y los descartes de cada mano suman más, pero comprimen bien).

**Verificación de los datos exportados:**
- Con señas, `consultar-web` da las mismas cifras que `mus equity` con la condición equivalente.
- 24 casos al azar por tipo de mesa, simulados de nuevo con otra semilla: las diferencias normalizadas (z) tienen media ≈ 0 y desviación típica ≈ 1, como deben. El máximo es |z| = 2,2, por debajo del umbral de 4,35 (99,9 % global con Bonferroni).
- Los 16 casos testigo en la mesa "Se corta mucho" reproducen las cifras de la Fase 3c.
- Regenerar desde la caché en otra carpeta da ficheros idénticos.

## 2026-10-08 · Fase 4: qué probabilidad de ganar enseña la web

Las probabilidades exactas con señas son las de las cartas **tal como se repartieron**. Valen cuando la mano se juega sin mus (alguien corta), que en una mesa "Normal" es el 70 % de las manos. Si hay mus, las manos de los demás mejoran mucho (el juego pasa del 27 % a ~56 %) y esas cifras dejan de valer.

**Decisión (aprobada por el usuario).** La web pregunta "¿Ha habido mus?":
- **No**: probabilidades exactas, con las señas del compañero.
- **Sí**: las de la mesa tras el mus del tipo de mesa elegido (ya exportadas en `mesa-<tipo>.json`), **sin señas**.

Las dos limitaciones se explicarán claramente en la web:
1. Tras el mus no se pueden usar las señas.
2. No se tiene en cuenta quién ha cortado: si corta un rival, suele ir bien, y la web no lo refleja.

**Versión 2, prioridad alta:**
- Señas tras el mus. Habría que simular la mesa agrupando por la mano final del compañero, con su margen de error.
- Quién ha cortado, como condición sobre el asiento que corta. Es exacto con el motor de la Fase 2: el que corta pesa κ(mano), los anteriores 1 − κ(mano), como en el test de la 3c que verifica el efecto de selección.

## 2026-10-08 · Datos reales: calibración de λ y corte por posición

**Qué manos se cuentan.** El usuario excluye la primera mano de cada partida: se juega con "mus corrido y sin señas", la norma tradicional para determinar la mano sin comunicación entre compañeros, así que no refleja decisiones de mus. También excluye una mano que no recuerda. Quedan 9 sesiones con 45 manos; la primera sustituye a la que había. **Fase 6:** al modelar la partida completa, la primera mano de cada partida tiene estas reglas especiales.

**Calibración.** Hubo mus en 13 de 45 manos: 29 % (IC 95 %: 18-43 %). Corresponde a λ = 0,65 (intervalo 0,46-0,85). La mesa "Normal" de la web usa λ = 0,63 (30 %), dentro del intervalo, así que se deja como está. `calibrar` lo comprueba ahora cada vez.

**Corte por posición** (`datos/cortes_por_posicion.csv`). Es una comprobación independiente de la calibración: λ se ajustó con un solo número, la frecuencia total de mus, así que **el reparto del corte entre posiciones es una predicción del modelo que no se ha ajustado con estos datos**. Los datos son coherentes: cada posición habla tantas veces como la anterior menos las que cortó, y los que llegan al final sin corte son las 13 manos con mus.

| Posición | Corta / habla | Observado (IC 95 %) | Modelo, mesa "Normal" | p (binomial exacto) |
|---|---|---|---|---|
| Mano | 8 / 45 | 18 % (9-31 %) | 21 % | 0,72 |
| Segundo | 11 / 37 | 30 % (17-46 %) | 33 % | 0,86 |
| Tercero | 5 / 26 | 19 % (9-38 %) | 18 % | 0,80 |
| Postre | 8 / 21 | 38 % (21-59 %) | 30 % | 0,48 |

- **Contraste global** (Pearson, 4 g.l.): χ² = 1,07, p = 0,90. Los datos encajan con el modelo.
- **Por parejas.** La de la mano corta el 18 % de las veces que habla (modelo: 20 %). La pareja segundo-postre, el 33 % (modelo: 32 %). La segunda corta **1,79 veces más** (IC 95 % 0,97-3,31), y el modelo predice 1,59.

**Interpretación.**
- La predicción de la Fase 3c (que la pareja 2-4 corta mucho más porque el mus favorece a la de la mano) se confirma en el valor central.
- Pero con 45 manos el intervalo de la razón casi llega a 1: los datos por sí solos aún no bastan para afirmar la diferencia. Lo que sí muestran es que no contradicen el modelo en ninguna posición.
- En el modelo, la razón es ~1,6 para cualquier λ. λ escala por igual el corte de los cuatro asientos, así que la estructura entre posiciones viene de los rivales razonables, no de λ.

**Herramientas.** `calibracion.leer_cortes`, `comparar_cortes` (binomial exacto por posición, χ² global con su cola exacta para grados pares y razón entre parejas por el método delta) y `cortes_del_modelo`. `python -m mus calibrar` lo muestra si existe el fichero y avisa si no cuadra con `mus_real.csv`.

## 2026-10-08 · Fase 4, paso 2: núcleo en TypeScript

**Qué se porta y qué no.** En el navegador se calcula solo lo exacto y barato:
- leer una mano escrita;
- evaluar cada lance (claves, fuerza densa de las 330 manos, resolución de un lance entre cuatro);
- las opciones de descarte;
- la distribución exacta de la mano final.

Lo pesado (equity, simulaciones de la mesa) llega precalculado. El núcleo también lee los datos exportados y busca la tabla que corresponde a las señas marcadas. Está en `web/src/nucleo` (`cartas`, `evaluacion`, `tablas`, `descarte`, `senas`, `datos`), con los mismos nombres que en Python.

**Tecnología.**

| Pieza | Elección y motivo |
|---|---|
| Proyecto | Vite 8 + React 19, creado a mano en vez de con la plantilla, para controlar exactamente qué lleva. |
| TypeScript | **6.0, no 7.** TypeScript 7 es la reescritura nativa en Go y acaba de salir: `typescript-eslint` todavía no la admite (exige < 6.1). Cuando la admita, el cambio es una línea. |
| Comprobación de tipos | `strict`, `noUncheckedIndexedAccess` (acceder a un array puede dar `undefined`) y `exactOptionalPropertyTypes`. |
| Configuración | Referencias de proyecto, como la plantilla oficial de Vite: `src` se comprueba solo con los tipos del navegador, y los tests con los de Node. |
| Lint y tests | ESLint 10 con `strictTypeChecked` y las reglas de los hooks de React; Vitest 5. |

`npm run verificar` = tipos + lint + tests.

**Exactitud: se compara sin tolerancia.** Toda la aritmética del núcleo es entera. Los numeradores de la distribución tras el descarte son < C(36, 4) = 58 905, y las huellas, < 2⁵³, así que en la doble precisión de JavaScript son exactos. Los tests exigen igualdad exacta (`toEqual`) con los ficheros de referencia de Python:
- 330 manos: conteos, código, combinaciones, suma, pares, tantos y fuerza en los cinco lances;
- 36 entradas de texto;
- 3 012 repartos resueltos;
- 3 546 opciones de descarte con sus numeradores por jugada y sus dos huellas;
- 234 distribuciones completas.

Se comprobó que los tests detectan errores: con dos fallos sutiles introducidos a propósito, fallaron.
1. Que los empates los gane el jugador más alejado de la mano.
2. Un caballo de más entre las cartas no vistas.

*Error del propio test, corregido:* la primera versión calculaba la huella como esperanza × denominador, y la división intermedia la desviaba en 4·10⁻⁶. Una cantidad entera se compara con aritmética entera.

**La carga de datos desconfía de lo que recibe.** Los arrays se indexan por posición, así que si las manos o las opciones de descarte no fueran en el mismo orden que en el núcleo, la web enseñaría las cifras de otra mano **sin ningún error visible**. Por eso, al cargar el manifiesto se comprueba:
- que sus 330 manos y 3 546 opciones coinciden, una a una, con las que calcula el núcleo;
- que las reglas son las de la web;
- el formato.

Además, cada fichero se verifica con su huella SHA-256 (Web Crypto). Esto detecta ficheros a medio descargar o de otra versión guardados en la caché del navegador, un riesgo real en una web que funciona sin conexión. Las descargas fallidas no se guardan, para poder reintentar cuando vuelva la cobertura. Un manifiesto mal formado da un `ErrorDatos` claro, no un `TypeError`.

**Los ficheros versionados no pueden quedarse desfasados.** Dos tests de Python lo comprueban:
- los ficheros de referencia coinciden byte a byte con los que genera el exportador;
- los datos de la web pasan su manifiesto y son de la misma versión del motor.

Si alguien cambia el motor y no regenera, fallan.

**Comprobado en un navegador real** con una página provisional (la interfaz es el paso 3): el manifiesto se valida, los ficheros se descargan con su huella correcta y no hay errores en la consola. El paquete pesa 228 KB (72 KB comprimido) con React incluido; los datos, 682 KB comprimidos.
