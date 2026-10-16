"""LV-316 (ola A del rediseño): listas, tablas y filtros.

Fija lo que la ola agrega y lo que no puede romper: la barra de filtros compacta en las dos
plantillas base, los estados como `.id-chip`, la sección A de `identity.css` (y sólo ella) y
la coherencia `.table-normalized` / `colspan` de las listas ya normalizadas.
"""

import re
from pathlib import Path

import pytest
from django.conf import settings
from django.urls import reverse

from apps.core.testing import login_as, without_template_comments

ROOT = Path(settings.BASE_DIR)
TEMPLATES = ROOT / "templates"
IDENTITY = (ROOT / "static" / "css" / "identity.css").read_text(encoding="utf-8")


def _section_a():
    start = IDENTITY.index("/* == A: listas, tablas y filtros == */")
    return IDENTITY[start : IDENTITY.index("/* == B:")]


def _read(name):
    return without_template_comments(
        (TEMPLATES / "generic" / name).read_text(encoding="utf-8")
    )


def test_the_generic_list_uses_the_compact_filter_bar():
    markup = _read("list.html")

    assert 'class="id-filterbar"' in markup
    assert "row g-2" not in markup
    assert 'class="id-filter-label"' in markup


def test_the_worktable_wraps_every_filter_bar():
    """Las listas hijas escriben su propio formulario dentro de `worktable_filters`;
    el envoltorio es lo que las deja en la misma franja sin tocarlas."""
    markup = _read("worktable.html")

    assert re.search(
        r'<div class="id-filters">\{% block worktable_filters %\}\{% endblock %\}</div>',
        markup,
    )
    assert "id-worktable" in markup


def test_the_default_row_states_are_chips_with_text():
    markup = _read("_table_body.html")

    assert "id-chip id-chip--ok" in markup
    assert "id-chip id-chip--neutral" in markup
    assert "badge bg-success" not in markup
    assert "badge bg-secondary" not in markup


@pytest.mark.django_db
def test_a_rendered_list_carries_the_filter_bar_and_the_worktable_class():
    body = login_as("view_alert").get(reverse("alert-list")).content.decode()

    assert 'class="id-filters"' in body
    assert "id-worktable" in body


def test_section_a_styles_the_bar_headers_and_pager():
    css = _section_a()

    for selector in (
        ".id-filterbar",
        ".id-filters > form.row",
        ".id-filter-label",
        ".id-worktable thead th",
        ".id-pager",
        ".bulk-bar",
    ):
        assert selector in css, selector
    assert "font-size: var(--id-fs-sm)" in css
    assert "var(--id-t-fast)" in css


def test_the_row_hover_transition_respects_reduced_motion():
    """La transición de 120 ms existe y `reduce` la anula. No se abre un bloque
    `no-preference` acá: los guardianes de la capa leen el primero del archivo."""
    css = _section_a()

    assert "transition: background-color var(--id-t-fast)" in css
    assert "prefers-reduced-motion: no-preference" not in css
    assert re.search(r"prefers-reduced-motion: reduce\)\s*\{[^}]*transition: none", css)


def test_section_a_does_not_touch_tokens_or_other_sections():
    css = _section_a()

    assert not re.search(r"(?m)^\s*--(id|ac|sev)-[\w-]+\s*:", css)
    assert "@keyframes" not in css


def test_the_generic_list_is_not_normalized_while_its_empty_row_spans_99():
    """El guardián del `colspan` de las listas normalizadas es `test_ux07_worktable`. Acá
    sólo se fija la frontera de esta ola: la lista genérica no declara colgroup, así que
    su fila vacía (`colspan="99"`) es inofensiva sólo si la tabla no es normalizada."""
    body = _read("_table_body.html")
    markup = _read("list.html")
    block = re.search(
        r"\{%\s*block\s+list_table_class\s*%\}(.*?)\{%\s*endblock", markup, re.S
    )

    if 'colspan="99"' in body:
        assert "table-normalized" not in (block.group(1) if block else "")
        assert "<col " not in markup
