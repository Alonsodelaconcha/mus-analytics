# Casos testigo para validar la Fase 3c

Fecha: 2026-10-07. Registrados por el usuario **antes** de calcular nada de la 3c.

Uso: solo para **validar** el modelo de cortar o dar mus. **No** se usan para ajustar el modelo ni sus parámetros. Al terminar la 3c se compara la decisión del modelo con la del usuario en cada caso y posición, y se explica cada discrepancia: si el modelo se equivoca (y por qué) o si la decisión del usuario es peor según los números (y cuánto pierde).

Texto del usuario, tal cual:

---

Lo que haría yo como jugador:

SIENDO MANO
- R R C S (par de reyes, 40): corto
- R C S A (31): corto
- R R R A (medias de reyes, 31): corto
- R R A A (duples): corto
- A A 4 5: dudaría. Seguramente daría mus para que hable mi compañero. Si hay mus, me quedo con A A.
- R C 5 4: mus, y me quedo con R.
- C S 6 5 (31): corto
- 7 7 7 S (medias de sietes, 31): corto

SIENDO POSTRE (los otros tres han dado mus)
- R R C S: corto
- R C S A: corto
- R R R A: corto
- R R A A: corto
- A A 4 5: dudaría. Le preguntaría a mi compañero: si va flojo, mus y me quedo con A A; si va bien, corto.
- R C 5 4: mus, y me quedo con R.
- C S 6 5: corto
- 7 7 7 S: corto

---

Peticiones asociadas:
- Para A A 4 5 de postre, calcular también la decisión con dos condiciones sobre el compañero ("flojo" y "va bien"), definidas de forma razonable y explicadas.
- Anotar como limitación conocida la coordinación de pareja: dar mus para que hable el compañero cuando la mano no es clara. Mejora futura.
