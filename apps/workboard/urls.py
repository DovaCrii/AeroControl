from django.urls import path
from . import views

urlpatterns = [
    # Existing CRUD
    path("", views.KanbanBoardView.as_view(), name="kanban"),
    path("tasks/new/", views.TaskCreate.as_view(), name="task-create"),
    path("tasks/", views.TaskList.as_view(), name="task-list"),
    path("boards/", views.BoardList.as_view(), name="board-list"),
    path("boards/new/", views.BoardCreate.as_view(), name="board-create"),
    path("stages/new/", views.StageCreate.as_view(), name="stage-create"),
    path("boards/<uuid:pk>/archive/", views.BoardArchiveView.as_view(), name="board-archive"),
    # Kanban endpoints
    path("_board/", views.BoardPartialView.as_view(), name="kanban-board-partial"),
    path("tasks/<uuid:pk>/move/", views.MoveTaskView.as_view(), name="task-move"),
    path("tasks/<uuid:pk>/archive/", views.TaskArchiveView.as_view(), name="task-archive"),
    path("tasks/quick/", views.QuickTaskCreate.as_view(), name="task-quick"),
    path("_boards/", views.BoardSelector.as_view(), name="board-selector"),
]
