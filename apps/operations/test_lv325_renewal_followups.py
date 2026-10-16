"""LV-325: renovar un permiso con la misma área (PR 2).

Tres seguimientos de `LV-320`, que dejó la renovación creada pero el resto de la
aplicación sin enterarse:

- la **lista de planes** no marca en rojo «Permiso vencido» a un plan cuyo permiso
  ya fue renovado: muestra un chip neutro «Renovado → PG-…»;
- la **lista de permisos** ofrece «Renovar» en la fila, con las condiciones de la
  ficha;
- al **crear** la renovación se cierran los avisos de vencimiento (T-45 y T-30)
  del permiso anterior, con el folio de la renovación como motivo.
"""

import pytest
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext

from apps.compliance.models import Alert, AlertRule
from apps.core.testing import login_as
from apps.geo.models import GeoPlan
from apps.operations.models import FlightPermission

from . import test_lv320_renew_permit as lv320

ADD, TODAY, _post, _url = lv320.ADD, lv320.TODAY, lv320._post, lv320._url
# Las fixtures de LV-320 se reexponen por nombre: pytest las registra aquí.
author, cost_center, plan, previous = (
    lv320.author,
    lv320.cost_center,
    lv320.plan,
    lv320.previous,
)

DAY = timezone.timedelta(days=1)


def _lapse(permit):
    """Deja el permiso vencido por fecha, sin pasar por el trabajo nocturno."""
    FlightPermission.objects.filter(pk=permit.pk).update(valid_until=TODAY - DAY)
    permit.refresh_from_db()


def _plan_page(client):
    return client.get(reverse("geo-plan-list")).content.decode()


def _rule(name, days, field="valid_until"):
    return AlertRule.objects.create(
        name=name,
        entity_type="operations.flightpermission",
        field_to_watch=field,
        days_before_expiry=days,
    )


def _alert(rule, permit):
    return Alert.objects.create(
        alert_rule=rule,
        content_type=ContentType.objects.get_for_model(FlightPermission),
        object_id=permit.pk,
        message="aviso",
        watched_value=str(permit.valid_until),
    )


@pytest.mark.django_db
class TestThePlanListDoesNotShoutAboutARenewedPermit:
    def test_a_renewed_plan_shows_the_chip_and_not_the_red_lapse(self, previous, plan):
        login_as(*ADD).post(_url(previous), _post(previous))
        copy = plan.copies.get()
        _lapse(previous)

        html = _plan_page(login_as("view_geoplan"))

        assert "id-chip--neutral" in html
        assert f"→ {copy.folio}" in html
        assert "Permit lapsed" not in html and "Permiso vencido" not in html

    def test_a_lapsed_plan_without_a_copy_stays_red(self, previous, plan):
        _lapse(previous)

        html = _plan_page(login_as("view_geoplan"))

        assert "sev-critical" in html
        assert "id-chip--neutral" not in html

    def test_a_dead_renewal_does_not_hide_the_lapse(self, previous, plan):
        """La copia cuyo permiso fue rechazado no renovó nada: el rojo sigue."""
        login_as(*ADD).post(_url(previous), _post(previous))
        new = FlightPermission.objects.exclude(pk=previous.pk).get()
        FlightPermission.objects.filter(pk=new.pk).update(status="denied")
        _lapse(previous)

        html = _plan_page(login_as("view_geoplan"))

        assert "id-chip--neutral" not in html
        assert "sev-critical" in html

    def test_it_costs_the_same_with_one_renewal_or_four(self, previous, plan, author):
        login_as(*ADD).post(_url(previous), _post(previous))
        _lapse(previous)
        client = login_as("view_geoplan")
        with CaptureQueriesContext(connection) as one:
            _plan_page(client)

        for n in range(3):
            permit = FlightPermission.objects.create(
                cost_center=previous.cost_center,
                purpose="photogrammetry",
                location=f"Otra {n}",
                area_type="unpopulated",
                status="approved",
                valid_from=TODAY - 60 * DAY,
                valid_until=TODAY - DAY,
            )
            old = GeoPlan.objects.create(
                title=f"P{n}",
                cost_center=previous.cost_center,
                created_by=author,
                flight_permission=permit,
            )
            GeoPlan.objects.create(
                title=f"P{n}",
                cost_center=previous.cost_center,
                created_by=author,
                copied_from=old,
                flight_permission=previous.renewals.first(),
            )
        with CaptureQueriesContext(connection) as four:
            html = _plan_page(client)

        assert html.count("id-chip--neutral") == 4
        assert len(four) == len(one)


@pytest.mark.django_db
class TestTheRenewButtonInThePermitList:
    def _list(self, client):
        return client.get(reverse("permission-list")).content.decode()

    def test_it_shows_with_both_permissions(self, previous, plan):
        html = self._list(login_as(*ADD))
        assert f"?renueva={previous.pk}" in html

    def test_it_is_hidden_without_add_geoplan(self, previous, plan):
        client = login_as("add_flightpermission", "view_flightpermission")
        assert "?renueva=" not in self._list(client)

    def test_it_is_hidden_without_add_flightpermission(self, previous, plan):
        client = login_as("add_geoplan", "view_flightpermission")
        assert "?renueva=" not in self._list(client)

    def test_it_is_hidden_once_the_permit_has_a_renewal(self, previous, plan):
        client = login_as(*ADD)
        client.post(_url(previous), _post(previous))
        html = self._list(client)
        # El anterior ya tiene sucesor; la renovación (solicitada) no es renovable.
        assert "?renueva=" not in html

    def test_it_is_hidden_for_a_permit_that_cannot_be_renewed(self, previous, plan):
        FlightPermission.objects.filter(pk=previous.pk).update(status="requested")
        assert "?renueva=" not in self._list(login_as(*ADD))

    def test_the_view_still_refuses_without_permission(self, previous, plan):
        client = login_as("add_flightpermission", "view_flightpermission")
        assert client.get(_url(previous)).status_code == 403


@pytest.mark.django_db
class TestStartingTheRenewalClosesTheNotices:
    def test_the_t45_and_t30_notices_of_the_previous_permit_are_closed(
        self, previous, plan
    ):
        t45 = _alert(_rule("T-45", 45), previous)
        t30 = _alert(_rule("T-30", 30), previous)

        login_as(*ADD).post(_url(previous), _post(previous))
        new = FlightPermission.objects.exclude(pk=previous.pk).get()

        for alert in (t45, t30):
            alert.refresh_from_db()
            assert alert.is_resolved
            assert alert.resolution_reason == gettext("Renewal started: %(folio)s") % {
                "folio": new.internal_folio
            }

    def test_other_alerts_are_left_alone(self, previous, plan):
        other = FlightPermission.objects.create(
            cost_center=previous.cost_center,
            purpose="photogrammetry",
            location="Otro",
            area_type="unpopulated",
            status="approved",
            valid_from=TODAY,
            valid_until=TODAY + 30 * DAY,
        )
        rule = _rule("T-30", 30)
        theirs = _alert(rule, other)
        not_expiry = _alert(_rule("Estado", 0, field="status"), previous)

        login_as(*ADD).post(_url(previous), _post(previous))

        theirs.refresh_from_db()
        not_expiry.refresh_from_db()
        assert not theirs.is_resolved
        assert not not_expiry.is_resolved

    def test_a_rejected_form_closes_nothing(self, previous, plan):
        alert = _alert(_rule("T-30", 30), previous)

        client = login_as(*ADD)
        response = client.post(_url(previous), _post(previous, purpose=""))

        assert response.status_code == 200
        alert.refresh_from_db()
        assert not alert.is_resolved
