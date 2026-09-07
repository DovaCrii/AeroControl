from django.urls import path
from . import report_views, views
from .models import Alert, NonConformity

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
    path(
        "report/pdf/",
        report_views.ComplianceReportPdfView.as_view(),
        name="compliance-report-pdf",
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
    # LV-200 paso 3: adjuntar un papel ya cargado. Vive al lado de "nuevo"
    # porque es la otra mitad de la misma acción -- dejar el documento en la
    # ficha--, y lo que cambia es de dónde sale el archivo.
    path(
        "document/attach/",
        views.DocumentAttachExisting.as_view(),
        name="document-attach-existing",
    ),
    # LV-86: several files onto one record in a single action.
    path(
        "document/upload-batch/",
        views.DocumentBulkUpload.as_view(),
        name="document-bulk-upload",
    ),
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
    # LV-85: the same bytes, served for viewing inside the page instead of as a
    # download. Same permission and tenant scope as the download above.
    path(
        "document/<uuid:pk>/preview/",
        views.DocumentPreview.as_view(),
        name="document-preview",
    ),
    # LV-92: the same bytes as document-preview, wrapped in the generic modal so
    # a folder can be reviewed without leaving the record's page.
    path(
        "document/<uuid:pk>/preview-frame/",
        views.DocumentPreviewFrame.as_view(),
        name="document-preview-frame",
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
    # UX-14: el dueño. Una sola vista para los dos modelos —es la misma acción
    # sobre el mismo campo— y el modelo lo fija la ruta, así que el permiso que
    # se pide sale de ahí y no de una condición dentro de la vista.
    path(
        "alert/<uuid:pk>/assign/",
        views.AssignOwner.as_view(model=Alert),
        name="alert-assign",
    ),
    path(
        "nonconformity/<uuid:pk>/assign/",
        views.AssignOwner.as_view(model=NonConformity),
        name="nonconformity-assign",
    ),
    # R7.4: deliverable quality control (ISO 9001 8.5.1/8.6).
    path("deliverable/", views.DeliverableList.as_view(), name="deliverable-list"),
    path(
        "deliverable/new/",
        views.DeliverableCreate.as_view(),
        name="deliverable-create",
    ),
    path(
        "deliverable/<uuid:pk>/",
        views.DeliverableDetail.as_view(),
        name="deliverable-detail",
    ),
    path(
        "deliverable/<uuid:pk>/edit/",
        views.DeliverableUpdate.as_view(),
        name="deliverable-update",
    ),
    path(
        "deliverable/<uuid:pk>/validate/",
        views.DeliverableValidate.as_view(),
        name="deliverable-validate",
    ),
    path(
        "deliverable/<uuid:pk>/release/",
        views.DeliverableRelease.as_view(),
        name="deliverable-release",
    ),
    path(
        "deliverable/<uuid:pk>/reject/",
        views.DeliverableReject.as_view(),
        name="deliverable-reject",
    ),
    # R7.6: non-conformities (ISO 10.2).
    path(
        "nonconformity/",
        views.NonConformityList.as_view(),
        name="nonconformity-list",
    ),
    path(
        "nonconformity/new/",
        views.NonConformityCreate.as_view(),
        name="nonconformity-create",
    ),
    path(
        "nonconformity/<uuid:pk>/",
        views.NonConformityDetail.as_view(),
        name="nonconformity-detail",
    ),
    path(
        "nonconformity/<uuid:pk>/edit/",
        views.NonConformityUpdate.as_view(),
        name="nonconformity-update",
    ),
    path(
        "nonconformity/<uuid:pk>/close/",
        views.NonConformityClose.as_view(),
        name="nonconformity-close",
    ),
    path(
        "nonconformity/<uuid:pk>/reopen/",
        views.NonConformityReopen.as_view(),
        name="nonconformity-reopen",
    ),
    path(
        "nonconformity/<uuid:pk>/verify-effectiveness/",
        views.NonConformityVerifyEffectiveness.as_view(),
        name="nonconformity-verify-effectiveness",
    ),
    path("alert/<uuid:pk>/reopen/", views.AlertReopen.as_view(), name="alert-reopen"),
    # R7.6: effectiveness verification of a corrective action (ISO 10.2).
    path(
        "alert/<uuid:pk>/verify-effectiveness/",
        views.AlertVerifyEffectiveness.as_view(),
        name="alert-verify-effectiveness",
    ),
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
