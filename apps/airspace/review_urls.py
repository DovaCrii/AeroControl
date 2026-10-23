from django.urls import path

from .review_views import (
    ReviewBulk,
    ReviewList,
    ReviewPublish,
    ReviewSnapshot,
    ReviewZone,
)

# Mounted at `administracion/espacio-aereo/` (config/urls.py): the review of the AIP snapshots.
urlpatterns = [
    path("", ReviewList.as_view(), name="airspace-review-list"),
    path("<uuid:snapshot>/", ReviewSnapshot.as_view(), name="airspace-review-snapshot"),
    path(
        "<uuid:snapshot>/zonas/<uuid:zone>/",
        ReviewZone.as_view(),
        name="airspace-review-zone",
    ),
    path(
        "<uuid:snapshot>/aprobar-limpias/",
        ReviewBulk.as_view(),
        name="airspace-review-bulk",
    ),
    path(
        "<uuid:snapshot>/publicar/",
        ReviewPublish.as_view(),
        name="airspace-review-publish",
    ),
]
