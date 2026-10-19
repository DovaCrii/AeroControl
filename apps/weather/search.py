"""Búsqueda de ciudades con tope por persona y hora, y resultados saneados.

El cliente (`apps.core.weather.search_places`) es el único que habla con la red. Aquí se
acota cuánto puede usarlo cada persona y se normaliza lo que devuelve, porque un servicio
externo no es de fiar: nada de lo que vuelve llega a la base sin pasar por `clean_place`.
"""

from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from apps.core import weather as weather_client

MAX_RESULTS = 8
MAX_QUERY_CHARS = 80
MIN_QUERY_CHARS = 2


class SearchLimitReached(Exception):
    """La persona agotó sus búsquedas de esta hora."""


def _consume_search(user):
    """Cuenta una búsqueda de `user` en la hora actual; levanta si pasó el tope.

    El contador vive en la caché, así que es **por proceso** con la caché local por omisión:
    con varios procesos de gunicorn el tope efectivo puede ser un múltiplo. Es un freno contra
    abuso de un servicio gratuito, no una cuota contractual; a diferencia del asistente, aquí
    no hay costo por llamada que justifique una tabla.
    """
    cap = settings.WEATHER_SEARCH_MAX_PER_HOUR
    if not cap:
        return
    bucket = timezone.now().strftime("%Y%m%d%H")
    key = f"weather_search:{user.pk}:{bucket}"
    cache.add(key, 0, 3700)
    try:
        used = cache.incr(key)
    except ValueError:  # expiró entre el add y el incr
        cache.set(key, 1, 3700)
        used = 1
    if used > cap:
        raise SearchLimitReached


def clean_place(raw):
    """Un resultado del cliente como dict seguro, o `None` si no sirve."""
    if not isinstance(raw, dict):
        return None
    try:
        latitude = Decimal(str(raw.get("latitude"))).quantize(Decimal("0.000001"))
        longitude = Decimal(str(raw.get("longitude"))).quantize(Decimal("0.000001"))
    except (InvalidOperation, ValueError, TypeError):
        return None
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return None
    name = str(raw.get("name") or "").strip()
    if not name:
        return None
    parts = [name]
    for extra in (raw.get("admin1"), raw.get("country_code")):
        extra = str(extra or "").strip()
        if extra and extra not in parts:
            parts.append(extra)
    return {
        "label": ", ".join(parts)[:120],
        "latitude": latitude,
        "longitude": longitude,
        "timezone": str(raw.get("timezone") or "").strip()[:64],
    }


def search_cities(user, query):
    """Resultados saneados para `query`, contando contra el tope de `user`.

    Devuelve una lista (posiblemente vacía). Levanta `SearchLimitReached` pasado el tope.
    Una consulta demasiado corta no llama al servicio ni gasta tope.
    """
    query = (query or "").strip()[:MAX_QUERY_CHARS]
    if len(query) < MIN_QUERY_CHARS:
        return []
    _consume_search(user)
    # Se resuelve en cada llamada (no al importar) para que el cliente sea reemplazable.
    search_places = getattr(weather_client, "search_places", None)
    if search_places is None:
        return []
    try:
        raw_results = search_places(query)
    except Exception:  # noqa: BLE001 - el servicio externo puede fallar de cualquier forma
        return []
    places = []
    for raw in list(raw_results or []):
        place = clean_place(raw)
        if place is not None:
            places.append(place)
        if len(places) >= MAX_RESULTS:
            break
    return places
