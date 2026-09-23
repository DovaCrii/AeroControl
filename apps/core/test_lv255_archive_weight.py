"""LV-255: «Archivar» pesa lo mismo en todas las fichas.

Cinco fichas lo dibujaban en rojo (`btn-outline-danger`) y dos —permisos y planes
geo— en gris, el mismo peso que «Volver» o «Editar». Archivar saca el registro de
todas las listas; no es irreversible (hay «Restaurar»), pero es la acción de
salida, y un botón que se ve igual que «Volver» se aprieta igual que «Volver».

Se lee del árbol y no de una página: las siete fichas están tras permisos
distintos, y un botón con otra clase es una decisión de la plantilla.
"""

import re
from pathlib import Path

from django.conf import settings

from apps.core.testing import without_template_comments

TEMPLATES = Path(settings.BASE_DIR) / "templates"
ARCHIVE_BUTTON = re.compile(
    r'<(?:button|a)\b[^>]*class="([^"]*)"[^>]*>\s*\{% translate "Archive" %\}'
)


def _archive_buttons():
    found = []
    for path in TEMPLATES.rglob("*_detail.html"):
        source = without_template_comments(path.read_text(encoding="utf-8"))
        for match in ARCHIVE_BUTTON.finditer(source):
            found.append((path.relative_to(TEMPLATES).as_posix(), match.group(1)))
    return found


def test_the_buttons_are_being_found():
    """Si el patrón deja de calzar, el test de abajo pasaría sin mirar nada."""
    pages = {page for page, _classes in _archive_buttons()}

    assert "operations/permission_detail.html" in pages
    assert "geo/plan_detail.html" in pages
    assert len(pages) >= 5, sorted(pages)


def test_every_archive_button_carries_the_destructive_weight():
    grey = [
        (page, classes)
        for page, classes in _archive_buttons()
        if "btn-outline-danger" not in classes.split()
    ]

    assert not grey, grey
