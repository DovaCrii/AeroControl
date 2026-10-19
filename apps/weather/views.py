"""Elegir la ciudad predeterminada del widget del tiempo (LV-343).

Toda vista opera sobre la fila de `request.user`: ninguna recibe un id de usuario, así que no
hay forma de apuntar a la de otra persona.
"""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views import View

from apps.core.audit import set_audit_context
from apps.core.views import ModelPermissionRequiredMixin

from .forms import WeatherLocationForm, sites_for
from .models import UserWeatherLocation
from .search import SearchLimitReached, search_cities


class WeatherLocationUpdate(ModelPermissionRequiredMixin, View):
    """GET: la ciudad actual, las faenas y un buscador. POST: guardar la elegida.

    Ver exige `view_userweatherlocation`; guardar exige `add_` si la persona aún no tiene
    ciudad y `change_` si ya la tiene.
    """

    model = UserWeatherLocation
    permission_action = "view"
    template_name = "weather/location_form.html"

    def has_permission(self):
        user = self.request.user
        if self.request.method in ("GET", "HEAD"):
            return user.has_perm("weather.view_userweatherlocation")
        action = "change" if self._current() is not None else "add"
        return user.has_perm(f"weather.{action}_userweatherlocation")

    def _current(self):
        return UserWeatherLocation.objects.filter(user=self.request.user).first()

    def _render(self, request, *, query="", places=None, error=None, status=200):
        context = {
            "current": self._current(),
            "sites": sites_for(request.user),
            "query": query,
            "places": places,
            "error": error,
        }
        return render(request, self.template_name, context, status=status)

    def get(self, request):
        query = (request.GET.get("q") or "").strip()
        places = None
        error = None
        if query:
            try:
                places = search_cities(request.user, query)
            except SearchLimitReached:
                error = _("Too many searches this hour. Try again later.")
        return self._render(request, query=query, places=places, error=error)

    def post(self, request):
        form = WeatherLocationForm(request.POST, user=request.user)
        if not form.is_valid():
            error = " ".join(
                message for errors in form.errors.values() for message in errors
            )
            return self._render(request, error=error, status=400)
        resolved = form.resolved
        instance = self._current() or UserWeatherLocation(user=request.user)
        instance.label = resolved["label"]
        instance.latitude = resolved["latitude"]
        instance.longitude = resolved["longitude"]
        instance.timezone = resolved["timezone"]
        instance.source = resolved["source"]
        instance.cost_center = resolved["cost_center"]
        instance.is_active = True
        try:
            instance.full_clean()
        except ValidationError as exc:
            return self._render(request, error=" ".join(exc.messages), status=400)
        instance.save()
        set_audit_context(
            request,
            instance,
            action="weather_location_set",
            metadata={"source": instance.source},
        )
        messages.success(request, _("Your city was saved."))
        return redirect(reverse("weather-location"))


class WeatherSearch(ModelPermissionRequiredMixin, View):
    """JSON: ciudades que coinciden con `q`. Cuenta contra el tope por persona y hora.

    Devuelve `index` y `label`, no coordenadas: quien elige manda el índice y el servidor
    repite la búsqueda, así que el navegador nunca decide lo que se guarda.
    """

    model = UserWeatherLocation
    permission_action = "view"

    def get(self, request):
        try:
            places = search_cities(request.user, request.GET.get("q"))
        except SearchLimitReached:
            return JsonResponse({"error": "limit"}, status=429)
        return JsonResponse(
            {
                "results": [
                    {"index": index, "label": place["label"]}
                    for index, place in enumerate(places)
                ]
            }
        )
