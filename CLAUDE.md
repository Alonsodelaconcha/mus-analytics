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
- **Fases 1, 2 y 3 – terminadas y aprobadas** (motor completo en paso). Resumen para portfolio en `README.md`; decisiones, alternativas y errores encontrados en `docs/decisiones.md`.
- **Fase 4 – en curso.** Plan aprobado con las respuestas del usuario en `docs/plan_fase4.md` (React + TypeScript + Vite, PWA sin conexión en GitHub Pages, solo 8 reyes, solo castellano). Pasos: 1) exportador y ficheros de referencia, 2) núcleo en TypeScript, 3) interfaz, 4) publicación. **Paso 1 aprobado (2026-10-08); paso 2 en curso.** La web pregunta "¿Ha habido mus?": si no, probabilidades exactas con señas; si sí, las de la mesa tras el mus sin señas (limitaciones a explicar en la web). En el paso 4, avisar al usuario: hará público el repositorio en ese momento.

Motor (`src/mus`):
- **Fase 1:** `reglas`, `cartas`, `evaluacion`, `tablas`, `simulacion`, `analisis`. Valores de referencia: P(≥1 Rey) = 0,606522; P(pares) = 0,565817; P(juego) = 0,267469. Para resolver lances de forma vectorizada usar `simulacion.ganadores_lance` (aplica el filtro del punto; repartos siempre en orden de juego, columna 0 = mano).
- **Fase 2:** `condiciones` (predicados sobre una mano, sintaxis de texto) y `equity` (exacta por programación dinámica sobre el mazo restante, con pesos por asiento; tabla completa con caché en `resultados/cache/`). Cambiar el cálculo exige subir `equity.VERSION_MOTOR`.
- **Fase 3:** `descarte` (3a: opciones y distribución exacta de la mano final), `tras_mus` (3b: mesa tras el mus por simulación de la ronda completa, punto fijo con criterio de explotabilidad) y `cortar` (3c: efecto de selección, equilibrio degenerado y escenario principal de rivales razonables con `factor_corte` λ). Reglas del mus en `ReglasMus.descarte`. Casos testigo en `testigos` y `docs/casos_testigo.md`.
- **Fase 4 (paso 1):** `senas` (las 11 señas de la mesa del usuario como condiciones: libres, combinables con "y", sin conclusiones de las que no se hacen; 16 conjuntos de manos distintos) y `web` (`python -m mus exportar-web`: datos de la web en `web/public/datos` y ficheros de referencia del núcleo TS en `web/test/referencia`; lo costoso, ~35 min la primera vez con 6 procesos, queda en `resultados/cache`). Los datos generados se versionan en git. Cambiar su estructura exige subir `web.FORMATO`; cambiar el cálculo de las decisiones, `web.VERSION_DECISIONES`.
- **Calibración de λ:** `calibracion` + `datos/mus_real.csv` (una fila por sesión: manos y manos con mus en la primera ronda, **sin la primera mano de cada partida**, que se juega con mus corrido y sin señas) + `datos/cortes_por_posicion.csv` (veces que habla y corta cada posición). A 2026-10-08: 45 manos, mus en 13 (29 %; λ ≈ 0,65, intervalo 0,46-0,85). La mesa "Normal" de la web (λ = 0,63) encaja y se mantiene; el corte por posición también encaja con el modelo (χ² p = 0,90). El λ por defecto de la CLI sigue en 1: cambiarlo solo si el usuario lo decide.

CLI (`python -m mus ...`): `evaluar`, `resolver`, `distribucion`, `verificar`, `tabla`, `grafica`, `equity`, `equity-tabla`, `ranking`, `mesa`, `grafica-posicion`, `grafica-condicion`, `descarte`, `descarte-tabla`, `tras-mus`, `corte-mesa`, `cortar`, `testigos`, `calibrar`, `exportar-web`, `consultar-web`.

Entorno y tests:
- Python 3.14 en `.venv` (`pip install -e ".[dev]"`). Las salidas generadas van a `resultados/` (ignorado por git).
- `pytest` ejecuta solo los rápidos (~20 s); `pytest -m slow`, los lentos (fuerza bruta, Monte Carlo grandes, tabla completa; ~2 min).
- En PowerShell, los mensajes de commit con comillas dobles se rompen: usar `git commit -F fichero`.

## Pendientes para fases futuras
- **Versión 2 de la web.** Prioridad alta: señas tras el mus y tener en cuenta quién ha cortado (condición sobre el asiento que corta). Además, por orden: 1) que las señas cuenten también en "¿mus o corto?"; 2) "modo torneo": señas obligatorias y completas (como en los reglamentos de Euskadi: con dos reyes y 31 hay que pasar la 31; el ciego no se puede pasar con 29 ni con pares). En ese modo, que el compañero NO haga una seña también informa, y tiene sentido la opción "Ninguna seña".
- **Fase 6 (partida completa):** la primera mano de cada partida se juega con "mus corrido y sin señas" (norma tradicional para determinar la mano sin comunicación entre compañeros).
- **Fase 5 (entrenador):** usar el número de cartas que pide cada jugador (información pública) como condición sobre su mano, a partir de la política de descarte. Será clave para el entrenador.
- **Limitación conocida: coordinación de pareja.** El modelo decide cortar o dar mus mano a mano, sin comunicación con el compañero. Un jugador real puede dar mus con una mano dudosa para que hable el compañero (o preguntarle con señas antes de decidir). Mejora futura (casos testigo de A A 4 5 en `docs/casos_testigo.md`).
- **Casos testigo de la 3c** en `docs/casos_testigo.md`: solo para validar, nunca para ajustar el modelo.
