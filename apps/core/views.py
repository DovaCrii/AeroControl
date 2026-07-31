import csv
import json
import logging
from datetime import date, timedelta
from pathlib import Path

from django.contrib import messages
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import ImproperlyConfigured, PermissionDenied
from django.db import transaction
from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from django.conf import settings
from django.db import connection
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views import View
from django.views.generic import ListView, TemplateView
from .audit import set_audit_context


class SearchMixin:
    """Add text search and the common active/archive filter to list views."""

    search_fields = []
    htmx_template_name = "generic/_table_body.html"

    def get_template_names(self):
        if self.request.headers.get("HX-Request") == "true":
            return [self.htmx_template_name]
        return super().get_template_names()

    def _list_action_exists(self, suffix):
        """Whether `<list-path><suffix>` (e.g. `new/`) resolves to a view."""
        from django.urls import Resolver404, resolve

        try:
            resolve(f"{self.request.path}{suffix}")
        except Resolver404:
            return False
        return True

    def _row_action_exists(self, suffix=""):
        """Whether `<list-path><pk>/<suffix>` resolves to a real view.

        The generic table builds its row links relatively, and it offered View
        and Edit on every list whether or not the URLs existed: on document
        types, alert rules, flight records and maintenance history the buttons
        were 404s (or a modal stuck on "Loading...").
        """
        from uuid import uuid4

        from django.urls import Resolver404, resolve

        probe = f"{self.request.path}{uuid4()}/{suffix}"
        try:
            resolve(probe)
        except Resolver404:
            return False
        return True

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        meta = self.model._meta
        context["has_detail_url"] = self._row_action_exists()
        context["has_update_url"] = self._row_action_exists("edit/")
        # Restore shows only on archived rows, for models that support it and
        # users allowed to change them.
        context["has_restore_url"] = self._row_action_exists(
            "restore/"
        ) and self.request.user.has_perm(f"{meta.app_label}.change_{meta.model_name}")
        context["has_create_url"] = self._list_action_exists(
            "new/"
        ) and self.request.user.has_perm(f"{meta.app_label}.add_{meta.model_name}")
        # An empty table means two different things: no data yet (guide the
        # user to create the first record) or a filter that matched nothing
        # (offer to clear it). The template needs to know which.
        context["is_filtered"] = bool(
            self.request.GET.get("q") or self.request.GET.get("is_active")
        )
        return context

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


class _CsvEchoBuffer:
    """File-like object whose write() returns what it was given.

    csv.writer needs something with write(); returning the value lets each
    writerow() feed a StreamingHttpResponse instead of accumulating the whole
    export in memory.
    """

    def write(self, value):
        return value


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
        fields = self.csv_fields or [
            field
            for field in self.model._meta.fields
            if field.name
            not in {"id", "notes", "is_active", "created_at", "updated_at"}
        ]
        # str(value) on an FK column used to fire one query per relation per
        # row, and the whole table was materialised in memory: a full flight
        # log export was ~3 queries per row. Join the relations up front and
        # stream in chunks instead. select_related only accepts forward FK/O2O,
        # never M2M (OPS-4's FlightPermission.operators/aircraft_fleet), so
        # those are prefetched instead.
        related = [
            field.name
            for field in fields
            if field.is_relation and not field.many_to_many
        ]
        if related:
            queryset = queryset.select_related(*related)
        many_related = [field.name for field in fields if field.many_to_many]
        if many_related:
            queryset = queryset.prefetch_related(*many_related)

        def rows():
            yield "\ufeff"  # the BOM makes UTF-8 CSV open correctly in Excel
            buffer = _CsvEchoBuffer()
            writer = csv.writer(buffer, lineterminator="\r\n")
            yield writer.writerow([field.verbose_name.title() for field in fields])
            for obj in queryset.iterator(chunk_size=2000):
                row = []
                for field in fields:
                    if field.many_to_many:
                        # getattr() on a M2M field returns a manager, not a
                        # value; a plain str(value) would print a repr like
                        # "<RelatedManager ...>" instead of the members.
                        value = ", ".join(
                            str(item) for item in getattr(obj, field.name).all()
                        )
                        row.append(value)
                        continue
                    value = getattr(obj, field.name)
                    if value is None:
                        row.append("")
                    elif hasattr(value, "strftime"):
                        row.append(value.strftime("%Y-%m-%d"))
                    else:
                        value = str(value)
                        # Excel/LibreOffice interpret leading formula characters.
                        row.append(
                            f"'{value}"
                            if value.startswith(("=", "+", "-", "@"))
                            else value
                        )
                yield writer.writerow(row)

        response = StreamingHttpResponse(rows(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = (
            f'attachment; filename="{self.get_csv_filename()}"'
        )
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


# The calendar aggregates seven models, so no single model permission describes
# it. Each source is gated by the view permission of its own model instead: a
# user sees the event types they are allowed to see and nothing else.
CALENDAR_EVENT_PERMISSIONS = {
    "permission": "operations.view_flightpermission",
    "flight": "operations.view_flightrecord",
    "assignment": "registry.view_assignment",
    "maintenance": "maintenance.view_maintenancerecord",
    "document": "compliance.view_document",
    "qualification": "registry.view_qualification",
    "task": "workboard.view_kanbantask",
}


def allowed_calendar_types(user):
    """Calendar event types this user is allowed to see."""
    return {
        event_type
        for event_type, permission in CALENDAR_EVENT_PERMISSIONS.items()
        if user.has_perm(permission)
    }


class CalendarAccessMixin(LoginRequiredMixin):
    """Deny the calendar to a user who cannot view a single event source.

    Per-source filtering still happens inside each view; this only stops a user
    with no permissions at all from reaching the page, whose filter dropdowns
    would otherwise list every aircraft, operator and cost center on record.
    """

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not allowed_calendar_types(request.user):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class AlertCountPartial(LoginRequiredMixin, View):
    """Render the sidebar alert badge for periodic HTMX refreshes."""

    def get(self, request):
        from apps.compliance.models import Alert

        # Same read contract as the calendar (T2.3): an aggregate over alerts
        # is still alert data. Without the permission the badge renders empty
        # rather than 403ing, because it refreshes every 60s from the shell and
        # a red error would outshout the page the user is allowed to see.
        if not request.user.has_perm("compliance.view_alert"):
            return render(
                request, "core/_alert_badge.html", {"unresolved_alert_count": None}
            )
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
        checks["documents"] = (
            "ok" if documents.exists() and documents.is_dir() else "error"
        )
        healthy = all(value == "ok" for value in checks.values())
        return JsonResponse(
            {"status": "ok" if healthy else "degraded", "checks": checks},
            status=200 if healthy else 503,
        )


@method_decorator(csrf_exempt, name="dispatch")
class CspReportView(View):
    """Sink for browser CSP violation reports (the policy's report-uri).

    Public and CSRF-exempt because the browser posts it automatically with no
    token. It only logs; it never trusts the payload. The body is capped so a
    hostile client cannot flood the log with one request, and only the fields
    a real report carries are logged, never the raw blob.
    """

    MAX_BODY = 8192

    def post(self, request):
        raw = request.body[: self.MAX_BODY]
        try:
            report = json.loads(raw).get("csp-report", {})
        except (ValueError, AttributeError):
            report = {}
        logging.getLogger("aerocontrol.csp").warning(
            "csp_violation",
            extra={
                "blocked_uri": str(report.get("blocked-uri", ""))[:500],
                "violated_directive": str(report.get("violated-directive", ""))[:200],
                "document_uri": str(report.get("document-uri", ""))[:500],
            },
        )
        return HttpResponse(status=204)


class UnifiedCalendarEventsView(CalendarAccessMixin, View):
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

    # Widest window the calendar UI can legitimately ask for (a quarter).
    # start/end come straight from the query string, and without a clamp
    # ?start=2020-01-01&end=2035-01-01 serialised seven whole tables into one
    # JSON response - an authenticated user could stall the worker at will.
    MAX_RANGE_DAYS = 92

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
        if end < start:
            end = start
        end = min(end, start + timedelta(days=self.MAX_RANGE_DAYS))
        return start, end

    def get(self, request):
        from django.db.models import Q
        from django.contrib.contenttypes.models import ContentType
        from apps.compliance.models import Document
        from apps.maintenance.models import MaintenanceRecord
        from apps.operations.models import FlightPermission, FlightRecord
        from apps.registry.models import (
            Aircraft,
            Assignment,
            CostCenter,
            Operator,
            Qualification,
        )
        from apps.workboard.selectors import visible_tasks_for_user

        start, end = self.get_date_range(request)
        selected_types = set(filter(None, request.GET.get("types", "").split(",")))
        if not selected_types:
            selected_types = set(CALENDAR_EVENT_PERMISSIONS)
        # Asking for a type is not the same as being allowed to see it: the
        # requested set is narrowed to what the user may view, so a crafted
        # ?types= cannot widen the feed.
        selected_types &= allowed_calendar_types(request.user)
        events = []
        cost_center_id = request.GET.get("cost_center") or None
        aircraft_id = request.GET.get("aircraft") or None
        operator_id = request.GET.get("operator") or None

        # T3.2 Fase 1: single source of truth for read scoping (was an inline
        # membership query here and in the assignment list). None = all tenants
        # (superuser); otherwise the user's tenants, falling back to the default
        # tenant when they have no membership.
        from apps.core.tenancy import visible_tenant_ids

        tenant_ids = visible_tenant_ids(request.user)

        if "permission" in selected_types:
            # OPS-4: a permission now covers a validity range (not a single
            # flight_date) for a roster of operators/aircraft (not one of
            # each), so this is an overlap test against [start, end] and a
            # FullCalendar start/end range instead of a single "start" day.
            # select_related -> prefetch_related: M2M isn't selectable.
            permissions = FlightPermission.objects.filter(
                valid_from__lte=end, valid_until__gte=start, is_active=True
            ).prefetch_related("operators", "aircraft_fleet")
            if tenant_ids is not None:
                # T3.2 Fase 2: scope by the cost center's tenant, the single
                # canonical path, instead of an OR over operators/aircraft/CC
                # that matched a permission if *any* of its FKs was in the
                # tenant (F-08 leak across tenants on a mixed roster).
                permissions = permissions.filter(cost_center__tenant_id__in=tenant_ids)
            if cost_center_id:
                permissions = permissions.filter(cost_center_id=cost_center_id)
            if aircraft_id:
                permissions = permissions.filter(
                    aircraft_fleet__id=aircraft_id
                ).distinct()
            if operator_id:
                permissions = permissions.filter(operators__id=operator_id).distinct()

            def _permission_title(permission):
                names = [operator.full_name for operator in permission.operators.all()]
                if not names:
                    return permission.permission_number
                label = names[0] if len(names) == 1 else f"{names[0]} +{len(names) - 1}"
                return f"{permission.permission_number} · {label}"

            events.extend(
                {
                    "id": f"permission-{permission.pk}",
                    "type": "permission",
                    "title": _permission_title(permission),
                    "start": permission.valid_from.isoformat(),
                    "end": (permission.valid_until + timedelta(days=1)).isoformat(),
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
            assignments = (
                Assignment.objects.filter(
                    start_date__lte=end,
                    is_active=True,
                )
                .filter(Q(end_date__isnull=True) | Q(end_date__gte=start))
                .select_related("operator", "aircraft", "cost_center")
            )
            if tenant_ids is not None:
                # T3.2 Fase 2: canonical scope by the cost center's tenant; the
                # legacy Assignment allows a null cost center, so fall back to
                # the operator's tenant only in that case. No more OR-any-FK leak.
                assignments = assignments.filter(
                    Q(cost_center__tenant_id__in=tenant_ids)
                    | Q(cost_center__isnull=True, operator__tenant_id__in=tenant_ids)
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
                    "end": (assignment.end_date + timedelta(days=1)).isoformat()
                    if assignment.end_date
                    else None,
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
                maintenance = maintenance.filter(
                    aircraft__cost_center_id=cost_center_id
                )
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
            ).select_related("operator", "qualification_type")
            if tenant_ids is not None:
                qualifications = qualifications.filter(
                    operator__tenant_id__in=tenant_ids
                )
            if cost_center_id:
                qualifications = qualifications.filter(
                    operator__cost_center_id=cost_center_id
                )
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
                # T3.2 Fase 2: Document now carries its own tenant (Fase 0b), so
                # scope on it directly instead of deriving through the subject's
                # ContentType (three subqueries) -- simpler and canonical.
                documents = documents.filter(tenant_id__in=tenant_ids)
            if aircraft_id:
                documents = documents.filter(
                    content_type=ContentType.objects.get_for_model(Aircraft),
                    object_id=aircraft_id,
                )
            elif operator_id:
                documents = documents.filter(
                    content_type=ContentType.objects.get_for_model(Operator),
                    object_id=operator_id,
                )
            elif cost_center_id:
                documents = documents.filter(
                    content_type=ContentType.objects.get_for_model(CostCenter),
                    object_id=cost_center_id,
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
            tasks = (
                visible_tasks_for_user(request.user)
                .filter(due_date__range=(start, end))
                .select_related("board", "stage", "assigned_to")
            )
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
                    # Month cells only fit ~2 short lines. The stage is already
                    # conveyed by the event colour, so it moves to the tooltip
                    # instead of doubling the title length.
                    "title": task.title,
                    "tooltip": f"{task.title} · {task.stage.name}",
                    "start": task.due_date.isoformat(),
                    "allDay": True,
                    "color": self.EVENT_COLORS["task"],
                    # The task detail endpoint is an HTMX fragment. Link calendar
                    # events to the full Workboard view so direct navigation never
                    # leaves the user on an unstyled fragment page.
                    "url": f"{reverse('kanban')}?board={task.board_id}",
                }
                for task in tasks
            )

        return JsonResponse(events, safe=False)


class GlobalSearchView(LoginRequiredMixin, TemplateView):
    template_name = "core/search.html"

    SEARCH_SOURCES = (
        ("registry", "CostCenter", "costcenter-list", ("code", "name")),
        ("registry", "Aircraft", "aircraft-list", ("registration", "model", "type")),
        (
            "registry",
            "Operator",
            "operator-list",
            ("employee_id", "full_name", "email"),
        ),
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
                if not self.request.user.has_perm(
                    f"{app_label}.view_{model._meta.model_name}"
                ):
                    continue
                condition = Q()
                for field in fields:
                    condition |= Q(**{f"{field}__icontains": query})
                objects = model.objects.filter(condition, is_active=True).order_by(
                    "-updated_at"
                )[:10]
                for obj in objects:
                    results.append(
                        {
                            "model": model._meta.verbose_name.title(),
                            "label": str(obj),
                            "url": reverse(url_name),
                            "id": obj.pk,
                        }
                    )
        context.update({"query": query, "results": results[:50]})
        return context


class AdministrationCenterView(LoginRequiredMixin, TemplateView):
    """Operational configuration hub; technical Django Admin remains separate."""

    template_name = "core/administration.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from django.contrib.auth.models import User

        from apps.compliance.models import AlertRule, DocumentType
        from apps.core.models import (
            AuditEvent,
            BackupConfig,
            OperationalTenant,
            TenantMembership,
        )
        from apps.registry.models import QualificationType
        from apps.workboard.models import KanbanBoard, KanbanLabel, KanbanStage

        sections = [
            {
                "title": _("Organization"),
                "description": _("Define the operational scope and who can access it."),
                "items": [
                    self.item(
                        _("Operational tenants"),
                        _("Manage organizations and their data boundaries."),
                        "admin:core_operationaltenant_changelist",
                        OperationalTenant,
                        icon="organization",
                    ),
                    self.item(
                        _("Tenant memberships"),
                        _("Assign users to an operational tenant."),
                        "admin:core_tenantmembership_changelist",
                        TenantMembership,
                        icon="people",
                    ),
                    self.item(
                        _("Users and roles"),
                        _("Read-only view of who holds which role."),
                        "user-role-list",
                        User,
                        icon="people",
                        read_only=True,
                    ),
                ],
            },
            {
                "title": _("Compliance configuration"),
                "description": _(
                    "Prepare document and alert rules before loading records."
                ),
                "items": [
                    self.item(
                        _("Document types"),
                        _("Control expiry requirements and document categories."),
                        "documenttype-list",
                        DocumentType,
                        icon="document",
                    ),
                    self.item(
                        _("Alert rules"),
                        _("Define when AeroControl should generate an alert."),
                        "alertrule-list",
                        AlertRule,
                        icon="bell",
                    ),
                    self.item(
                        _("Qualification types"),
                        _("Operator ratings and the aircraft models they cover."),
                        "qualificationtype-list",
                        QualificationType,
                        icon="tag",
                    ),
                ],
            },
            {
                "title": _("Workboard configuration"),
                "description": _(
                    "Shape how teams organize and follow operational work."
                ),
                "items": [
                    self.item(
                        _("Boards"),
                        _("Create and archive operational boards."),
                        "board-list",
                        KanbanBoard,
                        icon="board",
                    ),
                    self.item(
                        _("Stages"),
                        _("Manage the workflow stages used by a board."),
                        "stage-create",
                        KanbanStage,
                        icon="columns",
                    ),
                    self.item(
                        _("Labels"),
                        _("Create labels used to classify tasks."),
                        "label-list",
                        KanbanLabel,
                        icon="tag",
                    ),
                ],
            },
            {
                # Was "System", which repeated the page's own eyebrow and said
                # nothing about what is inside.
                "title": _("Backups and audit"),
                "description": _(
                    "Review backups and trace changes without editing audit records."
                ),
                "items": [
                    self.item(
                        _("Backup configuration"),
                        _("Review the local backup destination and schedule."),
                        "admin:core_backupconfig_changelist",
                        BackupConfig,
                        icon="backup",
                    ),
                    self.item(
                        _("Audit log"),
                        _("Filterable, read-only audit trail inside the app."),
                        "audit-log",
                        AuditEvent,
                        icon="history",
                        read_only=True,
                    ),
                    self.item(
                        _("Audit events (technical)"),
                        _("Read-only history of authenticated changes."),
                        "admin:core_auditevent_changelist",
                        AuditEvent,
                        icon="history",
                        read_only=True,
                    ),
                ],
            },
        ]
        context["sections"] = []
        for section in sections:
            items = [item for item in section["items"] if item]
            if items:
                context["sections"].append({**section, "items": items})
        context["technical_admin_url"] = "/admin/" if self.request.user.is_staff else ""
        context["situation"] = self._build_situation(self.request.user)
        return context

    # ── BLOQUE 5: situation panel (read-only) ────────────────────────────────
    # Each block is gated by its own view_* permission, like the config rows and
    # the calendar tabs: no permission simply hides that block, never 403s.
    DAILY_JOBS = {"generate_alerts": 48, "send_alert_digest": 48, "backup": 48}
    WATCHED_JOBS = [
        "generate_alerts",
        "send_alert_digest",
        "backup",
        "send_executive_report",
    ]

    def _build_situation(self, user):
        metrics = self._situation_metrics(user)
        jobs = self._situation_jobs(user)
        can_view_backup = user.has_perm("core.view_backupconfig")
        backup = self._latest_backup() if can_view_backup else None
        health = self._situation_health() if jobs is not None else None
        return {
            "metrics": metrics,
            "jobs": jobs,
            "backup": backup,
            "can_view_backup": can_view_backup,
            "health": health,
            "has_any": bool(metrics or jobs is not None or can_view_backup),
        }

    def _situation_metrics(self, user):
        from datetime import timedelta

        metrics = []
        today = timezone.localdate()
        if user.has_perm("compliance.view_alert"):
            from apps.compliance.models import Alert

            count = Alert.objects.filter(is_active=True, is_resolved=False).count()
            metrics.append(
                {
                    "label": _("Unresolved alerts"),
                    "value": count,
                    "tone": "warn" if count else "ok",
                    "url": reverse("alert-list"),
                }
            )
        if user.has_perm("compliance.view_document"):
            from apps.compliance.models import Document

            count = Document.objects.filter(
                is_active=True,
                is_current_version=True,
                expiry_date__isnull=False,
                expiry_date__lte=today + timedelta(days=30),
            ).count()
            metrics.append(
                {
                    "label": _("Documents expiring in 30 days"),
                    "value": count,
                    "tone": "warn" if count else "ok",
                    "url": reverse("document-list"),
                }
            )
        if user.has_perm("compliance.view_alertrule"):
            from apps.compliance.models import AlertRule

            count = AlertRule.objects.filter(is_active=True, enabled=True).count()
            metrics.append(
                {"label": _("Active alert rules"), "value": count, "tone": "muted"}
            )
        if user.has_perm("auth.view_user"):
            from django.contrib.auth import get_user_model

            count = (
                get_user_model()
                .objects.filter(is_active=True, groups__isnull=True)
                .count()
            )
            metrics.append(
                {
                    "label": _("Users without a role"),
                    "value": count,
                    "tone": "warn" if count else "ok",
                }
            )
        return metrics

    def _situation_jobs(self, user):
        if not user.has_perm("core.view_jobrun"):
            return None
        from datetime import timedelta

        from apps.core.models import JobRun

        now = timezone.now()
        rows = []
        for command in self.WATCHED_JOBS:
            run = JobRun.objects.filter(command=command).order_by("-started_at").first()
            max_age = self.DAILY_JOBS.get(command)
            if run is None:
                rows.append(
                    {"command": command, "result": None, "when": None, "stale": True}
                )
                continue
            reference = run.finished_at or run.started_at
            stale = max_age is not None and (now - reference) > timedelta(hours=max_age)
            rows.append(
                {
                    "command": command,
                    "result": run.result,
                    "when": run.started_at,
                    "stale": stale,
                }
            )
        return rows

    @staticmethod
    def _situation_health():
        checks = {}
        try:
            connection.ensure_connection()
            checks["database"] = True
        except Exception:
            checks["database"] = False
        documents = Path(settings.DOCUMENTS_ROOT)
        checks["documents"] = documents.exists() and documents.is_dir()
        return checks

    @staticmethod
    def _latest_backup():
        import json

        from apps.core.management.commands.backup import backups_dir

        directory = backups_dir()
        try:
            manifests = sorted(
                directory.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True
            )
        except OSError:
            return None
        for manifest in manifests:
            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if "sha256" in data:
                return {
                    "name": data.get("backup", manifest.stem),
                    "created_at": data.get("created_at", ""),
                    "sha256": data.get("sha256", ""),
                    "size": data.get("size"),
                }
        return None

    def item(self, title, description, url_name, model, icon, read_only=False):
        """One row of the administration list.

        `icon` names a symbol in the sprite at the top of the template. Every
        row used to draw the same cog, which meant the icons carried no
        information and only added noise to nine near-identical rows.
        """
        permission = f"{model._meta.app_label}.view_{model._meta.model_name}"
        if (
            not self.request.user.has_perm(permission)
            and not self.request.user.is_superuser
        ):
            return None
        return {
            "title": title,
            "description": description,
            "url": reverse(url_name),
            "icon": icon,
            "read_only": read_only,
        }


class AuditEventListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """B5.4: read-only audit trail, filterable by actor / model / date range.

    Gated on ``core.view_auditevent`` (withheld from the Viewer role). The model
    itself is append-only, so there is nothing to edit here — this is a window
    onto the trail, not an editor.
    """

    permission_required = "core.view_auditevent"
    raise_exception = True
    template_name = "core/audit_log.html"
    context_object_name = "events"
    paginate_by = 50

    def get_queryset(self):
        from .models import AuditEvent

        queryset = AuditEvent.objects.select_related("actor")  # ordered -sequence
        actor = self.request.GET.get("actor", "").strip()
        if actor:
            queryset = queryset.filter(actor__username__icontains=actor)
        model_label = self.request.GET.get("model", "").strip()
        if model_label:
            queryset = queryset.filter(model_label__icontains=model_label)
        since = self.request.GET.get("since", "").strip()
        if since:
            queryset = queryset.filter(created_at__date__gte=since)
        until = self.request.GET.get("until", "").strip()
        if until:
            queryset = queryset.filter(created_at__date__lte=until)
        return queryset

    def get_context_data(self, **kwargs):
        from .models import AuditEvent

        context = super().get_context_data(**kwargs)
        context["model_labels"] = (
            AuditEvent.objects.exclude(model_label="")
            .values_list("model_label", flat=True)
            .distinct()
            .order_by("model_label")
        )
        context["filters"] = {
            "actor": self.request.GET.get("actor", ""),
            "model": self.request.GET.get("model", ""),
            "since": self.request.GET.get("since", ""),
            "until": self.request.GET.get("until", ""),
        }
        return context


class UserRoleListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """B5.5: read-only panel of users and the roles (groups) they hold.

    Answers "who can do what" at a glance without opening the technical Django
    admin. Gated on ``auth.view_user`` (the Viewer role does not have it). Edits
    still happen in /admin/ -- this is a window, with a link there.
    """

    permission_required = "auth.view_user"
    raise_exception = True
    template_name = "core/users_roles.html"
    context_object_name = "users"
    paginate_by = 50

    def get_queryset(self):
        from django.contrib.auth.models import User

        return User.objects.prefetch_related("groups").order_by("username")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["technical_admin_url"] = (
            "/admin/auth/user/" if self.request.user.is_staff else ""
        )
        return context


class StatusTransitionView(ModelPermissionRequiredMixin, View):
    model = None
    permission_action = "change"
    target_status = None
    valid_from_statuses = []
    # Subclasses must set this with a *marked* literal (gettext_lazy):
    # `_(self.success_message)` on a variable is invisible to makemessages, so
    # every transition message rendered in English inside a Spanish UI.
    success_message = gettext_lazy("Status updated.")

    def post(self, request, pk):
        obj = get_object_or_404(self.model, pk=pk, is_active=True)
        if obj.status not in self.valid_from_statuses:
            set_audit_context(
                request,
                obj,
                action="status_transition_rejected",
                metadata={"from_status": obj.status, "to_status": self.target_status},
            )
            messages.error(
                request,
                _("Cannot transition from %(status)s")
                % {"status": obj.get_status_display()},
            )
            return redirect(obj)

        from_status = obj.status
        with transaction.atomic():
            obj.status = self.target_status
            obj._changed_by = request.user.get_username()
            obj._changed_by_user = request.user
            obj._transition_notes = request.POST.get("notes", "")
            obj.save(update_fields=["status", "updated_at"])
        set_audit_context(
            request,
            obj,
            action="status_changed",
            metadata={"from_status": from_status, "to_status": self.target_status},
        )
        messages.success(request, self.success_message)
        return redirect(obj)
