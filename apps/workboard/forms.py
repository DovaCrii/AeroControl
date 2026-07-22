from django import forms

from .models import KanbanBoard, KanbanStage, KanbanTask


class KanbanBoardForm(forms.ModelForm):
    class Meta:
        model = KanbanBoard
        fields = ["name", "description"]


class KanbanStageForm(forms.ModelForm):
    class Meta:
        model = KanbanStage
        fields = ["board", "name", "order", "color"]


class KanbanTaskForm(forms.ModelForm):
    class Meta:
        model = KanbanTask
        fields = [
            "board",
            "stage",
            "title",
            "description",
            "assigned_to",
            "due_date",
            "priority",
            "order",
        ]

    def clean(self):
        cleaned = super().clean()
        board = cleaned.get("board")
        stage = cleaned.get("stage")
        if board and stage and stage.board_id != board.id:
            self.add_error("stage", "The stage must belong to the selected board.")
        return cleaned
