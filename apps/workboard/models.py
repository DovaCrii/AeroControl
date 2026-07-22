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
    board = models.ForeignKey(
        KanbanBoard, on_delete=models.CASCADE, related_name="stages"
    )
    name = models.CharField(max_length=100)
    order = models.PositiveIntegerField(default=0)
    color = models.CharField(max_length=20, default="#2EC4B6")


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
