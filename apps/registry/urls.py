from django.urls import path
from . import views

urlpatterns = []
urlpatterns += [
    path("costcenter/import/", views.CostCenterImportView.as_view(), name="costcenter-import"),
    path("costcenter/import/<uuid:pk>/revert/", views.CostCenterImportRevertView.as_view(), name="costcenter-import-revert"),
    path("aircraft/import/", views.AircraftImportView.as_view(), name="aircraft-import"),
    path("operator/import/", views.OperatorImportView.as_view(), name="operator-import"),
]
for name in ("CostCenter", "Aircraft", "Operator", "Assignment", "Qualification"):
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
    ]
