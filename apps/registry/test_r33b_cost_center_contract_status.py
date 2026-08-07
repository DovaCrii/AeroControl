"""R3.3(b): a cost center whose client contract ended is not an error or a
duplicate -- the two things `is_active` (AGENTS.md soft delete) already
covers. `contract_status` is a separate axis: closed cost centers keep
showing on the normal list (greyed, grouped after the active ones), not
archived away."""

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from apps.registry.forms import CostCenterForm
from apps.registry.models import CostCenter


@pytest.fixture
def admin_client(db):
    User.objects.create_superuser("admin", "admin@test.com", "password")
    client = Client()
    assert client.login(username="admin", password="password")
    return client


@pytest.mark.django_db
def test_cost_center_defaults_to_an_active_contract():
    cc = CostCenter.objects.create(code="CC1")

    assert cc.contract_status == "active"


@pytest.mark.django_db
def test_cost_center_form_defaults_to_active_when_omitted():
    """Closing a contract is an occasional action on an existing record, not
    a fact every cost center needs on creation -- unlike an unrequired
    ChoiceField's ordinary behaviour, an omitted value must not save as ""
    (which would not match any choice and render as blank in the list)."""
    form = CostCenterForm(
        data={
            "code": "CC1",
            "name": "",
            "responsible": "Someone",
            "responsible_type": "administrator",
        }
    )

    assert form.is_valid(), form.errors
    assert form.save().contract_status == "active"


@pytest.mark.django_db
def test_cost_center_form_accepts_a_closed_contract():
    form = CostCenterForm(
        data={
            "code": "CC1",
            "name": "",
            "contract_status": "closed",
            "responsible": "Someone",
            "responsible_type": "administrator",
        }
    )

    assert form.is_valid(), form.errors
    assert form.save().contract_status == "closed"


@pytest.mark.django_db
def test_closed_cost_centers_are_marked_and_grouped_after_active_ones(
    admin_client,
):
    # "CC2" would otherwise sort before "CC110" (R3.2) -- closed status
    # takes priority over that so it does not interleave with active rows.
    CostCenter.objects.create(code="CC2", contract_status="closed")
    CostCenter.objects.create(code="CC110", contract_status="active")

    response = admin_client.get(reverse("costcenter-list"))
    content = response.content.decode()

    codes = [cc.code for cc in response.context["objects"]]
    assert codes == ["CC110", "CC2"]
    assert "Cerrado" in content  # LANGUAGE_CODE="es" -- runtime default


@pytest.mark.django_db
def test_cost_center_detail_shows_the_contract_status(admin_client):
    cc = CostCenter.objects.create(code="CC1", contract_status="closed")

    content = admin_client.get(
        reverse("costcenter-detail", args=[cc.pk])
    ).content.decode()

    assert "Cerrado" in content
