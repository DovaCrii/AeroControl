from django.urls import path

from .panel import WeatherPanel
from .views import WeatherLocationUpdate, WeatherSearch

urlpatterns = [
    path("location/", WeatherLocationUpdate.as_view(), name="weather-location"),
    path("search/", WeatherSearch.as_view(), name="weather-search"),
    path("panel/", WeatherPanel.as_view(), name="weather-panel"),
]
