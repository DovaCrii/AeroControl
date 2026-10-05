"""LV-266: una faena cerrada o sin operación no entra en los registros.

Regla del usuario el 2026-10-05, al cerrar el informe de septiembre: *«al estar
como sin vuelo u operación no entra en los registros»*. Estaba escrita tres veces y
distinta: la cobertura y el cierre mensual excluían las cerradas, «¿Puedo volar?»
sólo las que no vuelan, y el resumen de vencimientos ninguna — así que seguía
escribiéndole a `CC716`, cerrada y con un permiso vivo, mientras el informe ya no
la contaba.
"""

from datetime import date

import pytest
from django.urls import reverse

from apps.compliance.digest import cost_centers_to_notify
from apps.compliance.kpis import permit_status_by_cost_center
from apps.registry.models import CostCenter
from apps.registry.selectors import operating_cost_centers

TODAY = date(2026, 9, 15)
pytestmark = pytest.mark.django_db


def _centre(code, **fields):
    return CostCenter.objects.create(code=code, name=code, **fields)


@pytest.fixture
def centres():
    return {
        "open": _centre("CC1"),
        "closed": _centre("CC716", contract_status=CostCenter.CONTRACT_CLOSED),
        "no_flights": _centre("CC110", operates_flights=False),
        "archived": _centre("CC9", is_active=False),
    }


class TestTheOneDefinition:
    def test_only_an_active_flying_open_centre_enters(self, centres):
        assert list(operating_cost_centers()) == [centres["open"]]

    def test_the_permit_coverage_uses_it(self, centres):
        rows = permit_status_by_cost_center(TODAY)
        assert [row["cost_center"] for row in rows] == [centres["open"]]

    def test_the_monthly_close_uses_it(self, centres, admin_client):
        response = admin_client.get(reverse("monthly-review"), {"month": "2026-08"})
        listed = [row["cost_center"] for row in response.context["rows"]]
        assert listed == [centres["open"]]

    def test_can_i_fly_offers_only_those_that_operate(self, centres, admin_client):
        response = admin_client.get(reverse("can-i-fly"))
        assert list(response.context["rosters"]["cost_center"]) == [centres["open"]]


class TestTheDigest:
    def test_a_closed_centre_is_not_written_to(self, centres):
        assert centres["closed"] not in cost_centers_to_notify()

    def test_a_centre_that_does_not_fly_still_is(self, centres):
        """Administra equipos: sus vencimientos (seguros, mantenciones) siguen
        siendo de alguien. La regla de «sin operación» no los silencia."""
        assert centres["no_flights"] in cost_centers_to_notify()
        assert centres["open"] in cost_centers_to_notify()
