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
    # R9.5: solicitudes de vuelo SIGO. Una circunferencia por solicitud, que es
    # lo que el formulario del Estado acepta.
    path("requests/", views.FlightRequestList.as_view(), name="flight-request-list"),
    path(
        "requests/<uuid:pk>/",
        views.FlightRequestDetail.as_view(),
        name="flight-request-detail",
    ),
    path(
        "requests/<uuid:pk>/edit/",
        views.FlightRequestUpdate.as_view(),
        name="flight-request-update",
    ),
    path(
        "requests/<uuid:pk>/kmz/",
        views.FlightRequestKmz.as_view(),
        name="flight-request-kmz",
    ),
    path(
        "requests/<uuid:pk>/note/",
        views.FlightRequestAddNote.as_view(),
        name="flight-request-add-note",
    ),
    path(
        "requests/<uuid:pk>/work-item/",
        views.FlightRequestAddWorkItem.as_view(),
        name="flight-request-add-work-item",
    ),
    path(
        "requests/<uuid:pk>/work-item/<uuid:item_pk>/remove/",
        views.FlightRequestRemoveWorkItem.as_view(),
        name="flight-request-remove-work-item",
    ),
    path(
        "requests/<uuid:pk>/file/",
        views.FlightRequestFile.as_view(),
        name="flight-request-file",
    ),
    path(
        "requests/<uuid:pk>/link/",
        views.FlightRequestLink.as_view(),
        name="flight-request-link",
    ),
    path(
        "requests/<uuid:pk>/close/",
        views.FlightRequestClose.as_view(),
        name="flight-request-close",
    ),
    # Entra por el plan: separar es una acción sobre el KMZ madre, no sobre una
    # solicitud que todavía no existe.
    path(
        "plans/<uuid:pk>/split/",
        views.GeoPlanSplitIntoRequests.as_view(),
        name="geo-plan-split",
    ),
]
