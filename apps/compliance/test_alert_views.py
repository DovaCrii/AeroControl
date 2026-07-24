from datetime import date, timedelta

import pytest
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.test import Client
from django.urls import reverse

from apps.registry.models import CostCenter, Operator, Qualification
from apps.workboard.models import KanbanTask
from .models import Alert, AlertRule


@pytest.fixture
def qualification(db):
    cost_center = CostCenter.objects.create(code="OPS", name="Operations")
    operator = Operator.objects.create(
        employee_id="P1", full_name="Pilot One", cost_center=cost_center
    )
    return Qualification.objects.create(
        operator=operator,
        qualification_type="Credencial DGAC",
        issue_date=date(2026, 1, 1),
        expiry_date=date.today() + timedelta(days=3),
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
    assert "Pilot One" in content
    # The raw UUID of the watched entity must not be the only identifier shown
    assert "Qualification object" not in content


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
    assert any("No Kanban board" in m.message for m in response.context["messages"])


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
