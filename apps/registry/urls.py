from django.urls import path
from . import views

urlpatterns = []
urlpatterns += [
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
