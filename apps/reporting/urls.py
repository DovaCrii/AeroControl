from django.urls import path

from apps.reporting.views import (
    MonthlyReportView,
    ReportDraftCreate,
    ReportNarrativeUpdate,
)

urlpatterns = [
    path("monthly/", MonthlyReportView.as_view(), name="monthly-report"),
    path("monthly/draft/", ReportDraftCreate.as_view(), name="monthly-report-draft"),
    path(
        "monthly/<uuid:pk>/narrative/",
        ReportNarrativeUpdate.as_view(),
        name="monthly-report-narrative",
    ),
]
