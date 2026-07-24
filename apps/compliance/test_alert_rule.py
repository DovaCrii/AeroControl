import pytest
from django.core.exceptions import ValidationError

from apps.workboard.models import KanbanBoard, KanbanStage
from .models import AlertRule


def _rule(**kwargs):
    defaults = dict(
        name="Doc expiry",
        entity_type="document",
        field_to_watch="expiry_date",
    )
    defaults.update(kwargs)
    return AlertRule(**defaults)


@pytest.mark.django_db
def test_create_kanban_task_requires_board_and_stage():
    rule = _rule(create_kanban_task=True)
    with pytest.raises(ValidationError):
        rule.clean()


@pytest.mark.django_db
def test_stage_must_belong_to_board():
    board_a = KanbanBoard.objects.create(name="A")
    board_b = KanbanBoard.objects.create(name="B")
    stage_b = KanbanStage.objects.create(board=board_b, name="Stage B")
    rule = _rule(create_kanban_task=True, target_board=board_a, target_stage=stage_b)
    with pytest.raises(ValidationError):
        rule.clean()


@pytest.mark.django_db
def test_valid_kanban_rule_passes_clean():
    board = KanbanBoard.objects.create(name="Compliance")
    stage = KanbanStage.objects.create(board=board, name="To do")
    rule = _rule(create_kanban_task=True, target_board=board, target_stage=stage)
    rule.clean()  # should not raise


@pytest.mark.django_db
def test_rule_without_kanban_task_ignores_board_and_stage():
    rule = _rule(create_kanban_task=False)
    rule.clean()  # should not raise even without board/stage
