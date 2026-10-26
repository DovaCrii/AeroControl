"""LV-376 (fase 1a): «Nuevo permiso» con la faena precargada (`?cost_center=<pk>`).

El enlace sale de la fila de la faena en Cumplimiento. Se precarga SOLO lo que el formulario ofrece:
una faena de otra empresa, archivada, inexistente o un valor que no es UUID se ignora sin error.
"""

from uuid import uuid4

import pytest
from django.urls import reverse

from apps.core.models import OperationalTenant
from apps.core.testing import login_as
from apps.operations.test_lv320_renew_permit import (  # noqa: F401
    cost_center,
    previous,
)
from apps.registry.models import CostCenter

URL = "permission-create"


def _initial(response):
    return response.context["form"].initial.get("cost_center")


@pytest.fixture
def centre(db):
    return CostCenter.objects.create(code="CC376", name="Faena ficticia")


@pytest.mark.django_db
def test_the_faena_is_preselected(centre):
    client = login_as("add_flightpermission")
    response = client.get(reverse(URL), {"cost_center": str(centre.pk)})
    assert response.status_code == 200
    assert _initial(response) == centre.pk
    assert f'<option value="{centre.pk}" selected>' in response.content.decode()


@pytest.mark.django_db
def test_without_the_parameter_the_form_is_blank(centre):
    response = login_as("add_flightpermission").get(reverse(URL))
    assert response.status_code == 200
    assert _initial(response) is None


@pytest.mark.django_db
@pytest.mark.parametrize(
    "raw", ["no-es-uuid", "", "00000000-0000-0000-0000-000000000000"]
)
def test_garbage_or_unknown_ids_are_ignored_without_error(centre, raw):
    response = login_as("add_flightpermission").get(reverse(URL), {"cost_center": raw})
    assert response.status_code == 200
    assert _initial(response) is None


@pytest.mark.django_db
def test_a_random_uuid_is_ignored(centre):
    response = login_as("add_flightpermission").get(
        reverse(URL), {"cost_center": str(uuid4())}
    )
    assert response.status_code == 200 and _initial(response) is None


@pytest.mark.django_db
def test_an_archived_faena_is_not_preselected(centre):
    CostCenter.objects.filter(pk=centre.pk).update(is_active=False)
    response = login_as("add_flightpermission").get(
        reverse(URL), {"cost_center": str(centre.pk)}
    )
    assert response.status_code == 200 and _initial(response) is None


@pytest.mark.django_db
def test_a_faena_of_another_company_is_ignored():
    mine = OperationalTenant.objects.create(name="Mía", slug="mia")
    other = OperationalTenant.objects.create(name="Ajena", slug="ajena")
    own = CostCenter.objects.create(code="OWN", name="Propia", tenant=mine)
    foreign = CostCenter.objects.create(code="FOR", name="Ajena", tenant=other)
    client = login_as("add_flightpermission", member_of=mine)
    assert _initial(client.get(reverse(URL), {"cost_center": str(own.pk)})) == own.pk
    response = client.get(reverse(URL), {"cost_center": str(foreign.pk)})
    assert response.status_code == 200
    assert _initial(response) is None
    assert f'<option value="{foreign.pk}" selected>' not in response.content.decode()


@pytest.mark.django_db
def test_without_add_flightpermission_it_is_still_403(centre):
    client = login_as("view_flightpermission")
    response = client.get(reverse(URL), {"cost_center": str(centre.pk)})
    assert response.status_code == 403


@pytest.mark.django_db
def test_a_renewal_keeps_the_faena_of_the_permit_it_renews(previous, centre):  # noqa: F811
    client = login_as("add_flightpermission", "add_geoplan", "view_flightpermission")
    url = f"{reverse(URL)}?renueva={previous.pk}&cost_center={centre.pk}"
    response = client.get(url)
    assert response.status_code == 200
    assert _initial(response) == previous.cost_center_id
