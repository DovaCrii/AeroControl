from datetime import date

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.compliance.models import Document, DocumentType
from apps.core.models import AuditEvent
from apps.operations.models import FlightPermission
from apps.registry.merge import (
    find_duplicate_groups,
    merge_operators,
    normalize_name,
    suggest_canonical,
)
from apps.registry.models import Aircraft, CostCenter, Operator, Qualification


@pytest.fixture
def cost_center(db):
    return CostCenter.objects.create(code="FAENA-01", name="Faena Norte")


def _operator(cost_center, employee_id, full_name, **extra):
    return Operator.objects.create(
        employee_id=employee_id, full_name=full_name, cost_center=cost_center, **extra
    )


def test_normalize_name_ignores_case_accents_and_spacing():
    assert normalize_name("MARÍA  González") == "maria gonzalez"
    assert normalize_name("maria gonzalez") == "maria gonzalez"


@pytest.mark.django_db
def test_groups_only_names_held_by_more_than_one_operator(cost_center):
    _operator(cost_center, "OP-1", "Maria Gonzalez")
    _operator(cost_center, "OP-2", "MARÍA  GONZÁLEZ")
    _operator(cost_center, "OP-3", "Carlos Rojas")

    groups = find_duplicate_groups()

    assert [group["key"] for group in groups] == ["maria-gonzalez"]
    assert len(groups[0]["operators"]) == 2


@pytest.mark.django_db
def test_report_lists_field_by_field_differences(cost_center):
    _operator(cost_center, "OP-1", "Maria Gonzalez", email="maria@test.local")
    _operator(cost_center, "OP-2", "Maria Gonzalez", phone="+56 9 1111 1111")

    differences = find_duplicate_groups()[0]["differences"]

    assert set(differences) == {"employee_id", "email", "phone"}
    assert "maria@test.local" in differences["email"]
    # full_name is normalised to the same person, so it is not a difference
    assert "full_name" not in differences


@pytest.mark.django_db
def test_suggested_record_is_the_one_other_records_point_at(cost_center):
    referenced = _operator(cost_center, "OP-1", "Maria Gonzalez")
    # The other record has more fields filled in but nothing points at it
    thin = _operator(
        cost_center,
        "OP-2",
        "Maria Gonzalez",
        email="m@test.local",
        phone="+56 9 1111 1111",
        rut="11.111.111-1",
    )
    Qualification.objects.create(
        operator=referenced,
        qualification_type="Credencial",
        issue_date=date(2026, 1, 1),
    )
    cost_center.responsible_operator = referenced
    cost_center.save(update_fields=["responsible_operator"])

    assert suggest_canonical([referenced, thin]).pk == referenced.pk


@pytest.mark.django_db
def test_merge_moves_every_fk_reference_and_archives_the_duplicate(cost_center):
    canonical = _operator(cost_center, "OP-1", "Maria Gonzalez")
    duplicate = _operator(cost_center, "OP-2", "Maria Gonzalez")
    aircraft = Aircraft.objects.create(
        registration="CC-AAA",
        type="Multirotor",
        model="M300",
        manufacturer="DJI",
        cost_center=cost_center,
    )
    qualification = Qualification.objects.create(
        operator=duplicate, qualification_type="Credencial", issue_date=date(2026, 1, 1)
    )
    permission = FlightPermission.objects.create(
        permission_number="PERM-1",
        cost_center=cost_center,
        purpose="Training",
        valid_from=date(2026, 7, 22),
        valid_until=date(2026, 7, 22),
        location="Santiago",
    )
    permission.operators.add(duplicate)
    permission.aircraft_fleet.add(aircraft)
    other_cc = CostCenter.objects.create(code="OTRA", name="Otra")
    other_cc.responsible_operator = duplicate
    other_cc.save(update_fields=["responsible_operator"])

    result = merge_operators(canonical, [duplicate])

    qualification.refresh_from_db()
    other_cc.refresh_from_db()
    duplicate.refresh_from_db()
    assert qualification.operator_id == canonical.pk
    # OPS-4: operators is now M2M -- the merge must swap membership, not
    # update a FK column that no longer exists.
    assert permission.operators.filter(pk=canonical.pk).exists()
    assert not permission.operators.filter(pk=duplicate.pk).exists()
    assert other_cc.responsible_operator_id == canonical.pk
    # Archived, never deleted
    assert duplicate.is_active is False
    assert Operator.objects.filter(pk=duplicate.pk).exists()
    assert "OP-1" in duplicate.notes
    assert result["archived"] == ["OP-2"]


@pytest.mark.django_db
def test_merge_moves_generic_foreign_key_references(cost_center):
    canonical = _operator(cost_center, "OP-1", "Maria Gonzalez")
    duplicate = _operator(cost_center, "OP-2", "Maria Gonzalez")
    doc_type = DocumentType.objects.create(code="lic", name="Licencia")
    operator_ct = ContentType.objects.get_for_model(Operator)
    document = Document.objects.create(
        title="Licencia",
        doc_type=doc_type,
        content_type=operator_ct,
        object_id=duplicate.pk,
        file_path="lic/op.pdf",
        issue_date=date(2026, 1, 1),
    )

    merge_operators(canonical, [duplicate])

    document.refresh_from_db()
    # Documents attach through a generic FK, which no FK walk would have caught
    assert document.object_id == canonical.pk


@pytest.mark.django_db
def test_merge_records_an_audit_event(cost_center):
    canonical = _operator(cost_center, "OP-1", "Maria Gonzalez")
    duplicate = _operator(cost_center, "OP-2", "Maria Gonzalez")

    merge_operators(canonical, [duplicate])

    event = AuditEvent.objects.get(action="operator_merged")
    assert event.metadata["merged_employee_id"] == "OP-2"
    assert event.metadata["canonical_employee_id"] == "OP-1"


@pytest.mark.django_db
def test_command_reports_without_changing_anything(cost_center, capsys):
    _operator(cost_center, "OP-1", "Maria Gonzalez")
    _operator(cost_center, "OP-2", "Maria Gonzalez")

    call_command("find_duplicate_operators")

    out = capsys.readouterr().out
    assert "maria-gonzalez" in out
    assert Operator.objects.filter(is_active=True).count() == 2


@pytest.mark.django_db
def test_apply_without_group_is_refused(cost_center):
    _operator(cost_center, "OP-1", "Maria Gonzalez")
    _operator(cost_center, "OP-2", "Maria Gonzalez")

    with pytest.raises(CommandError, match="requires --group"):
        call_command("find_duplicate_operators", "--apply")

    assert Operator.objects.filter(is_active=True).count() == 2


@pytest.mark.django_db
def test_apply_with_unknown_group_is_refused(cost_center):
    _operator(cost_center, "OP-1", "Maria Gonzalez")
    _operator(cost_center, "OP-2", "Maria Gonzalez")

    with pytest.raises(CommandError, match="No duplicate group"):
        call_command("find_duplicate_operators", "--apply", "--group", "nope")


@pytest.mark.django_db
def test_into_lets_the_operator_override_the_suggestion(cost_center):
    _operator(cost_center, "OP-1", "Maria Gonzalez", email="a@test.local")
    chosen = _operator(cost_center, "OP-2", "Maria Gonzalez")

    call_command(
        "find_duplicate_operators",
        "--apply",
        "--group",
        "maria-gonzalez",
        "--into",
        "OP-2",
    )

    chosen.refresh_from_db()
    assert chosen.is_active is True
    assert Operator.objects.get(employee_id="OP-1").is_active is False


@pytest.mark.django_db
def test_into_outside_the_group_is_refused(cost_center):
    _operator(cost_center, "OP-1", "Maria Gonzalez")
    _operator(cost_center, "OP-2", "Maria Gonzalez")
    _operator(cost_center, "OP-9", "Carlos Rojas")

    with pytest.raises(CommandError, match="not part of this group"):
        call_command(
            "find_duplicate_operators",
            "--apply",
            "--group",
            "maria-gonzalez",
            "--into",
            "OP-9",
        )
