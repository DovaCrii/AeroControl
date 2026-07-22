import pytest
from django.contrib.auth.models import Permission, User
from django.test import Client
from django.urls import reverse

from apps.registry.models import CostCenter, Operator
from .models import KanbanBoard, KanbanChecklistItem, KanbanLabel, KanbanStage, KanbanTask


@pytest.fixture
def user(db):
    user = User.objects.create_user("operator", password="password")
    user.user_permissions.add(
        *Permission.objects.filter(
            content_type__app_label="workboard",
            content_type__model__in=["kanbantask", "kanbanstage", "kanbanboard", "kanbanchecklistitem", "kanbanlabel"],
            codename__in=[
                "add_kanbantask",
                "change_kanbantask",
                "view_kanbantask",
                "add_kanbanstage",
                "add_kanbanboard",
                "change_kanbanboard",
                "add_kanbanchecklistitem",
                "change_kanbanchecklistitem",
                "add_kanbanlabel",
                "view_kanbanlabel",
            ],
        )
    )
    return user


@pytest.fixture
def auth_client(user):
    client = Client()
    assert client.login(username="operator", password="password")
    return client


@pytest.fixture
def board(db):
    board = KanbanBoard.objects.create(name="Operations")
    todo = KanbanStage.objects.create(board=board, name="Todo", order=0)
    done = KanbanStage.objects.create(board=board, name="Done", order=1)
    return board, todo, done


@pytest.fixture
def operator(db):
    cost_center = CostCenter.objects.create(code="OPS", name="Operations")
    return Operator.objects.create(
        employee_id="EMP-001",
        full_name="Test Operator",
        cost_center=cost_center,
    )


@pytest.mark.django_db
def test_kanban_and_mutating_endpoints_require_auth(board):
    _, todo, _ = board
    task = KanbanTask.objects.create(board=todo.board, stage=todo, title="Task")
    client = Client()

    assert client.get(reverse("kanban")).status_code == 302
    assert (
        client.post(
            reverse("task-move", args=[task.pk]), {"stage_id": todo.pk}
        ).status_code
        == 302
    )
    assert client.get(reverse("task-quick"), {"stage_id": todo.pk}).status_code == 302
    assert (
        client.post(
            reverse("task-quick"), {"stage_id": todo.pk, "title": "Task"}
        ).status_code
        == 302
    )


@pytest.mark.django_db
def test_authenticated_kanban_renders_and_empty_board_state(auth_client, board):
    board_obj, _, _ = board
    response = auth_client.get(reverse("kanban"))
    assert response.status_code == 200
    assert "Operations" in response.content.decode()

    board_obj.stages.update(is_active=False)
    response = auth_client.get(reverse("kanban"))
    assert response.status_code == 200
    assert "This board has no active stages." in response.content.decode()


@pytest.mark.django_db
def test_kanban_without_boards_shows_empty_state(auth_client):
    response = auth_client.get(reverse("kanban"))
    assert response.status_code == 200
    assert "No board configured." in response.content.decode()


@pytest.mark.django_db
def test_kanban_filters_by_operator_and_priority(auth_client, board, operator):
    board_obj, todo, _ = board
    matching = KanbanTask.objects.create(
        board=board_obj,
        stage=todo,
        title="Matching",
        assigned_to=operator,
        priority="high",
    )
    KanbanTask.objects.create(
        board=board_obj, stage=todo, title="Other", priority="low"
    )

    response = auth_client.get(
        reverse("kanban"), {"operator": operator.pk, "priority": "high"}
    )
    content = response.content.decode()
    assert response.status_code == 200
    assert "Matching" in content
    assert "Other" not in content
    assert 'data-drag-disabled="true"' in content
    assert "Drag-and-drop ordering is disabled" in content
    assert str(matching.pk) in content


@pytest.mark.django_db
def test_malformed_board_and_operator_filters_are_ignored(auth_client, board):
    response = auth_client.get(
        reverse("kanban"), {"board": "not-a-uuid", "operator": "also-not-a-uuid"}
    )
    assert response.status_code == 200
    assert "Operations" in response.content.decode()

    response = auth_client.get(
        reverse("kanban-board-partial"),
        {"board": "not-a-uuid", "operator": "also-not-a-uuid"},
    )
    assert response.status_code == 302
    assert response.url.startswith(reverse("kanban"))

    response = auth_client.get(
        reverse("kanban-board-partial"),
        {"board": board[0].pk, "operator": "also-not-a-uuid"},
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 200
    assert response.headers["HX-Push-Url"].startswith(reverse("kanban"))


@pytest.mark.django_db
def test_stage_create_is_available_from_empty_board(auth_client, board):
    board_obj, _, _ = board
    response = auth_client.post(
        reverse("stage-create") + f"?board={board_obj.pk}",
        {"board": board_obj.pk, "name": "Review", "order": 2, "color": "#2EC4B6"},
    )

    assert response.status_code == 302
    assert response.url == f"{reverse('kanban')}?board={board_obj.pk}"
    assert board_obj.stages.filter(name="Review").exists()


@pytest.mark.django_db
def test_board_and_task_archives_are_reversible(auth_client, board):
    board_obj, todo, _ = board
    task = KanbanTask.objects.create(board=board_obj, stage=todo, title="Archive me")

    task_response = auth_client.post(reverse("task-archive", args=[task.pk]))
    assert task_response.status_code == 302
    task.refresh_from_db()
    assert task.is_active is False

    board_response = auth_client.post(reverse("board-archive", args=[board_obj.pk]))
    assert board_response.status_code == 302
    board_obj.refresh_from_db()
    assert board_obj.is_active is False


@pytest.mark.django_db
def test_quick_add_preserves_filters_and_refreshes_column(auth_client, board, operator):
    board_obj, todo, _ = board
    KanbanTask.objects.create(
        board=board_obj,
        stage=todo,
        title="Visible",
        assigned_to=operator,
        priority="high",
    )
    KanbanTask.objects.create(
        board=board_obj, stage=todo, title="Hidden", priority="low"
    )

    form = auth_client.get(
        reverse("task-quick"),
        {
            "stage_id": todo.pk,
            "board": board_obj.pk,
            "operator": operator.pk,
            "priority": "high",
        },
    )
    assert form.status_code == 200
    form_content = form.content.decode()
    assert f'name="board" value="{board_obj.pk}"' in form_content
    assert f'name="operator" value="{operator.pk}"' in form_content
    assert 'name="filter_priority" value="high"' in form_content
    assert '<option value="high" selected>' not in form_content
    assert '<option value="medium" selected>Medium</option>' in form_content

    response = auth_client.post(
        reverse("task-quick"),
        {
            "stage_id": todo.pk,
            "title": "New visible",
            "assigned_to": operator.pk,
            "priority": "high",
            "filter_priority": "high",
            "board": board_obj.pk,
            "operator": operator.pk,
        },
    )
    assert response.status_code == 200
    content = response.content.decode()
    assert "Visible" in content and "New visible" in content
    assert "Hidden" not in content
    assert "&amp;board=" in content
    assert "&amp;operator=" in content
    assert "&amp;priority=high" in content
    assert "kanban-column" in content
    assert "HX-Retarget" not in response
    assert "HX-Reswap" not in response


@pytest.mark.django_db
def test_quick_add_rejects_stage_on_inactive_board(auth_client, board):
    _, todo, _ = board
    todo.board.is_active = False
    todo.board.save(update_fields=["is_active"])
    response = auth_client.post(
        reverse("task-quick"), {"stage_id": todo.pk, "title": "Invalid"}
    )
    assert response.status_code == 400
    assert not KanbanTask.objects.filter(title="Invalid").exists()


@pytest.mark.django_db
def test_move_updates_stage_and_order_and_rejects_invalid_stage(auth_client, board):
    board_obj, todo, done = board
    first = KanbanTask.objects.create(
        board=board_obj, stage=todo, title="First", order=0
    )
    second = KanbanTask.objects.create(
        board=board_obj, stage=todo, title="Second", order=1
    )

    response = auth_client.post(
        reverse("task-move", args=[second.pk]), {"stage_id": done.pk, "new_order": 0}
    )
    assert response.status_code == 204
    second.refresh_from_db()
    first.refresh_from_db()
    assert second.stage_id == done.pk
    assert second.order == 0
    assert first.order == 0

    other_board = KanbanBoard.objects.create(name="Other")
    other_stage = KanbanStage.objects.create(board=other_board, name="Other stage")
    response = auth_client.post(
        reverse("task-move", args=[first.pk]),
        {"stage_id": other_stage.pk, "new_order": 0},
    )
    assert response.status_code == 400

    done.is_active = False
    done.save(update_fields=["is_active"])
    response = auth_client.post(
        reverse("task-move", args=[first.pk]), {"stage_id": done.pk, "new_order": 0}
    )
    assert response.status_code == 400
    assert first.stage_id == todo.pk

    response = auth_client.post(
        reverse("task-move", args=[first.pk]),
        {"stage_id": "not-a-uuid", "new_order": 0},
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_move_rejects_task_from_inactive_board(auth_client, board):
    board_obj, todo, done = board
    task = KanbanTask.objects.create(board=board_obj, stage=todo, title="Task")
    board_obj.is_active = False
    board_obj.save(update_fields=["is_active"])
    response = auth_client.post(
        reverse("task-move", args=[task.pk]), {"stage_id": done.pk, "new_order": 0}
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_move_rejects_task_with_mismatched_board_and_stage(auth_client, board):
    board_obj, todo, done = board
    other_board = KanbanBoard.objects.create(name="Other")
    task = KanbanTask.objects.create(board=board_obj, stage=todo, title="Task")
    task.board = other_board
    task.save(update_fields=["board"])

    response = auth_client.post(
        reverse("task-move", args=[task.pk]), {"stage_id": done.pk, "new_order": 0}
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_move_requires_csrf(auth_client, board):
    _, todo, done = board
    task = KanbanTask.objects.create(board=todo.board, stage=todo, title="Task")
    client = Client(enforce_csrf_checks=True)
    assert client.login(username="operator", password="password")

    response = client.post(
        reverse("task-move", args=[task.pk]), {"stage_id": done.pk, "new_order": 0}
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_quick_add_validates_active_assignee(auth_client, board, operator):
    _, todo, _ = board
    inactive = Operator.objects.create(
        employee_id="EMP-002",
        full_name="Inactive Operator",
        cost_center=operator.cost_center,
        is_active=False,
    )
    url = reverse("task-quick")

    for assigned_to in ("not-a-uuid", inactive.pk):
        response = auth_client.post(
            url, {"stage_id": todo.pk, "title": "Invalid", "assigned_to": assigned_to}
        )
        assert response.status_code == 400
    assert not KanbanTask.objects.filter(title="Invalid").exists()


@pytest.mark.django_db
def test_quick_add_creates_task_and_renders_assignee(auth_client, board, operator):
    board_obj, todo, _ = board
    response = auth_client.post(
        reverse("task-quick"),
        {
            "stage_id": todo.pk,
            "title": "Inspect aircraft",
            "priority": "high",
            "assigned_to": operator.pk,
        },
    )
    assert response.status_code == 200
    task = KanbanTask.objects.get(title="Inspect aircraft")
    assert task.board_id == board_obj.pk
    assert task.assigned_to_id == operator.pk
    assert task.priority == "high"

    form = auth_client.get(reverse("task-quick"), {"stage_id": todo.pk})
    assert "Test Operator" in form.content.decode()


@pytest.mark.django_db
def test_workboard_urls_keep_kanban_and_task_list_distinct(auth_client):
    assert reverse("kanban") == "/workboard/"
    assert reverse("task-list") == "/workboard/tasks/"
    assert auth_client.get("/workboard/").status_code == 200
    assert auth_client.get("/workboard/tasks/").status_code == 200


@pytest.mark.django_db
def test_task_detail_checklist_progress_and_list_filters(auth_client, board):
    board_obj, todo, _ = board
    label = KanbanLabel.objects.create(board=board_obj, name="Safety", color="#EF4444")
    task = KanbanTask.objects.create(board=board_obj, stage=todo, title="Inspect")
    task.labels.add(label)
    first = KanbanChecklistItem.objects.create(task=task, title="Review log", order=0)
    KanbanChecklistItem.objects.create(task=task, title="Sign off", order=1, is_completed=True)

    detail = auth_client.get(reverse("task-detail", args=[task.pk]))
    assert detail.status_code == 200
    assert "50%" in detail.content.decode()

    response = auth_client.post(reverse("checklist-toggle", args=[first.pk]))
    assert response.status_code == 200
    task.refresh_from_db()
    assert task.checklist_progress == 100

    listing = auth_client.get(reverse("workboard-list"), {"q": "Inspect", "label": label.pk})
    assert listing.status_code == 200
    assert "Inspect" in listing.content.decode()


@pytest.mark.django_db
def test_task_report_exports_filtered_csv(auth_client, board):
    board_obj, todo, _ = board
    KanbanTask.objects.create(board=board_obj, stage=todo, title="Export me", priority="high")
    response = auth_client.get(reverse("task-report-csv"), {"priority": "high"})
    assert response.status_code == 200
    assert "Export me" in response.content.decode()
    assert response["Content-Disposition"].endswith('aerocontrol-tasks.csv"')


@pytest.mark.django_db
def test_task_report_exports_xlsx(auth_client, board):
    board_obj, todo, _ = board
    KanbanTask.objects.create(board=board_obj, stage=todo, title="XLSX task")
    response = auth_client.get(reverse("task-report-xlsx"))
    assert response.status_code == 200
    assert response["Content-Type"].startswith("application/vnd.openxmlformats")
    assert response.content[:2] == b"PK"
