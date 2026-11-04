"""LV-399: el banner oficial de SIGO y SIPA para las tarjetas del panel.

LV-406: ya no se carga a mano. El comando `load_official_link_images` lo descarga de la URL
oficial de cada sistema (`official_links.py`) y esta vista lo sirve. Verlo pide sólo sesión,
igual que las tarjetas que lo muestran: es la imagen pública del sistema de la DGAC, la misma
para todas las empresas, y se sirve desde la app para que el CSP no tenga que admitir otro
dominio (declarado en `test_lv268_permission_contract.LOGIN_ONLY`).
"""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.views import View

from apps.core.models import OfficialLinkImage
from apps.core.official_images import image_response
from apps.core.official_links import OFFICIAL_LINKS

_KEYS = {link["key"] for link in OFFICIAL_LINKS}


class OfficialLinkImageView(LoginRequiredMixin, View):
    def get(self, request, key):
        if key not in _KEYS:
            raise Http404
        image = get_object_or_404(OfficialLinkImage, link_key=key, is_active=True)
        return image_response(image.storage_key)
