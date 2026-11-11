"""LV-431: «Flight logs» como sección propia: lista por centro de costo y aeronave, y alta."""

from __future__ import annotations

import hashlib
from datetime import datetime

from django.contrib import messages
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import CharField
from django.db.models.fields.json import KT
from django.db.models.functions import Cast, Coalesce, Substr, TruncDate
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.generic import FormView, ListView

from apps.compliance.models import Document, DocumentType
from apps.compliance.views import save_uploaded_file, uploaded_file_cleanup
from apps.core.audit import set_audit_context
from apps.core.tenancy import scope_queryset_to_tenant
from apps.core.views import (
    ModelPermissionRequiredMixin,
    ModelViewPermissionRequiredMixin,
    SearchMixin,
    lookup_by_pk,
)
from apps.registry.models import Aircraft, CostCenter

from ..models import FlightLogAnalysis
from .forms import FlightLogUploadForm
from .service import FLIGHT_LOG_TYPE

STATUS_FILTERS = (
    (FlightLogAnalysis.STATUS_OK, gettext_lazy("Analysed")),
    (FlightLogAnalysis.STATUS_ERROR, gettext_lazy("Error")),
    (FlightLogAnalysis.STATUS_PENDING, gettext_lazy("Pending")),
)


def _clock(seconds):
    if seconds is None:
        return None
    seconds = int(round(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


def digest(analysis) -> dict:
    """Lo que la fila de la lista muestra del resultado guardado (sin inventar nada)."""
    result = analysis.result or {}
    summary = result.get("summary") or {}
    battery = next(
        (
            p["battery_pct"]
            for p in reversed(result.get("points") or [])
            if p.get("battery_pct") is not None
        ),
        None,
    )
    started = ""
    raw = summary.get("started_at")
    if raw:
        try:
            # La hora del propio log (con su zona), sin convertirla a la del servidor.
            started = datetime.fromisoformat(raw).strftime("%d-%m-%Y %H:%M")
        except ValueError:
            started = ""
    # Sin fecha de vuelo en el log, se muestra la de subida (y la fila lo dice).
    shown = started or timezone.localtime(analysis.created_at).strftime(
        "%d-%m-%Y %H:%M"
    )
    return {
        "started": started,
        "date": shown[:10],
        "time": shown[11:],
        "duration": _clock(summary.get("duration_s")),
        "distance_m": summary.get("distance_m"),
        "max_height_m": summary.get("max_height_m"),
        "battery_pct": battery,
        "warnings": sum(
            1
            for e in result.get("events") or []
            if e.get("level") in ("warning", "critical")
        ),
    }


class FlightLogList(SearchMixin, ModelViewPermissionRequiredMixin, ListView):
    """La lista de logs de vuelo: filtra por centro, aeronave, estado y fechas. Acota por tenant
    del centro de costo (`cost_center__tenant_id`); lee con `view_flightloganalysis`."""

    model = FlightLogAnalysis
    template_name = "operations/flightlog_list.html"
    htmx_template_name = "operations/_flightlog_rows.html"
    context_object_name = "objects"
    paginate_by = 25
    tenant_scope = "cost_center__tenant_id"
    sortable_columns = {
        "date": "flight_day",
        "cost_center": "cost_center__code",
        "aircraft": "aircraft__registration",
        "status": "status",
    }
    search_fields = [
        "aircraft__registration",
        "aircraft__serial_number",
        "aircraft__model",
        "document__title",
    ]
    FILTER_KEYS = ("cost_center", "aircraft", "status", "date_from", "date_to")

    def _params(self):
        get = self.request.GET
        return {key: get.get(key, "").strip() for key in self.FILTER_KEYS}

    def _tenant_scoped(self, queryset, path="tenant_id"):
        return scope_queryset_to_tenant(queryset, self.request.user, path)

    def _chosen(self, model, raw):
        if not raw:
            return None
        return lookup_by_pk(self._tenant_scoped(model.objects.all()), raw)

    def get_queryset(self):
        started = KT("result__summary__started_at_utc")
        queryset = (
            super()
            .get_queryset()
            .filter(is_active=True)
            .select_related("cost_center", "aircraft", "document", "permission")
            .annotate(
                flight_day=Coalesce(
                    Substr(started, 1, 10),
                    Cast(TruncDate("created_at"), CharField()),
                    output_field=CharField(),
                )
            )
        )
        params = self._params()
        centre = params["cost_center"]
        if centre:
            chosen = self._chosen(CostCenter, centre)
            queryset = (
                queryset.filter(cost_center=chosen) if chosen else queryset.none()
            )
        aircraft = params["aircraft"]
        if aircraft:
            chosen = self._chosen(Aircraft, aircraft)
            queryset = queryset.filter(aircraft=chosen) if chosen else queryset.none()
        if params["status"] in {value for value, _label in STATUS_FILTERS}:
            queryset = queryset.filter(status=params["status"])
        # Fechas ISO (AAAA-MM-DD): comparar texto contra texto ordena igual que las fechas.
        # Un valor mal escrito no filtra (convención del repo), no falla.
        for key, lookup in (("date_from", "gte"), ("date_to", "lte")):
            try:
                day = datetime.strptime(params[key], "%Y-%m-%d").date().isoformat()
            except ValueError:
                continue
            queryset = queryset.filter(**{f"flight_day__{lookup}": day})
        if not self._requested_sort()[0]:
            queryset = queryset.order_by("-flight_day", "-created_at")
        return queryset

    def _cost_center_options(self):
        return (
            self._tenant_scoped(CostCenter.objects.all())
            .filter(flight_log_analyses__is_active=True)
            .distinct()
            .order_by("code")
        )

    def _aircraft_options(self, centre):
        queryset = self._tenant_scoped(Aircraft.objects.all()).filter(
            flight_log_analyses__is_active=True
        )
        if centre is not None:
            queryset = queryset.filter(cost_center=centre)
        return queryset.distinct().order_by("registration")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        params = self._params()
        for analysis in context["objects"]:
            analysis.digest = digest(analysis)
        centre = self._chosen(CostCenter, params["cost_center"])
        context.update(
            {
                "title": _("Flight logs"),
                "filters": params,
                "status_choices": STATUS_FILTERS,
                "cost_center_options": self._cost_center_options(),
                "aircraft_options": self._aircraft_options(centre),
                "is_filtered": bool(context.get("is_filtered") or any(params.values())),
                "can_upload": self.request.user.has_perm(
                    "operations.add_flightloganalysis"
                ),
                "search_placeholder": _("Registration, serial number or file name…"),
            }
        )
        return context


class FlightLogUpload(ModelPermissionRequiredMixin, FormView):
    """Alta: centro de costo → aeronave → `.TXT`. Exige `add_flightloganalysis`."""

    model = FlightLogAnalysis
    permission_action = "add"
    form_class = FlightLogUploadForm
    template_name = "operations/flightlog_upload.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        if self.request.method == "GET":
            kwargs["initial"] = {
                key: self.request.GET[key]
                for key in ("cost_center", "aircraft")
                if self.request.GET.get(key)
            }
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["cancel_url"] = reverse("flight-log-list")
        return context

    @staticmethod
    def _sha256(uploaded) -> str:
        digest_ = hashlib.sha256()
        for chunk in uploaded.chunks():
            digest_.update(chunk)
        uploaded.seek(0)
        return digest_.hexdigest()

    def form_valid(self, form):
        uploaded = form.cleaned_data["file"]
        analysis = form.save(commit=False)
        aircraft = analysis.aircraft
        analysis.uploaded_by = self.request.user
        try:
            with uploaded_file_cleanup() as stored, transaction.atomic():
                # El `.TXT` es un documento más de la aeronave (como los del taller, LV-388).
                document = Document.objects.create(
                    tenant_id=aircraft.tenant_id,
                    content_type=ContentType.objects.get_for_model(Aircraft),
                    object_id=aircraft.pk,
                    doc_type=DocumentType.objects.get(code=FLIGHT_LOG_TYPE),
                    title=uploaded.name.replace("\\", "/").rsplit("/", 1)[-1][:200],
                    file_path="",
                    content_sha256=self._sha256(uploaded),
                )
                # El análisis se crea antes del archivo: la señal de `Document` lo encuentra y
                # lo completa, con el centro y la aeronave que se eligieron.
                analysis.document = document
                analysis.save()
                stored["path"] = save_uploaded_file(document, uploaded)
        except ValidationError as exc:
            for message in exc.messages:
                form.add_error(None, message)
            return self.form_invalid(form)
        analysis.refresh_from_db()
        set_audit_context(self.request, analysis, action="create")
        messages.success(self.request, _("Flight log saved."))
        return redirect("flight-analysis", pk=analysis.pk)
