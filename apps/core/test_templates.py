import pathlib

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
