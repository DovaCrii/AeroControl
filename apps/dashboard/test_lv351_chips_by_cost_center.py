"""LV-351: los chips de «Requiere atención» enlazan a listas que respetan la faena.

Con una faena elegida en el panel, la cifra de «Mantenciones por definir» y la de
«Solicitudes en SIGO» es de **esa** faena, pero el enlace llevaba a una lista de
todas: el chip decía 1 y la lista, 3. La garantía de `LV-310` (cifra == total de la
lista a la que enlaza) se afirma ahora con y sin faena elegida.
"""

import pytest
from django.urls import reverse

from apps.core.models import OperationalTenant
from apps.core.testing import login_as
from apps.dashboard.test_lv310_panel_attention import (
    _aircraft,
    _chips,
    _record,
    _request,
)
from apps.registry.models import CostCenter


@pytest.fixture
def two_sites(db):
    mine = CostCenter.objects.create(code="CC900", name="Mía")
    other = CostCenter.objects.create(code="CC901", name="Otra")
    _record(_aircraft("RPA-1", mine), kind="to_be_defined")
    _record(_aircraft("RPA-2", other), kind="to_be_defined")
    _record(_aircraft("RPA-3", other), scheduled=None)
    _request(mine, "Mía uno")
    _request(other, "Otra uno")
    _request(other, "Otra dos")
    return mine, other


@pytest.mark.django_db
class TestTheChipFigureEqualsTheListItLinksTo:
    @pytest.mark.parametrize("key", ["maintenance_to_define", "awaiting_sigo"])
    @pytest.mark.parametrize("chosen", [None, "mine", "other"])
    def test_with_and_without_a_chosen_cost_centre(
        self, admin_client, two_sites, key, chosen
    ):
        params = (
            {"cost_center": dict(zip(("mine", "other"), two_sites))[chosen].pk}
            if chosen
            else {"cost_center": ""}
        )
        response = admin_client.get(reverse("dashboard"), params)

        chip = _chips(response)[key]
        listed = admin_client.get(chip["url"])

        assert listed.status_code == 200
        assert chip["count"] == listed.context["paginator"].count
        if chosen:
            assert (
                str(dict(zip(("mine", "other"), two_sites))[chosen].pk) in chip["url"]
            )
        else:
            assert "cost_center" not in chip["url"]

    def test_the_figures_really_differ_per_site(self, admin_client, two_sites):
        """Sin esto la prueba de arriba pasaría con datos iguales en todas partes."""
        mine, other = two_sites
        counts = {
            site: _chips(admin_client.get(reverse("dashboard"), {"cost_center": pk}))[
                "awaiting_sigo"
            ]["count"]
            for site, pk in (("mine", mine.pk), ("other", other.pk))
        }
        assert counts == {"mine": 1, "other": 2}


@pytest.mark.django_db
class TestTheListsAcceptTheFilter:
    def test_the_active_filter_is_named_and_removable(self, admin_client, two_sites):
        mine, _other = two_sites
        for name in ("flight-request-list", "maintenance-list"):
            response = admin_client.get(reverse(name), {"cost_center": mine.pk})
            content = response.content.decode()

            assert response.context["is_filtered"] is True
            assert 'data-active-filter="cost_center"' in content
            assert "CC900 - Mía" in content
            assert response.context["cost_center_filter"]["clear_url"] == reverse(name)

    def test_removing_the_filter_keeps_the_rest_of_the_query(
        self, admin_client, two_sites
    ):
        mine, _other = two_sites
        response = admin_client.get(
            reverse("flight-request-list"),
            {"cost_center": mine.pk, "status": "filed", "page": 1},
        )
        assert response.context["cost_center_filter"]["clear_url"].endswith(
            "?status=filed"
        )

    def test_a_malformed_value_is_an_empty_list_not_a_500(
        self, admin_client, two_sites
    ):
        for name in ("flight-request-list", "maintenance-list"):
            response = admin_client.get(reverse(name), {"cost_center": "abc"})

            assert response.status_code == 200
            assert response.context["paginator"].count == 0
            assert response.context["cost_center_filter"]["name"] is None

    def test_another_tenants_cost_centre_is_empty_and_unnamed(self, two_sites):
        foreign_tenant = OperationalTenant.objects.create(name="Otra", slug="otra")
        foreign = CostCenter.objects.create(
            code="CC777", name="Ajena", tenant=foreign_tenant
        )
        _request(foreign, "Ajena uno")
        _record(_aircraft("RPA-9", foreign), kind="to_be_defined")
        client = login_as("view_flightrequest", "view_maintenancerecord")

        for name in ("flight-request-list", "maintenance-list"):
            response = client.get(reverse(name), {"cost_center": foreign.pk})
            content = response.content.decode()

            assert response.status_code == 200
            assert response.context["paginator"].count == 0
            assert "CC777" not in content
            assert "Ajena" not in content

    @pytest.mark.parametrize("name", ["flight-request-list", "maintenance-list"])
    def test_the_read_permission_still_applies(self, two_sites, name):
        mine, _other = two_sites
        client = login_as("view_aircraft")

        response = client.get(reverse(name), {"cost_center": mine.pk})

        assert response.status_code == 403
