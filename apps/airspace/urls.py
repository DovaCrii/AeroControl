from django.urls import path

from .views import AirspaceData, AirspaceNear, AirspaceOwnLayers, AirspaceTab

# Mounted at `environment/airspace/` (config/urls.py). The name `airspace-map` is what
# `apps/environment/tabs.py` looks for to show the tab.
urlpatterns = [
    path("", AirspaceTab.as_view(), name="airspace-map"),
    path("data.json", AirspaceData.as_view(), name="airspace-data"),
    path("near/", AirspaceNear.as_view(), name="airspace-near"),
    path("own-layers.json", AirspaceOwnLayers.as_view(), name="airspace-own-layers"),
]
