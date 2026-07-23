import csv
from datetime import date, timedelta
from pathlib import Path

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.http import HttpResponse
from django.http import JsonResponse
from django.conf import settings
from django.db import connection
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views import View
from django.views.generic import TemplateView
from .audit import set_audit_context


class SearchMixin:
    """Add text search and the common active/archive filter to list views."""

    search_fields = []
    htmx_template_name = "generic/_table_body.html"

    def get_template_names(self):
        if self.request.headers.get("HX-Request") == "true":
            return [self.htmx_template_name]
        return super().get_template_names()

    def get_queryset(self):
        queryset = super().get_queryset()
        query_text = self.request.GET.get("q", "").strip()
        if query_text and self.search_fields:
            from django.db.models import Q

            query = Q()
            for field in self.search_fields:
                query |= Q(**{f"{field}__icontains": query_text})
            queryset = queryset.filter(query)

        active = self.request.GET.get("is_active")
        if active == "active":
            queryset = queryset.filter(is_active=True)
        elif active == "archived":
            queryset = queryset.filter(is_active=False)
        return queryset if queryset.ordered else queryset.order_by("created_at")


class CsvExportMixin:
    """Add ``?export=csv`` support to list views."""

    csv_filename = None
    csv_fields = None

    def get_csv_filename(self):
        if self.csv_filename:
            return self.csv_filename
        model_name = self.model._meta.verbose_name_plural.replace(" ", "_")
        return f"{model_name}.csv"

    def render_csv_response(self, queryset):
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = (
            f'attachment; filename="{self.get_csv_filename()}"'
        )
        # The BOM makes UTF-8 CSV files open correctly in Excel.
        response.write("\ufeff")

        writer = csv.writer(response, lineterminator="\r\n")
        fields = self.csv_fields or [
            field
            for field in self.model._meta.fields
            if field.name
            not in {"id", "notes", "is_active", "created_at", "updated_at"}
        ]
        writer.writerow([field.verbose_name.title() for field in fields])

        for obj in queryset:
            row = []
            for field in fields:
                value = getattr(obj, field.name)
                if value is None:
                    row.append("")
                elif hasattr(value, "strftime"):
                    row.append(value.strftime("%Y-%m-%d"))
                else:
                    value = str(value)
                    # Excel/LibreOffice interpret leading formula characters on open.
                    row.append(
                        f"'{value}" if value.startswith(("=", "+", "-", "@")) else value
                    )
            writer.writerow(row)

        return response

    def get(self, request, *args, **kwargs):
        if request.GET.get("export") == "csv":
            if hasattr(self, "has_permission") and not self.has_permission():
                return self.handle_no_permission()
            return self.render_csv_response(self.get_queryset())
        return super().get(request, *args, **kwargs)


class HtmxFormMixin:
    """Return form fragments for HTMX while preserving normal form behavior."""

    htmx_template_name = "generic/_form_content.html"

    def get_template_names(self):
        if self.request.headers.get("HX-Request") == "true":
            return [self.htmx_template_name]
        return super().get_template_names()

    def form_invalid(self, form):
        if self.request.headers.get("HX-Request") == "true":
            return render(
                self.request,
                self.htmx_template_name,
                self.get_context_data(form=form),
                status=422,
            )
        return super().form_invalid(form)

    def form_valid(self, form):
        response = super().form_valid(form)
        set_audit_context(self.request, getattr(self, "object", None))
        messages.success(self.request, _("Saved successfully."))
        if self.request.headers.get("HX-Request") == "true":
            return HttpResponse(
                status=204, headers={"HX-Trigger": "modal-form-success"}
            )
        return response


class ModelPermissionRequiredMixin(LoginRequiredMixin, PermissionRequiredMixin):
    """Require the Django model permission declared by a mutating view."""

    permission_action = None
    raise_exception = True

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return redirect_to_login(
                self.request.get_full_path(),
                self.get_login_url(),
                self.get_redirect_field_name(),
            )
        return super().handle_no_permission()

    def get_permission_required(self):
        if not self.permission_action or self.model is None:
            raise ImproperlyConfigured(
                "A protected model view needs model and permission_action."
            )
        meta = self.model._meta
        return (f"{meta.app_label}.{self.permission_action}_{meta.model_name}",)


class ModelViewPermissionRequiredMixin(ModelPermissionRequiredMixin):
    """Require the model's Django view permission for lists and exports."""

    permission_action = "view"


class AlertCountPartial(LoginRequiredMixin, View):
    """Render the sidebar alert badge for periodic HTMX refreshes."""

    def get(self, request):
        from apps.compliance.models import Alert

        count = Alert.objects.filter(is_active=True, is_resolved=False).count()
        return render(
            request, "core/_alert_badge.html", {"unresolved_alert_count": count}
        )


class HealthCheckView(View):
    """Small dependency health endpoint for local monitors and reverse proxies."""

    def get(self, request):
        checks = {}
        try:
            connection.ensure_connection()
            checks["database"] = "ok"
        except Exception:
            checks["database"] = "error"
        documents = Path(settings.DOCUMENTS_ROOT)
        checks["documents"] = "ok" if documents.exists() and documents.is_dir() else "error"
        healthy = all(value == "ok" for value in checks.values())
        return JsonResponse(
            {"status": "ok" if healthy else "degraded", "checks": checks},
            status=200 if healthy else 503,
        )


class UnifiedCalendarEventsView(LoginRequiredMixin, View):
    """Return calendar events from the operational modules in one scoped feed."""

    EVENT_COLORS = {
        "permission": "#f59e0b",
        "flight": "#0ea5e9",
        "assignment": "#2563eb",
        "maintenance": "#8b5cf6",
        "document": "#ef4444",
        "qualification": "#e11d48",
        "task": "#0f9f95",
    }

    def get_date_range(self, request):
        today = timezone.localdate()
        try:
            start = date.fromisoformat(request.GET.get("start", ""))
        except ValueError:
            start = today.replace(day=1)
        try:
            end = date.fromisoformat(request.GET.get("end", ""))
        except ValueError:
            end = start + timedelta(days=42)
        return start, end

    def get(self, request):
        from django.db.models import Q
        from django.contrib.contenttypes.models import ContentType
        from apps.compliance.models import Document
        from apps.maintenance.models import MaintenanceRecord
        from apps.operations.models import FlightPermission, FlightRecord
        from apps.registry.models import Aircraft, Assignment, CostCenter, Operator, Qualification
        from apps.workboard.selectors import visible_tasks_for_user

        start, end = self.get_date_range(request)
        selected_types = set(filter(None, request.GET.get("types", "").split(",")))
        if not selected_types:
            selected_types = {"permission", "flight", "assignment", "maintenance", "document", "qualification", "task"}
        events = []
        cost_center_id = request.GET.get("cost_center") or None
        aircraft_id = request.GET.get("aircraft") or None
        operator_id = request.GET.get("operator") or None

        if request.user.is_superuser:
            tenant_ids = None
        else:
            from apps.core.models import OperationalTenant

            tenant_ids = list(
                OperationalTenant.objects.filter(
                    members=request.user, is_active=True
                ).values_list("id", flat=True)
            )

        if "permission" in selected_types:
            permissions = FlightPermission.objects.filter(
                flight_date__range=(start, end), is_active=True
            ).select_related("operator", "aircraft")
            if tenant_ids is not None:
                permissions = permissions.filter(
                    Q(operator__tenant_id__in=tenant_ids)
                    | Q(aircraft__tenant_id__in=tenant_ids)
                    | Q(cost_center__tenant_id__in=tenant_ids)
                )
            if cost_center_id:
                permissions = permissions.filter(cost_center_id=cost_center_id)
            if aircraft_id:
                permissions = permissions.filter(aircraft_id=aircraft_id)
            if operator_id:
                permissions = permissions.filter(operator_id=operator_id)
            events.extend(
                {
                    "id": f"permission-{permission.pk}",
                    "type": "permission",
                    "title": f"{permission.permission_number} · {permission.operator}",
                    "start": permission.flight_date.isoformat(),
                    "allDay": True,
                    "color": self.EVENT_COLORS["permission"],
                    "url": reverse("permission-detail", args=[permission.pk]),
                }
                for permission in permissions
            )

        if "flight" in selected_types:
            records = FlightRecord.objects.filter(
                actual_date__range=(start, end), is_active=True
            ).select_related("pilot", "aircraft", "permission")
            if tenant_ids is not None:
                records = records.filter(aircraft__tenant_id__in=tenant_ids)
            if cost_center_id:
                records = records.filter(aircraft__cost_center_id=cost_center_id)
            if aircraft_id:
                records = records.filter(aircraft_id=aircraft_id)
            if operator_id:
                records = records.filter(pilot_id=operator_id)
            events.extend(
                {
                    "id": f"flight-{record.pk}",
                    "type": "flight",
                    "title": f"{record.aircraft} · {record.pilot}",
                    "start": record.actual_date.isoformat(),
                    "allDay": True,
                    "color": self.EVENT_COLORS["flight"],
                    "url": reverse("record-detail", args=[record.pk]),
                }
                for record in records
            )

        if "assignment" in selected_types:
            assignments = Assignment.objects.filter(
                start_date__lte=end,
                is_active=True,
            ).filter(Q(end_date__isnull=True) | Q(end_date__gte=start)).select_related(
                "operator", "aircraft", "cost_center"
            )
            if tenant_ids is not None:
                assignments = assignments.filter(
                    Q(operator__tenant_id__in=tenant_ids)
                    | Q(aircraft__tenant_id__in=tenant_ids)
                    | Q(cost_center__tenant_id__in=tenant_ids)
                )
            if cost_center_id:
                assignments = assignments.filter(cost_center_id=cost_center_id)
            if aircraft_id:
                assignments = assignments.filter(aircraft_id=aircraft_id)
            if operator_id:
                assignments = assignments.filter(operator_id=operator_id)
            events.extend(
                {
                    "id": f"assignment-{assignment.pk}",
                    "type": "assignment",
                    "title": f"{assignment.aircraft} · {assignment.operator}",
                    "start": assignment.start_date.isoformat(),
                    "end": (assignment.end_date + timedelta(days=1)).isoformat() if assignment.end_date else None,
                    "allDay": True,
                    "color": self.EVENT_COLORS["assignment"],
                    "url": reverse("assignment-detail", args=[assignment.pk]),
                }
                for assignment in assignments
            )

        if "maintenance" in selected_types:
            maintenance = MaintenanceRecord.objects.filter(
                scheduled_date__range=(start, end), is_active=True
            ).select_related("aircraft")
            if tenant_ids is not None:
                maintenance = maintenance.filter(aircraft__tenant_id__in=tenant_ids)
            if cost_center_id:
                maintenance = maintenance.filter(aircraft__cost_center_id=cost_center_id)
            if aircraft_id:
                maintenance = maintenance.filter(aircraft_id=aircraft_id)
            events.extend(
                {
                    "id": f"maintenance-{record.pk}",
                    "type": "maintenance",
                    "title": f"{record.aircraft} · {record.get_maintenance_type_display()}",
                    "start": record.scheduled_date.isoformat(),
                    "allDay": True,
                    "color": self.EVENT_COLORS["maintenance"],
                    "url": reverse("maintenance-detail", args=[record.pk]),
                }
                for record in maintenance
            )

        if "qualification" in selected_types:
            qualifications = Qualification.objects.filter(
                expiry_date__range=(start, end), is_active=True
            ).select_related("operator")
            if tenant_ids is not None:
                qualifications = qualifications.filter(operator__tenant_id__in=tenant_ids)
            if cost_center_id:
                qualifications = qualifications.filter(operator__cost_center_id=cost_center_id)
            if operator_id:
                qualifications = qualifications.filter(operator_id=operator_id)
            events.extend(
                {
                    "id": f"qualification-{qualification.pk}",
                    "type": "qualification",
                    "title": f"{qualification.operator} · {qualification.qualification_type}",
                    "start": qualification.expiry_date.isoformat(),
                    "allDay": True,
                    "color": self.EVENT_COLORS["qualification"],
                    "url": reverse("qualification-detail", args=[qualification.pk]),
                }
                for qualification in qualifications
            )

        if "document" in selected_types:
            documents = Document.objects.filter(
                expiry_date__range=(start, end), is_current_version=True, is_active=True
            ).select_related("doc_type", "content_type")
            if tenant_ids is not None:
                aircraft_type = ContentType.objects.get_for_model(Aircraft)
                operator_type = ContentType.objects.get_for_model(Operator)
                cost_center_type = ContentType.objects.get_for_model(CostCenter)
                allowed_aircraft = Aircraft.objects.filter(tenant_id__in=tenant_ids).values_list("pk", flat=True)
                allowed_operators = Operator.objects.filter(tenant_id__in=tenant_ids).values_list("pk", flat=True)
                allowed_centers = CostCenter.objects.filter(tenant_id__in=tenant_ids).values_list("pk", flat=True)
                documents = documents.filter(
                    Q(content_type=aircraft_type, object_id__in=allowed_aircraft)
                    | Q(content_type=operator_type, object_id__in=allowed_operators)
                    | Q(content_type=cost_center_type, object_id__in=allowed_centers)
                )
            if aircraft_id:
                documents = documents.filter(
                    content_type=ContentType.objects.get_for_model(Aircraft), object_id=aircraft_id
                )
            elif operator_id:
                documents = documents.filter(
                    content_type=ContentType.objects.get_for_model(Operator), object_id=operator_id
                )
            elif cost_center_id:
                documents = documents.filter(
                    content_type=ContentType.objects.get_for_model(CostCenter), object_id=cost_center_id
                )
            events.extend(
                {
                    "id": f"document-{document.pk}",
                    "type": "document",
                    "title": f"{document.title} · {document.doc_type}",
                    "start": document.expiry_date.isoformat(),
                    "allDay": True,
                    "color": self.EVENT_COLORS["document"],
                    "url": reverse("document-detail", args=[document.pk]),
                }
                for document in documents
            )

        if "task" in selected_types:
            tasks = visible_tasks_for_user(request.user).filter(
                due_date__range=(start, end)
            ).select_related("board", "stage", "assigned_to")
            board_id = request.GET.get("board")
            if board_id:
                tasks = tasks.filter(board_id=board_id)
            if operator_id:
                tasks = tasks.filter(assigned_to_id=operator_id)
            if cost_center_id:
                tasks = tasks.filter(assigned_to__cost_center_id=cost_center_id)
            events.extend(
                {
                    "id": f"task-{task.pk}",
                    "type": "task",
                    "title": f"{task.title} · {task.stage.name}",
                    "start": task.due_date.isoformat(),
                    "allDay": True,
                    "color": self.EVENT_COLORS["task"],
                    # The task detail endpoint is an HTMX fragment. Link calendar
                    # events to the full Workboard view so direct navigation never
                    # leaves the user on an unstyled fragment page.
                    "url": f'{reverse("kanban")}?board={task.board_id}',
                }
                for task in tasks
            )

        return JsonResponse(events, safe=False)


class GlobalSearchView(LoginRequiredMixin, TemplateView):
    template_name = "core/search.html"

    SEARCH_SOURCES = (
        ("registry", "CostCenter", "costcenter-list", ("code", "name")),
        ("registry", "Aircraft", "aircraft-list", ("registration", "model", "type")),
        ("registry", "Operator", "operator-list", ("employee_id", "full_name", "email")),
        ("workboard", "KanbanBoard", "board-list", ("name", "description")),
        ("workboard", "KanbanTask", "workboard-list", ("title", "description")),
        ("compliance", "Document", "document-list", ("title",)),
    )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        query = self.request.GET.get("q", "").strip()
        results = []
        if query:
            from django.db.models import Q
            from apps.compliance.models import Document
            from apps.registry.models import Aircraft, CostCenter, Operator
            from apps.workboard.models import KanbanBoard, KanbanTask

            models = {
                "CostCenter": CostCenter,
                "Aircraft": Aircraft,
                "Operator": Operator,
                "KanbanBoard": KanbanBoard,
                "KanbanTask": KanbanTask,
                "Document": Document,
            }
            for app_label, model_name, url_name, fields in self.SEARCH_SOURCES:
                model = models[model_name]
                if not self.request.user.has_perm(f"{app_label}.view_{model._meta.model_name}"):
                    continue
                condition = Q()
                for field in fields:
                    condition |= Q(**{f"{field}__icontains": query})
                objects = model.objects.filter(condition, is_active=True).order_by("-updated_at")[:10]
                for obj in objects:
                    results.append({
                        "model": model._meta.verbose_name.title(),
                        "label": str(obj),
                        "url": reverse(url_name),
                        "id": obj.pk,
                    })
        context.update({"query": query, "results": results[:50]})
        return context


class AdministrationCenterView(LoginRequiredMixin, TemplateView):
    """Operational configuration hub; technical Django Admin remains separate."""

    template_name = "core/administration.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from apps.compliance.models import AlertRule, DocumentType
        from apps.core.models import AuditEvent, BackupConfig, OperationalTenant, TenantMembership
        from apps.workboard.models import KanbanBoard, KanbanLabel, KanbanStage

        sections = [
            {
                "title": _("Organization"),
                "description": _("Define the operational scope and who can access it."),
                "items": [
                    self.item(_("Operational tenants"), _("Manage organizations and their data boundaries."), "admin:core_operationaltenant_changelist", OperationalTenant),
                    self.item(_("Tenant memberships"), _("Assign users to an operational tenant."), "admin:core_tenantmembership_changelist", TenantMembership),
                ],
            },
            {
                "title": _("Compliance configuration"),
                "description": _("Prepare document and alert rules before loading records."),
                "items": [
                    self.item(_("Document types"), _("Control expiry requirements and document categories."), "documenttype-list", DocumentType),
                    self.item(_("Alert rules"), _("Define when AeroControl should generate an alert."), "alertrule-list", AlertRule),
                ],
            },
            {
                "title": _("Workboard configuration"),
                "description": _("Shape how teams organize and follow operational work."),
                "items": [
                    self.item(_("Boards"), _("Create and archive operational boards."), "board-list", KanbanBoard),
                    self.item(_("Stages"), _("Manage the workflow stages used by a board."), "stage-create", KanbanStage),
                    self.item(_("Labels"), _("Create labels used to classify tasks."), "label-list", KanbanLabel),
                ],
            },
            {
                "title": _("System"),
                "description": _("Review backups and trace changes without editing audit records."),
                "items": [
                    self.item(_("Backup configuration"), _("Review the local backup destination and schedule."), "admin:core_backupconfig_changelist", BackupConfig),
                    self.item(_("Audit events"), _("Read-only history of authenticated changes."), "admin:core_auditevent_changelist", AuditEvent, read_only=True),
                ],
            },
        ]
        context["sections"] = []
        for section in sections:
            items = [item for item in section["items"] if item]
            if items:
                context["sections"].append({**section, "items": items})
        context["technical_admin_url"] = "/admin/" if self.request.user.is_staff else ""
        return context

    def item(self, title, description, url_name, model, read_only=False):
        permission = f"{model._meta.app_label}.view_{model._meta.model_name}"
        if not self.request.user.has_perm(permission) and not self.request.user.is_superuser:
            return None
        return {"title": title, "description": description, "url": reverse(url_name), "read_only": read_only}


class StatusTransitionView(ModelPermissionRequiredMixin, View):
    model = None
    permission_action = "change"
    target_status = None
    valid_from_statuses = []
    success_message = "Status updated."

    def post(self, request, pk):
        obj = get_object_or_404(self.model, pk=pk, is_active=True)
        if obj.status not in self.valid_from_statuses:
            messages.error(
                request,
                _("Cannot transition from %(status)s")
                % {"status": obj.get_status_display()},
            )
            return redirect(obj)

        with transaction.atomic():
            obj.status = self.target_status
            obj._changed_by = request.user.get_username()
            obj._changed_by_user = request.user
            obj._transition_notes = request.POST.get("notes", "")
            obj.save(update_fields=["status", "updated_at"])
        messages.success(request, _(self.success_message))
        return redirect(obj)
