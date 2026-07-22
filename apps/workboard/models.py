from django.db import models
from django.utils.translation import gettext_lazy as _
from apps.core.models import BaseModel
from apps.registry.models import Operator


class KanbanBoard(BaseModel):
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name


class KanbanStage(BaseModel):
    STATUS_TYPES = [
        ("pending", _("Pending")),
        ("planned", _("Planned")),
        ("in_progress", _("In progress")),
        ("blocked", _("Blocked")),
        ("review", _("In review")),
        ("completed", _("Completed")),
        ("custom", _("Custom")),
    ]
    board = models.ForeignKey(
        KanbanBoard, on_delete=models.CASCADE, related_name="stages"
    )
    name = models.CharField(max_length=100)
    order = models.PositiveIntegerField(default=0)
    color = models.CharField(max_length=20, default="#2EC4B6")
    status_type = models.CharField(max_length=20, choices=STATUS_TYPES, default="custom")


class KanbanLabel(BaseModel):
    board = models.ForeignKey(KanbanBoard, on_delete=models.CASCADE, related_name="labels")
    name = models.CharField(max_length=80)
    color = models.CharField(max_length=20, default="#2EC4B6")
    order = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["board", "name"], name="unique_board_label_name")]

    def __str__(self):
        return self.name


class KanbanTask(BaseModel):
    PRIORITIES = [
        ("low", _("Low")),
        ("medium", _("Medium")),
        ("high", _("High")),
        ("critical", _("Critical")),
    ]
    board = models.ForeignKey(
        KanbanBoard, on_delete=models.CASCADE, related_name="tasks"
    )
    stage = models.ForeignKey(
        KanbanStage, on_delete=models.PROTECT, related_name="tasks"
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    assigned_to = models.ForeignKey(
        Operator, on_delete=models.SET_NULL, null=True, blank=True
    )
    due_date = models.DateField(null=True, blank=True)
    priority = models.CharField(max_length=20, choices=PRIORITIES, default="medium")
    order = models.PositiveIntegerField(default=0)
    created_by = models.CharField(max_length=150, blank=True)
    labels = models.ManyToManyField(KanbanLabel, through="KanbanTaskLabel", blank=True, related_name="tasks")

    @property
    def checklist_total(self):
        return self.checklist_items.count()

    @property
    def checklist_completed(self):
        return self.checklist_items.filter(is_completed=True).count()

    @property
    def checklist_progress(self):
        total = self.checklist_total
        return round(self.checklist_completed * 100 / total) if total else 0


class KanbanTaskLabel(BaseModel):
    task = models.ForeignKey(KanbanTask, on_delete=models.CASCADE)
    label = models.ForeignKey(KanbanLabel, on_delete=models.CASCADE)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["task", "label"], name="unique_task_label")]


class KanbanChecklistItem(BaseModel):
    task = models.ForeignKey(KanbanTask, on_delete=models.CASCADE, related_name="checklist_items")
    title = models.CharField(max_length=200)
    order = models.PositiveIntegerField(default=0)
    is_completed = models.BooleanField(default=False)

    class Meta:
        ordering = ["order", "created_at"]
