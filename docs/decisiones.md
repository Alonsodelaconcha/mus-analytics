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

Cuando haya 40-50 manos anotadas, el 30 % de "Normal" se cambiará por el calibrado. *(Sustituido el 2026-10-08: el 30 % solo se cambia si el intervalo de los datos lo excluye; ver "Datos reales: 15 partidas".)*

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

> **Corregido el mismo día.** En la partida 1, la primera mano ("corto (tercero)") también era la especial y no se había excluido: los datos de esta entrada llevaban una mano de más (45 en vez de 44, y un corte de más del tercero). Las cifras de abajo ya están corregidas; entre corchetes, las que se publicaron. Los datos actuales, con 15 partidas, están en "Datos reales: 15 partidas, anotadas mano a mano".

**Qué manos se cuentan.** El usuario excluye la primera mano de cada partida: se juega con "mus corrido y sin señas", la norma tradicional para determinar la mano sin comunicación entre compañeros, así que no refleja decisiones de mus. También excluye una mano que no recuerda. Quedan 9 sesiones con 44 manos [45]; la primera sustituye a la que había. **Fase 6:** al modelar la partida completa, la primera mano de cada partida tiene estas reglas especiales.

**Calibración.** Hubo mus en 13 de 44 manos: 30 % (IC 95 %: 18-44 %) [29 %, 18-43 %]. Corresponde a λ = 0,64 (intervalo 0,45-0,84) [0,65; 0,46-0,85]. La mesa "Normal" de la web usa λ = 0,63 (30 %), dentro del intervalo, así que se deja como está. `calibrar` lo comprueba ahora cada vez.

**Corte por posición** (`datos/cortes_por_posicion.csv`). Es una comprobación independiente de la calibración: λ se ajustó con un solo número, la frecuencia total de mus, así que **el reparto del corte entre posiciones es una predicción del modelo que no se ha ajustado con estos datos**. Los datos son coherentes: cada posición habla tantas veces como la anterior menos las que cortó, y los que llegan al final sin corte son las 13 manos con mus.

| Posición | Corta / habla | Observado (IC 95 %) | Modelo, mesa "Normal" | p (binomial exacto) |
|---|---|---|---|---|
| Mano | 8 / 44 [8 / 45] | 18 % (10-32 %) | 21 % | 0,72 |
| Segundo | 11 / 36 [11 / 37] | 31 % (18-47 %) | 33 % | 0,86 |
| Tercero | 4 / 25 [5 / 26] | 16 % (6-35 %) | 18 % | 1,00 |
| Postre | 8 / 21 | 38 % (21-59 %) | 30 % | 0,48 |

- **Contraste global** (Pearson, 4 g.l.): χ² = 0,99, p = 0,91 [1,07; 0,90]. Los datos encajan con el modelo.
- **Por parejas.** La de la mano corta el 17 % de las veces que habla (modelo: 20 %). La pareja segundo-postre, el 33 % (modelo: 32 %). La segunda corta **1,92 veces más** (IC 95 % 1,02-3,61) [1,79; 0,97-3,31], y el modelo predice 1,58.

**Interpretación.**
- La predicción de la Fase 3c (que la pareja 2-4 corta mucho más porque el mus favorece a la de la mano) se confirma en el valor central.
- Pero con 44 manos el intervalo de la razón queda justo por encima de 1 (antes de corregir, lo incluía): los datos por sí solos apenas bastan para afirmar la diferencia. Lo que sí muestran es que no contradicen el modelo en ninguna posición. (Con 15 partidas, la razón baja a 1,41 y su intervalo vuelve a incluir el 1.)
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

## 2026-10-08 · λ por defecto de la línea de órdenes = mesa "Normal"

A petición del usuario, `cortar`, `corte-mesa` y `testigos` usan por defecto el λ de la mesa "Normal" de la web (0,63), para que la web y la línea de órdenes den siempre lo mismo.
- El λ no se escribe a mano: `web.factor_corte_de_mesa` lo calcula igual que el exportador, invirtiendo la curva P(hay mus | λ). Si un día cambia la frecuencia de mus de "Normal" (por ejemplo, al recalibrar), cambian las dos a la vez.
- Un test lento comprueba que coincide con el `factor_corte` de cada mesa en el manifiesto.
- `--mesa mucho-mus | normal | se-corta` elige el tipo de mesa y `--factor-corte` sigue permitiendo un λ a mano.

Las cifras de los casos testigo de la Fase 3c se calcularon con λ = 1. Para reproducirlas: `python -m mus testigos --mesa se-corta`.

## 2026-10-08 · Fase 4, paso 3: interfaz (primera versión completa)

**Indicaciones del usuario:**
- primero el móvil, usable con una mano en el bar;
- nada de imágenes de barajas comerciales;
- cifras en lenguaje de jugador ("ganas la grande unas 7 de cada 10 veces").

**Una sola pantalla, de arriba abajo:**
1. **Tu mano**: las 4 cartas, la jugada ("Par de reyes · 31 de juego"), la posición y "¿Ha habido mus?".
2. **Señas del compañero**, plegadas.
3. **¿Mus o corto?**, con el tipo de mesa.
4. **Si hay mus, ¿qué tiro?**
5. **Probabilidades de ganar.**
6. **ⓘ Cifras sin apostar (en paso)**: las limitaciones en lenguaje llano.

**Pensada para el pulgar:**
- El teclado de cartas está fijo abajo, con teclas de casi 60 px en el orden en que piensa un jugador: R C S 7 / 6 5 4 A. Las teclas del rey y del as indican "· 3" y "· 2".
- Con la cuarta carta, el teclado deja sitio a una barra con "Ha habido mus" y "Nueva mano", y el veredicto queda a la vista sin desplazar la pantalla (comprobado a 390 × 844).
- Todos los botones miden al menos 47 px de alto.

**Cartas de diseño propio:** una letra grande sobre un rectángulo claro, como el cartón de una baraja (también en modo oscuro). Las figuras van en rojo para distinguirlas de un vistazo. No hay imágenes.

**Flujo de una mano:**
- **La posición no tiene valor por defecto.** Un valor por defecto equivocado daría un consejo equivocado sin que se notara. Una vez elegida, se mantiene durante la sesión.
- **No se gira sola de una mano a otra:** habría que suponer cómo se pasa la mano en la mesa del usuario. Queda como idea.
- **Cambiar "¿Ha habido mus?" vacía las cartas.** Tras el mus la mano siempre es otra, porque hay que tirar al menos una.
- **"Ha habido mus" borra también las señas**, que en el MVP no se usan tras el mus.
- **"Nueva mano"** lo vacía todo menos la posición.
- **El tipo de mesa se recuerda en el móvil** (`localStorage`; si el navegador no deja guardar, funciona igual sin recordarlo).

**Lenguaje.** Todo el texto que ve el usuario sale de `web/src/vista/lenguaje.ts` y `vista.ts` (funciones puras, con tests). Sin "equity", "λ" ni "Monte Carlo".
- **Probabilidades:** el porcentaje y una frecuencia. "Unas 7 de cada 10 veces"; "1 de cada 14 veces" por debajo del 10 %; "casi nunca" y "casi siempre" en los extremos. "Ganáis" es la pareja; "tú solo" va en segundo plano. La barra enseña las dos cosas.
- **Tantos:** por cada 10 manos cuando la diferencia llega a 1 tanto cada 10 manos ("unos 3 tantos más cada 10 manos"); si no, por cada 100. Se pasa a "por mano" desde 1. Un primer redondeo convertía 0,07 en "1 tanto cada 10 manos", que exagera un 40 %; lo detectó un test.

**Umbrales de presentación** (decididos para esta versión; a revisar con la opinión del usuario como jugador):

| Situación | Cómo se presenta |
|---|---|
| Diferencia < 0,03 tantos por mano, o la simulación no distingue | "Da igual" (menos de 1 tanto cada 30 manos) |
| De 0,03 a 0,15 | "Corta" o "Da mus", con la etiqueta "Por poco" |
| Desde 0,15 | "Corta" o "Da mus", con la etiqueta "Claro" |
| Descarte a menos de 0,02 de la mejor, o dentro de su margen de error | "Casi igual que la mejor" |

**Descartes:**
- Arriba, la mejor opción ("Quédate con R C. Pides 2: tiras el cinco y el cuatro"). Las cartas iguales se agrupan: "tiras la sota y los dos cuatros".
- Debajo, las alternativas, con lo que se pierde con cada una. Al tocar una se ve con qué acabarías: probabilidad exacta de pares, juego y 31, calculada en el navegador.
- También cuánto ganaríais cada lance tras el mus: la distribución exacta de la mano final ponderada con la tabla de la mesa tras el mus.

**Señas:**
- Se marcan tocándolas y se combinan.
- Si son imposibles juntas, o con tus cartas, la web lo dice y no enseña probabilidades.
- La chuleta (nombre, gesto y cartas) se abre como hoja desde abajo y se cierra con "Cerrar", con Escape o tocando fuera.

**Tests de la interfaz** (26 nuevos; 101 en total en la web):
- Lenguaje y modelo de vista, con los datos reales.
- El flujo completo con React Testing Library en jsdom: meter cartas, posición, tipo de mesa (y que se recuerde), señas, señas imposibles, chuleta, "Ha habido mus", "Nueva mano", quitar y borrar cartas, y un fallo de carga con su reintento.

**Error encontrado al probarla en el navegador, ya corregido.** Dos toques muy seguidos en el teclado perdían una carta: cada toque calculaba la mano nueva a partir de una copia anterior del estado. Ahora se usan actualizaciones funcionales, que siempre parten del estado actual. El test de regresión falla con la versión antigua (comprobado) y pasa con la nueva.

**Probarla en el móvil.** `npm run movil` (servidor de desarrollo) o `npm run movil-final` (versión construida) la sirven en la red local. Instalarla y usarla sin conexión queda para el paso 4: el *service worker* que lo permite exige HTTPS, que en la red local no hay y en GitHub Pages sí.

## 2026-10-08 · Error al abrir la web por la red local: `crypto.subtle` solo existe en contextos seguros

**Qué pasó (lo encontró el usuario).** Al abrir la web por la dirección de red (http://172.20.10.2:4173), incluso desde el propio portátil, la recomendación, los descartes y las probabilidades fallaban con "Cannot read properties of undefined (reading 'digest')". Con localhost funcionaba.

**Causa.** La comprobación de huellas usaba `crypto.subtle`, que los navegadores solo ofrecen en contextos seguros: HTTPS o localhost. Por eso no lo vio ninguna prueba:
- Node y jsdom (donde corren los tests) tienen siempre `crypto.subtle`;
- las pruebas en el navegador se hicieron en localhost, que cuenta como seguro.

**Lección:** probar en las mismas condiciones que el usuario. Desde ahora, las pruebas en el navegador se hacen también por la IP de red.

**Arreglo:**
- **SHA-256 en JavaScript puro** (`web/src/nucleo/sha256.ts`, FIPS 180-4), como alternativa. `sha256()` usa `crypto.subtle` si existe y, si no existe o falla, la propia. La verificación de huellas se hace siempre.
- **Implementación propia en vez de una librería:** son 60 líneas sin dependencias, y se puede comprobar a fondo:
  - los vectores oficiales del NIST ("abc", la cadena vacía, los mensajes de 448 y 896 bits y un millón de "a");
  - las 72 constantes, calculadas aparte con aritmética entera exacta (BigInt): K[i] es la raíz cúbica entera de p·2⁹⁶ módulo 2³²;
  - la implementación de Node, en todas las longitudes de 0 a 300 bytes (cruzando todos los bordes del relleno);
  - las huellas del manifiesto de los 20 ficheros de datos.
- **Constantes escritas literalmente, no calculadas al cargar.** El estándar de JavaScript no obliga a que `Math.cbrt` redondee igual en todos los motores, y un solo bit distinto en Safari rompería todas las huellas en el iPhone.
- **Tests que simulan el contexto no seguro:** `crypto` sin `subtle`, sin `crypto` del todo, y con un `digest` que falla. Los datos se cargan y se verifican igual, y un fichero alterado se sigue rechazando. También hay uno del flujo completo de la web sin `crypto.subtle`.
- **Comprobado en un navegador real** abriendo la web por la IP de red: `isSecureContext` es `false`, `crypto.subtle` no existe y todo carga sin errores.

**Otras APIs que solo existen en contextos seguros.** En el código actual no hay ninguna más: `localStorage`, `fetch`, `TextDecoder` e `Intl` funcionan también por HTTP (y `localStorage` ya estaba protegido por si el navegador no deja guardar). Las que llegarán con el paso 4 sí lo son:
- el *service worker* y la caché del navegador (`caches`), necesarios para el uso sin conexión;
- la instalación como aplicación.

Para que no vuelva a pasar, una regla de ESLint prohíbe en `src` usar directamente `crypto.subtle`, `crypto.randomUUID`, `navigator.serviceWorker`, `navigator.clipboard`, `navigator.storage` y `caches`. Quien las use tiene que comprobar antes que existen y justificarlo en ese punto.

**Regla para el paso 4:** registrar el *service worker* solo si existe. Por la red local, la web funcionará conectada pero sin modo sin conexión; en GitHub Pages (HTTPS), con todo.

**De paso:**
- Concordancia de los mensajes de error: "No se ha podido cargar la recomendación", "No se han podido cargar los descartes". Hay un test.
- Los errores de red, que cada navegador da en inglés ("Failed to fetch", "Load failed"), ahora dicen "no hay conexión con el servidor de la web".

## 2026-10-08 · Fase 4, paso 3: comentarios del usuario tras probarla en el móvil

El usuario probó en su móvil, y le funcionaron bien:
- R R C S de mano: «Corta, claro».
- R C 5 4 de mano en mesa Normal: «Da mus», quedándose R C.
- A A 4 5 de postre, con y sin señas.
- Una mano tras el mus, los toques rápidos, el uso con una mano, la chuleta y el modo oscuro.

Pidió cuatro cambios.

**1. Las señas no cambian «¿mus o corto?» en el MVP, pero lo parecía.** El bloque de señas está encima del veredicto. El caso que señaló, comprobado con la línea de órdenes (mesa Normal):

| A A 4 5 de postre | Dar mus − cortar | Decisión |
|---|---|---|
| Sin información (`mus cortar "A A 4 5" --posicion 4`) | −0,51 [−0,53, −0,49] | Cortar |
| Compañero ciego (`--companero "sin_pares, sin_juego"`) | **+0,42** [+0,39, +0,46] | **Dar mus** |

La seña sí cambia la decisión, así que:
- con señas marcadas, el bloque de la recomendación dice «Ojo: este consejo no cuenta las señas de tu compañero»;
- el caso figura como ejemplo en las limitaciones.

*Una diferencia que no es un error.* Para el mismo caso sin información, la web enseña −0,56 ± 0,04 y la línea de órdenes, −0,51 ± 0,02. Con la semilla de la exportación, la línea de órdenes reproduce exactamente −0,5599, así que no hay diferencia sistemática. Con otras tres semillas sale −0,52. La simulación exportada cayó a casi dos desviaciones típicas del valor real, algo que pasa una de cada veinte veces, y su intervalo lo contiene. Por eso el texto de las limitaciones no da una cifra para el caso sin señas, y el test comprueba la decisión («Corta», clara) en vez de una cifra con un margen demasiado justo.

**2. Estructura y desplazamiento:** propuesta pendiente del visto bueno del usuario (al final de esta entrada). Lo que se comprobó: con «Ha habido mus = Sí» ya no aparecen «¿Mus o corto?» ni «¿Qué tiro?», solo «Tras el mus». Pero el bloque de señas, aunque desactivado, empuja las probabilidades por debajo del borde de la pantalla.

**3. La posición gira con «Nueva mano».** En la mesa del usuario la mano pasa al de la derecha: mano → postre, segundo → mano, tercero → segundo, postre → tercero.
- **El estado de la mano es ahora un *reducer*** (`web/src/mano.ts`): una función pura con todas las transiciones, probada sin React.
- **Solo gira «Nueva mano».** Las cartas, «¿Ha habido mus?» y las señas no cambian la posición.
- **El giro se anuncia** («Nueva mano: ahora eres postre (antes, mano). Si no es así, toca tu posición.»). El título del teclado dice «Tus cartas · eres postre», donde está el pulgar. Tocar la posición lo corrige y retira el aviso.
- **Si se pulsa «Nueva mano» varias veces seguidas** sin completar una mano, el aviso lo dice («Ojo: has pulsado «Nueva mano» 2 veces seguidas…»). Es justo el error que preocupaba: que la posición quede mal sin avisar.
- **Sin posición elegida no gira.** En la primera mano de cada partida basta con elegirla a mano.
- **Tests:** cuatro «Nueva mano» seguidas vuelven a la posición inicial (en las cuatro posiciones); los demás controles no la giran; el aviso aparece, cuenta las pulsaciones seguidas y desaparece al corregir.

**4. Umbrales:** se quedan en 0,03 y 0,15. En «Por poco» y «Da igual» se añade «Con envites o según el marcador, podría cambiar».

**Comprobación.**
- `npm run verificar`: 132 tests.
- Navegador, por localhost y por la IP de red.
- Las capturas a 390 × 844 se hicieron con Edge sin ventana, manejado por su protocolo de depuración desde un script de Node sin dependencias (en el directorio temporal de la sesión), con los mismos pasos para la versión anterior y la nueva. El navegador del panel daba capturas con mosaicos repetidos.
- Por la IP de red, el script comprueba además que no hay contexto seguro, que `crypto.subtle` no existe y que no aparece ningún error.
- La IP del portátil cambió durante la sesión (de 172.20.10.2 a 192.168.1.37) al cambiar de red Wi-Fi: hay que usar siempre la que muestra `npm run movil-final`.

**Propuesta de estructura (pendiente de que el usuario elija).** En la mesa hay tres momentos distintos:
- decidir mus o corto;
- alguien ha cortado y se juega con las cartas del reparto;
- ha habido mus y se juega con cartas nuevas.

Cada uno necesita cosas distintas, y hoy todo va en una sola columna larga. Dos opciones, con maquetas a 390 × 844:

- **A. Una pestaña por momento.** Bajo la mano (más compacta, con la posición), un selector con «¿Mus o corto?», «Se ha cortado» y «Ha habido mus». Cada pestaña enseña solo lo suyo:
  - la recomendación y el descarte;
  - las señas y las probabilidades con señas;
  - las cartas nuevas y las probabilidades tras el mus.

  Las señas solo están donde cuentan, así que no pueden parecer parte de la recomendación. Sustituye a «¿Ha habido mus? Sí/No».
- **B. Todo de un vistazo y el detalle en hojas.** Una tarjeta resume el veredicto, el mejor descarte y lo que se espera tener, y debajo hay una fila con las cinco probabilidades sin señas. La barra de abajo tiene «Han cortado», «Ha habido mus» y «Nueva mano»; «Han cortado» abre una hoja desde abajo con las señas y las probabilidades con señas.

**Recomendación: A.** Coincide con cómo transcurre la mano, separa las señas de la recomendación por diseño y casi no obliga a desplazarse. B es más rápida de leer pero esconde más cosas tras un toque.

## 2026-10-08 · Datos reales: 15 partidas, anotadas mano a mano

**Las anotaciones en bruto son la fuente.** Hasta ahora se apuntaban a mano los totales por sesión (`mus_real.csv`) y por posición (`cortes_por_posicion.csv`). Así se perdía lo que pasaba después de la primera ronda, y un error al sumar no se podía revisar. Ahora:
- `datos/manos_reales.csv` tiene una fila por mano: partida, número de mano, la secuencia de rondas, si se excluye y por qué, la posición del usuario, si ha usado la web y la anotación original, tal cual. Cada ronda es `mus` o la posición que corta: `mus mus mano` son dos rondas de mus y en la tercera corta la mano. `?` es lo que no se recuerda.
- `python -m mus manos-reales` (módulo `manos_reales`) valida el fichero y genera los dos resúmenes: `mus_real.csv` por partida y `cortes_por_posicion.csv` por partida y posición. Por partida, y no en totales, para poder medir la variación entre partidas.
- La validación rechaza lo que daría cifras falsas sin avisar: una primera mano sin excluir, una mano excluida sin motivo, una mano con la primera ronda desconocida sin excluir, rondas después de un corte, una mano que acaba en mus o huecos en la numeración. Los errores dicen la línea.
- `calibrar` avisa si los resúmenes no coinciden con las anotaciones, y un test falla si los versionados quedan desfasados.

**Criterios (del usuario).**
- **Se excluye la primera mano de cada partida.** Se juega con mus corrido y sin señas, y quien corta pasa a ser mano: así se decide la mano de la partida. No refleja decisiones de mus normales. **Fase 6:** la partida completa tiene que modelar esta primera mano aparte.
- Se excluyen las manos que no se recuerdan (una).
- Para las estadísticas solo cuenta la primera ronda.
- **Corrección:** en la partida 1, la primera mano también era la especial. Los datos anteriores llevaban una mano de más; la entrada anterior está corregida.

**Las cuentas a mano del usuario coinciden todas** con las que salen del fichero (un test las fija para las partidas 1-15):
- 87 manos anotadas; se excluyen 16 (15 primeras manos y 1 que no recuerda). Quedan 71, con mus en la primera ronda en 24 (34 %).
- Partidas 1-9: 44 manos y 13 con mus.
- Cortes en la primera ronda: mano 14 de 71, segundo 15 de 57, tercero 8 de 42 y postre 10 de 34. Son coherentes: cada posición habla tantas veces como la anterior menos las que cortó, y las 24 restantes son las manos con mus.

**Calibración (71 manos).** Mus en 24 de 71: 34 % (IC 95 %: 24-45 %). Corresponde a **λ = 0,58 (intervalo 0,44-0,73)**.

**Regla para la mesa "Normal" (del usuario).** Se mantiene en el 30 % (λ = 0,63) salvo que el intervalo de los datos la excluya. Ahora queda dentro, así que no cambia. Motivo: cambiarla con cada estimación movería las recomendaciones de la web sin una razón sólida, y el valor central todavía se mueve con cada partida (0,64 con 9 partidas; 0,58 con 15).

**Corte por posición** (comprobación independiente: λ se ajustó solo con la frecuencia total de mus):

| Posición | Corta / habla | Observado (IC 95 %) | Modelo, mesa "Normal" | p (binomial exacto) |
|---|---|---|---|---|
| Mano | 14 / 71 | 20 % (12-30 %) | 21 % | 0,88 |
| Segundo | 15 / 57 | 26 % (17-39 %) | 33 % | 0,33 |
| Tercero | 8 / 42 | 19 % (10-33 %) | 18 % | 0,84 |
| Postre | 10 / 34 | 29 % (17-46 %) | 30 % | 1,00 |

- **Contraste global** (Pearson, 4 g.l.): χ² = 1,21, p = 0,88. Los datos encajan con el modelo.
- **Por parejas.** La de la mano corta el 19 % de las veces que habla (modelo: 20 %); la pareja segundo-postre, el 27 % (modelo: 32 %). **Razón: 1,41 (IC 95 % 0,85-2,33)**; el modelo predice 1,59.
- **Interpretación.** Con las 9 primeras partidas la razón era 1,92 (1,02-3,61). Las 6 nuevas la bajan, sobre todo porque el segundo corta menos de lo previsto (26 % frente a 33 %, p = 0,33). La predicción del modelo queda dentro de los dos intervalos. Los datos siguen sin contradecir el modelo, pero tampoco bastan aún para confirmar que la pareja 2-4 corta más.

**Limitaciones de los datos.**
1. **Las manos de una misma partida no son independientes.** Juegan los mismos, con el mismo marcador y el estilo de esa noche. La frecuencia de mus varía mucho entre partidas: de 0 de 3 (partida 14) a 5 de 7 (partida 10). Los intervalos de Wilson suponen manos independientes. Para medirlo, `calibrar` muestra ahora:
   - **Si varía más de lo que daría el azar.** χ² de homogeneidad entre partidas = 15,8 con 14 g.l. Con partidas de 1 a 9 manos la aproximación χ² no vale, así que el p-valor sale de 100 000 permutaciones: se reparten al azar las 24 manos con mus entre las partidas, con sus tamaños. **p = 0,33**: la variación observada es compatible con el azar.
   - **Cuánto se ensancharía el error.** El error típico contando cada partida como un bloque (estimador robusto por conglomerados) es **×1,06** el binomial: el intervalo de λ apenas cambiaría.
   - **Pero con 15 partidas el contraste tiene poca potencia**: no detectaría una variación real moderada entre partidas. La limitación se mantiene, y conviene volver a mirarlo con más partidas.
2. **El usuario juega en todas las partidas**, así que su forma de jugar pesa en los datos. Según él, no es ni muy agresiva ni muy conservadora, y varía según la partida. Para poder separar sus decisiones de las de los demás, el fichero tiene dos columnas nuevas: `mi_posicion` y `usa_web`. Están vacías en las 15 partidas anotadas hasta ahora; el usuario las rellenará desde ahora. `manos-reales` cuenta cuántas manos las tienen.

**Dato para la Fase 6: rondas siguientes** (sin cambiar el modelo, que es de una sola ronda de mus). De las 24 manos con mus en la primera ronda, se sabe cómo siguieron 23 (en una solo se anotó "mus"). En **8 de 23 hubo otra ronda de mus: 35 % (IC 95 %: 19-55 %)**, como contó el usuario. Rondas de mus antes del corte: 1 en 15 manos, 2 en 7 y 3 en 1. La frecuencia se parece a la de la primera ronda (34 %), pero con 23 manos no se puede saber si tras el mus se corta más o menos que con las cartas del reparto.

## 2026-10-08 · Fase 4, paso 3: estructura A (una pestaña por momento de la mano)

El usuario eligió la estructura A (`docs/plan_fase4.md`, con sus decisiones al final) y aprobó los cambios anteriores: el aviso de las señas, el giro de la posición y el matiz de las decisiones ajustadas. Sobre la cifra de A A 4 5 de postre: −0,56 en la web frente a −0,51 en la línea de órdenes es ruido de la simulación (explicado en la entrada anterior); no se toca.

**Pantalla:**
- **Arriba, la mano compacta:** las cuatro cartas, más pequeñas (se siguen quitando tocándolas); a su lado, la jugada en dos líneas («Sin pares» / «29 al punto») y de qué cartas se trata («Mesa: normal», «Cartas del reparto», «Cartas tras el mus»); debajo, la posición.
- **Abajo, fijo para el pulgar:** las tres pestañas y, encima, el teclado mientras faltan cartas o «Nueva mano» con la mano completa. Antes de seguir se comprobó que caben bien a 390 px: título y subtítulo en una línea cada uno (captura `1-mus-o-corto`).
- **«¿Mus o corto?»:** la recomendación y el descarte. Una línea fija, «No tiene en cuenta las señas de tu compañero», sustituye al aviso que solo salía con señas marcadas (aquí ya no se pueden marcar).
- **«Se ha cortado»:** las señas en una rejilla de tres columnas, con el enlace a la chuleta en la fila del título, y debajo la fila de los cinco lances: el porcentaje de la pareja y la frecuencia corta («9 de 10», «1 de 14», «casi nunca»; mismos cortes que la frase larga). Al tocar un lance: la frase completa, «Tú solo: x %» y la nota del lance; otro toque lo cierra. Si el punto no se juega (tienes juego), la celda dice «—» y «no se juega».
- **«Ha habido mus»:** las cartas nuevas y la lista de probabilidades tras el mus, como antes, sin señas.
- **Accesibilidad:** las pestañas siguen el patrón ARIA de pestañas (`tablist`, `tab`, `tabpanel`, y las flechas del teclado cambian de pestaña).

**Estado de la mano (`mano.ts`).** La pestaña abierta pasa al *reducer*, con dos manos separadas: la del reparto (con sus señas) y la de después del mus. Así las reglas del usuario salen solas y se prueban sin pintar nada:
- completar las cartas no toca la pestaña;
- «Se ha cortado» y «¿Mus o corto?» comparten la mano del reparto;
- «Ha habido mus» empieza siempre vacía y no usa las señas;
- volver de «Ha habido mus» enseña otra vez la mano del reparto, que no se había borrado;
- la posición solo cambia con «Nueva mano» o tocándola.

**Una decisión a confirmar con el usuario: la mano repartida se restaura con sus señas.** Pidió que «Ha habido mus» borre las señas y que, al volver por un toque equivocado, se restaure la mano repartida. Si se restauraran las cartas pero no las señas, «Se ha cortado» enseñaría probabilidades sin las señas que había marcado, y el único indicio sería la nota «sin señas de tu compañero»: un error fácil de no ver. Por eso las señas se guardan con la mano repartida. En «Ha habido mus» no se ven ni se usan, y «Nueva mano» las borra de verdad. Al volver a entrar en «Ha habido mus», sus cartas empiezan otra vez vacías, como pidió el usuario.

**Que quepa en 390 × 844.** Con las pestañas abajo, el pie fijo mide unos 140 px (en la maqueta, unos 70 más 70 de las pestañas bajo la mano: el total es el mismo). En la primera versión, la fila de lances de «Se ha cortado» quedaba tapada por el pie. Se ganó el sitio así:
- la jugada en dos líneas fijas;
- cartas un poco más pequeñas y cabecera más baja;
- el enlace a la chuleta en la fila del título;
- la nota de la fila en una línea («Exacto, con las señas marcadas»: las señas se ven justo encima);
- bloques algo menos acolchados;
- **botones de seña de 44 px de alto** en vez de 47: es el mínimo recomendado para el dedo, y son anchos (un tercio de la pantalla). Es la única excepción a la regla de 47 px.

Al tocar un lance, la página se desplaza lo justo para que su frase no quede bajo el pie (`scrollIntoView` con un `scroll-margin-bottom` igual al alto del pie). Al cambiar de pestaña o con «Nueva mano», vuelve arriba.

**Tests** (149 en la web; 17 nuevos):
- *Reducer:* «Nueva mano» abre «¿Mus o corto?» desde las tres pestañas; completar las cartas no cambia de pestaña en ninguna; «Se ha cortado» conserva cartas y señas; «Ha habido mus» empieza vacía (también al volver a entrar); volver restaura la mano repartida con sus señas, hacia «¿Mus o corto?» y hacia «Se ha cortado»; la posición no cambia al cambiar de pestaña.
- *Flujo completo (jsdom):* lo mismo con clics; la fila de lances y su detalle; la línea fija; las flechas del teclado.
- *Los tests detectan los errores que deben:* con dos fallos introducidos a propósito en el *reducer* (no restaurar la mano; volver a «¿Mus o corto?» al completar las cartas) fallan 4 tests en cada caso, del *reducer* y del flujo.

**Script de capturas** (`web/scripts/capturas.mjs`, `npm run capturas`). Es el de la sesión anterior, guardado y mejorado; sin dependencias (Node trae `WebSocket` y `fetch`):
- escenas por defecto para las tres pestañas, el detalle de un lance y el teclado, con las manos de las maquetas;
- `--url` (localhost o la IP de red), `--tema claro|oscuro|ambos` y `--escenas` (un JSON con escenas propias);
- comprueba que no hay errores en la consola (salvo el `favicon.ico` que pide el navegador; la web tendrá icono en el paso 4) y dice si el contexto es seguro y si existe `crypto.subtle`. Sale con código 1 si algo falla.

*Error encontrado en el script antiguo:* mataba solo el proceso principal de Edge, y sus procesos hijos seguían vivos con el perfil temporal abierto. Había **56 procesos de Edge sin ventana** acumulados de las sesiones anteriores, y sus perfiles no se podían borrar. Se cerraron. Ahora el script cierra Edge de forma ordenada (`Browser.close` por el protocolo de depuración) y usa siempre la misma carpeta de perfil. Comprobado: tras ejecutarlo no queda ningún proceso.

**Comprobación:**
- `npm run verificar`: tipos, lint y 149 tests.
- Por localhost (servidor de desarrollo y versión construida) y por la IP de red (http://192.168.1.37:4173, versión construida): en las cinco escenas, sin errores en la consola. Por la IP de red, sin contexto seguro ni `crypto.subtle`, como debe ser.
- En un navegador real, el toque equivocado: reparto con seña → «Ha habido mus» (mano vacía) → dos cartas → «Se ha cortado» restaura R C 5 4, la seña y la posición.
- Capturas a 390 × 844, en claro y en oscuro, en `resultados/capturas` (no se versionan).

## 2026-10-12 · Fase 4, paso 4: publicación

El usuario aprobó el paso 3 tras probar la estructura A en su móvil y aprobó el plan de publicación con sus decisiones. Móvil de referencia: iPhone 15 (393 × 852).

### Qué queda expuesto al hacer público el repositorio

Se revisaron los ficheros y el historial completo (24 commits, una rama) antes de tocar nada:

| Qué | Lo que había | Decisión |
|---|---|---|
| Email | El gmail del usuario como autor y committer de los 24 commits; en ningún fichero | **Reescribir** con su dirección `noreply` de GitHub |
| Nombre | Nombre y apellidos en los commits; el usuario de GitHub también los lleva | Se deja: es un portfolio |
| Rutas y nombres | Ninguna ruta personal ni nombre en ficheros, historial o mensajes; dos IP privadas | Nada: no identifican |
| `datos/` | 87 filas sin nombres, fechas ni lugares | Se publican |
| `CLAUDE.md` y `docs/` | Se ve que el proyecto está hecho con Claude Code, y cómo | Se publican tal cual; el README lo dice en una línea |
| `.claude/` | Solo `launch.json`, nunca en git; la exclusión era local | `.claude/` a `.gitignore` |
| Secretos | Ninguno | — |

**Historial reescrito.** Solo cambian los campos de email de autor y committer (`git filter-branch --env-filter`); `git config user.email` se cambió antes de cualquier commit nuevo. Comprobado después: los 30 commits llevan la dirección `noreply` en los dos campos; el árbol, los nombres, las fechas, los asuntos y los mensajes de cada commit son idénticos a los de antes; el contenido final no cambia.
- *Por qué antes de publicar:* con el repositorio privado, un solo autor y ningún documento que cite hashes, cuesta poco. Una vez público, ya no sirve.
- *Por qué borrar y volver a crear el repositorio en GitHub, y no un push forzado:* tras un push forzado, GitHub conserva los commits antiguos accesibles por su hash, y la pestaña «Activity» los enlaza.
- *Copia de seguridad:* `resultados/copia-seguridad/mus-analytics-antes-de-reescribir.bundle` (fuera de git; contiene el email antiguo). **No se borra hasta que el usuario confirme que la web publicada funciona.**
- *Alternativas:* dejar el email (sin trabajo, pero público para siempre); un repositorio nuevo con un solo commit (se pierde el historial, que es parte del portfolio).

**Datos sin conversión de fin de línea.** `web/public/datos` y `web/test/referencia` se marcan `-text` en `.gitattributes`. La web comprueba la huella SHA-256 de cada fichero, y tiene que ser la misma en Windows, en GitHub y en el móvil. Hoy coinciden (los ficheros no tienen saltos de línea), pero con `text=auto` un cambio del exportador podía romperlo sin avisar.

### Licencia: AGPL-3.0

Decisión del usuario, con su motivo: la protección se puede reducir más adelante, pero no aumentar. De AGPL se puede pasar a MIT en versiones futuras; lo publicado con MIT queda libre para siempre. Como la web puede llegar a tener usuarios (Fase 5), prefiere que nadie pueda sacar una versión cerrada: la AGPL obliga a publicar el código también a quien la ofrezca como servicio web.

- `LICENSE` es el texto oficial de gnu.org, sin cambios; `pyproject.toml` y `package.json` declaran `AGPL-3.0-only`.
- **Dependencias compatibles.** Todas tienen licencias permisivas (MIT, BSD, Apache-2.0, ISC, MPL-2.0, PSF). Dentro del JavaScript publicado solo van `react`, `react-dom` y `scheduler` (MIT). La MIT pide conservar su aviso: el plugin escribe `licencias-de-terceros.txt` al construir, a partir de los módulos que entran de verdad en el paquete, y la web lo enlaza en el pie.
- **Enlace al código en la propia web** («Código fuente · licencia AGPL-3.0»): es lo que la AGPL exige ofrecer a quien usa una versión modificada por la red, y aquí queda puesto desde el principio.
- **Límites que conviene conocer** (no cambian la elección): la licencia se apoya en los derechos de autor, y cuánto protegen el código escrito con una IA es una cuestión legal sin cerrar; los datos y las cifras tienen una protección más débil que el código; y si algún día se aceptan contribuciones de otras personas, para cambiar de licencia hará falta su permiso.

### GitHub Pages

- **Ruta base `./`** en Vite: la misma versión construida sirve en localhost, por la IP de red y en `https://alonsodelaconcha.github.io/mus-analytics/`.
- **La publicación solo construye la web** (`npm ci`, `npm run verificar`, `npm run build`): los datos ya están versionados. Un segundo flujo, aparte, pasa los tests rápidos de Python en cada cambio; en una copia limpia, sin la caché local, tardan menos de un minuto.
- El flujo de publicación es el último commit, después de hacer público el repositorio: antes fallaría, porque Pages no está disponible.

### Modo sin conexión: *service worker* propio

**Cada versión publicada es un conjunto cerrado de ficheros con su huella.** Al construir, el plugin (`web/plugins/sinConexion.ts`) recorre la carpeta de salida, calcula el SHA-256 de cada fichero (31: la página, el JS, el CSS, los iconos y los 21 de datos) y mete la lista en `sw.js`. La huella de la lista es el identificador de la versión. De ahí sale todo lo demás:

- **`sw.js` va siempre en la misma dirección**, sin huella en el nombre: el navegador lo compara byte a byte con el que tiene. Como lleva la lista dentro, cualquier cambio del código o de los datos lo convierte en una versión nueva. Se pide sin caché HTTP (`updateViaCache: "none"`).
- **Todo o nada.** Una versión se descarga entera a su propia caché (`mus-analytics-<versión>`), pidiendo cada fichero sin caché HTTP y comprobando su huella. Si uno falla, llega a medias o no coincide, la caché se borra y la instalación falla: el navegador descarta ese *service worker* y la versión anterior sigue entera. Se reintenta en la siguiente comprobación.
- **Se guarda todo al instalar**, no según se usa: si no, una tabla de señas que nunca se abrió faltaría en modo avión.
- **La versión nueva espera.** No toma el mando por su cuenta: la página avisa («Hay una versión nueva. Al actualizar se empieza una mano nueva.») y solo cambia al pulsar «Actualizar», o sola al abrir la web si ya había una esperando, cuando todavía no hay ninguna mano a medias. Al cambiar se borran las cachés anteriores y la página se recarga: nunca se mezclan el código de una versión y los datos de otra.
- **Cuándo se busca:** al abrir la web y, como las webs instaladas en el móvil no se recargan sino que se quedan dormidas, también al volver a ella (como mucho una vez por minuto).
- **Solo se registra si existe** (`"serviceWorker" in navigator`) y en la web construida. Por la red local (HTTP) no lo hay y la web funciona igual; lo dice en el pie: «Aquí no se puede usar sin conexión».
- **La comprobación de la web sigue ahí** como segunda barrera: valida el manifiesto contra el núcleo y la huella de cada fichero al cargarlo. El plugin comprueba además, al construir, que los datos publicados son byte a byte los del manifiesto.
- **Pie de la web:** «Versión 0.1.0 (d5d0e6c) · datos del 2026-10-07» y el estado («Lista para usar sin conexión»). Sirve para saber qué versión hay en el móvil.

**Alternativas descartadas:**
- *`vite-plugin-pwa` (Workbox):* es lo habitual y ahorra código, pero la lógica delicada (qué pasa si una descarga falla, cuándo se cambia de versión) queda dentro de la librería. Aquí son unas 100 líneas, separadas en `web/sw/logica.ts` para poder probarlas con una caché y una red de mentira.
- *Que la versión nueva tome el mando enseguida* (`skipWaiting` al instalar): recargaría la página a mitad de una mano.
- *Guardar cada fichero la primera vez que se pide:* más simple, pero no garantiza que la web esté entera sin conexión ni que todos los ficheros sean de la misma versión.

### Salida de emergencia: si se publica un *service worker* con un fallo

El problema: los móviles que ya tienen un *service worker* siguen usándolo aunque se corrija la web, porque es él quien sirve la página. Lo único que el navegador pide siempre a la red, sin pasar por el *service worker*, es el propio `sw.js`: por eso su dirección no cambia nunca.

**Qué hacer:**
1. `npm run build:emergencia` (en `web/`). Construye la web con `web/sw/emergencia.ts` como `sw.js`, y una página que no registra ningún *service worker*.
2. Publicarla (en GitHub: lanzar a mano el flujo de publicación con la opción de emergencia, o subir ese cambio).
3. En cada móvil, la próxima vez que abra la web con conexión: el navegador encuentra el `sw.js` nuevo, que toma el mando enseguida, **borra las cachés de la web, se desregistra y recarga la página**, que vuelve a salir de la red.
4. Corregir el fallo y publicar una versión normal: la web vuelve a guardarse sola.

**Límites:** hace falta que el móvil abra la web con conexión (sin conexión sigue con la versión que tenga). Y está probado en Edge (Chromium), no en Safari: en el iPhone solo se puede comprobar publicándola.

**Probado en local** (paso 6 de `npm run prueba-sin-conexion`): con una versión normal instalada, se publica la de emergencia; el navegador queda sin *service worker* y sin cachés, la web funciona desde la red y dice «Aquí no se puede usar sin conexión», al recargar no se vuelve a registrar, y al publicar otra vez una versión normal vuelve a guardarse. Aparte se probó el caso menos favorable: abrir la web con una navegación normal cuando la página anterior sigue en la caché HTTP del navegador (GitHub Pages la deja 10 minutos). A los dos segundos la página ya es la nueva, y no hay bucle de recargas: `index.html` y `sw.js` se piden una sola vez.

### Instalación en el iPhone

- Manifiesto de la web (`manifest.webmanifest`), iconos y las etiquetas `apple-*` que usa «Añadir a pantalla de inicio». La barra de estado en estilo `default`: la pone el sistema, con texto legible en claro y en oscuro.
- **Zonas seguras:** `viewport-fit=cover` y márgenes con `env(safe-area-inset-*)` arriba (isla), abajo (barra de inicio; las pestañas quedan por encima) y a los lados.
- **Icono propio:** dos naipes lisos sobre el verde de la web y un 31, la mejor jugada. No usa dibujos de ninguna baraja. Sale de `web/scripts/iconos.mjs` (`npm run iconos`); los PNG se versionan.
- En el iPhone, la web instalada tiene su propio almacenamiento, distinto del de Safari: hay que abrirla una vez con conexión para que se guarde.

### Pruebas

- **Tests unitarios** (199 en la web; 50 nuevos): la lógica del *service worker* con una caché y una red de mentira (todo o nada con cinco tipos de fallo), la lista de ficheros y la versión, la comprobación de los datos, la parte de la página (cuándo se recarga y cuándo no) y la interfaz.
- **En un navegador de verdad** (`npm run prueba-sin-conexion`, Edge sin ventana): 58 comprobaciones con un servidor propio en `/mus-analytics/`, con la misma caché HTTP que GitHub Pages, que se apaga para simular el modo avión y hace fallar un fichero de datos **a mitad de la descarga** (con el resto ya descargado) de tres formas: corte de la conexión, contenido cambiado y error 500. En los tres casos la versión nueva no se instala y la anterior sigue entera, también sin red.
- **Zonas seguras** (`npm run capturas -- --instalada`): simula las del iPhone 15 (59 px arriba, 34 abajo), las dibuja en la captura y falla si algún botón o texto queda dentro.
- **Los tests detectan los errores que deben.** Con fallos puestos a propósito: sin comprobar la huella, sin borrar la caché a medias, sin desregistrarse en la emergencia, sin márgenes de zona segura, y recargando sin esperar al cambio de versión.

**Error encontrado en la propia prueba.** Con un fallo puesto a propósito (la versión nueva tomaba el mando sin esperar), la primera versión de la prueba pasaba entera. Miraba la página en cuanto aparecía el aviso, y en ese instante todo estaba todavía en su sitio: la recarga llegaba después. Ahora espera tres segundos, vuelve a mirar y exige que haya una versión esperando. *Lección:* una prueba que comprueba que algo **no** pasa tiene que dar tiempo a que pase.

### Publicada (2026-10-12)

<https://alonsodelaconcha.github.io/mus-analytics/>

**Orden seguido**, para que nada se viera antes de tiempo:
1. Todo lo anterior, en local, y el historial reescrito.
2. El usuario borró el repositorio de GitHub y lo creó de nuevo, privado y vacío. Se subió `main` y se comprobó en una copia recién clonada: una sola rama, todos los commits con la dirección `noreply` en autor y committer, el gmail en ningún campo ni mensaje, ninguna dirección de correo en los ficheros, y nada de `.claude/`, `resultados/` ni la copia de seguridad.
3. Aviso al usuario («Ahora»): lo hizo público y eligió Pages → «GitHub Actions».
4. El flujo de publicación, como último commit. Subirlo antes habría sido un riesgo: con un plan de pago, Pages publica también desde un repositorio privado.

**Resultado:** «Publicar la web» tardó 53 segundos y «Tests del motor», 40; los dos en verde. GitHub reconoce la licencia (AGPL-3.0).

**Comprobación de la web publicada** (`npm run comprobar-publicada`, 14 comprobaciones; sirve para después de cada publicación):
- Lee la lista de `sw.js` y descarga los 31 ficheros: todos coinciden con su huella, y los 21 de datos son byte a byte los del repositorio.
- Primera visita en un Edge limpio: contexto seguro, *service worker* registrado, una caché con los 31 ficheros, sin errores en la consola.
- **Modo avión de verdad:** el mismo navegador se vuelve a abrir sin poder resolver ningún nombre (`--host-resolver-rules`). Ni otra web ni un fichero sin guardar responden, y la web abre y funciona entera.
- La versión publicada (`d5d0e6c`) es la misma que sale al construir en Windows: la construcción da el mismo resultado en Windows y en Linux.

**Pendiente:** las pruebas del usuario en su iPhone (instalación, modo avión y actualización con una 0.1.1). Es lo único que no se ha podido probar aquí: todo lo anterior es en Edge, y el iPhone usa Safari.

### Pruebas en el iPhone y versión 0.1.1 (2026-10-12)

El usuario probó la web publicada en su iPhone 15. **Bien:** la instalación desde Safari, las franjas de arriba (barra de estado) y de abajo (barra de inicio) en claro y en oscuro, y el modo avión con las tres pestañas, las señas, los tres tipos de mesa y la chuleta. Era lo único que no se había podido probar aquí.

Antes de que la instalara se publicó un arreglo: el enlace a las licencias de terceros se abre aparte, como el del código, porque la web instalada no tiene botón de volver.

**Versión 0.1.1**, para probar la actualización. El cambio visible es el número de versión del pie. Antes de publicarla, un Edge guardó la 0.1.0; después (`npm run comprobar-publicada -- --actualizacion despues`), contra la web real de GitHub Pages: abrió con la 0.1.0 que tenía guardada, avisó de la nueva con una mano a medias sin tocarla, y al pulsar «Actualizar» pasó a la 0.1.1 con una sola caché. Queda que el usuario lo confirme en el iPhone.

## 2026-10-12 · Tras usarla en partidas reales: el entrenador pasa delante

**Opinión del usuario después de jugar con la web:**
- Usarla durante la partida es muy difícil: el juego va demasiado rápido. Su valor real está en analizar manos antes o después de jugar.
- Lo que más le interesa es un modo entrenamiento, al estilo de los entrenadores de póker: que plantee situaciones y haya que elegir la mejor jugada.

**Decisión:** el entrenador (Fase 5) se adelanta a las mejoras de la versión 2 de la web (señas tras el mus, quién ha cortado, modo torneo). No se empieza todavía: al cerrar el paso 4 se propone su plan.

*Qué cambia en la forma de pensar la web.* La calculadora se diseñó para consultarla con las cartas en la mano: teclado al alcance del pulgar, tres pestañas por momento de la mano, que quepa sin desplazar. Eso sigue sirviendo para repasar una mano, pero ya no es la prioridad. Lo que viene se piensa para quien estudia con calma.

**Lo que el plan de la Fase 5 tiene que tener en cuenta** (pedido por el usuario):
1. Qué se puede entrenar ya con el modelo en paso (mus o corto, descarte, intuición de las probabilidades) y qué necesita la Fase 6 (envites, órdagos, marcador).
2. Puntuar por los tantos perdidos frente a la mejor opción, no por acierto o fallo. Si la diferencia está dentro del margen de error, cualquier opción vale.
3. Si se puede empezar sin servidor, con todo precalculado y el progreso guardado en el móvil.
4. Qué manos plantear: al azar con su frecuencia real, o centrándose en las decisiones dudosas, que son las que enseñan.
5. No llamarlo "GTO": no hay un equilibrio fiable (el del modelo es degenerado). Es la mejor respuesta frente al tipo de mesa elegido, y la mesa "Normal" está calibrada con sus partidas reales. Hay que explicarlo así, en lenguaje de jugador.
6. Más adelante, el entrenador podría recoger de forma anónima las decisiones de los usuarios, como primer conjunto de datos de mus con jugadores reales. No para la primera versión, pero el diseño no debe impedirlo.

**Datos reales: plan de recogida.** El usuario seguirá apuntando partidas en `datos/manos_reales.csv`, ahora rellenando su posición en cada mano y si ha usado la web (las dos columnas ya existían, vacías en las 87 filas actuales).
- **Meta: unas 200 manos en total.** Con una frecuencia de mus del 34 %, el intervalo al 95 % es de ± 6,6 puntos, y ± 7,0 con el factor 1,06 por la variación entre partidas. Hoy, con 71 manos, es de ± 11.
- **Revisión de la calibración cada 50 manos más o menos** (`python -m mus manos-reales` y `python -m mus calibrar`).
- **Sigue la regla:** la mesa "Normal" solo cambia si el intervalo excluye el 30 %. Con 200 manos, eso pasaría con una frecuencia observada de alrededor del 37 % o más (o del 23 % o menos): con el 34 % actual, seguiría sin cambiar.
- Las dos columnas nuevas servirán para dos cosas que hoy no se pueden mirar: si el usuario corta distinto que el resto de la mesa (juega todas las partidas, y es una de las limitaciones anotadas) y si usar la web cambia lo que hace.

## 2026-10-12 · Fase 4 terminada

**La última prueba, bien.** En el iPhone del usuario, con una mano a medias salió el aviso de versión nueva sin tocar la mano; «Actualizar» pasó a la 0.1.1 (`60df1e6`), que funciona en modo avión. El usuario aprueba el paso 4 y la Fase 4.

**Qué deja la fase:** <https://alonsodelaconcha.github.io/mus-analytics/>, versión 0.1.1.
1. *Exportador* (`python -m mus exportar-web`): 21 ficheros de datos precalculados (3 MB) con su huella, y los ficheros de referencia para comprobar el núcleo de la web.
2. *Núcleo en TypeScript*: traducción exacta de la parte del motor que se calcula en el navegador, comparada con Python sin ninguna tolerancia.
3. *Interfaz*: tres pestañas, una por momento de la mano («¿Mus o corto?», «Se ha cortado», «Ha habido mus»), pensada para el móvil.
4. *Publicación*: repositorio público con el historial limpio, licencia AGPL-3.0, GitHub Pages con GitHub Actions, web instalable y uso sin conexión con un *service worker* propio.

**Pruebas al cerrar** (todas bien):

| Qué | Cuántas |
|---|---|
| Motor, tests rápidos (`pytest`) | 323 |
| Motor, tests lentos (`pytest -m slow`) | 47 |
| Web: tipos, lint y tests (`npm run verificar`) | 201 |
| Modo sin conexión en Edge (`npm run prueba-sin-conexion`) | 58 comprobaciones |
| Web publicada (`npm run comprobar-publicada -- --version 0.1.1`) | 14 comprobaciones |
| Paso de la 0.1.0 a la 0.1.1 en Edge, contra la web publicada | 6 comprobaciones |
| En el iPhone 15 del usuario | instalación, zonas seguras, modo avión y actualización |

**Cierre:**
- Etiqueta `v0.1.1` en el commit del que salió la versión publicada. A partir de ahora, cada versión publicada lleva la suya.
- La copia de seguridad del historial anterior a la reescritura se retiró del proyecto, a petición del usuario, una vez comprobada la web publicada. Nunca se subió.

**Lo que no se ha probado:** ningún móvil Android. La web instalada y el modo sin conexión están comprobados en Chromium (Edge) y en el iPhone del usuario.

**Lo que queda para después**, anotado en los pendientes de `CLAUDE.md`: señas tras el mus, tener en cuenta quién ha cortado, que las señas cuenten en «¿Mus o corto?» y el modo torneo. Todo eso va detrás del entrenador.

**Tres cosas aprendidas en la fase:**
- *Probar en las mismas condiciones que el usuario.* La web falló al abrirla por la red local porque ahí no hay contexto seguro; desde entonces se prueba también por la IP de red, y una regla de ESLint impide usar esas funciones sin comprobar antes que existen.
- *Una prueba de que algo no pasa tiene que dar tiempo a que pase.* La primera prueba del modo sin conexión daba por buena una versión que recargaba la página a mitad de una mano.
- *Usarla enseña más que diseñarla.* La calculadora se pensó para consultarla durante la partida, y en la mesa el juego va demasiado rápido. Lo que el usuario quiere de verdad es entrenar.

**Siguiente:** Fase 5, el entrenador. Su plan se propone en una sesión nueva.

## 2026-10-12 · Los dos códigos de una versión: el del pie y el commit

**Pregunta del usuario:** el pie de la web publicada dice «Versión 0.1.1 (60df1e6)», pero la etiqueta `v0.1.1` apunta al commit `01c64d0`. ¿Cuál es el bueno?

**Los dos: son cosas distintas.**
- `01c64d0` es el **commit de git** del que se construyó la versión publicada. La etiqueta `v0.1.1` apunta a él y está bien puesta.
- `60df1e6` **no es un commit** (git no tiene ningún objeto con ese nombre). Son los 7 primeros caracteres del **identificador de lo guardado** (`60df1e6e47eebcfb`): la huella SHA-256 de la lista de los 31 ficheros publicados con la huella de cada uno, que calcula `web/plugins/sinConexion.ts` al construir. Es el nombre de la caché del móvil (`mus-analytics-60df1e6e47eebcfb`) y lo que cambia cuando hay una versión nueva.

**Por qué el pie enseña ese y no el commit.** El pie responde a «¿qué hay guardado en este móvil?», y eso lo decide el contenido de los ficheros, no el historial. El identificador sale también en una web construida en local con cambios sin confirmar (`npm run movil-final`), donde un commit diría algo falso. Y dos commits con la misma web dan el mismo: los posteriores a `01c64d0` solo tocan documentación.

**Cómo se pasa de uno a otro.**
- *Del commit al pie:* construir la web en ese commit (`npm ci` y `npm run build` en `web/`) escribe «sw.js: versión 60df1e6e47eebcfb». Comprobado el 2026-10-12: sale ese identificador con el `web/` de la etiqueta (`git diff v0.1.1 HEAD -- web` no da nada), y es el que lleva el `sw.js` publicado.
- *Del pie al commit:* por el número de versión, no por el código: «0.1.1» → etiqueta `v0.1.1` → commit. De una huella no se puede volver atrás; por eso cada versión publicada lleva su etiqueta.

**La confusión es razonable:** siete caracteres hexadecimales entre paréntesis parecen un commit abreviado. No se cambia ahora, porque cambiar el pie es publicar una versión; se decide con la próxima.

## 2026-10-13 · Fase 5, paso 1: el motor y los datos del entrenador

Plan, respuestas y cambios pedidos por el usuario: `docs/plan_fase5.md`. El trabajo va en la rama `entrenador` hasta la publicación.

**El entrenador no calcula nada nuevo del juego.** Valora cada respuesta con las cifras que ya publica la web y con la misma regla que la calculadora: si la calculadora dice «Da igual» o «Casi igual que la mejor», no se pierde nada; si no, se pierde la diferencia con la mejor opción. `mus.entrenador` es esa regla en Python. Lee **solo los ficheros publicados**, con los mismos enteros que el navegador, y de él sale `web/test/referencia/entrenador.json`, que los tests de la web comparan sin tolerancia.

**Dos cifras nuevas por mano y posición**, de la misma simulación con la mano fija (`valorar_corte`):
- `p_habla`: probabilidad de que te toque hablar con esa mano, es decir, de que den mus todos los anteriores. Siendo mano vale 1.
- La ventaja de dar mus **lance a lance** (grande, chica, pares, juego y punto), cada una con su intervalo de confianza. Suman la ventaja total.

**Lo que ya publicaba la web no cambia.** El desglose se calcula con una función nueva (`tantos_netos_por_lance`) que, sumada, da bit a bit los tantos de siempre; hay un test que lo comprueba. Con las decisiones recalculadas:
- los 12 campos que ya existían son idénticos, número a número, en las tres mesas (3 960 decisiones y 42 552 descartes);
- los 20 ficheros de datos son los de la versión publicada (`v0.1.1`), salvo el campo `formato` y lo nuevo de las mesas.

Formato de los datos: 2 (`web.FORMATO`); cálculo de las decisiones: versión 2 (`web.VERSION_DECISIONES`).

**Coste del desglose por lance** (el usuario puso el límite en una hora de cálculo y 300 KB comprimidos):

| Qué | Medido |
|---|---|
| Cálculo de las tres mesas (6 procesos) | 34 minutos |
| Peso añadido a los ficheros de las mesas | 147 KB sin comprimir, 46 KB con gzip |
| Todos los datos de la web | 3,06 MB sin comprimir, 727 KB con gzip |
| Referencia para los tests (no se publica) | 389 KB |

Queda dentro de los dos límites, así que se hizo sin preguntar. El margen de error de cada lance es pequeño: de mediana, ± 0,007 tantos en la mesa Normal.

**Situaciones «como en la mesa» (cambio A).** Los pesos son productos de enteros, exactos también en JavaScript:
- «¿Mus o corto?»: combinaciones de la mano × `p_habla`. En la mesa Normal salen de mano el 36 % de las veces, de segundo el 29 %, de tercero el 19 % y de postre el 16 %.
- «¿Qué tiras?»: combinaciones × `p_habla` × probabilidad de que den mus los de después, y **solo si el entrenador no corta con esa mano**. Quien se entrena es quien decide con ella, y el modelo le supone la mejor respuesta; el λ de la mesa describe cuánto cortan los demás. Con R R C S no sale nunca. *El usuario pidió que «casi nunca» se llegara a descartar con ella: queda por confirmar que «nunca» le vale, antes del paso 4.*

**Tantos por cada 100 manos de partida.** No en todas las manos toca decidir. En la mesa Normal se decide mus o corto en el 69 % de las manos (84 % si se da mucho mus, 55 % si se corta mucho), y se llega a descartar en el 19 %. El resumen multiplica lo perdido por decisión por esa fracción.

**«Ajustadas».** Situaciones en que una opción es mejor de verdad, pero por menos de 0,20 tantos (2 cada 10 manos): 238 de las 1 320 en la mesa Normal. Las que dan igual quedan fuera: no enseñan nada, porque cualquier respuesta vale.

**Comprobaciones:**
- *Frente al cálculo exacto.* `p_habla` tiene valor combinatorio exacto. Se compara con él en las posiciones 2, 3 y 4 con una mesa de prueba, y en la 2 y la 3 con la política real de la mesa Normal.
- *Lo publicado es lo que da el motor.* Repetir `valorar_corte` con la semilla del exportador reproduce la ventaja, el desglose y `p_habla` publicados.
- *Casos testigo.* Dan en el entrenador el mismo veredicto que `python -m mus testigos`.
- *A mano.* `python -m mus entrenador "7 7 4 4" --posicion 1` imprime lo que enseña la pantalla: «CORTA (claro)», 1,069 tantos perdidos si se da mus, y el porqué: en pares se pierden 1,30.

**Alternativas descartadas:**
- *Un fichero aparte para el entrenador, sin subir el formato.* Los ficheros existentes habrían quedado byte a byte iguales. Se descartó porque el desglose es una propiedad de la decisión y también le sirve a la calculadora; la comprobación de que nada cambia se hizo comparando campo a campo.
- *`p_habla` exacta en vez de simulada.* De postre exige recorrer las manos de tres jugadores para cada una de las 330. La simulada tiene un error típico menor de 0,002 y solo se usa para sortear.
- *Usar el λ de la mesa también para la propia mano.* Supondría que en la mesa Normal se da mus con R R C S el 37 % de las veces.

## 2026-10-13 · Fase 5, paso 2: el núcleo del entrenador en la web

`web/src/entrenador/`: tres módulos sin interfaz, con sus tests.

**Valoración (`valoracion.ts`): una sola regla, la de la calculadora.** «¿Mus o corto?» se valora con `vistaDecision`, y los descartes con `esCasiIgual`, que se ha sacado de `vistaDescartes` para usarla en los dos sitios. El entrenador no tiene umbrales propios para decidir quién acierta: si un día cambian los de la calculadora, cambian los suyos.

**Comparación con Python, sin tolerancia.** Los tantos perdidos van en milésimas (enteros). Los tests comparan con `entrenador.json`, en las tres mesas: veredicto, intensidad y tantos perdidos de las 3 960 decisiones; tantos perdidos, opciones que valen y mejor opción de los 42 552 descartes; el peso de cada situación en los dos ejercicios y los dos modos; y los umbrales.

**Sorteo (`situaciones.ts`).** Una serie no repite situación. El azar llega por parámetro: en la web es `Math.random` y cada serie es distinta; solo los tests usan una semilla (cambio E). Un test sortea 40 000 veces y compara la frecuencia de cada posición con la que le toca por su peso.

**Progreso (`progreso.ts`, cambio D).**
- Es un registro de respuestas en el almacenamiento del navegador. Cada anotación va completa: fecha, ejercicio, modo, mesa, la mano escrita, posición, respuesta, la mejor, lo clara que era, tantos perdidos, fecha de los datos y versión de la web. No lleva ningún dato de quién responde: es el formato que algún día se podría recoger de forma anónima. Las cifras se calculan del registro; no se guarda ninguna aparte.
- **Exportar e importar.** Importar une el fichero con lo que hay, sin repetir: importar dos veces el mismo no cambia nada. Un fichero que no se entiende (no es de progreso, es de otra versión o tiene una respuesta dañada) no toca nada y dice por qué.
- **Un registro guardado que no se entiende no se pisa:** se aparta con otra clave antes de empezar uno nuevo.
- **Almacenamiento persistente.** Se pide con `navigator.storage.persist()` si existe. Solo existe en contextos seguros: por la red local no está, y el progreso se guarda igual.
- **Límite conocido.** El almacenamiento del navegador admite unos 5 MB, que dan para más de 10 000 respuestas (estimación: unos 190 caracteres por respuesta). Si un día no deja guardar, el entrenador lo dice y sigue. Si se queda corto, la alternativa es IndexedDB.

**Alternativa descartada:** guardar solo totales (respuestas y tantos perdidos). Ocupa menos, pero no permite el repaso de fallos ni sirve como conjunto de datos.
