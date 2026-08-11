"""LV-70: geo plan titles frozen with the pre-R2.2 permission repr.

`GeoPlan.title` is denormalised text built from `FlightPermission.__str__` at
import time. The two real plans on production were imported before R2.2/R2.3
gave every permission an `internal_folio`, so they still read
`Solicitado · Fotogrametría - Fotos - Videos · CC861_area_permiso` -- carrying
`purpose` as if it were an identifier, the exact confusion those items removed
everywhere else, and impossible to cross-reference against the permission.
"""

from datetime import date

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command

from apps.geo.models import GeoPlan
from apps.operations.models import FlightPermission
from apps.registry.models import CostCenter


@pytest.fixture
def plan_with_stale_title(db):
    author = User.objects.create_user("importer", password="pw")
    cost_center = CostCenter.objects.create(code="CC861", name="Tranque Talabre")
    permission = FlightPermission.objects.create(
        cost_center=cost_center,
        purpose="photogrammetry",
        valid_from=date(2026, 8, 1),
        valid_until=date(2026, 8, 30),
        location="Talabre",
    )
    plan = GeoPlan.objects.create(
        # Exactly the shape production had: the old status-plus-purpose fallback
        # followed by the source file stem.
        title="Solicitado · Fotogrametría - Fotos - Videos · CC861_area_permiso",
        cost_center=cost_center,
        flight_permission=permission,
        created_by=author,
        status="approved",
    )
    return plan, permission


@pytest.mark.django_db
def test_dry_run_reports_without_changing_anything(plan_with_stale_title, capsys):
    plan, _permission = plan_with_stale_title
    original = plan.title

    call_command("refresh_geoplan_titles")

    plan.refresh_from_db()
    assert plan.title == original
    assert "Would update 1" in capsys.readouterr().out


@pytest.mark.django_db
def test_apply_rebuilds_the_title_from_the_permission(plan_with_stale_title):
    plan, permission = plan_with_stale_title

    call_command("refresh_geoplan_titles", "--apply")

    plan.refresh_from_db()
    # The folio makes the plan cross-referenceable against its permission,
    # which is the whole point of the fix.
    assert plan.title == f"{permission.internal_folio} · CC861_area_permiso"
    assert "Fotogrametría - Fotos - Videos" not in plan.title


@pytest.mark.django_db
def test_the_original_file_stem_survives(plan_with_stale_title):
    """The stem is the only thing distinguishing two plans of one permission
    (the link is 1:N), so it must not be lost in the rewrite."""
    plan, _permission = plan_with_stale_title

    call_command("refresh_geoplan_titles", "--apply")

    plan.refresh_from_db()
    assert plan.title.endswith("· CC861_area_permiso")


@pytest.mark.django_db
def test_rerunning_changes_nothing(plan_with_stale_title, capsys):
    call_command("refresh_geoplan_titles", "--apply")
    capsys.readouterr()

    call_command("refresh_geoplan_titles", "--apply")

    assert "Updated 0" in capsys.readouterr().out


@pytest.mark.django_db
def test_a_plan_without_a_permission_is_left_alone(db, capsys):
    """Nothing to derive a better title from, so it must not be touched."""
    author = User.objects.create_user("importer2", password="pw")
    cost_center = CostCenter.objects.create(code="CC1", name="One")
    plan = GeoPlan.objects.create(
        title="Plan suelto · archivo",
        cost_center=cost_center,
        created_by=author,
        status="draft",
    )

    call_command("refresh_geoplan_titles", "--apply")

    plan.refresh_from_db()
    assert plan.title == "Plan suelto · archivo"
    assert "Updated 0" in capsys.readouterr().out


@pytest.mark.django_db
def test_a_hand_written_title_with_no_separator_is_left_alone(plan_with_stale_title):
    """Without a ' · ' there is no file stem to recover, so rewriting would
    invent one. Leave the human's text as it is."""
    plan, _permission = plan_with_stale_title
    plan.title = "Area de vuelo Talabre"
    plan.save(update_fields=["title"])

    call_command("refresh_geoplan_titles", "--apply")

    plan.refresh_from_db()
    assert plan.title == "Area de vuelo Talabre"
