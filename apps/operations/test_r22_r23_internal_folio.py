"""R2.2/R2.3: every permission gets an annual correlative folio
(JEJ-<year>-<seq>) at creation, never blank -- unlike the DGAC folio
(`permission_number`), which stays optional until approval (LV-39).
`__str__` uses the internal folio, so it cascades into the list, the
calendar, the cost-center fiche and any geo plan title without a
per-screen fix."""

from datetime import date

import pytest
from django.utils import timezone

from apps.registry.models import CostCenter

from .forms import FlightPermissionForm
from .models import FlightPermission


def _cc():
    return CostCenter.objects.create(code="OPS", name="Operations")


def _permission(cost_center, **kwargs):
    kwargs.setdefault("purpose", "Training")
    kwargs.setdefault("valid_from", date(2026, 7, 22))
    kwargs.setdefault("valid_until", kwargs["valid_from"])
    kwargs.setdefault("location", "Santiago")
    return FlightPermission.objects.create(cost_center=cost_center, **kwargs)


@pytest.mark.django_db
def test_internal_folio_is_assigned_at_creation_never_blank():
    permission = _permission(_cc())

    year = timezone.now().year
    assert permission.internal_folio == f"JEJ-{year}-001"


@pytest.mark.django_db
def test_internal_folio_is_a_correlative_that_increments_per_year():
    cc = _cc()
    first = _permission(cc)
    second = _permission(cc)
    third = _permission(cc)

    year = timezone.now().year
    assert first.internal_folio == f"JEJ-{year}-001"
    assert second.internal_folio == f"JEJ-{year}-002"
    assert third.internal_folio == f"JEJ-{year}-003"


@pytest.mark.django_db
def test_internal_folio_is_never_regenerated_on_update():
    permission = _permission(_cc())
    original = permission.internal_folio

    permission.location = "Valparaiso"
    permission.save(update_fields=["location", "updated_at"])

    permission.refresh_from_db()
    assert permission.internal_folio == original


@pytest.mark.django_db
def test_str_uses_the_internal_folio_not_status_and_purpose():
    """R2.3: was `permission_number or f"{status} · {purpose[:30]}"` --
    purpose leaked into the list/calendar/geo-plan titles as a de-facto
    identifier for any permit without a DGAC folio yet."""
    permission = _permission(_cc(), purpose="Audiovisual survey of the coast")

    assert permission.permission_number is None
    assert str(permission) == permission.internal_folio
    assert "Audiovisual" not in str(permission)
    assert "requested" not in str(permission)


@pytest.mark.django_db
def test_internal_folio_is_not_a_form_field():
    """It is assigned by the model, not editable -- offering it on the
    create/edit form would let a typo collide with another permit's folio
    or break the annual correlative sequence."""
    assert "internal_folio" not in FlightPermissionForm.Meta.fields


@pytest.mark.django_db
def test_two_permissions_created_within_the_same_transaction_do_not_collide():
    """The concurrency guard is select_for_update() inside save()'s
    transaction.atomic() (see FlightPermission._next_internal_folio) --
    this pins the sequential, non-colliding outcome that guard exists to
    guarantee."""
    cc = _cc()
    permissions = [_permission(cc) for _ in range(5)]

    folios = [p.internal_folio for p in permissions]
    assert len(set(folios)) == 5
