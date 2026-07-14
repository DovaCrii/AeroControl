from django.urls import path
from . import views
urlpatterns=[path("records/",views.MaintenanceRecordList.as_view(),name="maintenance-list"),path("records/new/",views.MaintenanceRecordCreate.as_view(),name="maintenance-create"),path("history/",views.MaintenanceHistoryList.as_view(),name="history-list")]
