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
