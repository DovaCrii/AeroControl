from django.urls import path
from . import views
urlpatterns=[path("",views.TaskList.as_view(),name="task-list"),path("tasks/new/",views.TaskCreate.as_view(),name="task-create"),path("boards/",views.BoardList.as_view(),name="board-list"),path("boards/new/",views.BoardCreate.as_view(),name="board-create")]
