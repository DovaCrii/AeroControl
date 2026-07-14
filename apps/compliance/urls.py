from django.urls import path
from . import views

urlpatterns = [
    path("document/", views.DocumentList.as_view(), name="document-list"),
    path("document/new/", views.DocumentCreate.as_view(), name="document-create"),
    path("document/<uuid:pk>/", views.DocumentDetail.as_view(), name="document-detail"),
    path("document/<uuid:pk>/download/", views.DocumentDownload.as_view(), name="document-download"),
    path("document/<uuid:pk>/replace/", views.DocumentReplace.as_view(), name="document-replace"),
    path("document/<uuid:pk>/delete/", views.DocumentDelete.as_view(), name="document-delete"),
    path("alert/", views.AlertList.as_view(), name="alert-list"),
    path("alert/<uuid:pk>/resolve/", views.AlertResolve.as_view(), name="alert-resolve"),
    path("alert/new/", views.AlertCreate.as_view(), name="alert-create"),
    path("documenttype/", views.DocumentTypeList.as_view(), name="documenttype-list"),
    path("documenttype/new/", views.DocumentTypeCreate.as_view(), name="documenttype-create"),
    path("alertrule/", views.AlertRuleList.as_view(), name="alertrule-list"),
    path("alertrule/new/", views.AlertRuleCreate.as_view(), name="alertrule-create"),
]
