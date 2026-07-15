from django.urls import path
from . import views

urlpatterns = [
    # Permission
    path("permissions/", views.FlightPermissionList.as_view(), name="permission-list"),
    path("permissions/new/", views.FlightPermissionCreate.as_view(), name="permission-create"),
    path("permissions/<uuid:pk>/", views.FlightPermissionDetail.as_view(), name="permission-detail"),
    path("permissions/<uuid:pk>/approve/", views.FlightPermissionApprove.as_view(), name="permission-approve"),
    path("permissions/<uuid:pk>/deny/", views.FlightPermissionDeny.as_view(), name="permission-deny"),
    path("permissions/<uuid:pk>/complete/", views.FlightPermissionComplete.as_view(), name="permission-complete"),
    # Flight Records
    path("records/", views.FlightRecordList.as_view(), name="record-list"),
    path("records/new/", views.FlightRecordCreate.as_view(), name="record-create"),
    path("records/<uuid:pk>/", views.FlightRecordDetail.as_view(), name="record-detail"),
    path("records/<uuid:pk>/delete/", views.FlightRecordDelete.as_view(), name="record-delete"),
    path("calendar/", views.CalendarView.as_view(), name="ops-calendar"),
]
