from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
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
        return queryset


class HtmxFormMixin:
    """Return form fragments for HTMX while preserving normal form behavior."""

    htmx_template_name = "generic/_form_content.html"

    def get_template_names(self):
        if self.request.headers.get("HX-Request") == "true":
            return [self.htmx_template_name]
        return super().get_template_names()

    def form_invalid(self, form):
        if self.request.headers.get("HX-Request") == "true":
            return render(self.request, self.htmx_template_name, self.get_context_data(form=form), status=422)
        return super().form_invalid(form)

    def form_valid(self, form):
        response = super().form_valid(form)
        if self.request.headers.get("HX-Request") == "true":
            return HttpResponse(status=204, headers={"HX-Trigger": "modal-form-success"})
        return response


class AlertCountPartial(LoginRequiredMixin, View):
    """Render the sidebar alert badge for periodic HTMX refreshes."""

    def get(self, request):
        from apps.compliance.models import Alert

        count = Alert.objects.filter(is_active=True, is_resolved=False).count()
        return render(request, "core/_alert_badge.html", {"unresolved_alert_count": count})


class StatusTransitionView(LoginRequiredMixin, View):
    model = None
    target_status = None
    valid_from_statuses = []
    success_message = "Status updated."

    def post(self, request, pk):
        obj = get_object_or_404(self.model, pk=pk, is_active=True)
        if obj.status not in self.valid_from_statuses:
            messages.error(request, f"Cannot transition from {obj.get_status_display()}")
            return redirect(obj)

        obj.status = self.target_status
        obj._changed_by = request.user.get_username()
        obj._transition_notes = request.POST.get("notes", "")
        obj.save(update_fields=["status", "updated_at"])
        messages.success(request, self.success_message)
        return redirect(obj)
