from django.urls import path

from .views import AssistantAsk, AssistantPanelAsk

urlpatterns = [
    path("", AssistantAsk.as_view(), name="assistant-ask"),
    path("ask/panel/", AssistantPanelAsk.as_view(), name="assistant-panel-ask"),
]
