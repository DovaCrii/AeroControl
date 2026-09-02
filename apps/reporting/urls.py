from django.urls import path

from apps.reporting.views import MonthlyReportView

urlpatterns = [
    path("monthly/", MonthlyReportView.as_view(), name="monthly-report"),
]
