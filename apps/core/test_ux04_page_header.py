"""`UX-04`: un solo encabezado de página, y un solo tamaño.

Había **ocho formas** de escribir el `<h1>` —`h3`, `h3 mb-0`, `h3 mb-1`,
`h3 mb-3`, `mb-0`, `h4`, `h4 mb-3` y pelado— repartidas en 59 apariciones. No es
una preferencia estética: un encabezado que cambia de tamaño al navegar hace
dudar de si cambiaste de sección.

**El criterio visible se cierra con CSS y el estructural es incremental**, y esa
separación es deliberada. La regla sobre `main h1` empareja las 59 de una vez y
se puede comprobar; migrar 30 plantillas de marcado denso —muchas escritas en
una sola línea larga— a ciegas y sin poder mirar las 30 pantallas es cómo se
introduce una rotura silenciosa. Así que el marcado se migra al tocar cada
plantilla por otra razón, y el techo de abajo lleva la cuenta.
"""

import re
from pathlib import Path

from django.conf import settings

TEMPLATES = Path(settings.BASE_DIR) / "templates"
PARTIAL = TEMPLATES / "generic" / "_page_header.html"
CSS = Path(settings.BASE_DIR) / "static" / "css" / "app.css"

# Las dos pantallas sin sesión. Su `<h1>` no es un encabezado de sección: llevan
# su propia chapa, su propio tamaño y no viven dentro de `main`. Excluirlas es
# la decisión, no un olvido — meterlas en el parcial las haría parecer una
# pantalla más de la aplicación.
OUTSIDE_THE_SHELL = {"login.html", "lockout.html"}

# Medido el 2026-09-02. **Techo, no meta**: baja cuando alguien migra una
# plantilla; si sube, alguien escribió un `<h1>` a mano teniendo el parcial.
HAND_WRITTEN_H1_CEILING = 57


def _hand_written_h1():
    """Los `<h1>` escritos en una plantilla en vez de salir del parcial."""
    found = []
    for path in TEMPLATES.rglob("*.html"):
        if path.name in OUTSIDE_THE_SHELL or path == PARTIAL:
            continue
        for _match in re.finditer(r"<h1\b", path.read_text(encoding="utf-8")):
            found.append(path.name)
    return found


class TestThePartialExists:
    def test_it_is_there_and_draws_the_three_pieces(self):
        source = PARTIAL.read_text(encoding="utf-8")

        assert "page_eyebrow" in source
        assert "page_title" in source
        assert "page_description" in source
        assert "<h1" in source

    def test_it_draws_only_the_left_column(self):
        """Los botones se quedan en la plantilla que llama.

        Django no puede pasar un bloque a un `{% include %}`, y fingirlo con una
        variable habría obligado a escribir el HTML de los botones como cadena —
        peor que la repetición que se viene a quitar.
        """
        source = PARTIAL.read_text(encoding="utf-8")

        assert "btn" not in source


class TestOneSizeForEveryPageTitle:
    def test_the_rule_covers_every_h1_inside_the_shell(self):
        """**El criterio visible, y por qué el selector es `main h1`.**

        La clase `.page-title` la ponen sólo las plantillas ya migradas. Con una
        regla que dependiera de la clase, las que faltan seguirían con su
        `h3`/`h4` de Bootstrap y la pantalla quedaría dispareja **durante** la
        migración, que es justo lo que la fila quiere terminar.
        """
        css = CSS.read_text(encoding="utf-8")

        assert re.search(r"main h1,\s*main h1\[class\],\s*\.page-title\s*\{", css)

    def test_the_selector_beats_bootstraps_heading_classes(self):
        """**Sin `main h1[class]` la regla no hace nada en 26 de las 59.**

        `main h1` vale (0,0,2) y la `.h3` de Bootstrap vale (0,1,0), así que
        Bootstrap gana — y el orden de las hojas no ayuda cuando la
        especificidad difiere. Medido en el navegador **después** de escribir la
        regla: los `h1.h3` seguían en 24,37 px mientras los pelados iban a
        30,93. El selector de atributo sube a (0,1,2) y sí gana.

        Se afirma sobre la presencia del selector y no sobre un píxel porque el
        cálculo de especificidad es de CSS, no del navegador: un test que
        abriera una página mediría además qué hoja cargó primero.
        """
        css = CSS.read_text(encoding="utf-8")

        assert "main h1[class]" in css

    def test_it_uses_the_scale_and_not_a_literal(self):
        """`UX-02` existe para esto: un tamaño nuevo tecleado acá sería el
        noveno de la lista que esta fila viene a cerrar."""
        css = CSS.read_text(encoding="utf-8")
        block = css.split("main h1,", 1)[1].split("}", 1)[0]

        assert "var(--fs-" in block

    def test_the_sign_in_screens_keep_their_own(self):
        """Fuera de `main` a propósito: no son encabezados de sección."""
        login = (TEMPLATES / "registration" / "login.html").read_text(encoding="utf-8")

        assert "login-title" in login


class TestTheHandWrittenOnesDoNotGrow:
    def test_the_count_stays_under_the_ceiling(self):
        found = _hand_written_h1()

        assert len(found) <= HAND_WRITTEN_H1_CEILING, (
            f"{len(found)} `<h1>` escritos a mano, techo "
            f"{HAND_WRITTEN_H1_CEILING}. Usá `generic/_page_header.html`."
        )

    def test_at_least_one_template_already_uses_the_partial(self):
        """Sin esto, el parcial podría existir sin que nadie lo llame y los tres
        tests de arriba seguirían verdes."""
        users = [
            path.name
            for path in TEMPLATES.rglob("*.html")
            if "generic/_page_header.html" in path.read_text(encoding="utf-8")
        ]

        assert users, "el parcial existe y no lo usa ninguna plantilla"
