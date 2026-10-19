"""La ciudad que usa el widget para una persona: la suya, o la de omisión, o ninguna."""

from dataclasses import dataclass

from django.conf import settings

from .models import UserWeatherLocation


@dataclass(frozen=True)
class Location:
    label: str
    latitude: float
    longitude: float
    timezone: str
    is_default: bool = False


def default_location():
    """La ciudad por omisión de `WEATHER_DEFAULT_*`, o `None` si falta o está mal escrita."""
    label = (settings.WEATHER_DEFAULT_LABEL or "").strip()
    try:
        latitude = float(settings.WEATHER_DEFAULT_LAT)
        longitude = float(settings.WEATHER_DEFAULT_LON)
    except (TypeError, ValueError):
        return None
    if not label or not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
        return None
    return Location(
        label=label,
        latitude=latitude,
        longitude=longitude,
        timezone=(settings.WEATHER_DEFAULT_TZ or "").strip(),
        is_default=True,
    )


def get_location_for(user):
    """La ciudad de `user`, la de omisión, o `None` (el widget dice «Elige tu ciudad»)."""
    if getattr(user, "is_authenticated", False):
        row = UserWeatherLocation.objects.filter(user=user, is_active=True).first()
        if row is not None:
            return Location(
                label=row.label,
                latitude=float(row.latitude),
                longitude=float(row.longitude),
                timezone=row.timezone,
            )
    return default_location()
