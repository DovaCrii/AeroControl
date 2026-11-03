from django.contrib import messages
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.generic import CreateView, DetailView, ListView, View
from django.utils.text import capfirst

from apps.compliance.attachments import attached_documents_context, category_rank
from apps.compliance.models import Document
from apps.core.audit import set_audit_context
from apps.core.views import (
    apply_cost_center_filter,
    CsvExportMixin,
    HtmxFormMixin,
    ModelPermissionRequiredMixin,
    ModelViewPermissionRequiredMixin,
    SearchMixin,
    StatusTransitionView,
    TenantScopedQuerysetMixin,
)
from apps.core.tenancy import scope_queryset_to_tenant
from apps.registry.models import Aircraft
from .forms import MaintenanceCompletionForm, MaintenanceRecordForm
from .models import MaintenanceHistory, MaintenanceRecord, WorkshopIntake


# LV-372 (F-08): el tenant de una mantención es el de su aeronave.
MAINTENANCE_TENANT_PATH = "aircraft__tenant_id"


class MList(CsvExportMixin, SearchMixin, ModelViewPermissionRequiredMixin, ListView):
    template_name = "generic/list.html"
    context_object_name = "objects"
    paginate_by = 25

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = capfirst(self.model._meta.verbose_name_plural)
        return context


class MCreate(HtmxFormMixin, ModelPermissionRequiredMixin, CreateView):
    permission_action = "add"
    template_name = "generic/form.html"

    def get_success_url(self):
        return reverse("maintenance-list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = _("New %(record)s") % {
            "record": self.model._meta.verbose_name
        }
        return context


class MaintenanceRecordList(MList):
    model = MaintenanceRecord
    template_name = "maintenance/record_list.html"
    htmx_template_name = "maintenance/_record_rows.html"
    # LV-280
    sortable_columns = {
        "aircraft": "aircraft__registration",
        "type": "maintenance_type",
        "scheduled": "scheduled_date",
        "status": "status",
    }
    search_fields = ["aircraft__registration", "description", "performed_by"]
    cost_center_filter = None
    tenant_scope = MAINTENANCE_TENANT_PATH

    def get_queryset(self):
        # LV-252: `select_related("aircraft")` porque cada fila dibuja su aeronave:
        # sin el join era una consulta por fila, hasta 25 de más por página, en una
        # lista que no tenía techo de consultas que lo notara.
        # LV-383 PR 4: `workshop_intake` para el distintivo de cada fila.
        queryset = (
            super()
            .get_queryset()
            .select_related("aircraft", "workshop_intake")
            .prefetch_related("history")
        )
        # LV-388: un registro archivado (por ejemplo, un ingreso anulado) no sale
        # en la lista; `?is_active=archived` sigue mostrándolo.
        if not self.request.GET.get("is_active"):
            queryset = queryset.filter(is_active=True)
        status = self.request.GET.get("status", "")
        maintenance_type = self.request.GET.get("maintenance_type", "")
        sent_by = self.request.GET.get("sent_by", "")
        # El valor inválido se ignora, como el estado y el tipo. Sólo cuentan los
        # ingresos activos, igual que el distintivo.
        if sent_by in dict(WorkshopIntake.SENT_BY_CHOICES):
            queryset = queryset.filter(
                workshop_intake__is_active=True, workshop_intake__sent_by=sent_by
            )
        if status in dict(MaintenanceRecord.STATUSES):
            queryset = queryset.filter(status=status)
        if maintenance_type in dict(MaintenanceRecord.TYPES):
            queryset = queryset.filter(maintenance_type=maintenance_type)
        # LV-310: destino del indicador «Mantenciones por definir» del panel; el
        # criterio es el mismo que el de su cifra (`needing_planning`).
        if self.request.GET.get("needs_planning") == "1":
            queryset = MaintenanceRecord.needing_planning(
                queryset.filter(is_active=True)
            )
        # LV-351: con una faena elegida en el panel, el chip enlaza acá con ella.
        queryset, self.cost_center_filter = apply_cost_center_filter(
            self.request, queryset, "aircraft__cost_center"
        )
        return queryset

    def _valid_sent_by(self):
        value = self.request.GET.get("sent_by", "")
        return value if value in dict(WorkshopIntake.SENT_BY_CHOICES) else ""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            status_choices=MaintenanceRecord.STATUSES,
            type_choices=MaintenanceRecord.TYPES,
            current_status=self.request.GET.get("status", ""),
            current_type=self.request.GET.get("maintenance_type", ""),
            sent_by_choices=WorkshopIntake.SENT_BY_CHOICES,
            current_sent_by=self._valid_sent_by(),
            cost_center_filter=self.cost_center_filter,
        )
        # LV-254: los dos filtros propios también cuentan como filtro, para que el
        # vacío ofrezca quitarlos en vez de decir que no hay registros.
        context["is_filtered"] = context["is_filtered"] or bool(
            context["current_status"]
            or context["current_type"]
            or context["current_sent_by"]
            or self.request.GET.get("needs_planning") == "1"
            or self.cost_center_filter
        )
        return context


class MaintenanceRecordCreate(MCreate):
    model = MaintenanceRecord
    form_class = MaintenanceRecordForm

    def get_initial(self):
        # LV-26: "Send to maintenance" from an aircraft's detail prefills it.
        initial = super().get_initial()
        aircraft = self.request.GET.get("aircraft")
        if aircraft:
            initial["aircraft"] = aircraft
        return initial


class MaintenanceRecordDetail(
    TenantScopedQuerysetMixin, ModelViewPermissionRequiredMixin, DetailView
):
    model = MaintenanceRecord
    template_name = "maintenance/record_detail.html"
    context_object_name = "record"
    tenant_path = MAINTENANCE_TENANT_PATH

    def get_queryset(self):
        return super().get_queryset().filter(is_active=True).select_related("aircraft")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # LV-82: the groups are prefetched because the shared traceability block
        # prints the actor's role from them -- one query per row without this.
        context["history"] = self.object.history.select_related(
            "changed_by_user"
        ).prefetch_related("changed_by_user__groups")
        context["completion_form"] = MaintenanceCompletionForm(instance=self.object)
        # R5.1: "pending" offers both paths -- most maintenance is resolved
        # in-house (short: start/complete) and forcing every record through
        # the workshop chain would be friction for a 10-minute in-house
        # check. "complete" itself is handled separately below (it needs the
        # full completion form, not a bare button) and is valid from both
        # in_progress (short path) and in_transit (workshop path arrived
        # home) -- MaintenanceComplete.valid_from_statuses covers both.
        context["status_actions"] = {
            "pending": [
                ("start", _("Start maintenance"), "btn-warning"),
                ("send", _("Send to workshop"), "btn-info"),
            ],
            "sent": [("arrive-at-workshop", _("Arrived at workshop"), "btn-info")],
            "at_workshop": [("finish", _("Finish repair"), "btn-info")],
            "finished": [("depart", _("Departed workshop"), "btn-info")],
        }.get(self.object.status, [])
        # LV-382: the Documents section every other ficha already carries. A
        # Document can hang from a maintenance record (it is in
        # DOCUMENTABLE_MODELS) but the ficha never listed it. The helper hides
        # the section without compliance.view_document.
        context.update(attached_documents_context(self.request.user, self.object))
        # LV-388: el ingreso a servicio técnico cuelga sus documentos de la
        # aeronave; esta ficha los sigue mostrando por `source_document` y
        # `quote_document`.
        intake = self._active_intake()
        context["intake"] = intake
        void_kind = self.object.void_kind()
        context["can_void"] = void_kind is not None and self.request.user.has_perm(
            "maintenance.change_maintenancerecord"
        )
        context["void_is_intake"] = void_kind == MaintenanceRecord.VOID_KIND_INTAKE
        if context["documents"] is not None and intake is not None:
            ids = [
                pk for pk in (intake.source_document_id, intake.quote_document_id) if pk
            ]
            if ids:
                context["documents"] = (
                    Document.objects.filter(
                        Q(pk__in=context["documents"].values("pk")) | Q(pk__in=ids),
                        is_current_version=True,
                        is_active=True,
                    )
                    .select_related("doc_type")
                    .annotate(category_rank=category_rank())
                    .order_by("category_rank", "-issue_date")
                )
        return context

    def _active_intake(self):
        try:
            intake = self.object.workshop_intake
        except ObjectDoesNotExist:
            return None
        return intake if intake.is_active else None


class MaintenanceVoid(ModelPermissionRequiredMixin, View):
    """LV-388/LV-389: «Anular» -- archiva la mantención, sin borrar nada.

    Dos casos (`MaintenanceRecord.void_kind`): un ingreso a taller activo, o una
    mantención pendiente que nunca se inició ni se envió. Cualquier otro estado
    no se anula. Permiso `change_maintenancerecord`: es un archivado
    (`is_active=False`), no un borrado, y los documentos quedan intactos. Acotada
    por empresa como el resto de la ficha. Sólo POST; la confirmación es el
    `data-confirm` del formulario.
    """

    model = MaintenanceRecord
    permission_action = "change"
    http_method_names = ["post", "options"]

    def post(self, request, pk):
        record = get_object_or_404(
            scope_queryset_to_tenant(
                MaintenanceRecord._default_manager.all(),
                request.user,
                MAINTENANCE_TENANT_PATH,
            ),
            pk=pk,
            is_active=True,
        )
        try:
            kind, outcome = record.void(user=request.user)
        except ValidationError:
            messages.error(request, _("This record cannot be voided."))
            return redirect(record)
        action = (
            "workshop_intake_voided"
            if kind == MaintenanceRecord.VOID_KIND_INTAKE
            else "maintenance_voided"
        )
        set_audit_context(request, record, action=action, metadata={})
        if kind == MaintenanceRecord.VOID_KIND_PENDING:
            messages.success(request, _("Maintenance voided."))
        elif outcome == MaintenanceRecord.VOID_AIRCRAFT_RESTORED:
            messages.success(
                request,
                _(
                    "Intake voided. The aircraft is back at headquarters and "
                    "active; its documents were kept."
                ),
            )
        elif outcome == MaintenanceRecord.VOID_AIRCRAFT_KEPT:
            messages.warning(
                request,
                _(
                    "Intake voided and its documents were kept, but the aircraft "
                    "status was not changed: check its location and status."
                ),
            )
        else:
            messages.success(request, _("Intake voided; its documents were kept."))
        return redirect("maintenance-list")


class MaintenanceStart(StatusTransitionView):
    model = MaintenanceRecord
    tenant_scope = MAINTENANCE_TENANT_PATH
    target_status = "in_progress"
    valid_from_statuses = ["pending"]
    success_message = gettext_lazy("Maintenance started.")


class MaintenanceSend(StatusTransitionView):
    """R5.1: the workshop chain's entry point -- see
    apps.maintenance.signals.sync_maintenance_status_transition for the
    Aircraft.current_location/status side effect this triggers."""

    model = MaintenanceRecord
    tenant_scope = MAINTENANCE_TENANT_PATH
    target_status = "sent"
    valid_from_statuses = ["pending"]
    success_message = gettext_lazy("Aircraft sent to the workshop.")


class MaintenanceArriveAtWorkshop(StatusTransitionView):
    model = MaintenanceRecord
    tenant_scope = MAINTENANCE_TENANT_PATH
    target_status = "at_workshop"
    valid_from_statuses = ["sent"]
    success_message = gettext_lazy("Aircraft arrived at the workshop.")


class MaintenanceFinish(StatusTransitionView):
    model = MaintenanceRecord
    tenant_scope = MAINTENANCE_TENANT_PATH
    target_status = "finished"
    valid_from_statuses = ["at_workshop"]
    success_message = gettext_lazy("Repair finished at the workshop.")


class MaintenanceDepart(StatusTransitionView):
    model = MaintenanceRecord
    tenant_scope = MAINTENANCE_TENANT_PATH
    target_status = "in_transit"
    valid_from_statuses = ["finished"]
    success_message = gettext_lazy("Aircraft in transit back to headquarters.")


class MaintenanceComplete(StatusTransitionView):
    model = MaintenanceRecord
    tenant_scope = MAINTENANCE_TENANT_PATH
    target_status = "completed"
    # R5.1: valid from either path's last working state -- in_progress (the
    # short in-house path) or in_transit (arrived home from the workshop
    # chain). apps.maintenance.signals decides, from old_status alone,
    # whether arriving at "completed" also means the aircraft is back
    # (only true from in_transit).
    valid_from_statuses = ["in_progress", "in_transit"]
    success_message = gettext_lazy("Maintenance completed.")

    def post(self, request, pk):
        record = get_object_or_404(
            scope_queryset_to_tenant(
                self.model._default_manager.all(), request.user, MAINTENANCE_TENANT_PATH
            ),
            pk=pk,
            is_active=True,
        )
        if record.status not in self.valid_from_statuses:
            return super().post(request, pk)
        form = MaintenanceCompletionForm(request.POST, instance=record)
        if not form.is_valid():
            return render(
                request,
                "maintenance/record_detail.html",
                {
                    "record": record,
                    "history": record.history.all(),
                    "status_actions": [("complete", _("Complete"), "btn-success")],
                    "completion_form": form,
                },
            )
        with transaction.atomic():
            record._changed_by = request.user.get_username()
            record._changed_by_user = request.user
            record._transition_notes = form.cleaned_data.get("notes", "")
            completed = form.save(commit=False)
            completed.status = self.target_status
            completed.save(
                update_fields=[
                    "completed_date",
                    "performed_by",
                    "notes",
                    "status",
                    "updated_at",
                ]
            )
            # LV-26: completing the maintenance closes its open alert, so the
            # "aircraft needs maintenance" warning does not linger once resolved.
            from apps.compliance.alerts import resolve_open_alerts_for

            resolve_open_alerts_for(completed)
        messages.success(request, self.success_message)
        return redirect(record)


class AircraftReportIncident(ModelPermissionRequiredMixin, View):
    """LV-46: one-click flag for an aircraft that just crashed or was damaged
    and has not yet been formally sent to maintenance.

    Sets the aircraft's own status (the "Mal estado" badge on the list/detail
    pages) and opens an emergency maintenance record in the same click --
    reusing the existing "Mantenciones abiertas" alert rule (LV-26, watches
    maintenance.maintenancerecord/status) so the alert fires on the next
    generate_alerts run without a new rule. No form to fill in first: an
    accident report should not wait on a scheduled date or an assignee.
    """

    model = MaintenanceRecord
    permission_action = "add"

    def post(self, request, pk):
        aircraft = get_object_or_404(
            scope_queryset_to_tenant(Aircraft._default_manager.all(), request.user),
            pk=pk,
            is_active=True,
        )
        aircraft.status = "damaged"
        aircraft.save(update_fields=["status", "updated_at"])
        MaintenanceRecord.objects.create(
            aircraft=aircraft,
            maintenance_type="emergency",
            status="pending",
            description=_(
                "Incident reported from the aircraft fiche. Pending assessment."
            ),
        )
        set_audit_context(request, aircraft, action="incident_reported")
        messages.success(
            request,
            _(
                "Incident logged: aircraft marked as damaged and an emergency "
                "maintenance record was opened."
            ),
        )
        return redirect(reverse("aircraft-detail", kwargs={"pk": aircraft.pk}))


MaintenanceHistoryList = type(
    "MaintenanceHistoryList",
    (MList,),
    {"model": MaintenanceHistory, "tenant_scope": "record__aircraft__tenant_id"},
)
MaintenanceHistoryCreate = type(
    "MaintenanceHistoryCreate", (MCreate,), {"model": MaintenanceHistory}
)
