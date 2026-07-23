from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.conf.urls.i18n import set_language
from django.urls import include, path

from apps.operations.views import CalendarView
from apps.core.views import AlertCountPartial, GlobalSearchView, HealthCheckView
from apps.workboard.views import ApiIndexView
from apps.workboard.api import KanbanTaskApiView, api_openapi_schema
from rest_framework.authtoken.views import obtain_auth_token

admin.site.site_header = "AeroControl Administration"
admin.site.site_title = "AeroControl"
admin.site.index_title = "Administration"

urlpatterns = [
    path("admin/", admin.site.urls),
    path(
        "accounts/login/",
        auth_views.LoginView.as_view(template_name="registration/login.html"),
        name="login",
    ),
    path(
        "accounts/logout/",
        auth_views.LogoutView.as_view(next_page="/accounts/login/"),
        name="logout",
    ),
    path("i18n/setlang/", set_language, name="set_language"),
    path("alerts/count/", AlertCountPartial.as_view(), name="alert-count"),
    path("health/", HealthCheckView.as_view(), name="health"),
    path("search/", GlobalSearchView.as_view(), name="global-search"),
    path("api/v1/workboard/tasks/", KanbanTaskApiView.as_view({"get": "list"}), name="api-v1-workboard-tasks"),
    path("api/v1/", ApiIndexView.as_view(), name="api-v1-index"),
    path("api/drf/v1/workboard/tasks/", KanbanTaskApiView.as_view({"get": "list"}), name="api-drf-v1-workboard-tasks"),
    path("api-token/", obtain_auth_token, name="api-token"),
    path("api/v1/openapi.json", api_openapi_schema, name="api-v1-openapi"),
    path("api/v1/workboard/tasks/<uuid:pk>/", KanbanTaskApiView.as_view({"patch": "partial_update"}), name="api-v1-workboard-task-update"),
    path("", include("apps.dashboard.urls")),
    path("registry/", include("apps.registry.urls")),
    path("compliance/", include("apps.compliance.urls")),
    path("operations/", include("apps.operations.urls")),
    path("calendar/", CalendarView.as_view(), name="calendar"),
    path("maintenance/", include("apps.maintenance.urls")),
    path("workboard/", include("apps.workboard.urls")),
]
