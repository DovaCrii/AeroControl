"""`UX-02`: la escala tipográfica y de espaciado existe como tokens.

**Lo que este archivo NO hace es tan importante como lo que hace.** No exige que
los 311 valores `rem` literales de `app.css` desaparezcan: un reemplazo masivo es
un diff que nadie puede revisar, y un `0.85rem` cambiado a `0.8rem` por descuido
no lo caza ningún test porque este CSS no tiene pruebas de píxel. La fila dice
que se migran **al tocar cada bloque por otra razón**, la misma política
incremental que el `MASTER_PLAN` aplica a `core/views.py`.

Lo que sí fija: que la escala esté declarada, que sus pasos sean los que el
archivo ya usaba —para que migrar no obligue a mover todo—, y que el número de
literales **no crezca**. Ese último es el que convierte la política en algo
comprobable en vez de una intención.
"""

import re
from collections import Counter
from pathlib import Path

from django.conf import settings

CSS = Path(settings.BASE_DIR) / "static" / "css" / "app.css"

# Medido el 2026-09-02, y **es un techo, no una meta**. Baja cuando alguien
# migra un bloque; si sube, alguien tecleó un `rem` en vez de usar el token y
# este test lo dice en el momento, no tres meses después.
LITERAL_REM_CEILING = 311


def _css():
    return CSS.read_text(encoding="utf-8")


def _literal_uses():
    """Los `rem` **tecleados en un uso**, que es lo que la fila quiere reducir.

    Fuera quedan dos cosas que contarlas habría hecho absurdo el techo:

    - **Los comentarios.** Este archivo documenta sus decisiones, y explicar por
      qué `0.78rem` y `0.8rem` no deberían convivir habría sumado dos al
      contador de lo que se quiere evitar.
    - **La declaración de la propia escala.** `--fs-sm: 0.78rem` no es un valor
      suelto: es la definición contra la que se mide el resto. Contarla es como
      contar el diccionario entre las palabras mal escritas — y fue el primer
      resultado de este test, que dio 327 sobre un techo de 311 sin que nadie
      hubiera tecleado un literal nuevo.
    """
    css = re.sub(r"/\*.*?\*/", "", _css(), flags=re.DOTALL)
    css = re.sub(r"--(?:fs|sp)-[a-z0-9]+:\s*[^;]+;", "", css)
    return re.findall(r"[\d.]+rem", css)


def _declared(prefix):
    return dict(re.findall(rf"(--{prefix}-[a-z0-9]+):\s*([^;]+);", _css()))


class TestTheScaleIsDeclared:
    def test_the_type_scale_exists(self):
        sizes = _declared("fs")

        assert set(sizes) == {
            "--fs-xs",
            "--fs-sm",
            "--fs-md",
            "--fs-base",
            "--fs-lg",
            "--fs-xl",
        }

    def test_the_spacing_scale_exists(self):
        spacing = _declared("sp")

        assert set(spacing) == {f"--sp-{step}" for step in range(1, 7)}

    def test_every_step_is_in_rem(self):
        """Una escala mezclada en `px` y `rem` deja de escalar con el navegador,
        que es la mitad de para qué sirve."""
        for name, value in {**_declared("fs"), **_declared("sp")}.items():
            assert value.strip().endswith("rem"), f"{name} = {value}"

    def test_the_steps_grow(self):
        """Una escala que no crece monótonamente no es una escala: es una lista
        de valores con nombres que engañan."""
        for prefix, order in (
            ("fs", ["xs", "sm", "md", "base", "lg", "xl"]),
            ("sp", [str(step) for step in range(1, 7)]),
        ):
            declared = _declared(prefix)
            values = [float(declared[f"--{prefix}-{k}"].strip()[:-3]) for k in order]
            assert values == sorted(values), f"{prefix}: {values}"


class TestTheScaleCameFromWhatTheFileAlreadyUsed:
    def test_the_busiest_literals_are_steps_of_the_scale(self):
        """**El motivo por el que la escala no se inventó.**

        Si los pasos no fueran los valores que el archivo ya repite, migrar
        obligaría a mover todo el CSS el día que se migre — y ese día el diff
        sería a la vez una migración y un cambio de diseño, indistinguibles.
        """
        literals = Counter(_literal_uses())
        busiest = {value for value, count in literals.items() if count >= 15}
        scale = {v.strip() for v in {**_declared("fs"), **_declared("sp")}.values()}

        assert busiest, "no se encontró ningún literal repetido: ¿cambió el CSS?"
        assert busiest <= scale, sorted(busiest - scale)


class TestTheLiteralsDoNotGrow:
    def test_the_count_stays_under_the_ceiling(self):
        """La política incremental, hecha comprobable.

        No se exige que bajen —eso pasa al tocar cada bloque— pero **crecer** es
        alguien tecleando un `rem` nuevo teniendo la escala al lado. Si este test
        falla hacia abajo, bajá el techo en el mismo commit que migró el bloque:
        el número es el registro de cuánto queda.
        """
        count = len(_literal_uses())

        assert count <= LITERAL_REM_CEILING, (
            f"{count} literales `rem`, techo {LITERAL_REM_CEILING}. Usá los "
            "tokens `--fs-*` / `--sp-*` en vez de un valor nuevo."
        )
