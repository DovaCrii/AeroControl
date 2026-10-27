"""LV-378 fase 4: sacar una faena de operación avisa de los permisos que deja vivos.

El informe mensual v2 ya separa a las faenas sin operación, pero el permiso de una
faena terminada seguía vivo sin que nadie lo notara al cerrarla (`CC716`). Esto es
el aviso: al guardar la faena como cerrada, «no vuela» o archivada, un mensaje con
los folios y su enlace. **No bloquea y no inventa un estado de permiso**: «cerrar»
se resuelve dejando que venza o archivándolo.
"""

from datetime import date, timedelta

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse
from django.utils import timezone

from apps.core.models import OperationalTenant
from apps.core.testing import login_as
from apps.operations.models import FlightPermission
from apps.registry.models import CostCenter
from apps.registry.selectors import closed_centre_permit_warning, live_permits_of

COMMON = {"purpose": "Survey", "location": "Sitio ficticio"}


def _centre(code="CC901", **kwargs):
    kwargs.setdefault("name", f"Faena {code}")
    kwargs.setdefault("responsible", "Alguien Test")
    return CostCenter.objects.create(code=code, **kwargs)


def _permit(centre, status="approved", days=30, **kwargs):
    today = timezone.localdate()
    kwargs.setdefault("valid_from", today - timedelta(days=10))
    kwargs.setdefault("valid_until", today + timedelta(days=days))
    return FlightPermission.objects.create(
        cost_center=centre,
        status=status,
        permission_number=f"P-378-{FlightPermission.objects.count()}",
        **COMMON,
        **kwargs,
    )


def _post_update(client, centre, **overrides):
    data = {
        "code": centre.code,
        "name": centre.name,
        "contract_status": centre.contract_status,
        "responsible": "Alguien Test",
        "responsible_type": "administrator",
        "notes": "",
    }
    if centre.operates_flights:
        data["operates_flights"] = "on"
    data.update(overrides)
    for key in [k for k, v in data.items() if v is None]:
        del data[key]
    return client.post(reverse("costcenter-update", args=[centre.pk]), data)


def _warnings(response):
    return [
        str(m) for m in get_messages(response.wsgi_request) if m.level_tag == "warning"
    ]


UPDATE_PERMS = ("change_costcenter", "view_costcenter", "view_flightpermission")


@pytest.mark.django_db
class TestUpdateWarning:
    def test_closing_the_contract_lists_the_live_permits_with_links(self):
        centre = _centre()
        approved = _permit(centre)
        requested = _permit(centre, status="requested", valid_until=None)

        response = _post_update(
            login_as(*UPDATE_PERMS), centre, contract_status="closed"
        )

        assert response.status_code == 302
        centre.refresh_from_db()
        assert centre.contract_status == "closed"  # no bloquea
        (warning,) = _warnings(response)
        for permit in (approved, requested):
            assert permit.internal_folio in warning
            assert reverse("permission-detail", args=[permit.pk]) in warning
        # y no inventa estado: los permisos quedan como estaban
        approved.refresh_from_db()
        assert approved.status == "approved"

    def test_marking_it_as_not_flying_warns_too(self):
        centre = _centre("CC902")
        permit = _permit(centre)

        response = _post_update(login_as(*UPDATE_PERMS), centre, operates_flights=None)

        (warning,) = _warnings(response)
        assert permit.internal_folio in warning

    def test_no_live_permit_no_warning(self):
        """Vencido, denegado o archivado no es «vivo»."""
        centre = _centre("CC903")
        _permit(centre, days=-3)
        _permit(centre, status="denied")
        _permit(centre, status="expired")
        archived = _permit(centre)
        archived.is_active = False
        archived.save()

        response = _post_update(
            login_as(*UPDATE_PERMS), centre, contract_status="closed"
        )

        assert _warnings(response) == []

    def test_an_edit_that_keeps_it_operating_does_not_warn(self):
        centre = _centre("CC904")
        _permit(centre)

        response = _post_update(login_as(*UPDATE_PERMS), centre, name="Otro nombre")

        assert _warnings(response) == []

    def test_an_already_closed_centre_does_not_warn_again_on_every_edit(self):
        centre = _centre("CC905", contract_status="closed")
        _permit(centre)

        response = _post_update(login_as(*UPDATE_PERMS), centre, name="Otro nombre")

        assert _warnings(response) == []

    def test_without_view_flightpermission_nothing_is_disclosed(self):
        centre = _centre("CC906")
        permit = _permit(centre)

        response = _post_update(
            login_as("change_costcenter", "view_costcenter"),
            centre,
            contract_status="closed",
        )

        assert response.status_code == 302  # el guardado sí ocurre
        assert _warnings(response) == []
        assert permit.internal_folio not in str(
            [str(m) for m in get_messages(response.wsgi_request)]
        )

    def test_without_change_permission_it_is_403(self):
        centre = _centre("CC907")
        _permit(centre)

        response = _post_update(
            login_as("view_costcenter", "view_flightpermission"),
            centre,
            contract_status="closed",
        )

        assert response.status_code == 403
        centre.refresh_from_db()
        assert centre.contract_status == "active"


@pytest.mark.django_db
class TestArchiveWarning:
    def test_archiving_lists_the_live_permits(self):
        centre = _centre("CC908")
        permit = _permit(centre)

        client = login_as(
            "delete_costcenter", "view_costcenter", "view_flightpermission"
        )
        response = client.post(reverse("costcenter-archive", args=[centre.pk]))

        assert response.status_code == 302
        centre.refresh_from_db()
        assert centre.is_active is False
        (warning,) = _warnings(response)
        assert permit.internal_folio in warning
        assert reverse("permission-detail", args=[permit.pk]) in warning

    def test_archiving_without_live_permits_does_not_warn(self):
        centre = _centre("CC909")

        client = login_as(
            "delete_costcenter", "view_costcenter", "view_flightpermission"
        )
        response = client.post(reverse("costcenter-archive", args=[centre.pk]))

        assert _warnings(response) == []

    def test_without_delete_permission_it_is_403(self):
        centre = _centre("CC910")
        _permit(centre)

        client = login_as("view_costcenter", "view_flightpermission")
        response = client.post(reverse("costcenter-archive", args=[centre.pk]))

        assert response.status_code == 403
        centre.refresh_from_db()
        assert centre.is_active is True


@pytest.mark.django_db
class TestTenantIsolation:
    def test_permits_of_another_tenant_are_never_listed(self):
        mine = OperationalTenant.objects.create(name="Mine", slug="mine-378")
        theirs = OperationalTenant.objects.create(name="Theirs", slug="theirs-378")
        centre = _centre("CC911", tenant=theirs)
        _permit(centre)
        client = login_as(*UPDATE_PERMS, member_of=mine)

        assert not live_permits_of(centre, client.user).exists()
        assert closed_centre_permit_warning(centre, client.user) is None

    def test_a_centre_of_another_tenant_cannot_be_edited(self):
        mine = OperationalTenant.objects.create(name="Mine", slug="mine-378b")
        theirs = OperationalTenant.objects.create(name="Theirs", slug="theirs-378b")
        centre = _centre("CC912", tenant=theirs)
        _permit(centre)

        response = _post_update(
            login_as(*UPDATE_PERMS, member_of=mine), centre, contract_status="closed"
        )

        assert response.status_code == 404
        centre.refresh_from_db()
        assert centre.contract_status == "active"

    def test_own_tenant_is_listed(self):
        mine = OperationalTenant.objects.create(name="Mine", slug="mine-378c")
        centre = _centre("CC913", tenant=mine)
        permit = _permit(centre)
        client = login_as(*UPDATE_PERMS, member_of=mine)

        assert list(live_permits_of(centre, client.user)) == [permit]


@pytest.mark.django_db
def test_the_live_window_is_today_inclusive():
    centre = _centre("CC914")
    today = date(2026, 6, 15)
    ends_today = _permit(centre, valid_until=today, valid_from=today - timedelta(5))
    _permit(centre, valid_until=today - timedelta(1), valid_from=today - timedelta(9))
    client = login_as(*UPDATE_PERMS)

    assert list(live_permits_of(centre, client.user, today=today)) == [ends_today]
