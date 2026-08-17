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


def test_every_table_header_declares_its_scope():
    offenders = []
    for path in sorted(TEMPLATES.rglob("*.html")):
        text = path.read_text(encoding="utf-8")
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
