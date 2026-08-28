from django.urls import path
from . import assessment_views, report_views, views

urlpatterns = []
urlpatterns += [
    # LV-145: el catastro de flota y personal. Va antes del bucle CRUD de abajo
    # para que `roster/` no quede a la sombra de un patrón genérico.
    path(
        "roster/",
        report_views.CatastroReportView.as_view(),
        name="registry-roster",
    ),
    path(
        "roster/pdf/",
        report_views.CatastroReportPdfView.as_view(),
        name="registry-roster-pdf",
    ),
    path(
        "roster/xlsx/",
        report_views.CatastroReportXlsxView.as_view(),
        name="registry-roster-xlsx",
    ),
    path(
        "roster/csv/",
        report_views.CatastroReportCsvView.as_view(),
        name="registry-roster-csv",
    ),
    # LV-158: la prueba de conocimientos. Va antes del bucle CRUD para que
    # `assessment/` no quede a la sombra de un patrón genérico.
    path(
        "assessment/take/",
        assessment_views.KnowledgeAssessmentTake.as_view(),
        name="assessment-take",
    ),
    path(
        "assessment/start/",
        assessment_views.KnowledgeAssessmentStart.as_view(),
        name="assessment-start",
    ),
    path(
        "assessment/<uuid:pk>/",
        assessment_views.KnowledgeAssessmentDetail.as_view(),
        name="assessment-detail",
    ),
    # LV-173: retirar un intento es **archivarlo**, nunca borrarlo. Van antes
    # del genérico por la misma razón que los de arriba.
    path(
        "assessment/<uuid:pk>/archive/",
        views.KnowledgeAssessmentArchive.as_view(),
        name="assessment-archive",
    ),
    path(
        "assessment/<uuid:pk>/restore/",
        views.KnowledgeAssessmentRestore.as_view(),
        name="assessment-restore",
    ),
    path(
        "costcenter/import/",
        views.CostCenterImportView.as_view(),
        name="costcenter-import",
    ),
    path(
        "costcenter/import/<uuid:pk>/revert/",
        views.CostCenterImportRevertView.as_view(),
        name="costcenter-import-revert",
    ),
    path(
        "aircraft/import/", views.AircraftImportView.as_view(), name="aircraft-import"
    ),
    path(
        "operator/import/", views.OperatorImportView.as_view(), name="operator-import"
    ),
    # OPS-1: read-only movement trail, not part of the per-model CRUD loop below.
    path(
        "resource-movements/",
        views.ResourceMovementLogList.as_view(),
        name="resourcemovementlog-list",
    ),
    # R7.2: read-only battery inventory (AeroLink is the master, ADR-0002), so
    # it is registered here rather than in the per-model CRUD loop below.
    path("battery/", views.BatteryList.as_view(), name="battery-list"),
    # LV-81: the insurance filing's transitions. Registered here and not in the
    # CRUD loop below because they advance `insurance_status`, a flow the
    # aircraft carries alongside its own condition, not the record's lifecycle.
    path(
        "aircraft/<uuid:pk>/insurance/pending/",
        views.AircraftInsurancePending.as_view(),
        name="aircraft-insurance-pending",
    ),
    path(
        "aircraft/<uuid:pk>/insurance/filed/",
        views.AircraftInsuranceFiled.as_view(),
        name="aircraft-insurance-filed",
    ),
    path(
        "aircraft/<uuid:pk>/insurance/active/",
        views.AircraftInsuranceActive.as_view(),
        name="aircraft-insurance-active",
    ),
    # B4.3: qualification-type catalog (config model, list/create/update only).
    path(
        "qualificationtype/",
        views.QualificationTypeList.as_view(),
        name="qualificationtype-list",
    ),
    path(
        "qualificationtype/new/",
        views.QualificationTypeCreate.as_view(),
        name="qualificationtype-create",
    ),
    path(
        "qualificationtype/<uuid:pk>/edit/",
        views.QualificationTypeUpdate.as_view(),
        name="qualificationtype-update",
    ),
]
for name in (
    "CostCenter",
    "Aircraft",
    "Operator",
    "Assignment",
    "OperatorAssignment",
    "AircraftAssignment",
    "Qualification",
):
    lower = name.lower()
    urlpatterns += [
        path(
            f"{lower}/", getattr(views, f"{name}List").as_view(), name=f"{lower}-list"
        ),
        path(
            f"{lower}/new/",
            getattr(views, f"{name}Create").as_view(),
            name=f"{lower}-create",
        ),
        path(
            f"{lower}/<uuid:pk>/",
            getattr(views, f"{name}Detail").as_view(),
            name=f"{lower}-detail",
        ),
        path(
            f"{lower}/<uuid:pk>/edit/",
            getattr(views, f"{name}Update").as_view(),
            name=f"{lower}-update",
        ),
        path(
            f"{lower}/<uuid:pk>/archive/",
            getattr(views, f"{name}Archive").as_view(),
            name=f"{lower}-archive",
        ),
        path(
            f"{lower}/<uuid:pk>/restore/",
            getattr(views, f"{name}Restore").as_view(),
            name=f"{lower}-restore",
        ),
    ]
