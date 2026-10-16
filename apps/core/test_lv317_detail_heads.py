"""LV-317 (ola B): la cabecera de ficha unificada, el chip de estado y la línea de tiempo.

Fija lo que las fichas comparten: una sola cabecera (`generic/_entity_head.html`) con el
estado como chip de texto + color, la navegación por secciones de la aeronave y la
trazabilidad como línea de tiempo, con el tono de cada estado en una sola tabla.
"""

import re
from pathlib import Path

import pytest
from django.urls import reverse
from django.utils.translation import gettext

from apps.core.templatetags.aero_tags import status_tone
from apps.core.testing import login_as
from apps.registry.models import Aircraft, CostCenter, Operator

ROOT = Path(__file__).resolve().parents[2]
IDENTITY = (ROOT / "static" / "css" / "identity.css").read_text(encoding="utf-8")


def _aircraft(status="active", **extra):
    centre = CostCenter.objects.create(code="CC1", name="Uno")
    return Aircraft.objects.create(
        registration="RPA-1",
        type="RPA",
        model="Matrice 300 RTK",
        manufacturer="DJI",
        cost_center=centre,
        status=status,
        **extra,
    )


@pytest.mark.parametrize(
    ("value", "tone"),
    [
        ("approved", "ok"),
        ("active", "ok"),
        ("damaged", "critical"),
        ("denied", "critical"),
        ("maintenance", "warning"),
        ("requested", "warning"),
        ("retired", "neutral"),
        ("", "neutral"),
        (None, "neutral"),
    ],
)
def test_status_tone_is_one_table(value, tone):
    assert status_tone(value) == tone


@pytest.mark.django_db
class TestAircraftHead:
    def _page(self, aircraft):
        client = login_as("view_aircraft", "view_costcenter")
        return client.get(
            reverse("aircraft-detail", args=[aircraft.pk])
        ).content.decode()

    def test_the_status_is_a_chip_with_text_and_tone(self):
        html = self._page(_aircraft("damaged"))
        head = html.split('<header class="entity-bar">')[1].split("</header>")[0]

        assert re.search(
            r'class="id-chip id-chip--critical">\s*' + re.escape(gettext("Damaged")),
            head,
        )
        assert "<h1" in head

    def test_the_section_nav_points_at_real_anchors(self):
        html = self._page(_aircraft())
        nav = html.split('class="entity-nav"')[1].split("</nav>")[0]
        targets = re.findall(r'href="#([^"]+)"', nav)

        assert "section-insurance" in targets
        for target in targets:
            assert f'id="{target}"' in html, target


@pytest.mark.django_db
def test_a_generic_detail_uses_the_shared_head():
    operator = Operator.objects.create(full_name="Ana Pérez", employee_id="E-1", rut="")
    html = (
        login_as("view_operator")
        .get(reverse("operator-detail", args=[operator.pk]))
        .content.decode()
    )

    assert '<header class="entity-bar">' in html
    assert "id-chip--ok" in html


@pytest.mark.django_db
def test_an_archived_record_says_so_in_its_chip():
    aircraft = _aircraft()
    aircraft.is_active = False
    aircraft.save()
    html = (
        login_as("view_aircraft")
        .get(reverse("aircraft-detail", args=[aircraft.pk]))
        .content.decode()
    )
    head = html.split('<header class="entity-bar">')[1].split("</header>")[0]

    assert "id-chip--neutral" in head
    assert gettext("Archived") in head


def test_traceability_is_a_timeline_not_a_table():
    source = (ROOT / "templates" / "generic" / "_traceability.html").read_text(
        encoding="utf-8"
    )

    assert '<ol class="id-timeline">' in source
    assert "<table" not in source


def test_the_detail_section_owns_its_rules():
    start = IDENTITY.index("/* == B: fichas de detalle == */")
    end = IDENTITY.index("/* == C: formularios == */")
    section = IDENTITY[start:end]

    for selector in (".entity-bar", ".entity-nav", ".id-timeline"):
        assert selector in section
        assert IDENTITY.count(f"\n{selector} ") + IDENTITY.count(f"\n{selector},") >= 1
    # Ninguna de estas reglas vive fuera de su sección.
    outside = IDENTITY[:start] + IDENTITY[end:]
    assert ".entity-bar" not in outside
    assert ".id-timeline" not in outside
