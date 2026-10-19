from django import forms
from django.utils.translation import gettext_lazy as _

from apps.core.tenancy import scope_queryset_to_tenant
from apps.registry.models import CostCenter

from .search import SearchLimitReached, search_cities


def sites_for(user):
    """Faenas activas con coordenadas que `user` puede ofrecer como ciudad. Sin red.

    Exige `registry.view_costcenter` (leer una faena es leer una faena, aunque sea para
    elegir una ciudad) y acota por empresa con el mecanismo del repo.
    """
    if not user.has_perm("registry.view_costcenter"):
        return CostCenter.objects.none()
    queryset = CostCenter.objects.filter(
        is_active=True, latitude__isnull=False, longitude__isnull=False
    ).order_by("code")
    return scope_queryset_to_tenant(queryset, user)


class WeatherLocationForm(forms.Form):
    """Elegir ciudad: una faena (`site`) **o** un resultado de búsqueda (`q` + `pick`).

    El formulario **no recibe coordenadas** y aunque el POST las traiga se ignoran: la faena
    se resuelve por su id contra las que `sites_for` ofrece a esta persona, y la búsqueda se
    repite en el servidor tomando el resultado por posición. Lo que se guarda sale siempre de
    la base o del cliente del tiempo, nunca del navegador.
    """

    site = forms.UUIDField(required=False)
    q = forms.CharField(required=False, max_length=80)
    pick = forms.IntegerField(required=False, min_value=0)

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.resolved = None

    def clean(self):
        cleaned = super().clean()
        if self.errors:
            return cleaned
        site_id = cleaned.get("site")
        query = (cleaned.get("q") or "").strip()
        pick = cleaned.get("pick")
        if site_id:
            site = sites_for(self.user).filter(pk=site_id).first()
            if site is None:
                raise forms.ValidationError(_("That site is not available."))
            label = (site.name or site.code)[:120]
            self.resolved = {
                "label": label,
                "latitude": site.latitude,
                "longitude": site.longitude,
                "timezone": "",
                "source": "cost_center",
                "cost_center": site,
            }
        elif query and pick is not None:
            try:
                places = search_cities(self.user, query)
            except SearchLimitReached:
                raise forms.ValidationError(
                    _("Too many searches this hour. Try again later.")
                ) from None
            if pick >= len(places):
                raise forms.ValidationError(
                    _("That result is no longer available. Search again.")
                )
            self.resolved = {**places[pick], "source": "search", "cost_center": None}
        else:
            raise forms.ValidationError(_("Choose a site or a search result."))
        return cleaned
