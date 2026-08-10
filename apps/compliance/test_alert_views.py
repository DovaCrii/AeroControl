from datetime import date, timedelta

from django.utils import timezone

import pytest
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.test import Client
from django.urls import reverse

from apps.registry.models import (
    CostCenter,
    Operator,
    Qualification,
    QualificationType,
)
from apps.workboard.models import KanbanTask
from .models import Alert, AlertRule


@pytest.fixture
def qualification(db):
    cost_center = CostCenter.objects.create(code="OPS", name="Operations")
    operator = Operator.objects.create(
        employee_id="P1", full_name="Pilot One", cost_center=cost_center
    )
    qualification_type = QualificationType.objects.create(
        code="dgac-credential", name="Credencial DGAC"
    )
    return Qualification.objects.create(
        operator=operator,
        qualification_type=qualification_type,
        issue_date=date(2026, 1, 1),
        expiry_date=timezone.localdate() + timedelta(days=3),
    )


def _alert_for(qualification, **rule_kwargs):
    rule = AlertRule.objects.create(
        name="Vencimiento de habilitaciones",
        entity_type="qualification",
        field_to_watch="expiry_date",
        **rule_kwargs,
    )
    return Alert.objects.create(
        alert_rule=rule,
        content_type=ContentType.objects.get_for_model(Qualification),
        object_id=qualification.pk,
        message="Expiring soon",
    )


@pytest.mark.django_db
def test_alert_list_shows_entity_name_not_uuid(qualification):
    _alert_for(qualification)
    User.objects.create_superuser("admin", "a@test.com", "password")
    client = Client()
    assert client.login(username="admin", password="password")

    response = client.get(reverse("alert-list"))
    content = response.content.decode()

    assert response.status_code == 200
    assert "Credencial DGAC" in content


@pytest.mark.django_db
def test_alert_list_shows_export_link_and_export_returns_csv(qualification):
    """T5.7 (U6): AlertList already mixes in CsvExportMixin (via
    ComplianceList), but its bespoke template never rendered the link."""
    _alert_for(qualification)
    User.objects.create_superuser("admin", "a@test.com", "password")
    client = Client()
    assert client.login(username="admin", password="password")

    page = client.get(reverse("alert-list"))
    assert "export=csv" in page.content.decode()

    export = client.get(reverse("alert-list"), {"export": "csv"})
    assert export.status_code == 200
    assert export["Content-Type"].startswith("text/csv")


@pytest.mark.django_db
def test_create_task_button_requires_add_kanbantask_permission(qualification):
    alert = _alert_for(qualification)
    User.objects.create_user("viewer", password="password")
    client = Client()
    assert client.login(username="viewer", password="password")

    response = client.post(reverse("alert-create-task", args=[alert.pk]))

    assert response.status_code == 403
    assert KanbanTask.objects.count() == 0


@pytest.mark.django_db
def test_manual_task_creation_falls_back_to_compliance_board(qualification):
    call_command("init_dgac_board")
    alert = _alert_for(qualification)  # rule has no target board configured
    User.objects.create_superuser("admin", "a@test.com", "password")
    client = Client()
    assert client.login(username="admin", password="password")

    response = client.post(reverse("alert-create-task", args=[alert.pk]))

    assert response.status_code == 302
    task = KanbanTask.objects.get()
    assert task.board.name == "Cumplimiento DGAC"
    assert task.source_object == alert
    assert task.priority == "high"  # expires in 3 days


@pytest.mark.django_db
def test_manual_task_creation_is_idempotent(qualification):
    call_command("init_dgac_board")
    alert = _alert_for(qualification)
    User.objects.create_superuser("admin", "a@test.com", "password")
    client = Client()
    assert client.login(username="admin", password="password")

    client.post(reverse("alert-create-task", args=[alert.pk]))
    client.post(reverse("alert-create-task", args=[alert.pk]))

    assert KanbanTask.objects.count() == 1


@pytest.mark.django_db
def test_manual_task_creation_without_any_board_reports_error(qualification):
    alert = _alert_for(qualification)
    User.objects.create_superuser("admin", "a@test.com", "password")
    client = Client()
    assert client.login(username="admin", password="password")

    response = client.post(reverse("alert-create-task", args=[alert.pk]), follow=True)

    assert KanbanTask.objects.count() == 0
    # Assert on the message level, not its wording: the copy is translated and
    # asserting the English text breaks under a Spanish locale.
    assert [m.level_tag for m in response.context["messages"]] == ["error"]


@pytest.mark.django_db
def test_refresh_alert_task_titles_rewrites_legacy_reprs(qualification):
    call_command("init_dgac_board")
    alert = _alert_for(qualification)
    task = alert.ensure_follow_up_task(allow_default_board=True)
    # Simulate a title stored before the models had __str__ methods
    task.title = f"Vencimiento: Qualification object ({qualification.pk})"
    task.save(update_fields=["title"])

    call_command("refresh_alert_task_titles")  # dry-run leaves it alone
    task.refresh_from_db()
    assert " object (" in task.title

    call_command("refresh_alert_task_titles", "--apply")
    task.refresh_from_db()
    assert " object (" not in task.title
    assert "Credencial DGAC" in task.title
    assert "Pilot One" in task.title


@pytest.mark.django_db
def test_reopen_requires_change_alert_permission(qualification):
    alert = _alert_for(qualification)
    alert.resolve()
    User.objects.create_user("viewer", password="password")
    client = Client()
    assert client.login(username="viewer", password="password")

    response = client.post(reverse("alert-reopen", args=[alert.pk]))

    alert.refresh_from_db()
    assert response.status_code == 403
    assert alert.is_resolved is True


@pytest.mark.django_db
def test_reopen_returns_the_task_to_the_stage_it_came_from(qualification):
    call_command("init_dgac_board")
    alert = _alert_for(qualification)
    User.objects.create_superuser("admin", "a@test.com", "password")
    client = Client()
    assert client.login(username="admin", password="password")
    client.post(reverse("alert-create-task", args=[alert.pk]))
    original_stage = KanbanTask.objects.get().stage

    client.post(reverse("alert-resolve", args=[alert.pk]), {"reason": "Fixed"})
    moved = KanbanTask.objects.get()
    assert moved.stage.status_type == "completed"
    assert moved.stage_id != original_stage.pk

    response = client.post(reverse("alert-reopen", args=[alert.pk]))

    alert.refresh_from_db()
    assert response.status_code == 302
    assert alert.is_resolved is False
    assert alert.resolved_at is None
    # Back exactly where it was, not merely out of the completed column.
    assert KanbanTask.objects.get().stage_id == original_stage.pk


@pytest.mark.django_db
def test_reopen_falls_back_when_the_original_stage_was_archived(qualification):
    call_command("init_dgac_board")
    alert = _alert_for(qualification)
    User.objects.create_superuser("admin", "a@test.com", "password")
    client = Client()
    assert client.login(username="admin", password="password")
    client.post(reverse("alert-create-task", args=[alert.pk]))
    original_stage = KanbanTask.objects.get().stage
    client.post(reverse("alert-resolve", args=[alert.pk]), {"reason": "Fixed"})

    original_stage.is_active = False
    original_stage.save(update_fields=["is_active"])

    client.post(reverse("alert-reopen", args=[alert.pk]))

    task = KanbanTask.objects.get()
    assert task.stage.status_type != "completed"
    assert task.stage.is_active is True


@pytest.mark.django_db
def test_reopening_an_open_alert_changes_nothing(qualification):
    alert = _alert_for(qualification)

    assert alert.reopen() is None
    alert.refresh_from_db()
    assert alert.is_resolved is False


class TestResolveRequiresAReason:
    """R6.2: ISO 10.2 asks for the root cause on record -- "Resolve" used to
    take nothing at all."""

    @pytest.mark.django_db
    def test_get_renders_the_reason_form_in_the_modal(self, qualification):
        alert = _alert_for(qualification)
        User.objects.create_superuser("admin", "a@test.com", "password")
        client = Client()
        assert client.login(username="admin", password="password")

        response = client.get(reverse("alert-resolve", args=[alert.pk]))

        assert response.status_code == 200
        assert b'name="reason"' in response.content

    @pytest.mark.django_db
    def test_blank_reason_does_not_resolve_the_alert(self, qualification):
        alert = _alert_for(qualification)
        User.objects.create_superuser("admin", "a@test.com", "password")
        client = Client()
        assert client.login(username="admin", password="password")

        response = client.post(
            reverse("alert-resolve", args=[alert.pk]), {"reason": ""}
        )

        assert response.status_code == 422
        alert.refresh_from_db()
        assert alert.is_resolved is False

    @pytest.mark.django_db
    def test_a_real_reason_resolves_the_alert_and_is_kept_on_record(
        self, qualification
    ):
        alert = _alert_for(qualification)
        User.objects.create_superuser("admin", "a@test.com", "password")
        client = Client()
        assert client.login(username="admin", password="password")

        response = client.post(
            reverse("alert-resolve", args=[alert.pk]),
            {"reason": "JAC policy renewed, folio 12345."},
        )

        assert response.status_code == 302
        alert.refresh_from_db()
        assert alert.is_resolved is True
        assert alert.resolution_reason == "JAC policy renewed, folio 12345."

    @pytest.mark.django_db
    def test_htmx_submit_returns_204_with_the_modal_close_trigger(self, qualification):
        alert = _alert_for(qualification)
        User.objects.create_superuser("admin", "a@test.com", "password")
        client = Client()
        assert client.login(username="admin", password="password")

        response = client.post(
            reverse("alert-resolve", args=[alert.pk]),
            {"reason": "Fixed"},
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 204
        assert response.headers.get("HX-Trigger") == "modal-form-success"

    @pytest.mark.django_db
    def test_reopening_clears_the_recorded_reason(self, qualification):
        alert = _alert_for(qualification)
        alert.resolve(reason="Fixed the first time")

        alert.reopen()

        alert.refresh_from_db()
        assert alert.resolution_reason == ""

    @pytest.mark.django_db
    def test_resolve_requires_change_alert_permission(self, qualification):
        alert = _alert_for(qualification)
        User.objects.create_user("viewer", password="password")
        client = Client()
        assert client.login(username="viewer", password="password")

        response = client.post(
            reverse("alert-resolve", args=[alert.pk]), {"reason": "Fixed"}
        )

        assert response.status_code == 403
        alert.refresh_from_db()
        assert alert.is_resolved is False

    @pytest.mark.django_db
    def test_automatic_resolution_stays_reason_less(self, qualification):
        """The system-driven callers (resolve_open_alerts_for,
        Document.resolve_related_alerts, R6.1's task-completion signal) have
        no human to ask -- Alert.resolve() must keep working without one."""
        alert = _alert_for(qualification)

        alert.resolve()

        alert.refresh_from_db()
        assert alert.is_resolved is True
        assert alert.resolution_reason == ""


@pytest.mark.django_db
def test_reopen_records_its_own_audit_event(qualification):
    from apps.core.models import AuditEvent

    alert = _alert_for(qualification)
    alert.resolve()
    User.objects.create_superuser("admin", "a@test.com", "password")
    client = Client()
    assert client.login(username="admin", password="password")

    client.post(reverse("alert-reopen", args=[alert.pk]))

    actions = list(AuditEvent.objects.values_list("action", flat=True))
    # The resolution is not erased; the undo is a second, opposite event.
    assert "alert_reopened" in actions


@pytest.mark.django_db
def test_resolve_is_atomic_with_the_task_move(qualification, monkeypatch):
    """V.10: a crash between the alert save and the task move left a resolved
    alert with its task still open. Inject the crash and check neither half
    persisted."""
    call_command("init_dgac_board")
    alert = _alert_for(qualification)
    task = alert.ensure_follow_up_task(allow_default_board=True)
    assert task is not None

    from apps.workboard.models import KanbanTask

    def explode(self, *args, **kwargs):
        raise RuntimeError("simulated crash mid-resolve")

    monkeypatch.setattr(KanbanTask, "save", explode)

    with pytest.raises(RuntimeError):
        alert.resolve()

    alert.refresh_from_db()
    task.refresh_from_db()
    assert alert.is_resolved is False, "the alert flag must roll back too"
    assert task.stage.status_type != "completed"
