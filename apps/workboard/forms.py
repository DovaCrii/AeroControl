from django import forms
from apps.core.models import OperationalTenant
from apps.core.forms import AeroModelForm

from .models import KanbanBoard, KanbanChecklistItem, KanbanLabel, KanbanStage, KanbanTask


class KanbanBoardForm(AeroModelForm):
    class Meta:
        model = KanbanBoard
        fields = ["name", "description", "tenant"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tenant"].required = False
        self.fields["tenant"].queryset = OperationalTenant.objects.filter(is_active=True)


class KanbanStageForm(AeroModelForm):
    status_type = forms.ChoiceField(choices=KanbanStage.STATUS_TYPES, required=False)
    class Meta:
        model = KanbanStage
        fields = ["board", "name", "order", "color", "status_type"]


class KanbanTaskForm(AeroModelForm):
    labels = forms.ModelMultipleChoiceField(queryset=KanbanLabel.objects.none(), required=False)
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
            "labels",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        board_id = self.data.get("board") or getattr(self.instance, "board_id", None)
        if board_id:
            self.fields["stage"].queryset = KanbanStage.objects.filter(board_id=board_id, is_active=True)
            self.fields["labels"].queryset = KanbanLabel.objects.filter(board_id=board_id, is_active=True)
        self.fields["board"].queryset = KanbanBoard.objects.filter(is_active=True)

    def clean(self):
        cleaned = super().clean()
        board = cleaned.get("board")
        stage = cleaned.get("stage")
        if board and stage and stage.board_id != board.id:
            self.add_error("stage", "The stage must belong to the selected board.")
        return cleaned


class KanbanLabelForm(AeroModelForm):
    class Meta:
        model = KanbanLabel
        fields = ["board", "name", "color", "order"]


class KanbanChecklistItemForm(AeroModelForm):
    class Meta:
        model = KanbanChecklistItem
        fields = ["title", "order"]
