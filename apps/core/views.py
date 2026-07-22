import csv
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
from django.utils.translation import gettext as _
from django.views import View


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
            obj._transition_notes = request.POST.get("notes", "")
            obj.save(update_fields=["status", "updated_at"])
        messages.success(request, _(self.success_message))
        return redirect(obj)
