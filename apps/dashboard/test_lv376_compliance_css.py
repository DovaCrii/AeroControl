"""LV-376 (fase 0): el CSS de «Cumplimiento» vive en su propia hoja (`static/css/compliance.css`).

Se fija: la hoja pesa menos de 16 KB (bytes con salto LF, como el CI), sólo define `--id-*`, no anima
ni hace transiciones (el único bloque de movimiento sigue en `identity.css`); lo mudado ya no está en
`identity.css`; y la hoja se carga en la página completa y en el panel SOLO cuando hay hueco de
Cumplimiento.
"""

import re

import pytest
from django.urls import reverse

from apps.core.test_lv315_identity_foundation import IDENTITY, ROOT
from apps.core.testing import login_as
from apps.dashboard.test_lv359_compliance_section import operation  # noqa: F401

PATH = ROOT / "static" / "css" / "compliance.css"
LINK = 'href="/static/css/compliance.css"'


def _lf_bytes(path):
    return path.read_bytes().replace(b"\r\n", b"\n")


def _css():
    return _lf_bytes(PATH).decode("utf-8")


def test_the_sheet_is_under_16_kb_in_lf_bytes():
    assert len(_lf_bytes(PATH)) < 16 * 1024


def test_the_sheet_defines_only_id_tokens():
    defined = set(re.findall(r"(?m)^\s*(--[\w-]+)\s*:", _css()))
    assert defined
    assert {name for name in defined if not name.startswith("--id-")} == set()


def test_the_sheet_has_no_motion():
    css = _css()
    assert not re.search(
        r"\banimation(-[a-z]+)?\s*:|@keyframes|transition\s*:|translateX", css
    )
    assert "prefers-reduced-motion" not in css  # el único bloque vive en identity.css


def test_what_moved_is_no_longer_in_the_global_sheet_and_dead_rules_are_gone():
    assert ".id-cx" not in IDENTITY and "--id-cx-" not in IDENTITY
    css = _css()
    for dead in (
        ".id-cx-block--heat",
        ".id-cx-block--alerts",
        ".id-cx-block--maintenance",
        ".id-cx-block--history",
        ".id-cx-block--permits",
        ".id-cx-past",
    ):
        assert dead not in css, dead
    # los anillos esperan su condición de cierre: siguen
    assert ".id-cx-track" in css and ".id-cx-ring-n" in css


@pytest.mark.django_db
def test_the_full_page_loads_the_sheet_after_identity():
    html = login_as("view_alert").get(reverse("dashboard-compliance")).content.decode()
    assert LINK in html
    assert html.index("css/identity.css") < html.index("css/compliance.css")


@pytest.mark.django_db
def test_the_panel_loads_the_sheet_only_with_the_compliance_slot(operation):  # noqa: F811
    with_slot = login_as("view_alert").get(reverse("dashboard")).content.decode()
    assert 'id="compliance-section"' in with_slot
    assert LINK in with_slot
    without = login_as().get(reverse("dashboard")).content.decode()
    assert LINK not in without
