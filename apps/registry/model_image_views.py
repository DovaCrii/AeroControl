"""LV-399: la foto oficial del fabricante por modelo de aeronave.

Se carga desde la ficha de una aeronave, pero la imagen es **del modelo**: todas las aeronaves
de ese modelo (en la misma empresa) la comparten. Cargar exige `change_aircraft` y verla
`view_aircraft` —es parte de la ficha, no un registro aparte que haya que repartir en los
roles—, y las dos vistas acotan por empresa: la aeronave de otra empresa da 404, y la imagen
también.
"""

from django.conf import settings
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.translation import gettext as _
from django.views import View
from django.views.generic import FormView

from apps.core.audit import set_audit_context
from apps.core.forms import OfficialImageForm
from apps.core.official_images import discard_image, image_response, store_image
from apps.core.tenancy import scope_queryset_to_tenant
from apps.core.views import ModelPermissionRequiredMixin

from .models import Aircraft, AircraftModelImage, normalize_model_key


class AircraftModelImageUpload(ModelPermissionRequiredMixin, FormView):
    model = Aircraft
    permission_action = "change"
    form_class = OfficialImageForm
    template_name = "generic/form.html"

    @cached_property
    def aircraft(self):
        # Después del permiso (lo usa `get`/`post`, que corren tras `dispatch`): sin
        # `change_aircraft` la respuesta es 403, exista o no la aeronave.
        return get_object_or_404(
            scope_queryset_to_tenant(
                Aircraft.objects.filter(is_active=True), self.request.user
            ),
            pk=self.kwargs["pk"],
        )

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["allowed_hosts"] = settings.OFFICIAL_IMAGE_ALLOWED_HOSTS
        kwargs["with_credit"] = True
        current = AircraftModelImage.for_aircraft(self.aircraft)
        kwargs.setdefault("initial", {})["credit"] = (
            current.credit if current else self.aircraft.manufacturer
        )
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = _("Official image of the model %(model)s") % {
            "model": self.aircraft.model
        }
        return context

    def form_valid(self, form):
        key = normalize_model_key(self.aircraft.model)
        if not key:
            form.add_error(None, _("The aircraft has no model to attach the image to."))
            return self.form_invalid(form)
        storage_key = store_image(
            f"aircraft-models/{self.aircraft.tenant_id}", form.webp
        )
        previous_key = (
            AircraftModelImage.objects.filter(
                tenant_id=self.aircraft.tenant_id, model_key=key
            )
            .values_list("storage_key", flat=True)
            .first()
        )
        image, _created = AircraftModelImage.objects.update_or_create(
            tenant_id=self.aircraft.tenant_id,
            model_key=key,
            defaults={
                "model_name": self.aircraft.model.strip(),
                "storage_key": storage_key,
                "source_url": (form.cleaned_data.get("source_url") or "").strip(),
                "source_host": form.source_host,
                "credit": (form.cleaned_data.get("credit") or "").strip(),
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
                "model_key": key,
                "source": "url" if form.source_host else "upload",
                "source_host": form.source_host,
            },
        )
        messages.success(self.request, _("Official image saved for this model."))
        return redirect(reverse("aircraft-detail", args=[self.aircraft.pk]))


class AircraftModelImageView(ModelPermissionRequiredMixin, View):
    """La imagen, servida desde el almacenamiento privado con su tipo y caché privada."""

    model = Aircraft
    permission_action = "view"

    def get(self, request, pk):
        image = get_object_or_404(
            scope_queryset_to_tenant(
                AircraftModelImage.objects.filter(is_active=True), request.user
            ),
            pk=pk,
        )
        return image_response(image.storage_key)
