from django.urls import path

from apps.reporting.views import (
    ExecutiveBriefView,
    MonthlyReportView,
    ReportApprove,
    ReportDraftCreate,
    ReportNarrativeUpdate,
    ReportTemplateUpdate,
)

urlpatterns = [
    path("monthly/", MonthlyReportView.as_view(), name="monthly-report"),
    # LV-235: la hoja de una página, del mismo payload y con el mismo permiso de
    # lectura: nombra las mismas faenas y su habilitación.
    path(
        "monthly/brief/",
        ExecutiveBriefView.as_view(),
        name="monthly-report-brief",
    ),
    path("monthly/draft/", ReportDraftCreate.as_view(), name="monthly-report-draft"),
    # LV-249: los bloques editables — portada, fases del plan y matriz.
    path(
        "monthly/template/",
        ReportTemplateUpdate.as_view(),
        name="monthly-report-template",
    ),
    path(
        "monthly/<uuid:pk>/narrative/",
        ReportNarrativeUpdate.as_view(),
        name="monthly-report-narrative",
    ),
    path(
        "monthly/<uuid:pk>/approve/",
        ReportApprove.as_view(),
        name="monthly-report-approve",
    ),
]
