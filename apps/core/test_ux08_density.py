"""`UX-08`: la densidad de las filas, conmutable y recordada por persona.

En una lista de veinte permisos, pasar de cómoda a compacta son **cuatro filas
más a la vista** — y quien revisa vencimientos mira la lista entera, no una fila.

⚠️ **Y esta fila destapó un defecto que llevaba en el árbol desde antes.**
`theme-init.js` leía `localStorage` **sin envolver**, y es el único de los cuatro
archivos de JS del proyecto que lo hacía — los otros tres envuelven sus nueve
accesos. Es el primero que corre en cada página: en una ventana privada, o con el
almacenamiento de sitio bloqueado, `getItem` **lanza** (no devuelve `null`), la
función abortaba y `data-theme` no se ponía nunca. Quien prefiere el tema oscuro
veía la aplicación en claro, en todas las pantallas, sin forma de saber por qué.
Es la lección que `AGENTS.md` ya tenía escrita de cuando pasó en `app.js`.
"""

import re
from pathlib import Path

from django.conf import settings

JS = Path(settings.BASE_DIR) / "static" / "js"
CSS = Path(settings.BASE_DIR) / "static" / "css" / "app.css"
BASE = Path(settings.BASE_DIR) / "templates" / "base.html"


class TestEveryLocalStorageAccessIsWrapped:
    """El guardián que habría atrapado el defecto de `theme-init.js`."""

    def test_no_javascript_file_reads_storage_outside_a_try(self):
        """Se cuenta por archivo y no se busca un patrón exacto: lo que importa
        es que ningún archivo toque `localStorage` sin tener un `try`, que es
        justamente la forma en que el defecto sobrevivió — tres archivos lo
        hacían bien y el cuarto no, con el patrón correcto a la vista."""
        offenders = []
        for path in JS.glob("*.js"):
            source = path.read_text(encoding="utf-8")
            uses = len(re.findall(r"localStorage\.", source))
            if uses and not re.search(r"\btry\s*\{", source):
                offenders.append(path.name)

        assert not offenders, (
            "`localStorage` lanza en una ventana privada, así que todo acceso "
            "va envuelto — lectura incluida: " + ", ".join(offenders)
        )

    def test_the_theme_still_lands_when_storage_is_unavailable(self):
        """El caso concreto: con el `getItem` dentro del `try`, el atributo se
        pone igual y sólo se pierde la preferencia guardada."""
        source = (JS / "theme-init.js").read_text(encoding="utf-8")
        before = source.index("function stored")
        after = source.index('h.setAttribute("data-theme"'.replace('"', "'"))

        assert "try {" in source[before:after]
        assert "return null" in source[before:after]


class TestTheDensityIsAppliedBeforePaint:
    def test_the_attribute_is_set_in_the_render_blocking_script(self):
        """Aplicarlo después de pintar haría **saltar la lista entera** a la
        vista, que es peor que no tener la función."""
        source = (JS / "theme-init.js").read_text(encoding="utf-8")

        assert "data-density" in source
        assert "js/theme-init.js" in BASE.read_text(encoding="utf-8")

    def test_the_default_is_comfortable(self):
        """Es la densidad que la aplicación ha tenido siempre: estrenar a
        alguien en compacta sería cambiarle la pantalla sin que lo pidiera."""
        source = (JS / "theme-init.js").read_text(encoding="utf-8")

        assert "=== 'compact'" in source or '=== "compact"' in source


class TestTheToggleIsThereAndReachable:
    def test_the_button_exists_with_its_two_labels(self):
        markup = BASE.read_text(encoding="utf-8")

        assert 'id="density-toggle"' in markup
        assert "data-label-compact" in markup
        assert "data-label-comfortable" in markup
        assert "aria-pressed" in markup

    def test_the_write_is_wrapped_so_a_private_window_does_not_break_it(self):
        """El fallo tiene que ser benigno: la preferencia no se recuerda entre
        visitas, pero el botón sigue funcionando en ésta. Lo que no puede pasar
        es que la excepción corte la función y deje el botón rotulado al revés
        — que es exactamente lo que `AGENTS.md` describe."""
        source = (JS / "app.js").read_text(encoding="utf-8")
        block = source[source.index("density-toggle") :][:1200]

        assert "try {" in block
        assert "catch" in block


class TestOnlyTheSpacingChanges:
    def test_the_compact_rule_touches_padding_and_not_the_type_size(self):
        """Bajar además el cuerpo de letra habría hecho que "compacta"
        significara también "más difícil de leer", que es otra decisión y no la
        que esta fila ofrece."""
        css = CSS.read_text(encoding="utf-8")
        block = css[css.index('[data-density="compact"]') :][:600]

        assert "padding-top" in block
        assert "font-size" not in block

    def test_the_stacked_card_gets_its_own_treatment(self):
        """Bajo 768 px la fila ya no es una fila: es una tarjeta apilada, y
        comprimir el relleno vertical juntaría los rótulos hasta hacerlos
        ilegibles."""
        css = CSS.read_text(encoding="utf-8")

        assert '[data-density="compact"] .table-responsive' in css
