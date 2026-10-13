from django.urls import path

from .views import AssistantAsk

urlpatterns = [
    path("", AssistantAsk.as_view(), name="assistant-ask"),
]
