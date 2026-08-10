from django.urls import path
from . import views

urlpatterns = [
    path("records/", views.MaintenanceRecordList.as_view(), name="maintenance-list"),
    path(
        "records/new/",
        views.MaintenanceRecordCreate.as_view(),
        name="maintenance-create",
    ),
    path(
        "records/<uuid:pk>/",
        views.MaintenanceRecordDetail.as_view(),
        name="maintenance-detail",
    ),
    path(
        "records/<uuid:pk>/start/",
        views.MaintenanceStart.as_view(),
        name="maintenance-start",
    ),
    path(
        "records/<uuid:pk>/send/",
        views.MaintenanceSend.as_view(),
        name="maintenance-send",
    ),
    path(
        "records/<uuid:pk>/arrive-at-workshop/",
        views.MaintenanceArriveAtWorkshop.as_view(),
        name="maintenance-arrive-at-workshop",
    ),
    path(
        "records/<uuid:pk>/finish/",
        views.MaintenanceFinish.as_view(),
        name="maintenance-finish",
    ),
    path(
        "records/<uuid:pk>/depart/",
        views.MaintenanceDepart.as_view(),
        name="maintenance-depart",
    ),
    path(
        "records/<uuid:pk>/complete/",
        views.MaintenanceComplete.as_view(),
        name="maintenance-complete",
    ),
    path("history/", views.MaintenanceHistoryList.as_view(), name="history-list"),
    path(
        "aircraft/<uuid:pk>/incident/",
        views.AircraftReportIncident.as_view(),
        name="aircraft-report-incident",
    ),
]
