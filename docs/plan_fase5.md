# Plan de la Fase 5 (entrenador)

Fecha: 2026-10-12. **Aprobado** por el usuario con las respuestas y los cambios del final.

**Idea general.** Una situación del entrenador es una pantalla de la calculadora con la respuesta tapada. El entrenador no calcula nada nuevo del juego: plantea, compara la respuesta con los datos que genera el motor y la explica. Así no puede decir una cosa distinta de la calculadora.

## Los seis puntos que pidió el usuario

1. **Qué se entrena ya, con el modelo en paso:**
   - «¿Mus o corto?»: 1 320 situaciones por tipo de mesa (330 manos × 4 posiciones).
   - «Ha habido mus: ¿qué tiras?»: 3 546 descartes × 4 posiciones.
   - Estimar la probabilidad de ganar un lance: después de la 0.2.0.

   **Esperan a la Fase 6:** envites, órdago y marcador. Tampoco entran las señas en la decisión ni una segunda ronda de mus, que no están en el modelo.
2. **Puntuación:** tantos perdidos frente a la mejor opción, y 0 cuando la calculadora dice «Da igual» (mus o corto) o «Casi igual» (descarte). Es la misma regla, con las mismas funciones. El resumen sale en tantos perdidos por cada 100 manos.
3. **Sin servidor:** todo lo necesario está en la web instalada. El progreso se guarda en el móvil como un registro de respuestas.
4. **Qué manos:** series de 10 con tres modos: «Como en la mesa» (por defecto), «Ajustadas» y «Repaso de mis fallos». Las decisiones dudosas cuestan poco por definición; donde se pierden tantos es en decisiones claras mal jugadas, y esas solo las descubren los fallos de cada uno.
5. **Sin "GTO":** no hay un equilibrio fiable. Cada situación dice contra qué mesa se juega y qué no se cuenta.
6. **Recogida anónima futura:** cada respuesta se guarda completa (versión de los datos, mesa, posición, mano, respuesta y tantos), sin identificadores. La primera versión no envía nada.

## Qué se reutiliza

- **Motor:** el cálculo de las decisiones no cambia. Se usan las simulaciones mano a mano de la Fase 4 (`web.DecisionesMesa`), `tablas` para la frecuencia de cada mano y `testigos`. Módulo nuevo y pequeño, `mus.entrenador`, con la regla de puntuación en Python.
- **Web:** el núcleo entero (`decisionDe`, `opcionesDe`, `equityDe`, `descarte.ts`), `vistaDecision` y `vistaDescartes` con sus umbrales, `lenguaje.ts`, y los componentes `Carta`, `Decision`, `Descartes`, `FilaLances`, `Limitaciones` y `Segmentado`. El *service worker* y su lógica no se tocan.

## Qué hay que precalcular

| Qué | Peso | Se publica |
|---|---|---|
| Valoración de los dos ejercicios | Nada nuevo: ya está en los ficheros de cada mesa | — |
| Probabilidad de que te toque hablar, por mano y posición (cambio A) | 1 320 números por mesa | Sí, en `mesa-<tipo>.json` |
| Ventaja de dar mus lance a lance, con su margen (cambio C) | 13 200 números por mesa | Sí, en `mesa-<tipo>.json` |
| Referencia para los tests, `web/test/referencia/entrenador.json` | Se mide al generarla | No |
| Descarte según las cartas que piden los de antes | Unos 4 MB por mesa (estimación) y simulación nueva | Fuera de esta versión |

Las cifras reales de peso y de tiempo de cálculo quedan en `docs/decisiones.md` al terminar el paso 1.

## Cómo se comprueba que coincide con el motor

1. El veredicto y los tantos salen de las mismas funciones que usa la calculadora, sobre los mismos ficheros con huella.
2. Python calcula la valoración de las 3 960 decisiones y de todos los descartes a partir de los ficheros publicados; Vitest la compara con la de TypeScript sin tolerancia.
3. `python -m mus entrenador "R C 5 4" --posicion 1` imprime lo que enseña la pantalla, para cotejarlo a mano con `python -m mus cortar`.
4. Los casos testigo deben dar en el entrenador lo mismo que `python -m mus testigos`.
5. El sorteo de manos usa los pesos exactos del motor, comparados con la referencia. La semilla solo es fija en los tests (cambio E).
6. Tests del flujo completo en jsdom, capturas a 393 × 852 y prueba por la IP de red.

## Pasos, cada uno con su commit

0. Este documento.
1. Motor: desglose por lance y probabilidad de hablar, `mus.entrenador`, la orden de la CLI, la referencia y sus tests. Datos regenerados.
2. Núcleo del entrenador en TypeScript (situaciones, valoración, progreso), con tests contra la referencia.
3. Interfaz de «¿Mus o corto?» con valoración y explicación. **Parada: el usuario la prueba en el móvil, sin publicar.**
4. Ejercicio de descarte, pantalla de progreso con «Exportar» e «Importar», y repaso de fallos.
5. Publicación de la 0.2.0, con el visto bueno del usuario y la etiqueta `v0.2.0`.

## Riesgos

- Las decisiones «Por poco» pueden cambiar con envites: se puntúan, pero con ese aviso y separadas de las claras en el progreso.
- El progreso vive solo en ese móvil y se pierde al borrar la web instalada: por eso «Exportar» e «Importar».
- El modelo decide sin comunicación con el compañero (limitación conocida, casos de A A 4 5 en `docs/casos_testigo.md`): en esas manos el entrenador puede discrepar de lo que haría un buen jugador.

## Respuestas del usuario (2026-10-12)

1. **Rama:** el trabajo va en la rama `entrenador` y pasa a `main` solo en la publicación. Comprobado: «Publicar la web» se lanza sola únicamente con cambios de `web/` en `main`, y el entorno `github-pages` solo admite despliegues desde `main` (un lanzamiento a mano desde otra rama fallaría al desplegar).
2. **Dónde vive:** dos modos, «Calculadora | Entrenador», en la misma web.
3. **Modo por defecto:** «Como en la mesa», con el cambio A.
4. **Estimar probabilidades:** después de la 0.2.0. Sale de esta versión.
5. **Cartas que piden los demás:** fuera de esta versión, pero se dice en cada situación (cambio B).
6. **Pie de la web:** que no pueda confundirse con un commit. Por ejemplo: «Versión 0.2.0 · commit 01c64d0 · huella 60df1e6».

## Cambios pedidos por el usuario

**A. Situaciones realistas en «Como en la mesa».** Plantear las cuatro posiciones por igual y cualquier mano en el descarte no se parece a la mesa.
- «¿Mus o corto?»: cada mano y posición pesa por la probabilidad de que te toque hablar en la mesa elegida, y la situación lo dice («Los tres anteriores han dado mus»).
- «¿Qué tiras?»: cada mano pesa por la probabilidad de que de verdad haya mus con ella en esa mesa. Con R R C S casi nunca se llega a descartar.
- Así los tantos perdidos por cada 100 manos se parecen a lo que se perdería en partidas reales. En «Ajustadas» y «Repaso de mis fallos» no hace falta.

**B. Contexto de cada situación**, en lenguaje de jugador: «La mejor jugada contra una mesa Normal, sin contar envites, señas ni las cartas que piden los demás».

**C. Explicación.** Un veredicto con su cifra no enseña por qué. Se exporta la ventaja de dar mus desglosada por lance (cuánto se gana o se pierde en grande, chica, pares, juego y punto) y se usa como explicación de cada situación. Límite para hacerlo sin preguntar: menos de una hora de cálculo y menos de 300 KB comprimidos.

**D. Progreso.** Además de «Exportar», «Importar»: sin él, la copia no sirve para recuperarlo. Se pide almacenamiento persistente si el navegador lo ofrece, comprobando antes que existe.

**E. Semilla fija solo en los tests.** En la aplicación, cada serie es distinta.

## Cómo se concreta el cambio A

Los pesos salen de tres cifras por mano y posición, todas de la simulación con la mano fija:

- `p_habla`: probabilidad de que den mus todos los anteriores, sabiendo mi mano. Siendo mano vale 1. Es nueva en los datos.
- `p_mus_despues`: probabilidad de que den mus todos los que hablan después. Ya estaba.
- El veredicto del entrenador para esa mano y posición.

**«¿Mus o corto?»:** peso = frecuencia de la mano × `p_habla`. La posición sale de ese mismo sorteo, así que de mano se decide más veces que de postre, como en la mesa.

**«¿Qué tiras?»:** peso = frecuencia de la mano × `p_habla` × `p_mus_despues`, y solo si el entrenador no recomienda cortar con ella. Motivo: quien se entrena es el que decide con esa mano, y el modelo le supone la mejor respuesta; el λ de la mesa describe cuánto cortan **los demás**. Con R R C S el entrenador corta siempre, así que en este modo no sale nunca. Usar el λ también para la propia mano supondría que en la mesa Normal se da mus con R R C S el 37 % de las veces, que es justo lo que se quiere evitar. **Confirmado por el usuario (2026-10-13):** vale «nunca». Son las situaciones a las que llega quien decide bien el mus o corto. En «Ajustadas» y «Repaso de mis fallos» puede salir cualquier mano.

**Tantos por cada 100 manos de partida.** No en todas las manos te toca hablar: el resumen multiplica lo perdido por decisión por la fracción de manos en que se decide en esa mesa (la media de `p_habla`). Solo en «Como en la mesa»; en los otros modos el sorteo no es el de la mesa y esa cifra no se da.

## Respuestas del usuario antes del paso 4 (2026-10-13)

1. **Descartes «como en la mesa»:** vale «nunca» con las manos que se cortan (ver «Cómo se concreta el cambio A»).
2. **La rama `entrenador` está en GitHub** (no lanza ningún flujo: ni los tests ni la publicación).
3. **En el paso 4, arreglar los «Daba igual»:** con la web instalada, el último lance no debe quedar bajo el botón.
4. **No empezar el paso 4** hasta que pase sus comentarios tras probar el entrenador en el móvil.
