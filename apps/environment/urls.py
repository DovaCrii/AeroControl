from django.urls import path

from .strip import EnvironmentStrip
from .views import EnvironmentGnssTab, EnvironmentHub, EnvironmentWeatherTab

# LV-358: la pestaña «Espacio aéreo» (`/environment/airspace/`, nombre `airspace-map`) la agrega
# otro bloque; basta con registrar su ruta con ese nombre para que `tabs.TABS` la muestre.
urlpatterns = [
    path("", EnvironmentHub.as_view(), name="environment-hub"),
    path("weather/", EnvironmentWeatherTab.as_view(), name="environment-weather"),
    path("gnss/", EnvironmentGnssTab.as_view(), name="environment-gnss"),
    # LV-358, E2: la franja «Entorno hoy» del panel (fragmento htmx).
    path("strip/", EnvironmentStrip.as_view(), name="environment-strip"),
]
