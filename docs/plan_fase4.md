# Plan de la Fase 4 (web, MVP)

Fecha: 2026-10-07. **Aprobado** por el usuario con las respuestas del final; los cambios respecto a la propuesta original están en la última sección.

**Idea general.** El motor en Python sigue siendo la referencia y genera todos los datos. La web solo los consulta y hace las cuentas ligeras. Así no hay que portar al navegador lo difícil y no hay riesgo de que las dos versiones den números distintos.

**Qué se hace en el navegador y qué se precalcula**

| Cálculo | Dónde | Por qué |
|---|---|---|
| Leer la mano, evaluar jugadas (pares, juego, punto) | Navegador | Trivial |
| Probabilidad de ganar cada lance (sin información) | Precalculado (~220 KB) | Es exacto y pequeño; el cálculo es pesado de portar |
| Lo mismo, sabiendo la seña del compañero | Precalculado, un fichero por seña | El cálculo exacto con condiciones no se porta en el MVP |
| Distribución de la mano tras descartarse | Navegador | Es exacta y barata (como mucho 330 robos por opción) |
| Valor de cada descarte | Navegador, con la tabla "tras el mus" de cada tipo de mesa | Una multiplicación sobre datos ya cargados |
| ¿Mus o corto? | Precalculado para cada tipo de mesa | Requiere simulación; con 20 millones de repartos por tipo de mesa son unos minutos en total |
| Condiciones libres ("pares>=medias") | Fuera del MVP | Habría que portar el motor exacto; posible más adelante |

**Selector de mesa.** Propongo tres niveles, cada uno con su λ por debajo:
- "Se da mucho mus": hay mus en ~60 % de las manos.
- "Normal": ~30 %, como tus primeras partidas.
- "Se corta mucho": ~11 %, los rivales razonables.

Cuando tengas las 40-50 manos, el nivel "Normal" se ajustará con `calibrar`.

**Pantalla única pensada para el móvil**, en tres bloques:
1. **Tu mano:** botones para las cartas (8 rangos, con la nota "el 3 cuenta como rey y el 2 como as"), la posición (Mano / Segundo / Tercero / Postre), el tipo de mesa y, opcionalmente, "¿Qué te ha dicho tu compañero?".
2. **¿Mus o corto?:** la recomendación, si es clara o dudosa, y en una frase cuánto se gana o se pierde.
3. **Si hay mus, ¿qué tiro?:** el mejor descarte, las alternativas y cómo quedarían tus probabilidades de pares y juego.

Siempre visible pero discreto: "ⓘ Cifras sin apostar (en paso)", que al tocarlo despliega las limitaciones en lenguaje llano. Nada de "equity", "λ" ni "Monte Carlo": "probabilidad de ganar", "tantos que se esperan", "tipo de mesa".

**Técnica.**
- Web estática con TypeScript y Vite, instalable en el móvil y usable sin conexión.
- Publicación automática en GitHub Pages con GitHub Actions.
- Los datos los genera un comando nuevo, `python -m mus exportar-web`, con la versión del motor incluida.
- Las partes portadas a TypeScript (evaluación y descarte) se prueban contra ficheros de referencia exportados por Python, para que los dos motores den exactamente lo mismo.

**Pasos, con commit y revisión en cada uno:**
1. Exportador y ficheros de referencia.
2. Núcleo en TypeScript con sus tests.
3. Interfaz.
4. Publicación y prueba en un móvil real.

**Riesgos:**
- **Peso de los datos.** Estimo 1-2 MB en total sin comprimir, cargados por partes según se necesiten.
- **Precisión de "¿mus o corto?" en manos raras.** Esas decisiones se marcarán como "dudosa" en vez de dar una respuesta falsa.
- **Las señas son regionales.** Por eso necesito que me las definas tú.

## Preguntas antes de empezar

1. **Señas:** ¿qué señas quieres incluir y qué significa cada una en cartas? Por ejemplo: duples, medias, 31, dos reyes, dos ases, "no llevo nada"… ¿Deben servir también para "¿mus o corto?" o solo para la probabilidad de ganar? Cada seña multiplica lo que hay que precalcular.
2. **Tipos de mesa:** ¿te valen tres niveles con esos nombres y porcentajes? ¿Cuál debe salir por defecto?
3. **Variante:** ¿solo 8 reyes en el MVP? (4 reyes duplicaría los datos).
4. **Tecnología:** ¿tienes preferencia o quieres aprender algo concreto (React, Svelte, TypeScript sin framework)? Yo propondría Svelte o Preact, por el poco peso en el móvil. ¿Quieres programar tú alguna parte?
5. **Repositorio:** GitHub Pages gratuito exige que el repositorio sea público. ¿Lo vas a publicar así? ¿Tienes nombre para la web y dirección de GitHub?
6. **Sin conexión:** ¿quieres que se pueda instalar y usar sin cobertura (útil en el bar)? Añade poco trabajo.
7. **Idioma:** ¿solo castellano?

## Respuestas del usuario (2026-10-07)

1. **Señas:** en el MVP solo afectan a la probabilidad de ganar; en "¿mus o corto?" serán lo primero de la versión 2. Son libres y combinables (ver `docs/decisiones.md` y `src/mus/senas.py`). La web incluirá una chuleta con los gestos.
2. **Tipos de mesa:** los tres niveles propuestos, con "Normal" por defecto.
3. **Variante:** solo 8 reyes.
4. **Tecnología:** React + TypeScript + Vite. Lo programa todo Claude, priorizando la calidad.
5. **Nombre:** Mus Analytics. El repositorio se hará público en el paso de publicación (hay que avisar al usuario en ese momento).
6. **Sin conexión:** sí, instalable y usable sin conexión.
7. **Idioma:** solo castellano.

## Cambios respecto a la propuesta

- **Señas combinables.** En vez de un fichero por seña, uno por cada conjunto distinto de manos que pueden dejar las señas: 16 (las 11 señas sueltas y 5 combinaciones). Cualquier otra combinación coincide con una de ellas o es imposible.
- **"¿Mus o corto?" mano a mano.** En vez de leer la decisión de la simulación agregada de la mesa (con poca precisión en las manos raras), cada mano y posición se simula con sus cartas fijas, como `python -m mus cortar`. Cuesta más tiempo de cálculo (una vez), pero la precisión no depende de lo rara que sea la mano y el descarte es la mejor respuesta de esa mano.
- **Valor de cada descarte precalculado.** Sale de la misma simulación, sabiendo que hay mus. El navegador solo calcula la distribución exacta de la mano final (P(pares), P(juego)...), que es exacta y barata.
