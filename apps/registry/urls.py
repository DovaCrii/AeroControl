from django.urls import path
from . import views

urlpatterns = []
for name in ("CostCenter", "Aircraft", "Operator", "Assignment", "Qualification"):
    lower = name.lower()
    urlpatterns += [path(f"{lower}/", getattr(views, f"{name}List").as_view(), name=f"{lower}-list"), path(f"{lower}/new/", getattr(views, f"{name}Create").as_view(), name=f"{lower}-create"), path(f"{lower}/<uuid:pk>/", getattr(views, f"{name}Detail").as_view(), name=f"{lower}-detail"), path(f"{lower}/<uuid:pk>/edit/", getattr(views, f"{name}Update").as_view(), name=f"{lower}-update")]
