"""Plugin de pytest: corre la suite con el reloj en otra fecha (`LV-257`).

Para encontrar tests que dependen del día en que se corren — los que fallan el
último día de cada mes, o los que tienen una bomba de tiempo a meses vista:

    $env:PYTHONPATH = "scripts"
    $env:CLOCKSHIFT = "2026-12-31T21:30:00-03:00"
    uv run --with time-machine pytest -n auto -p pytest_clockshift

`time-machine` **no** es dependencia del proyecto: `uv run --with` lo trae sólo
para esa corrida. Sin `CLOCKSHIFT` el plugin no hace nada.

Fechas que vale la pena probar, y por qué:

- **el último día de un mes**, de día y de noche: el mes todavía en curso, y a las
  21:30 de Santiago ya es el día siguiente en UTC;
- **el primer día del mes siguiente**;
- **meses y años más adelante**: un test con una fecha fija y un "+200 días" es
  una bomba que estalla sola cuando el reloj real alcanza esa fecha.

⚠️ **Nunca una fecha anterior a las fijas de los tests** (hoy, agosto de 2026):
esos informes serían "del futuro" y el código los rechaza con razón. El reloj real
sólo avanza, así que esa corrida no dice nada.

`tick=True` deja que el reloj avance, así que `auto_now` y los plazos siguen
comportándose; sólo cambia el punto de partida. Se engancha en
`pytest_configure`, que también corre en cada worker de xdist.
"""

import os

_traveller = None


def pytest_configure(config):
    global _traveller
    target = os.environ.get("CLOCKSHIFT")
    if not target:
        return
    import time_machine

    _traveller = time_machine.travel(target, tick=True)
    _traveller.start()


def pytest_unconfigure(config):
    if _traveller is not None:
        _traveller.stop()
