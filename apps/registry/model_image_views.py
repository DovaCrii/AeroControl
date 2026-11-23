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


def _discard_if_unused(key):
    """LV-457: borra el archivo reemplazado sólo si ninguna otra fila lo usa.

    Dos modelos pueden compartir el mismo archivo (`AircraftModelImageReuse`): reemplazar la
    imagen de uno no puede dejar al otro sin foto.
    """
    if key and not AircraftModelImage.objects.filter(storage_key=key).exists():
        discard_image(key)


class AircraftModelImageUpload(ModelPermissionRequiredMixin, FormView):
    model = Aircraft
    permission_action = "change"
    form_class = OfficialImageForm
    template_name = "registry/aircraft_model_image_form.html"

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
        context["reusable_images"] = self.reusable_images()
        return context

    def reusable_images(self):
        """LV-457: las imágenes que la empresa ya cargó para OTROS modelos.

        Una por archivo (dos modelos que ya comparten foto se ofrecen una vez) y sin la que
        este modelo ya usa. No se adivina que dos nombres son el mismo modelo
        (`normalize_model_key`): la persona lo decide, con un botón.
        """
        key = normalize_model_key(self.aircraft.model)
        current = AircraftModelImage.for_aircraft(self.aircraft)
        images, seen = [], {current.storage_key} if current else set()
        candidates = scope_queryset_to_tenant(
            AircraftModelImage.objects.filter(is_active=True), self.request.user
        ).exclude(model_key=key)
        for image in candidates.order_by("model_name", "pk"):
            if image.storage_key in seen:
                continue
            seen.add(image.storage_key)
            images.append(
                {
                    "image": image,
                    "url": "{}?v={}".format(
                        reverse("aircraft-model-image", args=[image.pk]),
                        int(image.updated_at.timestamp()),
                    ),
                    "reuse_url": reverse(
                        "aircraft-model-image-reuse",
                        args=[self.aircraft.pk, image.pk],
                    ),
                }
            )
        return images

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
            _discard_if_unused(previous_key)
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


class AircraftModelImageReuse(ModelPermissionRequiredMixin, View):
    """LV-457: usar para este modelo la imagen que la empresa ya cargó para otro.

    «Mavic 3 Enterprise» y «Mavic 3E» comparten foto sin volver a subirla: la fila de este
    modelo apunta al mismo archivo (`storage_key`), sin copiar bytes. Sólo POST, con el
    permiso de la carga y acotado por empresa: la imagen de otra empresa da 404.
    """

    model = Aircraft
    permission_action = "change"
    http_method_names = ["post", "options"]

    def post(self, request, pk, image_pk):
        aircraft = get_object_or_404(
            scope_queryset_to_tenant(
                Aircraft.objects.filter(is_active=True), request.user
            ),
            pk=pk,
        )
        source = get_object_or_404(
            scope_queryset_to_tenant(
                AircraftModelImage.objects.filter(
                    is_active=True, tenant_id=aircraft.tenant_id
                ),
                request.user,
            ),
            pk=image_pk,
        )
        key = normalize_model_key(aircraft.model)
        if not key:
            messages.error(
                request, _("The aircraft has no model to attach the image to.")
            )
            return redirect(reverse("aircraft-detail", args=[aircraft.pk]))
        previous_key = (
            AircraftModelImage.objects.filter(
                tenant_id=aircraft.tenant_id, model_key=key
            )
            .values_list("storage_key", flat=True)
            .first()
        )
        image, _created = AircraftModelImage.objects.update_or_create(
            tenant_id=aircraft.tenant_id,
            model_key=key,
            defaults={
                "model_name": aircraft.model.strip(),
                "storage_key": source.storage_key,
                "source_url": source.source_url,
                "source_host": source.source_host,
                "credit": source.credit,
                "uploaded_by": request.user,
                "is_active": True,
            },
        )
        if previous_key != source.storage_key:
            _discard_if_unused(previous_key)
        set_audit_context(
            request,
            image,
            action="official_image_reused",
            metadata={
                "model_key": key,
                "source": "reuse",
                "source_model_key": source.model_key,
                "source_image": str(source.pk),
            },
        )
        messages.success(request, _("Official image saved for this model."))
        return redirect(reverse("aircraft-detail", args=[aircraft.pk]))


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
