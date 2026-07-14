from django.urls import path
from . import views
urlpatterns=[path("permissions/",views.FlightPermissionList.as_view(),name="permission-list"),path("permissions/new/",views.FlightPermissionCreate.as_view(),name="permission-create"),path("records/",views.FlightRecordList.as_view(),name="record-list"),path("records/new/",views.FlightRecordCreate.as_view(),name="record-create")]
