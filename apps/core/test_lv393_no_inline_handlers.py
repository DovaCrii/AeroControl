"""LV-393: sin manejadores en línea y sin glifos sueltos como controles.

`CSP_REPORT_ONLY` está en `True`. El día que se aplique, un `onsubmit="..."` deja de
correr y «Reportar accidente / daño» se enviaría sin preguntar (`T8`). Las
confirmaciones van en `data-confirm`, que `app.js` lee con un solo manejador.

Los glifos («✎», «×», «⚠») que hacían de control no llegaban a 24x24 px ni tenían
nombre accesible (`T13`, WCAG 2.5.8).
"""

import re
from datetime import timedelta
from pathlib import Path

import pytest
from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.translation import gettext, override

TEMPLATES = Path(settings.BASE_DIR) / "templates"

# Un manejador `on<evento>=` dentro de una etiqueta HTML, no en prosa ni en un
# `{% comment %}`.
INLINE_HANDLER = re.compile(r"<[a-zA-Z][^<>]*?\son[a-z]+\s*=", re.S)
COMMENT_BLOCK = re.compile(r"\{%\s*comment\b.*?\{%\s*endcomment\s*%\}", re.S)

# Excepciones justificadas: ninguna hoy. Cada una exige su motivo.
ALLOWED: dict[str, str] = {}


def _source(path):
    return COMMENT_BLOCK.sub("", path.read_text(encoding="utf-8"))


def test_no_template_uses_an_inline_event_handler():
    offenders = []
    for path in sorted(TEMPLATES.rglob("*.html")):
        rel = path.relative_to(TEMPLATES).as_posix()
        if rel in ALLOWED:
            continue
        if INLINE_HANDLER.search(_source(path)):
            offenders.append(rel)
    assert not offenders, (
        "Manejadores en línea (onsubmit=/onclick=/...): usar data-confirm o un "
        f"listener en app.js. Plantillas: {offenders}"
    )


def test_the_guard_recognises_a_handler_when_there_is_one():
    assert INLINE_HANDLER.search('<form method="post" onsubmit="return confirm(1)">')
    assert INLINE_HANDLER.search("<a\n  onclick='x()'>")
    assert not INLINE_HANDLER.search('<form data-confirm="Delete? once on=">')


def _tag_with(path, needle):
    """La etiqueta de apertura que contiene `needle` (acotada: `<form ...>`)."""
    source = _source(TEMPLATES / path)
    start = source.index(needle)
    open_at = source.rfind("<form", 0, start)
    return source[open_at : source.index(">", start) + 1]


def test_report_incident_form_carries_data_confirm():
    tag = _tag_with("registry/aircraft_detail.html", "aircraft-report-incident")
    assert "data-confirm=" in tag
    assert "Mark this aircraft as damaged" in tag
    assert "onsubmit" not in tag


def test_unlink_plan_form_carries_data_confirm():
    tag = _tag_with("operations/permission_detail.html", "permission-unlink-plan")
    assert 'data-confirm="{{ unlink_confirm }}"' in tag


def test_saved_view_delete_confirms_on_the_form_not_the_button():
    """`app.js` lee `form.dataset.confirm`: en el botón nunca se preguntaba."""
    source = _source(TEMPLATES / "generic" / "_worktable_toolbar.html")
    form = source[source.index("list-view-delete") :]
    form_tag = form[: form.index(">")]
    assert "data-confirm=" in form_tag
    button = form[form.index("<button") : form.index("</button>")]
    assert "data-confirm" not in button
    assert "aria-label=\"{% translate 'Delete this view' %}\"" in button
    assert "ac-glyph-control" in button


def test_assign_owner_glyph_is_a_labelled_control():
    source = _source(TEMPLATES / "compliance" / "_alert_rows.html")
    at = source.index("data-alert-assign")
    link = source[source.rfind("<a ", 0, at) : source.index("</a>", at)]
    assert "btn btn-sm" in link
    assert "aria-label=\"{% translate 'Assign an owner' %}\"" in link
    assert "ac-glyph-control" in link


def test_glyph_control_class_guarantees_the_minimum_target():
    css = (Path(settings.BASE_DIR) / "static" / "css" / "app.css").read_text(
        encoding="utf-8"
    )
    rule = css[css.index(".ac-glyph-control {") :]
    rule = rule[: rule.index("}")]
    assert "min-width: 24px" in rule and "min-height: 24px" in rule


@pytest.mark.django_db
def test_dwell_badge_shows_the_days_as_visible_text():
    from apps.maintenance.models import MaintenanceRecord
    from apps.maintenance.tests import _aircraft

    record = MaintenanceRecord.objects.create(
        aircraft=_aircraft(),
        maintenance_type="unscheduled",
        description="Gearbox replacement",
        status="at_workshop",
    )
    days = MaintenanceRecord.WORKSHOP_DWELL_ALERT_DAYS + 3
    MaintenanceRecord.objects.filter(pk=record.pk).update(
        status_changed_at=timezone.now() - timedelta(days=days, hours=1)
    )
    record.refresh_from_db()
    assert record.workshop_dwell_is_overdue

    with override("es"):
        html = render_to_string(
            "maintenance/_record_rows.html", {"objects": [record], "perms": {}}
        )
        expected = f"{days} días en este estado"
        assert gettext("Dwelling in this status longer than usual") in html
    badge = html[html.index("data-dwell-badge") :]
    badge = badge[: badge.index("</span>", badge.index("</span>") + 1)]
    assert expected in badge
