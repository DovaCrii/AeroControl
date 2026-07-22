from django.contrib import admin
from .models import KanbanBoard, KanbanChecklistItem, KanbanLabel, KanbanStage, KanbanTask, KanbanTaskLabel

admin.site.register([KanbanBoard, KanbanStage, KanbanTask, KanbanLabel, KanbanTaskLabel, KanbanChecklistItem])
