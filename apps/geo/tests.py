import pytest
from django.contrib.auth.models import Group, Permission, User
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction

from apps.geo.models import GeoPlan, GeoPlanHistory, GeoPlanVersion
from apps.registry.models import CostCenter


def _plan(db, status="draft"):
    center = CostCenter.objects.create(code="GEO-CC", name="Geo tests")
    user = User.objects.create_user("planner", password="pw")
    return GeoPlan.objects.create(
        title="Plan 716",
        cost_center=center,
        created_by=user,
        status=status,
    )


def _version(plan, number):
    return GeoPlanVersion.objects.create(
        plan=plan,
        version_number=number,
        content={"schema_version": 1, "children": []},
        content_checksum="0" * 64,
        source="import",
        created_by=plan.created_by,
    )


class TestVersionImmutability:
    @pytest.mark.django_db
    def test_version_number_is_unique_per_plan(self, db):
        plan = _plan(db)
        _version(plan, 1)
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                _version(plan, 1)

    @pytest.mark.django_db
    def test_instance_save_after_create_is_rejected(self, db):
        plan = _plan(db)
        version = _version(plan, 1)
        version.summary = "tampered"
        with pytest.raises(ValidationError):
            version.save()

    @pytest.mark.django_db
    def test_queryset_update_and_delete_are_rejected(self, db):
        plan = _plan(db)
        _version(plan, 1)
        with pytest.raises(ValidationError):
            GeoPlanVersion.objects.filter(plan=plan).update(summary="x")
        with pytest.raises(ValidationError):
            GeoPlanVersion.objects.filter(plan=plan).delete()

    @pytest.mark.django_db
    def test_instance_delete_is_rejected(self, db):
        plan = _plan(db)
        version = _version(plan, 1)
        with pytest.raises(ValidationError):
            version.delete()


class TestEditableLock:
    """clean() is layer 2 of the approved-plan lock (GEO-6)."""

    @pytest.mark.django_db
    def test_editor_version_on_locked_plan_fails_clean(self, db):
        plan = _plan(db, status="approved")
        version = GeoPlanVersion(
            plan=plan,
            version_number=2,
            content={"schema_version": 1, "children": []},
            content_checksum="0" * 64,
            source="editor",
            created_by=plan.created_by,
        )
        with pytest.raises(ValidationError):
            version.full_clean()

    @pytest.mark.django_db
    def test_import_version_is_exempt_from_the_lock(self, db):
        # V1 is created with the plan while still draft; an import is never a
        # user content edit, so the lock must not block it even if the plan is
        # already in a non-editable state.
        plan = _plan(db, status="approved")
        version = GeoPlanVersion(
            plan=plan,
            version_number=1,
            content={"schema_version": 1, "children": []},
            content_checksum="0" * 64,
            source="import",
            created_by=plan.created_by,
        )
        version.full_clean()  # must not raise

    @pytest.mark.django_db
    def test_editor_version_on_editable_plan_passes_clean(self, db):
        plan = _plan(db, status="editing")
        version = GeoPlanVersion(
            plan=plan,
            version_number=2,
            content={"schema_version": 1, "children": []},
            content_checksum="0" * 64,
            source="editor",
            created_by=plan.created_by,
        )
        version.full_clean()  # must not raise


class TestStatusHistory:
    @pytest.mark.django_db
    def test_status_change_writes_history(self, db):
        plan = _plan(db, status="draft")

        plan.status = "editing"
        plan._changed_by = "planner"
        plan.save(update_fields=["status", "updated_at"])

        entry = GeoPlanHistory.objects.get(plan=plan)
        assert entry.previous_status == "draft"
        assert entry.new_status == "editing"
        assert entry.changed_by == "planner"

    @pytest.mark.django_db
    def test_creating_a_plan_writes_no_history(self, db):
        plan = _plan(db)
        # A UUID pk is set before the first save, so the signal must still not
        # mistake creation for a status change.
        assert GeoPlanHistory.objects.filter(plan=plan).count() == 0

    @pytest.mark.django_db
    def test_is_editable_tracks_status(self, db):
        plan = _plan(db, status="draft")
        assert plan.is_editable is True
        plan.status = "approved"
        assert plan.is_editable is False


class TestRolePermissions:
    @pytest.mark.django_db
    def test_bootstrap_roles_grants_geo_permissions_by_role(self, db):
        call_command("bootstrap_roles")

        def codes(group):
            return set(
                Group.objects.get(name=group).permissions.values_list(
                    "codename", flat=True
                )
            )

        operations = codes("Operations")
        compliance = codes("Compliance")
        viewer = codes("Viewer")

        # Operations draws plans but must not approve them.
        assert {"add_geoplan", "change_geoplan", "view_geoplan"} <= operations
        assert "approve_geoplan" not in operations
        # Compliance approves but does not draw.
        assert "approve_geoplan" in compliance
        assert "add_geoplan" not in compliance
        # Viewer only reads.
        assert viewer & {"add_geoplan", "change_geoplan", "approve_geoplan"} == set()
        assert "view_geoplan" in viewer

    @pytest.mark.django_db
    def test_approve_permission_exists(self, db):
        assert Permission.objects.filter(
            codename="approve_geoplan", content_type__app_label="geo"
        ).exists()
