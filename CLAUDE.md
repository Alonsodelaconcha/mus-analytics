# Mus Analytics: estadísticas y entrenamiento para el Mus a 8 reyes

## Visión del proyecto
Construir la herramienta de referencia de estadísticas y estrategia para el mus, al estilo de las calculadoras y entrenadores de póker (Equilab, GTO Wizard), pensada para jugadores reales: aficionados interesados y jugadores de torneo.

Producto final previsto (web progresiva, PWA):
1. **Calculadora de probabilidades**: mano + posición → probabilidad de ganar cada lance (individual y por pareja) y tantos esperados; opcionalmente condicionada a la información del compañero (señas).
2. **Asesor de descarte**: compara todas las formas de descartarse y recomienda según el objetivo (grande, chica, juego) y si conviene cortar mus.
3. **Entrenador de situaciones**: plantea manos con posición, marcador y envites previos; el usuario decide y recibe la valoración y una explicación.
4. **Calculadora de órdago según marcador**: equivalente al ICM del póker.

Este repositorio empieza por el **motor** (Python), que es la base de todo lo demás.

## Reglas del juego (variante por defecto: 8 reyes)
Si algo es ambiguo, PREGUNTA al usuario antes de asumir. Todas las reglas deben ser configurables mediante un objeto de configuración.

- Baraja española de 40 cartas: As, 2, 3, 4, 5, 6, 7, Sota, Caballo, Rey. El palo no importa.
- 8 reyes: los 3 cuentan como Reyes y los 2 como Ases a todos los efectos → 8 Reyes, 8 Ases y 4 de cada una del resto.
- Orden de mayor a menor: Rey > Caballo > Sota > 7 > 6 > 5 > 4 > As.
- Valor para Juego/Punto: Rey, Caballo y Sota = 10; del 7 al 4, su número; As = 1.
- 4 jugadores con 4 cartas. Posiciones en orden de juego: 1 = mano, 2, 3, 4 = postre. Parejas: (1,3) contra (2,4).
- Cualquier empate lo gana el jugador más cercano a la mano.

Lances:
1. **Grande**: gana la mano más alta, comparando las cartas ordenadas de mayor a menor, una a una.
2. **Chica**: gana la mano más baja, comparando las cartas ordenadas de menor a mayor, una a una.
3. **Pares**: Par < Medias (3 iguales) < Duples (dos parejas o 4 iguales). Dentro de cada categoría se compara por el orden de Grande; en Duples, primero la pareja alta y luego la baja. Quien no tiene pares no participa.
4. **Juego**: suma >= 31. Orden: 31 > 32 > 40 > 37 > 36 > 35 > 34 > 33. Opcional (desactivado por defecto): "31 real" (tres sietes y una sota) gana a cualquier otra 31.
5. **Punto**: solo si nadie tiene juego; gana la suma más alta (máximo 30).

Puntuación base (configurable): Grande y Chica en paso = 1; Pares: Par 1, Medias 2, Duples 3; Juego: 31 = 3, otro juego = 2; Punto = 1. Partida a juegos de 40 tantos.

Variante alternativa a soportar: 4 reyes / 4 ases.

## Datos clave para validar el motor
- Como el palo no importa, solo existen **330 manos distintas** (multiconjuntos de 4 rangos entre 8). Se pueden precalcular tablas completas.
- Valores exactos de referencia (8 reyes):
  - P(al menos un Rey en 4 cartas) ≈ 0,607
  - P(llevar pares) ≈ 0,566
- Toda estimación Monte Carlo debe coincidir con el cálculo combinatorio exacto cuando este exista.

## Hoja de ruta (una fase cada vez; espera el visto bueno del usuario antes de pasar a la siguiente)
- **Fase 1 – Motor y verificación**: cartas, evaluadores de cada lance, tablas de lookup de las 330 manos, tests con casos límite y verificación exacta vs. Monte Carlo. Distribución exacta de jugadas y P(juego).
- **Fase 2 – Equity**: probabilidad de ganar cada lance por mano y posición (individual y pareja), condicionada opcionalmente a información del compañero. Rankings exportables.
- **Fase 3 – Descarte**: políticas de descarte, mejora esperada y criterios para cortar mus.
- **Fase 4 – Web calculadora (MVP)**: PWA con tablas precalculadas en JSON; motor portado a TypeScript o WebAssembly para cálculos en el navegador. Sin backend.
- **Fase 5 – Entrenador**: situaciones con valoración; backend mínimo para usuarios y progreso.
- **Fase 6 – Apuestas y órdago**: modelo simplificado de envites, aproximación a equilibrios (CFR o self-play) y valor del órdago según el marcador.

## Requisitos técnicos
- Python 3, paquete modular (`cartas`, `evaluacion`, `simulacion`, `analisis`), type hints y docstrings.
- NumPy para vectorizar; semilla fijable para reproducibilidad.
- pytest para los tests; los tests deben pasar antes de dar una fase por terminada.
- CLI sencilla, por ejemplo: `python -m mus equity "R R C 5" --posicion 1 --n 1000000`.
- Exportación a CSV y gráficas con matplotlib.
- Intervalo de confianza en toda estimación Monte Carlo.

## Forma de trabajar
- Responde en español.
- El usuario es estudiante de Ingeniería Informática: explica las decisiones de diseño importantes sin rellenar.
- Antes de cada fase, resume el plan en pocas líneas y espera confirmación.
- Al terminar cada fase: ejecuta los tests, enseña los resultados y explica cómo comprobarlos.
- Señala riesgos, errores o alternativas más simples aunque contradigan lo decidido.
- Registra las decisiones importantes (y sus motivos) en `docs/decisiones.md`.
- Mantén actualizada la sección "Estado actual" de este archivo.
- Haz un commit con un mensaje claro y descriptivo al terminar cada tarea que funcione.

## Estado actual
- **Fase 1 – terminada, pendiente del visto bueno del usuario.** Paquete `src/mus` (reglas, cartas, evaluacion, tablas, simulacion, analisis) + CLI (`evaluar`, `resolver`, `distribucion`, `verificar`, `tabla`, `grafica`). 124 tests en verde. Valores de referencia comprobados: P(≥1 Rey) = 0,606522; P(pares) = 0,565817; P(juego) = 0,267469.
- Entorno: Python 3.14 en `.venv` (`pip install -e ".[dev]"`). Las salidas generadas van a `resultados/` (ignorado por git).
- Reglas confirmadas y diseño: ver `docs/decisiones.md`.
- Pendiente para la Fase 2: el punto debe filtrarse aparte en el código vectorizado (solo se juega si nadie en la mesa tiene juego).
