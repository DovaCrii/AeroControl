from django.contrib import admin
from .models import KanbanBoard,KanbanStage,KanbanTask
admin.site.register([KanbanBoard,KanbanStage,KanbanTask])
