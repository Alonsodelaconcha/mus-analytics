# Mus Analytics: estadísticas y entrenamiento para el Mus a 8 reyes

## Visión del proyecto
Construir la herramienta de referencia de estadísticas y estrategia para el mus, al estilo de las calculadoras y entrenadores de póker (Equilab, GTO Wizard), pensada para jugadores reales: aficionados interesados y jugadores de torneo.

Producto final previsto (web progresiva, PWA):
1. **Calculadora de probabilidades**: mano + posición → probabilidad de ganar cada lance (individual y por pareja) y tantos esperados; opcionalmente condicionada a la información del compañero (señas).
2. **Asesor de descarte**: compara todas las formas de descartarse y recomienda según el objetivo (grande, chica, juego) y si conviene cortar mus.
3. **Entrenador de situaciones**: plantea manos con posición, marcador y envites previos; el usuario decide y recibe la valoración y una explicación.
4. **Calculadora de órdago según marcador**: equivalente al ICM del póker.

Este repositorio empieza por el **motor** (Python), que es la base de todo lo demás.

**Lo aprendido al usarla (opinión del usuario tras jugar partidas reales con la web, 2026-10-12):**
- Usarla durante la partida es muy difícil: el juego va demasiado rápido. **Su valor real está en analizar manos antes o después de jugar.**
- Lo que más le interesa es un **modo entrenamiento**, al estilo de los entrenadores de póker: que plantee situaciones y haya que elegir la mejor jugada.
- Por eso **el entrenador (Fase 5) va antes que las mejoras de la versión 2 de la web.** Al diseñar, pensar en quien estudia una mano con calma, no en quien la consulta con las cartas en la mano.

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
- **Fase 5 – Entrenador**: situaciones con valoración; backend mínimo para usuarios y progreso. **Es lo siguiente tras la Fase 4** (decisión del usuario, 2026-10-12), por delante de la versión 2 de la web. Si puede empezar sin servidor se decide en su plan (ver «Pendientes»).
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
- **Fase 4 – en curso.** Plan aprobado con las respuestas del usuario en `docs/plan_fase4.md` (React + TypeScript + Vite, PWA sin conexión en GitHub Pages, solo 8 reyes, solo castellano). Pasos: 1) exportador y ficheros de referencia, 2) núcleo en TypeScript, 3) interfaz, 4) publicación. **Pasos 1 y 2 aprobados (2026-10-08). Paso 3 (interfaz) aprobado (2026-10-12): el usuario probó la estructura A en su móvil y aceptó que al volver de «Ha habido mus» se restauren también las señas y que los botones de seña midan 44 px.** Estructura A: tres pestañas en la barra de abajo («¿Mus o corto?», «Se ha cortado», «Ha habido mus»), mano compacta arriba y, en «Se ha cortado», las probabilidades en una fila de cinco lances. Probabilidades: en «Se ha cortado», exactas con señas; en «Ha habido mus», las de la mesa tras el mus sin señas (limitaciones explicadas en la web). **Paso 4 (publicación) en curso; plan aprobado el 2026-10-12** (detalle en `docs/decisiones.md`). Decisiones del usuario: email `noreply` de GitHub en todos los commits, licencia AGPL-3.0, `CLAUDE.md` se publica tal cual, *service worker* propio, móvil de referencia iPhone 15 (393 × 852). **Publicada el 2026-10-12: <https://alonsodelaconcha.github.io/mus-analytics/> (versión 0.1.0).** Hecho: limpieza, licencia, web instalable con modo sin conexión, icono y README aprobados por el usuario, **historial reescrito** (todos los commits con el email `noreply`; el usuario borró y volvió a crear el repositorio, y se comprobó en una copia recién clonada), repositorio público y los dos flujos de GitHub Actions en verde (`tests.yml` y `publicar.yml`). Comprobada la web publicada con `npm run comprobar-publicada` (huellas de los 31 ficheros, primera visita y modo avión real en Edge). **Pruebas del usuario en su iPhone 15 (2026-10-12): bien la instalación, las franjas de arriba y de abajo en claro y en oscuro, y el modo avión** (las tres pestañas, señas, tipos de mesa y chuleta). Publicada la **0.1.1** para que pruebe la actualización (el cambio visible es el número de versión del pie); en Edge, un navegador con la 0.1.0 guardada avisó de la nueva sin tocar la mano a medias y pasó a ella con «Actualizar» (`npm run comprobar-publicada -- --actualizacion antes|despues`). **Pendiente:** 1) que el usuario confirme la actualización en el iPhone; 2) cerrar el paso 4 y la Fase 4 con su visto bueno; 3) **entonces, y no antes, proponerle el plan de la Fase 5** (ver «Pendientes»); no empezarla sin su aprobación. **La copia de seguridad del historial (`resultados/copia-seguridad/mus-analytics-antes-de-reescribir.bundle`, lleva el email antiguo) no se borra hasta que el usuario lo diga (preguntárselo al cerrar el paso 4), y nunca se sube.**

Motor (`src/mus`):
- **Fase 1:** `reglas`, `cartas`, `evaluacion`, `tablas`, `simulacion`, `analisis`. Valores de referencia: P(≥1 Rey) = 0,606522; P(pares) = 0,565817; P(juego) = 0,267469. Para resolver lances de forma vectorizada usar `simulacion.ganadores_lance` (aplica el filtro del punto; repartos siempre en orden de juego, columna 0 = mano).
- **Fase 2:** `condiciones` (predicados sobre una mano, sintaxis de texto) y `equity` (exacta por programación dinámica sobre el mazo restante, con pesos por asiento; tabla completa con caché en `resultados/cache/`). Cambiar el cálculo exige subir `equity.VERSION_MOTOR`.
- **Fase 3:** `descarte` (3a: opciones y distribución exacta de la mano final), `tras_mus` (3b: mesa tras el mus por simulación de la ronda completa, punto fijo con criterio de explotabilidad) y `cortar` (3c: efecto de selección, equilibrio degenerado y escenario principal de rivales razonables con `factor_corte` λ). Reglas del mus en `ReglasMus.descarte`. Casos testigo en `testigos` y `docs/casos_testigo.md`.
- **Fase 4 (paso 1):** `senas` (las 11 señas de la mesa del usuario como condiciones: libres, combinables con "y", sin conclusiones de las que no se hacen; 16 conjuntos de manos distintos) y `web` (`python -m mus exportar-web`: datos de la web en `web/public/datos` y ficheros de referencia del núcleo TS en `web/test/referencia`; lo costoso, ~35 min la primera vez con 6 procesos, queda en `resultados/cache`). Los datos generados se versionan en git. Cambiar su estructura exige subir `web.FORMATO`; cambiar el cálculo de las decisiones, `web.VERSION_DECISIONES`.
- **Fase 4 (paso 3), interfaz:** `web/src/mano.ts` (reducer con las reglas de la mano: pestaña abierta, mano repartida y mano tras el mus por separado, giro de la posición solo con «Nueva mano»...), `web/src/App.tsx` (carga de datos y contenido de cada pestaña), `componentes/` (`TuMano`, `Pestanas`, teclado, señas con chuleta, decisión, descartes, `FilaLances`, probabilidades, limitaciones), `vista/lenguaje.ts` y `vista/vista.ts` (todo el texto y los umbrales de presentación, funciones puras con tests) y `estilos.css` (móvil primero, modo oscuro). Tests del flujo completo con Testing Library en jsdom (`test/app.test.tsx`).
- **Fase 4 (paso 2), web en `web/`:** Vite 8 + React 19 + TypeScript 6.0 (no 7: `typescript-eslint` aún no lo admite). Núcleo en `web/src/nucleo` (`cartas`, `evaluacion`, `tablas`, `descarte`, `senas`, `datos`): traducción exacta de la parte de Python que se calcula en el navegador, con aritmética entera. Los tests (`web/test`, Vitest) comparan sin tolerancia con `web/test/referencia`. La carga de datos valida el manifiesto contra el núcleo (orden de manos y opciones, reglas) y la huella SHA-256 de cada fichero. Dos tests de Python fallan si los ficheros versionados quedan desfasados: si cambia el motor o el exportador, regenerar con `python -m mus exportar-web`.
- **Fase 4 (paso 4), publicación:** `web/sw/` (*service worker* propio: `logica.ts`, probada con dobles; `sw.ts`, que conecta los eventos; `emergencia.ts`, que borra las cachés y se desregistra), `web/plugins/sinConexion.ts` (plugin de Vite: lista de ficheros con su huella SHA-256, de la que sale la versión; comprueba los datos contra el manifiesto; escribe `sw.js`, siempre con ese nombre, y `licencias-de-terceros.txt`), `web/src/sinConexion.ts` (registro solo si existe y en la web construida; estados y aviso de versión nueva) y `componentes/Creditos.tsx` (pie con la versión). Una versión se guarda entera en su caché o no se instala; la nueva espera a «Actualizar» o a la siguiente apertura. **No añadir `skipWaiting` al instalar** (recargaría a mitad de una mano) **ni cambiar la dirección de `sw.js`** (es la única salida si se publica uno roto: `npm run build:emergencia`). Licencia AGPL-3.0 (`LICENSE`); el pie de la web enlaza el código.
- **Datos reales y calibración de λ:** la fuente es `datos/manos_reales.csv` (una fila por mano: partida, número, rondas como `mus mus mano`, exclusión y motivo, posición del usuario y si usó la web, anotación original). `python -m mus manos-reales` (módulo `manos_reales`) lo valida y **genera** `datos/mus_real.csv` (por partida) y `datos/cortes_por_posicion.csv` (por partida y posición); no se editan a mano y un test falla si quedan desfasados. Se excluyen la primera mano de cada partida y las que no se recuerdan; solo cuenta la primera ronda. `calibracion` + `python -m mus calibrar`. A 2026-10-08: 15 partidas, 71 manos, mus en 24 (34 %; λ ≈ 0,58, intervalo 0,44-0,73); corte por posición compatible con el modelo (χ² p = 0,88); razón entre parejas 1,41 (0,85-2,33; modelo 1,59). **Regla:** la mesa "Normal" (30 %, λ = 0,63) solo se cambia si el intervalo de λ la excluye (es decir, si el intervalo de la frecuencia de mus excluye el 30 %). **Plan de recogida (usuario, 2026-10-12):** seguirá apuntando partidas, ahora rellenando en cada mano su posición y si ha usado la web (las dos columnas ya existen). Meta: unas 200 manos en total, que dan ± 7 puntos en la frecuencia de mus (IC 95 %); revisar la calibración cada 50 manos más o menos (`manos-reales` y `calibrar`) y aplicar la regla. Limitaciones: manos de una partida no independientes (variación entre partidas p = 0,33 por permutaciones, error ×1,06, poca potencia) y el usuario juega todas las partidas. Desde el 2026-10-08, el λ por defecto de la CLI (`cortar`, `corte-mesa`, `testigos`) es el de la mesa "Normal" de la web, calculado igual (`web.factor_corte_de_mesa`), para que web y CLI coincidan siempre; `--mesa` elige otro tipo de mesa y `--factor-corte`, un λ a mano.

CLI (`python -m mus ...`): `evaluar`, `resolver`, `distribucion`, `verificar`, `tabla`, `grafica`, `equity`, `equity-tabla`, `ranking`, `mesa`, `grafica-posicion`, `grafica-condicion`, `descarte`, `descarte-tabla`, `tras-mus`, `corte-mesa`, `cortar`, `testigos`, `manos-reales`, `calibrar`, `exportar-web`, `consultar-web`.

Entorno y tests:
- Python 3.14 en `.venv` (`pip install -e ".[dev]"`). Las salidas generadas van a `resultados/` (ignorado por git).
- Web: Node 24 y npm 11. En `web/`: `npm ci`, `npm run verificar` (tipos + lint + tests), `npm run dev`, `npm run build`. Para verla en el navegador del panel: `.claude/launch.json` (local; `.claude/` está en `.gitignore`). En el móvil por la red local: `npm run movil` o `npm run movil-final` (el cortafuegos de Windows tiene que permitir Node.js; la red Wi-Fi del usuario está marcada como "Pública"). **La IP del portátil cambia según la red Wi-Fi** (172.20.10.2 en la zona compartida del móvil, 192.168.1.37 en otra): usar siempre la que muestra `npm run movil-final` (la de "Wi-Fi"; 192.168.56.1 es un adaptador virtual). Capturas a tamaño de iPhone 15 (393 × 852, claro y oscuro) con `npm run capturas -- --url <dirección> [--tema ambos] [--instalada]` (`web/scripts/capturas.mjs`: Edge sin ventana, sin dependencias; comprueba también errores de consola y contexto seguro; `--instalada` simula las zonas seguras del iPhone y falla si algo queda dentro; salen en `resultados/capturas`). Usarlo en cada revisión visual: el navegador del panel da capturas con mosaicos repetidos. **Probar siempre también por la IP de red**, no solo en localhost: por HTTP en la red local no hay contexto seguro y faltan `crypto.subtle`, el *service worker* y la caché. ESLint prohíbe usarlos sin comprobar antes que existen; las huellas usan `nucleo/sha256.ts` como alternativa. **Modo sin conexión:** `npm run prueba-sin-conexion` lo prueba en Edge real (58 comprobaciones: modo avión, descarga que falla a mitad, actualización, emergencia; unos 40 s); pasarlo siempre que se toque `web/sw`, el plugin o `sinConexion.ts`. `npm run comprobar-publicada [-- --version X]` comprueba la web ya publicada (huellas, primera visita y modo avión real): pasarlo después de cada publicación. Para comprobar el paso de una versión a la siguiente: `-- --actualizacion antes` antes de publicar (un Edge guarda la versión actual) y `-- --actualizacion despues` cuando Pages ya sirva la nueva (el despliegue tarda entre uno y cuatro minutos). `npm run iconos` regenera los iconos; `npm run build:emergencia`, la salida de emergencia (en GitHub: Actions → «Publicar la web» → Run workflow, marcando la opción). El navegador del panel no deja registrar *service workers* (la web lo dice en el pie y funciona igual): el modo sin conexión solo se puede probar con Edge. En la web construida servida en local (puerto 4173) el *service worker* sí se registra: tras reconstruir, un navegador que ya la tenía avisa de la versión nueva o la aplica al volver a abrirla; las capturas empiezan siempre de cero.
- `pytest` ejecuta solo los rápidos (~20 s); `pytest -m slow`, los lentos (fuerza bruta, Monte Carlo grandes, tabla completa; ~2 min).
- En PowerShell, los mensajes de commit con comillas dobles se rompen: usar `git commit -F fichero`.
- **Email de los commits:** el `user.email` de este repositorio es la dirección `noreply` de GitHub del usuario (configuración local de git). Antes de confirmar en una copia nueva del repositorio, comprobar `git config user.email`: el gmail no debe volver a aparecer en ningún commit.
- GitHub Actions: `tests.yml` pasa los tests rápidos de Python en cada cambio (menos de un minuto); `publicar.yml` construye y publica la web al cambiar algo de `web/` en `main` (un minuto). **Subir a `main` un cambio de `web/` es publicar**: pasar antes `npm run verificar` y, si toca el modo sin conexión, `npm run prueba-sin-conexion`. Sin `gh`: el estado de los flujos se consulta en `https://api.github.com/repos/Alonsodelaconcha/mus-analytics/actions/runs` (sin sesión, 60 consultas por hora).

## Pendientes para fases futuras
- **Lo siguiente: Fase 5, el entrenador** (por delante de la versión 2 de la web). **No empezarla.** Al cerrar el paso 4, proponer su plan teniendo en cuenta lo que pidió el usuario (2026-10-12):
  1. Qué se puede entrenar ya con el modelo en paso (mus o corto, descarte, intuición de las probabilidades) y qué necesita la Fase 6 (envites, órdagos, marcador).
  2. Puntuar por los **tantos perdidos frente a la mejor opción**, no por acierto o fallo. Si la diferencia está dentro del margen de error, cualquier opción vale.
  3. Si se puede empezar **sin servidor**, con todo precalculado y el progreso guardado en el móvil.
  4. Qué manos plantear: al azar con su frecuencia real, o centrándose en las decisiones dudosas, que son las que enseñan.
  5. **No llamarlo "GTO"**: no hay un equilibrio fiable. Es la mejor respuesta frente al tipo de mesa elegido, y la mesa "Normal" está calibrada con sus partidas reales. Explicarlo así en el entrenador, en lenguaje de jugador.
  6. Más adelante, el entrenador podría recoger de forma anónima las decisiones de los usuarios, como primer conjunto de datos de mus con jugadores reales. No para la primera versión, pero que el diseño no lo impida.
- **Ideas para después del MVP (del usuario):** 1) una sección "Mitos del mus" que compruebe con el motor reglas populares (p. ej. "siendo mano, no quedarse con R 7 7, R 5 5 o R 4 4"); 2) que la web permita registrar de forma anónima qué hizo cada jugador con su mano, para crear con el tiempo el primer conjunto de datos de mus con jugadores reales (el entrenador es el sitio natural para recogerlo: punto 6 de arriba).
- **Versión 2 de la web (después del entrenador).** Prioridad alta: señas tras el mus y tener en cuenta quién ha cortado (condición sobre el asiento que corta). Además, por orden: 1) que las señas cuenten también en "¿mus o corto?"; 2) "modo torneo": señas obligatorias y completas (como en los reglamentos de Euskadi: con dos reyes y 31 hay que pasar la 31; el ciego no se puede pasar con 29 ni con pares). En ese modo, que el compañero NO haga una seña también informa, y tiene sentido la opción "Ninguna seña".
- **Fase 6 (partida completa):** la primera mano de cada partida se juega con "mus corrido y sin señas", y quien corta pasa a ser mano: así se decide la mano de la partida (norma tradicional, sin comunicación entre compañeros). Datos para modelar varias rondas de mus: en las partidas reales, tras una primera ronda con mus hubo otra ronda de mus en 8 de 23 manos (35 %, IC 19-55 %); ver `python -m mus manos-reales`.
- **Fase 5 (entrenador):** usar el número de cartas que pide cada jugador (información pública) como condición sobre su mano, a partir de la política de descarte. Será clave para el entrenador.
- **Limitación conocida: coordinación de pareja.** El modelo decide cortar o dar mus mano a mano, sin comunicación con el compañero. Un jugador real puede dar mus con una mano dudosa para que hable el compañero (o preguntarle con señas antes de decidir). Mejora futura (casos testigo de A A 4 5 en `docs/casos_testigo.md`).
- **Casos testigo de la 3c** en `docs/casos_testigo.md`: solo para validar, nunca para ajustar el modelo.
