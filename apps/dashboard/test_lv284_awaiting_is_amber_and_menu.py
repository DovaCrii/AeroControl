"""LV-284: «Esperando» va en naranja, y «¿Puedo volar?» y «Vuelos» salen del menú.

Pedido del usuario (2026-10-06):
- *«cuando diga esperando sea color naranjo y no rojo la sección»*: la fila de una
  faena sin permiso vigente pero con uno esperando respuesta pasa de rojo a ámbar.
- *«ocultar el puedo volar y vuelos no son necesarios de momento»*: sólo el enlace
  del menú; las pantallas siguen enteras.
"""

import re
from datetime import timedelta
from pathlib import Path

import pytest
from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from apps.operations.models import FlightPermission
from apps.registry.models import Aircraft, CostCenter

TODAY = timezone.localdate()
CSS = Path(settings.BASE_DIR) / "static" / "css" / "app.css"


def _page(client, admin_user):
    Aircraft.objects.create(
        registration="RPA-0001", type="RPA", model="M3", manufacturer="DJI"
    )
    client.force_login(admin_user)
    return client.get(reverse("dashboard")).content.decode()


def _centre(code, *, requested):
    centre = CostCenter.objects.create(code=code, name=code, operates_flights=True)
    if requested:
        FlightPermission.objects.create(
            cost_center=centre,
            purpose="photogrammetry",
            status=FlightPermission.STATUS_REQUESTED,
            location="Sector",
            area_type="unpopulated",
            valid_from=TODAY,
            valid_until=TODAY + timedelta(days=30),
        )
    return centre


def _row_class(table, code):
    """La clase del `<tr>` que contiene el código de la faena."""
    row = re.search(rf"<tr([^>]*)>(?:(?!</tr>).)*?{code}", table, re.S)
    assert row, f"no hay fila para {code}"
    return row.group(1)


@pytest.mark.django_db
class TestTheAwaitingRowIsAmber:
    def test_a_site_with_a_request_waiting_is_amber_not_red(self, client, admin_user):
        _centre("CC684", requested=True)
        _centre("CC900", requested=False)

        table = _page(client, admin_user).split("Permisos de vuelo por centro")[-1]

        assert "row-awaiting" in _row_class(table, "CC684")
        assert "row-critical" not in _row_class(table, "CC684")

    def test_a_site_with_nothing_stays_red(self, client, admin_user):
        _centre("CC684", requested=True)
        _centre("CC900", requested=False)

        table = _page(client, admin_user).split("Permisos de vuelo por centro")[-1]

        assert "row-critical" in _row_class(table, "CC900")
        assert "row-awaiting" not in _row_class(table, "CC900")

    def test_it_is_still_counted_as_a_site_without_a_permit(self, client, admin_user):
        """Naranja no es «en regla»: puede volar sólo cuando se apruebe."""
        _centre("CC684", requested=True)
        _page(client, admin_user)

        response = client.get(reverse("dashboard"))

        assert response.context["cost_centres_without_permit"] == 1


class TestTheStyleExists:
    def test_the_amber_row_class_is_in_the_stylesheet_with_its_hover(self):
        """El guardián contra una clase fantasma (`table-warning-subtle`, LV-246)."""
        css = CSS.read_text(encoding="utf-8")

        assert re.search(r"tr\.row-awaiting\s*>\s*td\s*\{", css)
        assert re.search(r"tr\.row-awaiting:hover", css)
        assert "tr.row-awaiting > td:first-child" in css

    def test_it_uses_the_warning_tokens_not_the_critical_ones(self):
        css = CSS.read_text(encoding="utf-8")
        block = css.split("tr.row-awaiting > td {")[1].split("}")[0]

        assert "--sev-warning-bg" in block
        assert "--sev-critical" not in block


@pytest.mark.django_db
class TestTheMenuHidesTwoEntries:
    def test_the_sidebar_has_neither_link(self, client, admin_user):
        client.force_login(admin_user)

        body = client.get(reverse("dashboard")).content.decode()

        assert f'href="{reverse("can-i-fly")}"' not in body
        assert f'href="{reverse("record-list")}"' not in body

    def test_the_other_flight_entries_are_still_there(self, client, admin_user):
        client.force_login(admin_user)

        body = client.get(reverse("dashboard")).content.decode()

        assert f'href="{reverse("permission-list")}"' in body
        assert f'href="{reverse("geo-plan-list")}"' in body

    @pytest.mark.parametrize("name", ["can-i-fly", "record-list"])
    def test_the_screens_themselves_still_work(self, client, admin_user, name):
        """Se oculta el enlace, no la pantalla: la URL sigue respondiendo."""
        client.force_login(admin_user)

        assert client.get(reverse(name)).status_code == 200
