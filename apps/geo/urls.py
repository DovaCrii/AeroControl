from django.urls import path

from . import views

urlpatterns = [
    path("plans/", views.GeoPlanListView.as_view(), name="geo-plan-list"),
    path("plans/import/", views.GeoPlanImportView.as_view(), name="geo-plan-import"),
    path("plans/<uuid:pk>/", views.GeoPlanDetailView.as_view(), name="geo-plan-detail"),
    # GEO-9 status transitions.
    path(
        "plans/<uuid:pk>/start-editing/",
        views.GeoPlanStartEditing.as_view(),
        name="geo-plan-start-editing",
    ),
    path(
        "plans/<uuid:pk>/submit-review/",
        views.GeoPlanSubmitReview.as_view(),
        name="geo-plan-submit-review",
    ),
    path(
        "plans/<uuid:pk>/approve/",
        views.GeoPlanApprove.as_view(),
        name="geo-plan-approve",
    ),
    path(
        "plans/<uuid:pk>/reject/",
        views.GeoPlanReject.as_view(),
        name="geo-plan-reject",
    ),
    path(
        "plans/<uuid:pk>/resume-editing/",
        views.GeoPlanResumeEditing.as_view(),
        name="geo-plan-resume-editing",
    ),
    path(
        "plans/<uuid:pk>/reopen/",
        views.GeoPlanReopen.as_view(),
        name="geo-plan-reopen",
    ),
]
