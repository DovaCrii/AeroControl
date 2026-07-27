from django.urls import path

from . import views

urlpatterns = [
    path("plans/", views.GeoPlanListView.as_view(), name="geo-plan-list"),
    path("plans/import/", views.GeoPlanImportView.as_view(), name="geo-plan-import"),
    path("plans/<uuid:pk>/", views.GeoPlanDetailView.as_view(), name="geo-plan-detail"),
]
