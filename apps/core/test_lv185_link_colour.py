"""LV-185: los enlaces usan el color de la app, no el azul de Bootstrap.

Observación del usuario mirando el listado de planes: *"el color de las letras
comparadas con toda la app, existen inconsistencias visuales"*.

**Lo primero que salió de medir fue que la sospecha inicial era falsa**: la
columna del listado de planes y la de Operadores dan **exactamente el mismo
color** (`--ac-text`), porque las dos usan `.table-primary-value`. Ahí no había
nada roto.

Lo que sí estaba roto es más grande: **la app nunca definió su color de enlace**,
así que todo `<a>` que no fuera una de esas columnas ni un botón salía en el azul
por defecto de Bootstrap —`#0d6efd` en claro, `#6ea8fe` en oscuro—, que no tiene
relación con el turquesa de la identidad. Eso es lo que se percibe como
inconsistencia: dos familias de color conviviendo sin criterio.

**La trampa, verificada en el navegador antes de escribir el arreglo**: Bootstrap
5.3 arma el color con `rgba(var(--bs-link-color-rgb), …)` e **ignora**
`--bs-link-color`. Fijar sólo la forma hex deja un CSS que parece decir algo y no
mueve un píxel — la peor clase de arreglo, porque se da por hecho.

De ahí que existan tripletes RGB junto a los hex. **Duplicar un color en dos
notaciones es la deriva que este repo ya arrastró con los tokens**, así que estos
tests exigen que las dos formas sean el mismo color. Sin eso se desincronizan y
nadie lo nota hasta que un enlace queda de otro color.
"""

import re
from pathlib import Path

import pytest
from django.conf import settings

CSS = Path(settings.BASE_DIR) / "static" / "css" / "app.css"

# WCAG AA para texto normal. Un enlace es texto de cuerpo en casi todos sus usos.
AA_TEXT = 4.5


def _block(pattern):
    match = re.search(
        pattern + r"[^{]*\{(.*?)\n\}", CSS.read_text(encoding="utf-8"), re.DOTALL
    )
    assert match, f"no se encontró el bloque {pattern!r}"
    return match.group(1)


def _tokens(block):
    hexes = dict(re.findall(r"(--ac-[a-z-]+):\s*(#[0-9a-fA-F]{3,8})", block))
    triplets = dict(re.findall(r"(--ac-[a-z-]+-rgb):\s*([\d,\s]+);", block))
    return hexes, triplets


def _rgb(value):
    raw = value.lstrip("#")
    if len(raw) == 3:
        raw = "".join(c * 2 for c in raw)
    return tuple(int(raw[i : i + 2], 16) for i in (0, 2, 4))


def _relative_luminance(value):
    def channel(component):
        component /= 255
        return (
            component / 12.92
            if component <= 0.03928
            else ((component + 0.055) / 1.055) ** 2.4
        )

    red, green, blue = (channel(c) for c in _rgb(value))
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _contrast(one, other):
    light, dark = sorted(
        (_relative_luminance(one), _relative_luminance(other)), reverse=True
    )
    return (light + 0.05) / (dark + 0.05)


@pytest.mark.parametrize(
    "selector", [r"(?m)^:root", r'\[data-theme="dark"\], \[data-bs-theme="dark"\]']
)
def test_the_rgb_triplets_say_the_same_colour_as_the_hex(selector):
    """Dos notaciones del mismo color se desincronizan calladas."""
    hexes, triplets = _tokens(_block(selector))

    for name, triplet in triplets.items():
        source = name.removesuffix("-rgb")
        expected = _rgb(hexes[source])
        written = tuple(int(part) for part in triplet.split(","))
        assert written == expected, f"{name} no coincide con {source}"


@pytest.mark.parametrize(
    "selector", [r"(?m)^:root", r'\[data-theme="dark"\], \[data-bs-theme="dark"\]']
)
def test_the_link_colour_is_the_apps_and_not_bootstraps(selector):
    block = _block(selector)

    assert "--bs-link-color-rgb: var(--ac-primary" in block, (
        "sin esto los enlaces salen en el azul de Bootstrap; y tiene que ser la "
        "forma `-rgb`, que es la única que Bootstrap 5.3 lee — ver LV-185"
    )


def test_the_link_colour_clears_aa_on_every_surface():
    """Se eligió el paso oscuro en claro por esto: el base roza el mínimo."""
    for selector, token in (
        (r"(?m)^:root", "--ac-primary-hover"),
        (r'\[data-theme="dark"\], \[data-bs-theme="dark"\]', "--ac-primary"),
    ):
        hexes, _triplets = _tokens(_block(selector))
        for surface in ("--ac-bg", "--ac-surface", "--ac-surface-raised"):
            ratio = _contrast(hexes[token], hexes[surface])
            assert ratio >= AA_TEXT, (
                f"{token} sobre {surface} da {ratio:.2f}:1 en {selector}"
            )
