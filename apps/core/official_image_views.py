"""LV-399: el banner oficial de SIGO y SIPA para las tarjetas del panel.

Cargarlo exige `core.change_officiallinkimage` (quien administra; ningún rol lo trae). Verlo
pide sólo sesión, igual que las tarjetas que lo muestran: es la imagen pública del sistema de
la DGAC, la misma para todas las empresas, y se sirve desde la app para que el CSP no tenga
que admitir otro dominio (declarado en `test_lv268_permission_contract.LOGIN_ONLY`).
"""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views import View
from django.views.generic import FormView

from apps.core.audit import set_audit_context
from apps.core.forms import OfficialImageForm
from apps.core.models import OfficialLinkImage
from apps.core.official_images import discard_image, image_response, store_image
from apps.core.official_links import OFFICIAL_LINKS
from apps.core.views import ModelPermissionRequiredMixin

_LINKS = {link["key"]: link for link in OFFICIAL_LINKS}


def _link_or_404(key):
    link = _LINKS.get(key)
    if link is None:
        raise Http404
    return link


class OfficialLinkImageUpload(ModelPermissionRequiredMixin, FormView):
    model = OfficialLinkImage
    permission_action = "change"
    form_class = OfficialImageForm
    template_name = "generic/form.html"

    def get_form_kwargs(self):
        _link_or_404(self.kwargs["key"])
        kwargs = super().get_form_kwargs()
        kwargs["allowed_hosts"] = settings.OFFICIAL_LINK_IMAGE_ALLOWED_HOSTS
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = _("Official banner of %(system)s") % {
            "system": _link_or_404(self.kwargs["key"])["acronym"]
        }
        return context

    def form_valid(self, form):
        key = _link_or_404(self.kwargs["key"])["key"]
        storage_key = store_image("official-links", form.webp)
        previous_key = (
            OfficialLinkImage.objects.filter(link_key=key)
            .values_list("storage_key", flat=True)
            .first()
        )
        image, _created = OfficialLinkImage.objects.update_or_create(
            link_key=key,
            defaults={
                "storage_key": storage_key,
                "source_url": (form.cleaned_data.get("source_url") or "").strip(),
                "source_host": form.source_host,
                "uploaded_by": self.request.user,
                "is_active": True,
            },
        )
        if previous_key != storage_key:
            discard_image(previous_key)
        set_audit_context(
            self.request,
            image,
            action="official_image_loaded",
            metadata={
                "link_key": key,
                "source": "url" if form.source_host else "upload",
                "source_host": form.source_host,
            },
        )
        messages.success(self.request, _("Official banner saved."))
        return redirect(reverse("dashboard"))


class OfficialLinkImageView(LoginRequiredMixin, View):
    def get(self, request, key):
        _link_or_404(key)
        image = get_object_or_404(OfficialLinkImage, link_key=key, is_active=True)
        return image_response(image.storage_key)
