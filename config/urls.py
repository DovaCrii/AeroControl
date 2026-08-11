from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.conf.urls.i18n import set_language
from django.urls import include, path

from apps.operations.views import CalendarView
from apps.core.views import (
    AdministrationCenterView,
    AlertCountPartial,
    AuditEventListView,
    CspReportView,
    GlobalSearchView,
    HealthCheckView,
    UnifiedCalendarEventsView,
    UserRoleListView,
)
from apps.workboard.views import ApiIndexView
from apps.workboard.api import (
    KanbanTaskApiView,
    ThrottledObtainAuthToken,
    api_openapi_schema,
)
from apps.geo.api import (
    GeoPlanExportView,
    GeoPlanMetaView,
    GeoPlanResourceView,
    GeoPlanRestoreView,
    GeoPlanVersionContentView,
    GeoPlanVersionsView,
)
from apps.registry.api import AircraftPadronViewSet

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
    # V.12: password change inside the app, so an operator never needs the
    # technical /admin/ to rotate their own credential.
    path(
        "accounts/password_change/",
        auth_views.PasswordChangeView.as_view(
            template_name="registration/password_change_form.html"
        ),
        name="password_change",
    ),
    path(
        "accounts/password_change/done/",
        auth_views.PasswordChangeDoneView.as_view(
            template_name="registration/password_change_done.html"
        ),
        name="password_change_done",
    ),
    path("i18n/setlang/", set_language, name="set_language"),
    path("alerts/count/", AlertCountPartial.as_view(), name="alert-count"),
    path("health/", HealthCheckView.as_view(), name="health"),
    path("csp-report/", CspReportView.as_view(), name="csp-report"),
    path(
        "calendar/events/", UnifiedCalendarEventsView.as_view(), name="calendar-events"
    ),
    path("administracion/", AdministrationCenterView.as_view(), name="administration"),
    path(
        "administracion/auditoria/",
        AuditEventListView.as_view(),
        name="audit-log",
    ),
    path(
        "administracion/usuarios/",
        UserRoleListView.as_view(),
        name="user-role-list",
    ),
    path("search/", GlobalSearchView.as_view(), name="global-search"),
    path(
        "api/v1/workboard/tasks/",
        KanbanTaskApiView.as_view({"get": "list"}),
        name="api-v1-workboard-tasks",
    ),
    path("api/v1/", ApiIndexView.as_view(), name="api-v1-index"),
    path(
        "api/drf/v1/workboard/tasks/",
        KanbanTaskApiView.as_view({"get": "list"}),
        name="api-drf-v1-workboard-tasks",
    ),
    path("api-token/", ThrottledObtainAuthToken.as_view(), name="api-token"),
    path("api/v1/openapi.json", api_openapi_schema, name="api-v1-openapi"),
    path(
        "api/v1/workboard/tasks/<uuid:pk>/",
        KanbanTaskApiView.as_view({"patch": "partial_update"}),
        name="api-v1-workboard-task-update",
    ),
    path(
        "api/v1/geo/plans/<uuid:pk>/",
        GeoPlanMetaView.as_view(),
        name="api-v1-geo-plan",
    ),
    path(
        "api/v1/geo/plans/<uuid:pk>/versions/",
        GeoPlanVersionsView.as_view(),
        name="api-v1-geo-plan-versions",
    ),
    path(
        "api/v1/geo/plans/<uuid:pk>/versions/<int:number>/content/",
        GeoPlanVersionContentView.as_view(),
        name="api-v1-geo-plan-version-content",
    ),
    path(
        "api/v1/geo/plans/<uuid:pk>/versions/<int:number>/restore/",
        GeoPlanRestoreView.as_view(),
        name="api-v1-geo-plan-version-restore",
    ),
    path(
        "api/v1/geo/plans/<uuid:pk>/export/",
        GeoPlanExportView.as_view(),
        name="api-v1-geo-plan-export",
    ),
    path(
        "api/v1/geo/plans/<uuid:pk>/resource/",
        GeoPlanResourceView.as_view(),
        name="api-v1-geo-plan-resource",
    ),
    # X.3: read-only padrón for AeroLink. Only "list" and "retrieve" are
    # routed -- there is no write route to gate, by design (ADR-0002).
    path(
        "api/v1/registry/aircraft/",
        AircraftPadronViewSet.as_view({"get": "list"}),
        name="api-v1-registry-aircraft",
    ),
    path(
        "api/v1/registry/aircraft/<uuid:pk>/",
        AircraftPadronViewSet.as_view({"get": "retrieve"}),
        name="api-v1-registry-aircraft-detail",
    ),
    path("", include("apps.dashboard.urls")),
    path("registry/", include("apps.registry.urls")),
    path("compliance/", include("apps.compliance.urls")),
    path("operations/", include("apps.operations.urls")),
    path("calendar/", CalendarView.as_view(), name="calendar"),
    path("maintenance/", include("apps.maintenance.urls")),
    path("workboard/", include("apps.workboard.urls")),
    path("geo/", include("apps.geo.urls")),
]
