from django.contrib import admin
from .models import KanbanBoard, KanbanBoardAccess, KanbanChecklistItem, KanbanLabel, KanbanStage, KanbanTask, KanbanTaskLabel

admin.site.register([KanbanBoard, KanbanBoardAccess, KanbanStage, KanbanTask, KanbanLabel, KanbanTaskLabel, KanbanChecklistItem])
