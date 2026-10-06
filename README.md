# mus-analytics

Motor de estadísticas y estrategia para el mus (variante a 8 reyes por defecto; también 4 reyes).

## Instalación

```bash
py -3.14 -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
```

## Uso

```bash
python -m mus evaluar "R R C 5"
python -m mus resolver "R R C 5" "7 7 7 S" "A A 4 5" "C C S S"
python -m mus distribucion
python -m mus verificar --n 1000000 --semilla 42 --csv resultados/verificacion.csv
python -m mus tabla --csv resultados/manos.csv
python -m mus grafica --salida resultados/distribucion.png
python -m mus --variante 4reyes distribucion
python -m mus --31-real distribucion
```

Las cartas se escriben `A 4 5 6 7 S C R` (también `1`, `10`, `11`, `12`; en 8 reyes, `2` = As y `3` = Rey).

### Equity (Fase 2)

```bash
python -m mus equity "R R C 5" --posicion 1
python -m mus equity "R R C 5" --posicion 1 --companero "pares>=medias" --n 1000000
python -m mus ranking --lance pares --posicion 4 --top 15
python -m mus mesa
python -m mus equity-tabla --csv resultados/equity.csv --json resultados/equity.json --rankings resultados/rankings.csv
python -m mus grafica-posicion --salida resultados/posicion.png
python -m mus grafica-condicion "R R C 5" --companero "sin_pares" --salida resultados/condicion.png
```

**Las condiciones van siempre entre comillas.** En PowerShell, y en cualquier shell, `>` y `<` sin comillas redirigen la salida a un fichero. Sintaxis: cláusulas separadas por comas, que se combinan con "y": `sin_pares`, `con_pares`, `sin_juego`, `con_juego`, `pares>=medias`, `pares=duples`, `juego=31`, `suma>=28`, `reyes>=2`, `ases<=1`…

La tabla completa (330 manos × 4 posiciones) tarda ~45 s la primera vez y se guarda en `resultados/cache/`.

### Descarte (Fase 3a)

```bash
python -m mus descarte "R R C 5" --posicion 1
python -m mus descarte "R R C 5" --posicion 1 --objetivo grande --n 200000
python -m mus descarte "A A 4 5" --pesos "chica=2,punto=0"
python -m mus descarte-tabla --objetivo tantos --csv resultados/descartes_tantos.csv
```

Objetivos: `tantos` (tantos netos en paso, por defecto), `grande`, `chica`, `pares` y `juego` (P de ganar yo ese lance). Con `--pesos` se ponderan los tantos de cada lance. Las opciones que difieren menos de `--umbral` (0,005 por defecto) se marcan como prácticamente equivalentes (≈).

Por defecto, la valoración usa la equity del reparto inicial. Con `--tras-mus` se valora contra la mesa tras el mus (los rivales también se descartan), y la mano servida se compara con la equity de cortar.

### Mesa tras el mus (Fase 3b)

```bash
python -m mus tras-mus
python -m mus tras-mus --verificar 2000000 --semilla 1
python -m mus descarte "R R C S" --posicion 1 --tras-mus
python -m mus descarte "R R C S" --posicion 1 --tras-mus --n 400000 --semilla 7
python -m mus descarte-tabla --tras-mus --csv resultados/descartes_tras_mus.csv
```

`tras-mus` itera la política de descarte de los cuatro jugadores y la equity tras el mus, que se estima simulando rondas completas, hasta un punto fijo. La primera vez simula unas pocas vueltas (~1 min en total), que quedan en `resultados/cache/`. Muestra:
- cómo cambia la distribución de manos tras el mus;
- cuántas cartas se piden;
- las probabilidades de mesa antes y después del mus.

Con `--verificar N` compara la mesa con N rondas simuladas de forma independiente.

`descarte --tras-mus --n N` valora cada opción simulando la ronda con esa mano fija (sobre los mismos repartos para todas las opciones) y la compara con cortar.

## Tests

```bash
python -m pytest
```
```bash
python -m pytest -m slow
```

El primero ejecuta los tests rápidos (~10 s). El segundo, las verificaciones costosas: fuerza bruta, Monte Carlo grandes y tabla de equity completa (unos minutos).

## Estructura

- `src/mus/reglas.py`: configuración de reglas (variante, orden del juego, 31 real, puntuación).
- `src/mus/cartas.py`: baraja y representación canónica de manos.
- `src/mus/evaluacion.py`: claves de cada lance y resolución entre 4 jugadores.
- `src/mus/tablas.py`: evaluaciones precalculadas de las 330 manos.
- `src/mus/simulacion.py`: reparto Monte Carlo vectorizado e intervalos de Wilson.
- `src/mus/condiciones.py`: condiciones sobre la mano de otro jugador (información del compañero o de los rivales).
- `src/mus/equity.py`: equity exacta por mano, posición y lance (individual y pareja), tantos netos en paso y verificación Monte Carlo.
- `src/mus/descarte.py`: formas de descartarse, distribución exacta de la mano resultante y descarte recomendado según el objetivo.
- `src/mus/tras_mus.py`: políticas de descarte, distribución de la mesa tras el mus, iteración hasta el punto fijo y simulador de la ronda completa.
- `src/mus/analisis.py`: distribuciones exactas, verificación, rankings y exportación (CSV, JSON y gráficas).
- `docs/decisiones.md`: decisiones de diseño y sus motivos.
