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


@pytest.fixture
def two_qualifications():
    """Two operators whose habilitación expires on the same date -- the shape
    R6.3 used to fold into one row and LV-75 keeps as two."""
    cost_center = CostCenter.objects.create(code="OPS", name="Operations")
    qualification_type = QualificationType.objects.create(
        code="dgac-credential", name="Credencial DGAC"
    )
    shared_expiry = timezone.localdate() + timedelta(days=3)
    operator_a = Operator.objects.create(
        employee_id="P1", full_name="Pilot One", cost_center=cost_center
    )
    operator_b = Operator.objects.create(
        employee_id="P2", full_name="Pilot Two", cost_center=cost_center
    )
    qual_a = Qualification.objects.create(
        operator=operator_a,
        qualification_type=qualification_type,
        issue_date=date(2026, 1, 1),
        expiry_date=shared_expiry,
    )
    qual_b = Qualification.objects.create(
        operator=operator_b,
        qualification_type=qualification_type,
        issue_date=date(2026, 1, 1),
        expiry_date=shared_expiry,
    )
    return qual_a, qual_b


class TestAlertRows:
    """LV-75: one alert, one row -- a shared expiry date never folds two
    findings together."""

    @pytest.mark.django_db
    def test_same_date_alerts_stay_on_separate_rows(self, two_qualifications):
        """R6.3 grouped these on the premise that a shared date meant a shared
        cause. LV-68 found that false against production data (two aircraft,
        two separate insurance policies, one coincident date) and dropped the
        shared-reason resolve; LV-75 drops the row that still implied it."""
        qual_a, qual_b = two_qualifications
        rule = AlertRule.objects.create(
            name="Vencimiento de habilitaciones",
            entity_type="qualification",
            field_to_watch="expiry_date",
        )
        alert_a = Alert.objects.create(
            alert_rule=rule,
            content_type=ContentType.objects.get_for_model(Qualification),
            object_id=qual_a.pk,
            message="Expiring soon",
        )
        alert_b = Alert.objects.create(
            alert_rule=rule,
            content_type=ContentType.objects.get_for_model(Qualification),
            object_id=qual_b.pk,
            message="Expiring soon",
        )
        User.objects.create_superuser("admin", "a@test.com", "password")
        client = Client()
        assert client.login(username="admin", password="password")

        response = client.get(reverse("alert-list"))
        content = response.content.decode()

        # One row each: the rule name is printed once per alert, not once for
        # the pair.
        assert content.count("Vencimiento de habilitaciones") == 2
        # Both entities are named -- neither is hidden inside another's row.
        assert "Pilot One" in content
        assert "Pilot Two" in content
        for alert in (alert_a, alert_b):
            assert reverse("alert-resolve", args=[alert.pk]) in content

    @pytest.mark.django_db
    def test_the_list_no_longer_pushes_work_to_the_hidden_workboard(
        self, two_qualifications
    ):
        """LV-69b: the board left the sidebar, so the alert list must not offer
        to create or open tasks there -- that sent work somewhere nobody
        navigates to. The list is self-contained: resolve and undo."""
        qual_a, _qual_b = two_qualifications
        rule = AlertRule.objects.create(
            name="Vencimiento de habilitaciones",
            entity_type="qualification",
            field_to_watch="expiry_date",
        )
        alert = Alert.objects.create(
            alert_rule=rule,
            content_type=ContentType.objects.get_for_model(Qualification),
            object_id=qual_a.pk,
            message="Expiring soon",
        )
        User.objects.create_superuser("admin", "a@test.com", "password")
        client = Client()
        assert client.login(username="admin", password="password")

        content = client.get(reverse("alert-list")).content.decode()

        assert reverse("alert-create-task", args=[alert.pk]) not in content
        assert reverse("kanban") not in content
        # The way out is still there, per alert.
        assert reverse("alert-resolve", args=[alert.pk]) in content

    @pytest.mark.django_db
    def test_no_bulk_group_resolve_endpoint_exists(self):
        """The removal is part of the contract: a URL that resolves N alerts
        with one shared reason must not come back by accident."""
        from django.urls import NoReverseMatch

        with pytest.raises(NoReverseMatch):
            reverse("alert-resolve-group", args=["whatever"])

    @pytest.mark.django_db
    def test_the_entity_type_filter_is_reachable_from_the_page(
        self, two_qualifications
    ):
        """LV-76: get_queryset() has always honoured ?entity_type and the
        context has always carried the list, but no template rendered the
        picker -- a working filter nobody could reach. The options carry the
        model's verbose_name, not the raw slug."""
        qual_a, _qual_b = two_qualifications
        rule = AlertRule.objects.create(
            name="Vencimiento de habilitaciones",
            entity_type="qualification",
            field_to_watch="expiry_date",
        )
        Alert.objects.create(
            alert_rule=rule,
            content_type=ContentType.objects.get_for_model(Qualification),
            object_id=qual_a.pk,
            message="Expiring soon",
        )
        User.objects.create_superuser("admin", "a@test.com", "password")
        client = Client()
        assert client.login(username="admin", password="password")

        content = client.get(reverse("alert-list")).content.decode()

        assert 'name="entity_type"' in content
        assert '<option value="qualification"' in content
        # And it actually narrows the list.
        filtered = client.get(
            reverse("alert-list"), {"entity_type": "flightpermission"}
        )
        assert "Pilot One" not in filtered.content.decode()

    @pytest.mark.django_db
    def test_the_resolution_reason_is_visible_not_only_a_tooltip(
        self, two_qualifications
    ):
        """LV-75: the reason lived only in a `title` attribute, invisible on
        touch and at a glance -- so the ISO 10.2 evidence the resolve modal
        insists on collecting was effectively write-only."""
        qual_a, _qual_b = two_qualifications
        rule = AlertRule.objects.create(
            name="Vencimiento de habilitaciones",
            entity_type="qualification",
            field_to_watch="expiry_date",
        )
        alert = Alert.objects.create(
            alert_rule=rule,
            content_type=ContentType.objects.get_for_model(Qualification),
            object_id=qual_a.pk,
            message="Expiring soon",
        )
        alert.resolve(reason="Credencial renovada ante la DGAC")
        User.objects.create_superuser("admin", "a@test.com", "password")
        client = Client()
        assert client.login(username="admin", password="password")

        # LV-118: la bandeja abre en "Sin resolver", así que una alerta resuelta
        # hay que ir a buscarla. Cambia la premisa del test, no su intención:
        # sigue afirmando que el motivo se lee donde la alerta se muestra.
        content = client.get(
            reverse("alert-list"), {"is_resolved": "all"}
        ).content.decode()

        # LV-110: se afirma que el motivo **está en la página**, no la lista
        # exacta de clases de Bootstrap que lo envuelve -- eso hacía fallar el
        # test por un cambio de color, que no es lo que este test protege.
        assert "alert-reason" in content
        assert "Credencial renovada ante la DGAC" in content
        assert 'title="Credencial renovada ante la DGAC"' not in content

    @pytest.mark.django_db
    def test_different_dates_never_group(self, two_qualifications):
        qual_a, qual_b = two_qualifications
        qual_b.expiry_date = qual_b.expiry_date + timedelta(days=1)
        qual_b.save(update_fields=["expiry_date"])
        rule = AlertRule.objects.create(
            name="Vencimiento de habilitaciones",
            entity_type="qualification",
            field_to_watch="expiry_date",
        )
        alerts = [
            Alert.objects.create(
                alert_rule=rule,
                content_type=ContentType.objects.get_for_model(Qualification),
                object_id=qual.pk,
                message="Expiring soon",
            )
            for qual in (qual_a, qual_b)
        ]
        User.objects.create_superuser("admin", "a@test.com", "password")
        client = Client()
        assert client.login(username="admin", password="password")

        response = client.get(reverse("alert-list"))
        content = response.content.decode()

        # Each keeps its own per-alert "Resolve" instead of the bulk button.
        for alert in alerts:
            assert reverse("alert-resolve", args=[alert.pk]) in content

    @pytest.mark.django_db
    def test_a_resolved_member_never_groups_back_in(self, two_qualifications):
        qual_a, qual_b = two_qualifications
        rule = AlertRule.objects.create(
            name="Vencimiento de habilitaciones",
            entity_type="qualification",
            field_to_watch="expiry_date",
        )
        alert_a = Alert.objects.create(
            alert_rule=rule,
            content_type=ContentType.objects.get_for_model(Qualification),
            object_id=qual_a.pk,
            message="Expiring soon",
        )
        alert_b = Alert.objects.create(
            alert_rule=rule,
            content_type=ContentType.objects.get_for_model(Qualification),
            object_id=qual_b.pk,
            message="Expiring soon",
        )
        alert_a.resolve(reason="Already handled")
        User.objects.create_superuser("admin", "a@test.com", "password")
        client = Client()
        assert client.login(username="admin", password="password")

        # LV-118: `alert_a` está resuelta y la bandeja abre en "Sin resolver".
        response = client.get(reverse("alert-list"), {"is_resolved": "all"})
        content = response.content.decode()

        assert reverse("alert-reopen", args=[alert_a.pk]) in content
        # alert_b is unresolved but no longer has a same-date, unresolved
        # partner -- it keeps its own single-alert "Resolve" instead of
        # joining a bulk button.
        assert reverse("alert-resolve", args=[alert_b.pk]) in content

    # LV-68: the six tests that covered AlertResolveGroup were deleted with the
    # view. They asserted that N alerts resolve with one shared reason, which is
    # the behaviour that turned out to be wrong against real data -- keeping
    # them would have locked in the defect. What replaced them:
    # test_no_bulk_group_resolve_endpoint_exists (the URL must stay gone) and
    # test_grouping_is_visual_only_and_every_action_stays_per_alert.


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
