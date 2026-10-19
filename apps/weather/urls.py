from django.urls import path

from .views import WeatherLocationUpdate, WeatherSearch

urlpatterns = [
    path("location/", WeatherLocationUpdate.as_view(), name="weather-location"),
    path("search/", WeatherSearch.as_view(), name="weather-search"),
]
