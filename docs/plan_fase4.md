# Plan de la Fase 4 (web, MVP)

Fecha: 2026-10-07. **Aprobado** por el usuario con las respuestas del final; los cambios respecto a la propuesta original están en la última sección.

**Fase terminada y aprobada el 2026-10-12:** web publicada en <https://alonsodelaconcha.github.io/mus-analytics/>, versión 0.1.1. El cierre está en `docs/decisiones.md`.

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

## Decisión sobre la probabilidad de ganar (2026-10-08)

La web pregunta "¿Ha habido mus?".
- **No:** probabilidades exactas, con las señas del compañero.
- **Sí:** las de la mesa tras el mus del tipo de mesa elegido, sin señas.

Las limitaciones (sin señas tras el mus, sin tener en cuenta quién ha cortado) se explican claramente en la web. Las dos mejoras son de prioridad alta en la versión 2.

## Propuesta de estructura A: una pestaña por momento de la mano (2026-10-08)

Guardada a petición del usuario, tal como se le presentó. **Elegida por el usuario e implementada el 2026-10-08**, con los cambios de "Decisiones del usuario sobre la estructura A" (al final).

**Por qué.** Al abrir los desplegables hay que desplazarse mucho, y el bloque de señas, encima del veredicto, parecía influir en la recomendación. En la mesa hay tres momentos, y cada uno necesita cosas distintas:
1. **Decidir mus o corto:** importan la recomendación y el descarte.
2. **Alguien ha cortado:** se juega con las cartas del reparto; importan las probabilidades con señas.
3. **Ha habido mus:** cartas nuevas; solo importan las probabilidades, sin señas (el modelo es de una sola ronda de mus).

**Estructura.**
- **Arriba, siempre:** la mano en versión compacta (las 4 cartas pequeñas, la jugada y el tipo de mesa) y el selector de posición.
- **Debajo, un selector de tres pestañas** que sustituye a «¿Ha habido mus? Sí/No»: «¿Mus o corto?» (*decidir*), «Se ha cortado» (*cartas del reparto*) y «Ha habido mus» (*cartas nuevas*).
- **Abajo, fijo:** el teclado mientras se meten cartas y, con la mano completa, «Nueva mano», que sigue girando la posición como ahora.

**Qué va en cada pestaña:**

| Pestaña | Contenido |
|---|---|
| **¿Mus o corto?** | La recomendación: veredicto, explicación, matiz de las decisiones ajustadas, aviso «Ojo: este consejo no cuenta las señas de tu compañero» si hay señas marcadas, y tipo de mesa. Debajo, el descarte: el mejor, con qué acabarías (pares, juego) y un enlace a las otras formas de descartarse. |
| **Se ha cortado** | Las señas del compañero en una rejilla compacta de tres columnas, con el enlace a la chuleta. Debajo, «Si se juega con estas cartas, ganáis…»: las cinco probabilidades exactas en una fila (con las señas marcadas), una nota con las señas que se usan y los tantos que se esperan. |
| **Ha habido mus** | Se meten las cartas nuevas y salen las probabilidades tras el mus, sin señas, con la nota de que llegarán en una versión posterior. Aquí no aparece el bloque de señas. |

Así las señas solo están donde cuentan, y no pueden parecer parte de la recomendación. Con la mano completa, cada pestaña cabe casi entera en una pantalla de 390 × 844.

**Maquetas.** `docs/maquetas/propuesta-A-pestanas.png` contiene las tres pantallas (A1, A2 y A3) a 390 × 844.
- Se hicieron como HTML estático con la hoja de estilos real de la web y cifras reales:
  - R C 5 4 de mano, mesa Normal;
  - en A2, compañero con dos reyes;
  - en A3, R R C S de postre tras el mus.
- Las capturas se hicieron con Edge sin ventana. El HTML de las maquetas y el script de capturas estaban en la carpeta temporal de la sesión y no se han guardado; solo la imagen.

**Alternativa presentada junto a esta (B):** todo de un vistazo, con el veredicto, el mejor descarte y una fila de probabilidades sin señas. La barra inferior lleva «Han cortado», «Ha habido mus» y «Nueva mano», y «Han cortado» abre una hoja desde abajo con las señas y las probabilidades con señas. Se recomendó A: sigue el orden de la mano y separa las señas de la recomendación por diseño. B se lee más rápido pero esconde más tras un toque.

**Decidido por el usuario (2026-10-08):**
1. ~~Si elige A.~~ **Elige A.**
2. ~~Formato de las probabilidades en «Se ha cortado».~~ **Una fila con los cinco lances**: en cada uno, el porcentaje de la pareja y debajo la frecuencia corta («9 de 10»). Al tocar un lance, la frase completa y la probabilidad individual.
3. ~~Si al completar las 4 cartas se abre sola «¿Mus o corto?».~~ **No: completar las cartas nunca cambia de pestaña** (en «Ha habido mus» se meten las cartas nuevas y saltar a la recomendación sería un error). **«Nueva mano» abre «¿Mus o corto?».**

**Otras cosas de esta fase:**
- **Script de capturas: hecho.** `web/scripts/capturas.mjs` (`npm run capturas`), sin dependencias, con Edge. Se usará en cada revisión y para las capturas del README en el paso 4.
- **IP de la red local:** el aviso de que cambia con la red Wi-Fi está ahora en la sección de entorno de `CLAUDE.md`.

## Decisiones del usuario sobre la estructura A (2026-10-08)

1. **Pestañas al alcance del pulgar:** en la barra de abajo (donde estaba «Ha habido mus»), no bajo la mano. Encima de ellas, el teclado mientras faltan cartas o «Nueva mano» con la mano completa.
2. **Aviso de las señas en «¿Mus o corto?»:** en esa pestaña no se marcan señas, pero el compañero las hace antes de decidir. Va una línea fija: «No tiene en cuenta las señas de tu compañero».
3. **Cambios de pestaña:**
   - «Nueva mano» abre «¿Mus o corto?».
   - Completar las 4 cartas nunca cambia de pestaña.
   - Pasar a «Se ha cortado» conserva las cartas.
   - Pasar a «Ha habido mus» las vacía y quita las señas.
   - La mano repartida se guarda: si se vuelve de «Ha habido mus» a «¿Mus o corto?» o a «Se ha cortado» (un toque equivocado), se restaura. *Se restaura con sus señas: ver `docs/decisiones.md`.*
   - La posición no cambia al cambiar de pestaña.
4. **Probabilidades en «Se ha cortado»:** la fila de cinco lances descrita arriba.
5. **Tests del flujo** para los cambios de pestaña, la restauración de la mano y que completar las cartas no cambia de pestaña.
