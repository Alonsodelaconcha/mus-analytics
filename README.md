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

## Tests

```bash
python -m pytest
```

## Estructura

- `src/mus/reglas.py`: configuración de reglas (variante, orden del juego, 31 real, puntuación).
- `src/mus/cartas.py`: baraja y representación canónica de manos.
- `src/mus/evaluacion.py`: claves de cada lance y resolución entre 4 jugadores.
- `src/mus/tablas.py`: evaluaciones precalculadas de las 330 manos.
- `src/mus/simulacion.py`: reparto Monte Carlo vectorizado e intervalos de Wilson.
- `src/mus/analisis.py`: distribuciones exactas, verificación y exportación (CSV y gráficas).
- `docs/decisiones.md`: decisiones de diseño y sus motivos.
