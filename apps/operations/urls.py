from django.urls import path
from . import views

urlpatterns = [
    # Permission
    path("permissions/", views.FlightPermissionList.as_view(), name="permission-list"),
    path(
        "permissions/new/",
        views.FlightPermissionCreate.as_view(),
        name="permission-create",
    ),
    path(
        "permissions/<uuid:pk>/",
        views.FlightPermissionDetail.as_view(),
        name="permission-detail",
    ),
    path(
        "permissions/<uuid:pk>/edit/",
        views.FlightPermissionUpdate.as_view(),
        name="permission-update",
    ),
    path(
        "permissions/<uuid:pk>/approve/",
        views.FlightPermissionApprove.as_view(),
        name="permission-approve",
    ),
    path(
        "permissions/<uuid:pk>/deny/",
        views.FlightPermissionDeny.as_view(),
        name="permission-deny",
    ),
    path(
        "permissions/<uuid:pk>/complete/",
        views.FlightPermissionComplete.as_view(),
        name="permission-complete",
    ),
    # LV-101: correcting a wrongly recorded status, with a reason on record.
    # Separate from the transitions above because it is a different act: those
    # say what happened next, this says what was written down was wrong.
    path(
        "permissions/<uuid:pk>/correct-status/",
        views.FlightPermissionCorrectStatus.as_view(),
        name="permission-correct-status",
    ),
    # Flight Records
    path("records/", views.FlightRecordList.as_view(), name="record-list"),
    path("records/new/", views.FlightRecordCreate.as_view(), name="record-create"),
    path(
        "records/<uuid:pk>/", views.FlightRecordDetail.as_view(), name="record-detail"
    ),
    path(
        "records/<uuid:pk>/delete/",
        views.FlightRecordDelete.as_view(),
        name="record-delete",
    ),
    path("calendar/", views.CalendarView.as_view(), name="ops-calendar"),
]
