from django.urls import path

from .views import EnvironmentGnssTab, EnvironmentHub, EnvironmentWeatherTab

# LV-358: la pestaña «Espacio aéreo» (`/environment/airspace/`, nombre `airspace-map`) vive en`n# `apps/airspace/urls.py` (LV-357, F3), montada antes que esta en `config/urls.py`.
urlpatterns = [
    path("", EnvironmentHub.as_view(), name="environment-hub"),
    path("weather/", EnvironmentWeatherTab.as_view(), name="environment-weather"),
    path("gnss/", EnvironmentGnssTab.as_view(), name="environment-gnss"),
]
