"""LV-441: la lista prevuelo del REG-016 Rev. 2 (sección 4) se siembra completa
y de forma idempotente, con los ítems críticos (★) como obligatorios."""

import pytest
from django.core.management import call_command

from apps.operations.management.commands.seed_reg016_checklist import CHECKLIST_NAME
from apps.operations.models import PreflightChecklist, PreflightChecklistItem
from apps.registry.models import Aircraft, CostCenter

NON_CRITICAL = {17}


@pytest.fixture
def seeded(db):
    call_command("seed_reg016_checklist")
    return PreflightChecklist.objects.get(name=CHECKLIST_NAME)


def test_seed_creates_17_items_and_is_idempotent(seeded):
    call_command("seed_reg016_checklist")
    assert PreflightChecklist.objects.filter(name=CHECKLIST_NAME).count() == 1
    assert seeded.items.count() == 17
    assert [i.order for i in seeded.items.all()] == list(range(1, 18))


def test_only_the_critical_items_are_required(seeded):
    required = {i.order for i in seeded.items.all() if i.is_required}
    assert required == set(range(1, 18)) - NON_CRITICAL
    assert len(required) == 16


def test_rerun_does_not_overwrite_an_edited_item(seeded):
    item = seeded.items.get(order=2)
    item.text = "Texto editado"
    item.save()
    call_command("seed_reg016_checklist")
    assert PreflightChecklistItem.objects.get(pk=item.pk).text == "Texto editado"
    assert seeded.items.count() == 17


def test_seeded_list_applies_to_any_aircraft_and_is_served_by_the_view(seeded):
    centre = CostCenter.objects.create(code="CC1", name="X", operates_flights=True)
    aircraft = Aircraft.objects.create(
        registration="RPA-1",
        type="RPA",
        model="Mavic 3 Enterprise",
        manufacturer="DJI",
        cost_center=centre,
    )
    assert PreflightChecklist.for_aircraft(aircraft) == seeded
    assert seeded.keyword_list() == []
