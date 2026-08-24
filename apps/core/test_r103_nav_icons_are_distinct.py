"""R10.3: dos entradas del menú no pueden dibujar el mismo icono.

Reportado por el usuario el 2026-08-24 mirando la barra lateral: *"pensar mejor
los iconos, sobre todo los que se repiten"*. Había **dos pares idénticos byte a
byte** en la sección Padrón — `Operadores` con `Asignaciones de operador`, y
`Aeronaves` con `Asignaciones de aeronave` — más dos pares que a 18 px se leían
iguales (`Permisos` con `Mantenciones`, y `Centro de administración` con
`Administración`).

Un icono repetido no rompe nada, y por eso nadie lo ve en una suite: la página
carga, el enlace funciona, el HTML es válido. Lo que se pierde es la única
función del icono, que es **distinguir de un vistazo** — y cuanto más crece el
menú, más caro sale.

Este test lee **el archivo**, no una página renderizada: la mitad de las
entradas están tras un permiso, así que una página cualquiera no las dibuja
todas, y ese es justo el punto ciego donde el defecto vivió.
"""

import re
from pathlib import Path

import pytest
from django.conf import settings

BASE_HTML = Path(settings.BASE_DIR) / "templates" / "base.html"

# Cada entrada del menú es un `<a … class="nav-item …">` con su `<svg>` dentro y
# la etiqueta traducible después. Se captura el dibujo y el nombre.
NAV_ENTRY = re.compile(
    r'<a\s[^>]*class="nav-item[^"]*"[^>]*>\s*'
    r"(?P<svg><svg\b.*?</svg>)\s*"
    r'\{%\s*translate\s+"(?P<label>[^"]+)"',
    re.DOTALL,
)


def _entries():
    """[(etiqueta, dibujo normalizado)] de todas las entradas activas.

    El dibujo se normaliza quitando espacios: dos SVG que sólo difieren en
    saltos de línea son el mismo icono para quien lo mira, y no queremos que un
    reformateo haga pasar el test por casualidad.
    """
    html = BASE_HTML.read_text(encoding="utf-8")
    # Los bloques comentados no se dibujan; incluirlos daría falsos positivos
    # sobre iconos que hoy nadie ve.
    html = re.sub(
        r"\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}", "", html, flags=re.DOTALL
    )
    return [
        (match.group("label"), re.sub(r"\s+", "", match.group("svg")))
        for match in NAV_ENTRY.finditer(html)
    ]


def test_the_menu_is_actually_being_read():
    """El guardián del guardián: si la expresión deja de calzar, las
    afirmaciones de abajo pasarían en verde sin haber mirado nada."""
    entries = _entries()

    assert len(entries) >= 15
    labels = {label for label, _svg in entries}
    assert {"Aircraft", "Operators", "Permissions"} <= labels


def test_no_two_menu_entries_draw_the_same_icon():
    """El defecto exacto que el usuario reportó."""
    by_drawing = {}
    for label, drawing in _entries():
        by_drawing.setdefault(drawing, []).append(label)

    repeated = {
        drawing: labels for drawing, labels in by_drawing.items() if len(labels) > 1
    }

    assert not repeated, "entradas del menú con el mismo icono:\n" + "\n".join(
        "  " + " ≡ ".join(labels) for labels in repeated.values()
    )


@pytest.mark.parametrize(
    "first, second",
    [
        # Los cuatro pares que se corrigieron, fijados por nombre para que la
        # próxima persona sepa cuáles ya costaron una revisión.
        ("Operators", "Operator assignments"),
        ("Aircraft", "Aircraft assignments"),
        ("Permissions", "Maintenance jobs"),
        ("Administration center", "Admin"),
    ],
)
def test_the_pairs_that_used_to_collide_stay_apart(first, second):
    drawings = dict(_entries())

    assert first in drawings and second in drawings
    assert drawings[first] != drawings[second]


def test_every_icon_is_hidden_from_screen_readers():
    """Un icono decorativo junto a su propio texto se lee dos veces si no se
    oculta. Va acá porque es la otra mitad de "el icono comunica": a quien usa
    lector de pantalla le comunica el texto, no el dibujo."""
    offenders = [
        label for label, drawing in _entries() if 'aria-hidden="true"' not in drawing
    ]

    assert not offenders, f"iconos sin aria-hidden: {offenders}"
