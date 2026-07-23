"""Reusable Workboard read and access selectors.

These functions intentionally contain the compatibility-tenancy rules in one
place so HTML, HTMX, exports and API consumers cannot drift apart.
"""

from uuid import UUID

from django.db.models import Q
from django.core.exceptions import ValidationError

from apps.core.models import OperationalTenant
from apps.registry.models import Operator

from .models import KanbanBoard, KanbanBoardAccess, KanbanStage, KanbanTask


def accessible_boards(user, queryset=None):
    queryset = (queryset or KanbanBoard.objects).filter(is_active=True)
    if user.is_superuser:
        return queryset

    tenants = OperationalTenant.objects.filter(
        members=user, is_active=True, tenantmembership__is_active=True
    )
    if tenants.exists():
        queryset = queryset.filter(
            Q(tenant__isnull=True) | Q(tenant_id__in=tenants.values("id"))
        )

    rules = KanbanBoardAccess.objects.filter(user=user, is_active=True)
    if rules.exists():
        queryset = queryset.filter(pk__in=rules.values("board_id"))
    return queryset.distinct()


def visible_tasks_for_user(user, queryset=None):
    queryset = queryset or KanbanTask.objects
    return queryset.filter(
        is_active=True,
        board__is_active=True,
        board__in=accessible_boards(user),
    )


def user_can_view_board(user, board):
    return accessible_boards(user, KanbanBoard.objects.filter(pk=board.pk)).exists()


def user_can_edit_board(user, board):
    if user.is_superuser:
        return True
    if not user_can_view_board(user, board):
        return False
    rules = KanbanBoardAccess.objects.filter(board=board, user=user, is_active=True)
    if KanbanBoardAccess.objects.filter(board=board, is_active=True).exists():
        return rules.filter(role__in={"editor", "manager"}).exists()
    return True


def filter_values(params):
    operator_id = params.get("operator", "")
    priority = params.get("priority", "")
    try:
        operator = (
            Operator.objects.filter(pk=operator_id, is_active=True).first()
            if operator_id
            else None
        )
    except (ValueError, TypeError, ValidationError):
        operator = None
    if priority not in dict(KanbanTask.PRIORITIES):
        priority = ""
    return operator, priority


def board_for_user(user, board_id=None):
    boards = accessible_boards(user)
    if not board_id:
        return boards.first()
    try:
        return boards.filter(pk=board_id).first() or boards.first()
    except (ValueError, TypeError, ValidationError):
        return boards.first()


def visible_tasks_for_board(board, params):
    operator, priority = filter_values(params)
    state = params.get("state") if params.get("state") in dict(KanbanStage.STATUS_TYPES) else ""
    label = params.get("label")
    try:
        if label:
            UUID(str(label))
    except (ValueError, TypeError):
        label = ""
    query = params.get("q", "").strip()
    tasks = board.tasks.filter(is_active=True).select_related("board", "stage", "assigned_to").prefetch_related("labels", "checklist_items")
    if operator:
        tasks = tasks.filter(assigned_to=operator)
    if priority:
        tasks = tasks.filter(priority=priority)
    if state:
        tasks = tasks.filter(stage__status_type=state)
    if label:
        tasks = tasks.filter(labels__id=label)
    if query:
        tasks = tasks.filter(title__icontains=query)
    return tasks.order_by("order", "created_at")


def build_stage_data(board, params):
    return [
        {"stage": stage, "tasks": visible_tasks_for_board(board, params).filter(stage=stage)}
        for stage in board.stages.filter(is_active=True).order_by("order")
    ]


def task_row(task):
    total = getattr(task, "checklist_total_value", task.checklist_total)
    completed = getattr(task, "checklist_completed_value", task.checklist_completed)
    progress = round(completed * 100 / total) if total else 0
    return [
        task.title,
        task.board.name,
        task.stage.get_status_type_display(),
        ", ".join(label.name for label in task.labels.all()),
        task.assigned_to.full_name if task.assigned_to else "",
        task.get_priority_display(),
        task.due_date.isoformat() if task.due_date else "",
        f"{progress}%" if total else "No steps",
    ]
