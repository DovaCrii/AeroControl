from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from apps.operations.views import CalendarView
from apps.core.views import AlertCountPartial

admin.site.site_header = "AeroOps Desk Administration"
admin.site.site_title = "AeroOps Desk"
admin.site.index_title = "Administration"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/login/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(next_page="/accounts/login/"), name="logout"),
    path("alerts/count/", AlertCountPartial.as_view(), name="alert-count"),
    path("", include("apps.dashboard.urls")),
    path("registry/", include("apps.registry.urls")),
    path("compliance/", include("apps.compliance.urls")),
    path("operations/", include("apps.operations.urls")),
    path("calendar/", CalendarView.as_view(), name="calendar"),
    path("maintenance/", include("apps.maintenance.urls")),
    path("workboard/", include("apps.workboard.urls")),
]
