import pytest
from django.core.management import call_command

from apps.workboard.models import KanbanBoard, KanbanLabel, KanbanStage


@pytest.mark.django_db
def test_init_dgac_board_creates_board_stages_and_labels():
    call_command("init_dgac_board")

    board = KanbanBoard.objects.get(name="Cumplimiento DGAC")
    assert board.stages.count() == 6
    assert board.labels.count() == 5
    # Stage ordering and a completed-type stage exist (needed by Alert.resolve)
    assert board.stages.filter(status_type="completed").exists()
    first = board.stages.order_by("order").first()
    assert first.name == "Por vencer"


@pytest.mark.django_db
def test_init_dgac_board_is_idempotent():
    call_command("init_dgac_board")
    call_command("init_dgac_board")

    assert KanbanBoard.objects.filter(name="Cumplimiento DGAC").count() == 1
    board = KanbanBoard.objects.get(name="Cumplimiento DGAC")
    assert board.stages.count() == 6
    assert KanbanStage.objects.filter(board=board).count() == 6
    assert KanbanLabel.objects.filter(board=board).count() == 5
