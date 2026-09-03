"""T5.8: cada `<th>` declara si encabeza una fila o una columna.

Sin `scope`, un lector de pantalla tiene que adivinar a qué celdas se refiere un
encabezado, y en las tablas de esta app las dos formas conviven: los listados
usan `<th>` en `<thead>` (encabezan columnas) y las fichas lo usan al principio
de cada fila, como etiqueta del dato (encabezan filas). Adivinar mal convierte
una tabla de datos en una lista de palabras sueltas.

Este test es un **guardián**, no una comprobación de lo que ya está: se corrigió
en 33 plantillas de una vez, y lo que importa es que la número 34 no nazca sin
`scope`. Lee las plantillas como texto porque es una propiedad del marcado, no
del render: una tabla que hoy no tiene datos igual tiene que estar bien escrita.

Nota de método, aprendida rompiendo las 33 plantillas de una pasada: el patrón
lleva `(?![a-z])` porque `<th` encaja también con el principio de `<thead`, y sin
eso una sustitución produce `<th scope="col"ead>`.
"""

import re
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parents[2] / "templates"
TH_WITHOUT_SCOPE = re.compile(r"<th(?![a-z])(?![^>]*\bscope=)", re.I)
# `UX-07`: un `{% comment %}` no se renderiza, así que un `<th>` escrito ahí
# adentro no es marcado — es una explicación **sobre** el marcado. Exigirle
# `scope` es pedirle un atributo a algo que no existe en la página, y el efecto
# práctico es que nadie puede nombrar `<th>` al documentar por qué una columna se
# dibuja como se dibuja. Es el mismo hueco que `LV-169` cerró en el guardián de
# traducciones, y por la misma razón.
#
# Se reemplaza por espacios en vez de recortar, para que los números de línea que
# este archivo reporta sigan apuntando al lugar real.
TEMPLATE_COMMENT = re.compile(
    r"\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}", re.DOTALL
)


def _without_comments(text):
    return TEMPLATE_COMMENT.sub(
        lambda match: re.sub(r"[^\n]", " ", match.group(0)), text
    )


def test_every_table_header_declares_its_scope():
    offenders = []
    for path in sorted(TEMPLATES.rglob("*.html")):
        text = _without_comments(path.read_text(encoding="utf-8"))
        for match in TH_WITHOUT_SCOPE.finditer(text):
            line = text[: match.start()].count("\n") + 1
            offenders.append(f"{path.relative_to(TEMPLATES).as_posix()}:{line}")

    assert not offenders, "«<th>» sin scope: " + ", ".join(offenders)


def test_the_pattern_does_not_confuse_thead_with_th():
    """El guardián tiene que distinguir `<thead>` de `<th>`, o daría por
    incumplidor a cada tabla bien escrita del proyecto."""
    assert not TH_WITHOUT_SCOPE.search("<thead><tr>")
    assert TH_WITHOUT_SCOPE.search("<th>Fecha</th>")
    assert not TH_WITHOUT_SCOPE.search('<th scope="col">Fecha</th>')


def test_a_th_inside_a_template_comment_is_not_markup():
    """Y uno fuera del comentario sí, o el recorte taparía la mitad del árbol."""
    inside = "{% comment %}degrada a <th> a secas{% endcomment %}<th>Fecha</th>"
    blanked = _without_comments(inside)

    assert len(TH_WITHOUT_SCOPE.findall(blanked)) == 1
    # El recorte conserva los saltos de línea, así que las líneas que el guardián
    # reporta siguen apuntando al lugar real.
    multiline = "a\n{% comment %}x\ny{% endcomment %}\nb"
    assert _without_comments(multiline).count("\n") == multiline.count("\n")
