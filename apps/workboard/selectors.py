"""Reusable Workboard read and access selectors.

These functions intentionally contain the compatibility-tenancy rules in one
place so HTML, HTMX, exports and API consumers cannot drift apart.
"""

from uuid import UUID

from django.db.models import Q
from django.core.exceptions import ValidationError
from django.utils import timezone

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


def drag_enabled(params):
    """Whether drag-and-drop ordering is active for these filter params.

    Must mirror the client check in kanban.html's initSortables exactly: the
    JS disables dragging for operator, priority, state, label and q, but the
    server flag only knew about the first two, so filtering by state, label or
    text silently froze the board with no notice - it just looked broken.
    """
    return not any(
        params.get(name, "").strip()
        for name in ("operator", "priority", "state", "label", "q")
    )


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


def operator_for_user(user):
    """B3.2: the operator record linked to this login, or None.

    A plain attribute lookup (``user.operator_profile``) raises on the
    reverse side of a OneToOneField when unset -- this is the query form so
    "no linked operator" is just None, not an exception to catch everywhere.
    """
    return Operator.objects.filter(user=user, is_active=True).first()


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
    state = (
        params.get("state")
        if params.get("state") in dict(KanbanStage.STATUS_TYPES)
        else ""
    )
    label = params.get("label")
    try:
        if label:
            UUID(str(label))
    except (ValueError, TypeError):
        label = ""
    query = params.get("q", "").strip()
    tasks = (
        board.tasks.filter(is_active=True)
        .select_related("board", "stage", "assigned_to")
        .prefetch_related("labels", "checklist_items")
    )
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
    """Stage columns with their tasks, from one task query.

    Filtering per stage re-ran the whole filtered queryset (plus its two
    prefetches) once per column: ~18 queries for a default six-stage board,
    on the partial that re-renders with every drag and filter change. One
    query, grouped in Python, keeps the render cost flat.
    """
    today = timezone.localdate()
    tasks_by_stage = {}
    for task in visible_tasks_for_board(board, params):
        tasks_by_stage.setdefault(task.stage_id, []).append(task)
    stage_rows = []
    for stage in board.stages.filter(is_active=True).order_by("order"):
        tasks = tasks_by_stage.get(stage.pk, [])
        stage_rows.append(
            {
                "stage": stage,
                "tasks": tasks,
                # B3.4: overdue count alongside the existing total, so a
                # loaded column ("47 tasks") also shows how many of those are
                # actually late, without opening every card.
                "overdue_count": sum(
                    1 for task in tasks if task.due_date and task.due_date < today
                ),
                # B3.5: a soft cap -- warns in the header, never blocks the
                # drop (MoveTaskView/QuickTaskCreate do not check this).
                "over_wip_limit": (
                    stage.wip_limit is not None and len(tasks) > stage.wip_limit
                ),
            }
        )
    return stage_rows


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
