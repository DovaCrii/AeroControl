import pathlib
import re

import pytest
from django.conf import settings
from django.template.loader import get_template


def _template_names():
    names = []
    for templates_dir in settings.TEMPLATES[0]["DIRS"]:
        root = pathlib.Path(templates_dir)
        for path in root.rglob("*.html"):
            names.append(str(path.relative_to(root)).replace("\\", "/"))
    return sorted(names)


@pytest.mark.parametrize("template_name", _template_names())
def test_template_compiles(template_name):
    """manage.py check does not compile templates, so a duplicated {% block %}
    or other syntax error only surfaces when a view renders it (see
    AUDIT_CLAUDE.md F-01, where this broke the dashboard). get_template()
    parses without needing a request or database, so this stays cheap."""
    get_template(template_name)


def test_dashboard_headings_do_not_skip_a_level():
    """El panel baja de nivel de uno en uno: h1, h2, h3, sin saltar a h4.

    Los lectores de pantalla navegan por encabezados, y un h2 seguido de un h4
    anuncia una seccion que no existe (LV-394). El tamano visual no depende del
    nivel: lo fija la clase `.h6`, asi que subir el nivel no cambia el aspecto.
    """
    source = (
        pathlib.Path(settings.BASE_DIR) / "templates" / "dashboard" / "index.html"
    ).read_text(encoding="utf-8")
    levels = [int(n) for n in re.findall(r"<h([1-6])\b", source)]
    assert levels, "el panel no tiene encabezados"
    assert levels[0] == 1
    jumps = [(a, b) for a, b in zip(levels, levels[1:]) if b > a + 1]
    assert not jumps, f"saltos de nivel en el panel: {jumps}"
