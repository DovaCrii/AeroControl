from django.urls import path
from . import report_views, views

urlpatterns = [
    path(
        "report/", report_views.ComplianceReportView.as_view(), name="compliance-report"
    ),
    path(
        "report/csv/",
        report_views.ComplianceReportCsvView.as_view(),
        name="compliance-report-csv",
    ),
    path(
        "report/xlsx/",
        report_views.ComplianceReportXlsxView.as_view(),
        name="compliance-report-xlsx",
    ),
    path(
        "report/docx/",
        report_views.ComplianceReportDocxView.as_view(),
        name="compliance-report-docx",
    ),
    path("document/", views.DocumentList.as_view(), name="document-list"),
    path(
        "company-documents/",
        views.CompanyDocumentsView.as_view(),
        name="company-documents",
    ),
    path(
        "operational-records/",
        views.OperationalRecordsView.as_view(),
        name="operational-records",
    ),
    path(
        "monthly-review/",
        views.MonthlyReviewView.as_view(),
        name="monthly-review",
    ),
    path(
        "monthly-review/<uuid:pk>/mark/",
        views.MonthlyReviewMark.as_view(),
        name="monthly-review-mark",
    ),
    path("document/new/", views.DocumentCreate.as_view(), name="document-create"),
    path(
        "document/entity-options/",
        views.DocumentEntityOptions.as_view(),
        name="document-entity-options",
    ),
    path("document/<uuid:pk>/", views.DocumentDetail.as_view(), name="document-detail"),
    path(
        "document/<uuid:pk>/download/",
        views.DocumentDownload.as_view(),
        name="document-download",
    ),
    path(
        "document/<uuid:pk>/replace/",
        views.DocumentReplace.as_view(),
        name="document-replace",
    ),
    path(
        "document/<uuid:pk>/delete/",
        views.DocumentDelete.as_view(),
        name="document-delete",
    ),
    path("alert/", views.AlertList.as_view(), name="alert-list"),
    path(
        "alert/<uuid:pk>/resolve/", views.AlertResolve.as_view(), name="alert-resolve"
    ),
    path("alert/<uuid:pk>/reopen/", views.AlertReopen.as_view(), name="alert-reopen"),
    path(
        "alert/<uuid:pk>/create-task/",
        views.AlertCreateTask.as_view(),
        name="alert-create-task",
    ),
    path("alert/new/", views.AlertCreate.as_view(), name="alert-create"),
    path("documenttype/", views.DocumentTypeList.as_view(), name="documenttype-list"),
    path(
        "documenttype/new/",
        views.DocumentTypeCreate.as_view(),
        name="documenttype-create",
    ),
    path(
        "documenttype/<uuid:pk>/edit/",
        views.DocumentTypeUpdate.as_view(),
        name="documenttype-update",
    ),
    path("alertrule/", views.AlertRuleList.as_view(), name="alertrule-list"),
    path("alertrule/new/", views.AlertRuleCreate.as_view(), name="alertrule-create"),
    path(
        "alertrule/<uuid:pk>/edit/",
        views.AlertRuleUpdate.as_view(),
        name="alertrule-update",
    ),
]
