"""Live-review batch: maintenance (LV-8), enriched lists (LV-9), CC prefix (LV-10a)."""

from datetime import date, timedelta

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.maintenance.models import MaintenanceRecord
from apps.registry.forms import CostCenterForm
from apps.registry.models import (
    Aircraft,
    CostCenter,
    Operator,
    Qualification,
    QualificationType,
)


@pytest.fixture
def admin_client(db):
    User.objects.create_superuser("admin", "admin@test.com", "password")
    client = Client()
    assert client.login(username="admin", password="password")
    return client


# ── LV-8: maintenance ────────────────────────────────────────────────────────
class TestMaintenanceToBeDefined:
    @pytest.mark.django_db
    def test_can_create_a_to_be_defined_record_without_date_or_assignee(self, db):
        cc = CostCenter.objects.create(code="CC1", name="One")
        aircraft = Aircraft.objects.create(
            registration="RPA-1",
            type="RPA",
            model="M300",
            manufacturer="DJI",
            cost_center=cc,
        )
        record = MaintenanceRecord.objects.create(
            aircraft=aircraft,
            maintenance_type="to_be_defined",
            description="Needs inspection, date TBD",
        )
        assert record.scheduled_date is None
        assert record.performed_by == ""
        assert record.is_incomplete is True

    @pytest.mark.django_db
    def test_scheduled_record_with_date_is_not_incomplete(self, db):
        cc = CostCenter.objects.create(code="CC1", name="One")
        aircraft = Aircraft.objects.create(
            registration="RPA-1",
            type="RPA",
            model="M300",
            manufacturer="DJI",
            cost_center=cc,
        )
        record = MaintenanceRecord.objects.create(
            aircraft=aircraft,
            maintenance_type="scheduled",
            description="100h",
            scheduled_date=date(2026, 8, 1),
        )
        assert record.is_incomplete is False

    @pytest.mark.django_db
    def test_dashboard_counts_incomplete_maintenance(self, admin_client):
        cc = CostCenter.objects.create(code="CC1", name="One")
        aircraft = Aircraft.objects.create(
            registration="RPA-1",
            type="RPA",
            model="M300",
            manufacturer="DJI",
            cost_center=cc,
        )
        MaintenanceRecord.objects.create(
            aircraft=aircraft, maintenance_type="to_be_defined", description="x"
        )
        response = admin_client.get(reverse("dashboard"))
        assert response.status_code == 200
        assert response.context["incomplete_maintenance_count"] == 1

    @pytest.mark.django_db
    def test_maintenance_form_has_no_cost_field(self, db):
        from apps.maintenance.forms import MaintenanceRecordForm

        assert "cost" not in MaintenanceRecordForm().fields


# ── LV-9: enriched lists ──────────────────────────────────────────────────────
class TestEnrichedLists:
    @pytest.mark.django_db
    def test_operator_list_shows_rut_and_qualification_badge(self, admin_client):
        cc = CostCenter.objects.create(code="CC1", name="One")
        operator = Operator.objects.create(
            employee_id="OP-1",
            full_name="Pilot One",
            rut="11.111.111-1",
            cost_center=cc,
        )
        qt = QualificationType.objects.create(code="mavic", name="Serie Mavic")
        Qualification.objects.create(
            operator=operator,
            qualification_type=qt,
            issue_date=date(2026, 1, 1),
            expiry_date=timezone.localdate() + timedelta(days=30),
        )
        response = admin_client.get(reverse("operator-list"))
        content = response.content.decode()
        assert "11.111.111-1" in content
        assert "Current" in content or "Vigente" in content

    @pytest.mark.django_db
    def test_cost_center_list_shows_resource_counts(self, admin_client):
        cc = CostCenter.objects.create(code="CC1", name="One", responsible="Admin X")
        Operator.objects.create(employee_id="OP-1", full_name="P1", cost_center=cc)
        Aircraft.objects.create(
            registration="RPA-1",
            type="RPA",
            model="M300",
            manufacturer="DJI",
            cost_center=cc,
        )
        response = admin_client.get(reverse("costcenter-list"))
        assert response.status_code == 200
        row = [o for o in response.context["objects"] if o.pk == cc.pk][0]
        assert row.operator_count == 1
        assert row.aircraft_count == 1
        assert "Admin X" in response.content.decode()


# ── Assignment backfill: FK-only data reconciled to OPS-1 assignments ─────────
class TestBackfillResourceAssignments:
    @pytest.mark.django_db
    def test_backfill_creates_assignments_from_the_fk(self, admin_client):
        from django.core.management import call_command

        from apps.registry.models import AircraftAssignment, OperatorAssignment

        cc = CostCenter.objects.create(code="CC684", name="684")
        aircraft = Aircraft.objects.create(
            registration="RPA-2750",
            type="RPA",
            model="Mavic 3",
            manufacturer="DJI",
            cost_center=cc,
        )
        operator = Operator.objects.create(
            employee_id="OP-1", full_name="Pilot One", cost_center=cc
        )
        # Imported state: FK set, but no assignment rows.
        assert not AircraftAssignment.objects.exists()
        assert not OperatorAssignment.objects.exists()

        call_command("backfill_resource_assignments")

        assert AircraftAssignment.objects.filter(
            aircraft=aircraft, cost_center=cc, is_active=True
        ).exists()
        assert OperatorAssignment.objects.filter(
            operator=operator, cost_center=cc, is_active=True
        ).exists()

        # The contract detail's Flota tab now reflects the aircraft.
        response = admin_client.get(reverse("costcenter-detail", args=[cc.pk]))
        assert aircraft in [
            a.aircraft for a in response.context["aircraft_assignments"]
        ]

        # Idempotent: a second run creates nothing.
        call_command("backfill_resource_assignments")
        assert AircraftAssignment.objects.count() == 1
        assert OperatorAssignment.objects.count() == 1


# ── LV-12: qualifications from Operator.authorizations ────────────────────────
class TestSeedOperatorQualifications:
    @pytest.mark.django_db
    def test_creates_qualifications_from_authorizations_text(self, db):
        from django.core.management import call_command

        cc = CostCenter.objects.create(code="CC1", name="One")
        QualificationType.objects.create(
            code="mavic", name="Serie Mavic", model_keywords="mavic"
        )
        QualificationType.objects.create(
            code="matrice", name="Serie Matrice", model_keywords="matrice"
        )
        operator = Operator.objects.create(
            employee_id="OP-1",
            full_name="Franco",
            cost_center=cc,
            authorizations="Matrice 300 Rtk/ 210 Rtk/ 600 - Mavic 3 - Phantom4",
        )

        call_command("seed_operator_qualifications")

        codes = set(
            Qualification.objects.filter(operator=operator).values_list(
                "qualification_type__code", flat=True
            )
        )
        assert codes == {"mavic", "matrice"}  # phantom not in the catalog here
        q = Qualification.objects.filter(operator=operator).first()
        assert q.issue_date is None and q.expiry_date is None

    @pytest.mark.django_db
    def test_is_idempotent(self, db):
        from django.core.management import call_command

        cc = CostCenter.objects.create(code="CC1", name="One")
        QualificationType.objects.create(
            code="mavic", name="Serie Mavic", model_keywords="mavic"
        )
        Operator.objects.create(
            employee_id="OP-1",
            full_name="F",
            cost_center=cc,
            authorizations="Mavic 3",
        )
        call_command("seed_operator_qualifications")
        call_command("seed_operator_qualifications")
        assert Qualification.objects.count() == 1

    @pytest.mark.django_db
    def test_qualification_issue_date_is_optional(self, db):
        cc = CostCenter.objects.create(code="CC1", name="One")
        operator = Operator.objects.create(
            employee_id="OP-1", full_name="F", cost_center=cc
        )
        qt = QualificationType.objects.create(code="mavic", name="Serie Mavic")
        q = Qualification.objects.create(operator=operator, qualification_type=qt)
        assert q.issue_date is None


# ── LV-16: cost-center form drops name, adds notes; notes column in the list ──
class TestCostCenterFormSimplified:
    @pytest.mark.django_db
    def test_form_has_an_optional_name_field_and_notes(self, db):
        # LV-19: name is back on the form (optional) so it can be edited.
        form = CostCenterForm()
        assert "name" in form.fields
        assert not form.fields["name"].required
        assert "notes" in form.fields

    @pytest.mark.django_db
    def test_can_save_a_cost_center_without_a_name_with_notes(self, db):
        form = CostCenterForm(
            data={
                "code": "738",
                "responsible": "Juan Quiroz",
                "notes": "Contrato MLP",
            }
        )
        assert form.is_valid(), form.errors
        cc = form.save()
        assert cc.code == "CC738"
        assert cc.name == ""
        assert cc.notes == "Contrato MLP"
        assert str(cc) == "CC738 · Juan Quiroz"  # __str__ falls back to code

    @pytest.mark.django_db
    def test_name_can_be_set_and_changed_from_the_form(self, db):
        # LV-19: the name shown in the list was frozen; now it is editable.
        cc = CostCenter.objects.create(code="CC410", name="Levantamientos")
        form = CostCenterForm(
            data={"code": "410", "name": "Levantamientos digital", "notes": ""},
            instance=cc,
        )
        assert form.is_valid(), form.errors
        form.save()
        cc.refresh_from_db()
        assert cc.name == "Levantamientos digital"

    @pytest.mark.django_db
    def test_cost_center_list_shows_a_notes_column(self, admin_client):
        CostCenter.objects.create(code="CC1", name="One", notes="Nota visible")
        response = admin_client.get(reverse("costcenter-list"))
        assert "Nota visible" in response.content.decode()

    @pytest.mark.django_db
    def test_registry_lists_show_an_import_button(self, admin_client):
        # T5.2: importers are reachable from their list, not just by URL.
        for name in ("costcenter", "aircraft", "operator"):
            response = admin_client.get(reverse(f"{name}-list"))
            assert reverse(f"{name}-import") in response.content.decode()


# ── LV-14: habilitations list grouped by operator ────────────────────────────
class TestQualificationListGroupedByOperator:
    @pytest.mark.django_db
    def test_one_row_per_operator_with_equipment_chips(self, admin_client):
        cc = CostCenter.objects.create(code="CC1", name="One")
        operator = Operator.objects.create(
            employee_id="OP-1", full_name="René Herrera", cost_center=cc
        )
        mavic = QualificationType.objects.create(code="mavic", name="Serie Mavic")
        matrice = QualificationType.objects.create(code="matrice", name="Serie Matrice")
        Qualification.objects.create(operator=operator, qualification_type=mavic)
        Qualification.objects.create(operator=operator, qualification_type=matrice)

        response = admin_client.get(reverse("qualification-list"))

        assert response.status_code == 200
        # One row for the operator (not one per qualification).
        assert list(response.context["objects"]) == [operator]
        content = response.content.decode()
        # Operator name appears once; both equipment chips are present.
        assert content.count("René Herrera") == 1
        assert "Serie Mavic" in content and "Serie Matrice" in content

    @pytest.mark.django_db
    def test_current_chips_are_coloured_per_type_expired_stay_red(self, admin_client):
        """LV-15: a current chip carries its type's stable colour class, while
        an expired chip keeps the red override."""
        cc = CostCenter.objects.create(code="CC1", name="One")
        operator = Operator.objects.create(
            employee_id="OP-1", full_name="René Herrera", cost_center=cc
        )
        mavic = QualificationType.objects.create(code="mavic", name="Serie Mavic")
        phantom = QualificationType.objects.create(code="phantom", name="Serie Phantom")
        Qualification.objects.create(operator=operator, qualification_type=mavic)
        Qualification.objects.create(
            operator=operator,
            qualification_type=phantom,
            expiry_date=date(2000, 1, 1),  # long expired
        )

        content = admin_client.get(reverse("qualification-list")).content.decode()

        # The current chip shows its type colour, the expired one stays red.
        assert mavic.chip_class in content
        assert "bg-danger" in content

    def test_chip_class_is_stable_in_palette_and_never_danger(self):
        """LV-15: the colour is deterministic, drawn from the palette, and
        never collides with the reserved expired-red."""
        a = QualificationType(code="mavic", name="Serie Mavic")
        b = QualificationType(code="matrice", name="Serie Matrice")
        assert a.chip_class in QualificationType.CHIP_PALETTE
        assert a.chip_class == QualificationType(code="mavic", name="x").chip_class
        assert "bg-danger" not in a.chip_class
        # Different families should not all look identical.
        assert a.chip_class != b.chip_class

    @pytest.mark.django_db
    def test_operator_without_qualifications_is_absent(self, admin_client):
        cc = CostCenter.objects.create(code="CC1", name="One")
        Operator.objects.create(
            employee_id="OP-1", full_name="No Quals", cost_center=cc
        )

        response = admin_client.get(reverse("qualification-list"))
        assert list(response.context["objects"]) == []

    @pytest.mark.django_db
    def test_csv_export_still_exports_individual_qualifications(self, admin_client):
        cc = CostCenter.objects.create(code="CC1", name="One")
        operator = Operator.objects.create(
            employee_id="OP-1", full_name="René", cost_center=cc
        )
        mavic = QualificationType.objects.create(code="mavic", name="Serie Mavic")
        Qualification.objects.create(operator=operator, qualification_type=mavic)

        response = admin_client.get(reverse("qualification-list"), {"export": "csv"})
        body = b"".join(response.streaming_content).decode("utf-8")
        assert "Serie Mavic" in body


# ── LV-10a: CC code prefix ────────────────────────────────────────────────────
class TestCostCenterCodePrefix:
    @pytest.mark.django_db
    def test_form_prefixes_a_bare_number(self, db):
        form = CostCenterForm(data={"code": "738", "name": "New CC"})
        assert form.is_valid(), form.errors
        assert form.cleaned_data["code"] == "CC738"

    @pytest.mark.django_db
    def test_form_does_not_double_prefix(self, db):
        form = CostCenterForm(data={"code": "cc738", "name": "New CC"})
        assert form.is_valid(), form.errors
        assert form.cleaned_data["code"] == "CC738"

    @pytest.mark.django_db
    def test_form_rejects_an_empty_number(self, db):
        form = CostCenterForm(data={"code": "CC", "name": "New CC"})
        assert not form.is_valid()
        assert "code" in form.errors
