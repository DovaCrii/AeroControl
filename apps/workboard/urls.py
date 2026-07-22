from django.urls import path
from . import views

urlpatterns = [
    # Existing CRUD
    path("", views.KanbanBoardView.as_view(), name="kanban"),
    path("tasks/new/", views.TaskCreate.as_view(), name="task-create"),
    path("tasks/", views.TaskList.as_view(), name="task-list"),
    path("list/", views.KanbanTaskListView.as_view(), name="workboard-list"),
    path("reports/tasks.csv", views.TaskReportCsvView.as_view(), name="task-report-csv"),
    path("reports/tasks.xlsx", views.TaskReportXlsxView.as_view(), name="task-report-xlsx"),
    path("boards/", views.BoardList.as_view(), name="board-list"),
    path("boards/new/", views.BoardCreate.as_view(), name="board-create"),
    path("stages/new/", views.StageCreate.as_view(), name="stage-create"),
    path("boards/<uuid:pk>/archive/", views.BoardArchiveView.as_view(), name="board-archive"),
    # Kanban endpoints
    path("_board/", views.BoardPartialView.as_view(), name="kanban-board-partial"),
    path("tasks/<uuid:pk>/move/", views.MoveTaskView.as_view(), name="task-move"),
    path("tasks/<uuid:pk>/archive/", views.TaskArchiveView.as_view(), name="task-archive"),
    path("tasks/<uuid:pk>/detail/", views.TaskDetailView.as_view(), name="task-detail"),
    path("tasks/<uuid:pk>/edit/", views.TaskEditView.as_view(), name="task-edit"),
    path("tasks/<uuid:pk>/checklist/", views.ChecklistItemCreate.as_view(), name="checklist-create"),
    path("checklist/<uuid:pk>/toggle/", views.ChecklistItemToggle.as_view(), name="checklist-toggle"),
    path("labels/", views.LabelList.as_view(), name="label-list"),
    path("labels/new/", views.LabelCreate.as_view(), name="label-create"),
    path("tasks/quick/", views.QuickTaskCreate.as_view(), name="task-quick"),
    path("_boards/", views.BoardSelector.as_view(), name="board-selector"),
]
