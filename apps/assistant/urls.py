from django.urls import path

from .usage_views import AssistantUsageView, AssistantVote
from .views import AssistantAsk, AssistantPanelAsk

urlpatterns = [
    path("", AssistantAsk.as_view(), name="assistant-ask"),
    path("ask/panel/", AssistantPanelAsk.as_view(), name="assistant-panel-ask"),
    path("usage/", AssistantUsageView.as_view(), name="assistant-usage"),
    path("vote/", AssistantVote.as_view(), name="assistant-vote"),
]
