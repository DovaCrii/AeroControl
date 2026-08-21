import calendar
from datetime import date, datetime, timedelta
from urllib.parse import quote

from django.contrib import messages
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView
from django.utils.text import capfirst, slugify

from apps.core.audit import set_audit_context
from apps.core.tenancy import scope_queryset_to_tenant
from apps.core.views import (
    CALENDAR_EVENT_PERMISSIONS,
    CalendarAccessMixin,
    CsvExportMixin,
    HtmxFormMixin,
    ModelPermissionRequiredMixin,
    ModelViewPermissionRequiredMixin,
    SearchMixin,
    StatusTransitionView,
    TenantScopedQuerysetMixin,
    allowed_calendar_types,
)
from apps.geo.models import GeoPlan
from apps.geo.sections import format_dms, split_sections
from .forms import (
    FlightPermissionForm,
    FlightPermissionUpdateForm,
    FlightRecordForm,
    FlightRequestForm,
    FlightRequestNoteForm,
    FlightRequestWorkItemForm,
    StatusCorrectionForm,
)
from .dossier import operational_dossier
from .flight_requests import (
    create_requests_from_plan,
    link_to_permission,
    section_kmz,
    sigo_sheet,
)
from .models import (
    FlightPermission,
    FlightRecord,
    FlightRequest,
    FlightRequestWorkItem,
)
from .selectors import DAILY_FLIGHT_LIMIT, duty_time_for, format_duration
from apps.registry.models import Aircraft, CostCenter, Operator
from apps.registry.selectors import operator_aircraft_compatibility_gaps


class OList(CsvExportMixin, SearchMixin, ModelViewPermissionRequiredMixin, ListView):
    template_name = "generic/list.html"
    context_object_name = "objects"
    paginate_by = 25

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = capfirst(self.model._meta.verbose_name_plural)
        return context


class OCreate(HtmxFormMixin, ModelPermissionRequiredMixin, CreateView):
    permission_action = "add"
    template_name = "generic/form.html"
    # This app's list URLs are named "permission-list"/"record-list", not the
    # "<model_name>-list" this base class assumed (a pre-existing bug: a
    # successful create crashed with NoReverseMatch, caught by OPS-4's first
    # test that POSTs all the way through FlightPermissionCreate).
    success_url_name = None

    def get_success_url(self):
        return reverse(self.success_url_name or f"{self.model._meta.model_name}-list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = _("New %(record)s") % {
            "record": self.model._meta.verbose_name
        }
        return context


class FlightPermissionList(
    CsvExportMixin, SearchMixin, ModelViewPermissionRequiredMixin, ListView
):
    model = FlightPermission
    template_name = "operations/permission_list.html"
    # LV-53: own partial (Operators/Aircraft/Validity/Status columns), not the
    # generic created_at/is_active one -- same reason as OperatorList's
    # override (T5.6\F-13): a live-search HTMX response must carry this
    # list's own columns, or the search result collapses to the generic ones.
    htmx_template_name = "operations/_permission_rows.html"
    context_object_name = "objects"
    paginate_by = 25
    # R2.2/R2.3: internal_folio is the identifier every screen actually
    # shows now; permission_number (the DGAC folio) stays searchable too,
    # it just is not always present. R2.7: the placeholder ("Search number,
    # purpose, location...") promised purpose/location matches that
    # search_fields never actually had -- purpose_detail (not the now-closed
    # `purpose` code) is the free text a search box should match.
    search_fields = [
        "internal_folio",
        "permission_number",
        "purpose_detail",
        "location",
    ]
    # Explicit override: the default (self.model._meta.fields) silently drops
    # ManyToManyFields (operators/aircraft_fleet live in _meta.many_to_many,
    # not _meta.fields), so without this the CSV export would quietly lose
    # its two most useful columns instead of erroring.
    csv_fields = [
        FlightPermission._meta.get_field(name)
        for name in (
            "internal_folio",
            "permission_number",
            "operators",
            "aircraft_fleet",
            "cost_center",
            "purpose",
            "valid_from",
            "valid_until",
            "location",
            "region",
            "commune",
            "area_name",
            "latitude",
            "longitude",
            "radius_km",
            "max_altitude_ft",
            "status",
        )
    ]

    def get_queryset(self):
        queryset = (
            super().get_queryset().prefetch_related("operators", "aircraft_fleet")
        )
        status = self.request.GET.get("status", "")
        if status in dict(FlightPermission.STATUS_CHOICES):
            queryset = queryset.filter(status=status)
        # OPS-4: a permission now covers a range, so "on or after date_from" /
        # "on or before date_to" become an overlap test against that range,
        # not an equality test against a single flight_date.
        if self.request.GET.get("date_from"):
            queryset = queryset.filter(valid_until__gte=self.request.GET["date_from"])
        if self.request.GET.get("date_to"):
            queryset = queryset.filter(valid_from__lte=self.request.GET["date_to"])
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            title=_("Permissions"),
            status_choices=FlightPermission.STATUS_CHOICES,
            current_status=self.request.GET.get("status", ""),
        )
        # LV-53: SearchMixin's is_filtered only knows about q/is_active, not
        # this list's own status/date_from/date_to -- widen it so "cleared
        # filters" offers correctly when only those are set.
        context["is_filtered"] = context["is_filtered"] or bool(
            self.request.GET.get("status")
            or self.request.GET.get("date_from")
            or self.request.GET.get("date_to")
        )
        return context


class FlightPermissionCreate(OCreate):
    model = FlightPermission
    form_class = FlightPermissionForm
    success_url_name = "permission-list"

    def form_valid(self, form):
        """B4.4: warn (do not block) when an assigned operator has no current
        qualification matching an assigned aircraft's model.

        The M2M rosters (operators, aircraft_fleet) only exist on self.object
        once form.save_m2m() has run, which happens inside
        super().form_valid() -- so the check has to come after it, not before.
        """
        response = super().form_valid(form)
        gaps = operator_aircraft_compatibility_gaps(
            self.object.operators.all(), self.object.aircraft_fleet.all()
        )
        aircraft_by_operator = {}
        for operator, aircraft in gaps:
            aircraft_by_operator.setdefault(operator, []).append(aircraft)
        for operator, aircraft_list in aircraft_by_operator.items():
            messages.warning(
                self.request,
                _(
                    "%(operator)s has no current qualification matching: "
                    "%(aircraft)s. The permission was saved; review the "
                    "operator's qualifications."
                )
                % {
                    "operator": operator,
                    "aircraft": ", ".join(str(a) for a in aircraft_list),
                },
            )
        return response


class FlightPermissionUpdate(
    TenantScopedQuerysetMixin, HtmxFormMixin, ModelPermissionRequiredMixin, UpdateView
):
    """R2.1: the only way to correct a permission used to be /admin/ -- there
    was no FlightPermissionUpdate/permission-update at all. Same pattern as
    RegistryUpdate; local rather than shared because this app's success URL
    ("permission-list", not "flightpermission-list") already needed its own
    override, same reason OCreate does."""

    model = FlightPermission
    # LV-101: not FlightPermissionForm -- the update variant drops `status`,
    # which turned this screen into a back door around every transition guard.
    form_class = FlightPermissionUpdateForm
    template_name = "generic/form.html"
    permission_action = "change"
    tenant_path = "cost_center__tenant_id"

    def get_queryset(self):
        return super().get_queryset().filter(is_active=True)

    def get_success_url(self):
        return reverse("permission-list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = _("Edit %(record)s") % {
            "record": self.model._meta.verbose_name
        }
        return context


class FlightPermissionDetail(
    TenantScopedQuerysetMixin, ModelViewPermissionRequiredMixin, DetailView
):
    model = FlightPermission
    template_name = "operations/permission_detail.html"
    context_object_name = "permission"
    tenant_path = "cost_center__tenant_id"

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .filter(is_active=True)
            .prefetch_related("operators", "aircraft_fleet")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # LV-107: "¿esta operación está completa y documentada?" respondida acá,
        # en vez de abriendo cinco pantallas y acordándose de todas. Composición
        # pura de lo que ya existe -- ver apps/operations/dossier.py.
        context["dossier"] = operational_dossier(self.object)
        # LV-72: the SIGO trace shows *who, with what role, when*. The role is
        # the user's groups, prefetched here rather than resolved per row --
        # `{{ h.changed_by_user.groups.all }}` in the template would be one
        # query per history entry (the shape V.18/V.19 already cost this
        # project twice).
        # Oldest first, unlike the model's default: SIGO numbers the trace 1..N
        # in the order things happened, and "in what order" is half of what the
        # screen is for.
        context["history"] = (
            self.object.history.select_related("changed_by_user")
            .prefetch_related("changed_by_user__groups")
            .order_by("sequence")
        )
        context["flight_records"] = self.object.records.filter(is_active=True)
        # OPS-5: attachments (additional letters/correspondence) through the
        # existing generic Document pipeline -- FlightPermission is already in
        # DOCUMENTABLE_MODELS (apps/compliance/forms.py), this just surfaces
        # them here and links to the existing upload form, pre-filled.
        if self.request.user.has_perm("compliance.view_document"):
            from django.contrib.contenttypes.models import ContentType

            from apps.compliance.models import Document

            content_type = ContentType.objects.get_for_model(FlightPermission)
            context["permission_content_type_id"] = content_type.pk
            context["documents"] = Document.objects.filter(
                content_type=content_type,
                object_id=self.object.pk,
                is_current_version=True,
                is_active=True,
            ).order_by("-issue_date")
        else:
            context["documents"] = None
        # R2.5: a single dropdown instead of one button per transition -- most
        # visits do not change the status at all, and the previous row of
        # colour-coded buttons was more chrome than the decision warranted.
        # Full URLs (not the bare "approve"/"deny" slug the old template
        # built into "{{ action }}/") so the JS that swaps the form's action
        # before submit does not have to know the URL structure.
        if self.object.status == "requested" and self.request.user.has_perm(
            "operations.change_flightpermission"
        ):
            actions = [
                (_("Approve"), reverse("permission-approve", args=[self.object.pk])),
                (_("Deny"), reverse("permission-deny", args=[self.object.pk])),
            ]
        elif self.object.status == "approved" and self.request.user.has_perm(
            "operations.change_flightpermission"
        ):
            actions = [
                (_("Complete"), reverse("permission-complete", args=[self.object.pk]))
            ]
        else:
            actions = []
        context["status_actions"] = actions
        return context


def has_dgac_authorization(permission):
    """Whether the signed DGAC operation authorization is on file (LV-51/LV-64).

    Extracted from the mixin below when LV-101 added the correction route: the
    guard is about a fact in the world, so both routes have to ask the same
    question. A second copy is how one of them quietly stops asking it.

    Deliberately **not** "dgac-flight-permit" -- that is the letter that goes
    *to* the DGAC as part of the request, and it can exist long before any
    approval.
    """
    from apps.compliance.models import Document

    return Document.objects.filter(
        content_type=ContentType.objects.get_for_model(type(permission)),
        object_id=permission.pk,
        doc_type__code="dgac-rpa-operation-authorization",
        is_current_version=True,
        is_active=True,
    ).exists()


class RequireDgacPermitPdfMixin:
    """LV-51/LV-64/R2.4: the signed DGAC authorization ("Autorización de
    Operación RPA", the folio'd PDF that comes back once the DGAC actually
    approves the operation) must be on file before a permit can move to
    this status -- otherwise AeroControl's status can outrun the real DGAC
    paperwork. This is deliberately NOT "dgac-flight-permit" (the letter
    that goes *to* the DGAC as part of the request) -- that one can exist
    long before an approval and does not itself certify one. Originally
    only guarded Approve (LV-64); R2.4 extended it to Complete because a
    permit reaching approved and then completed without ever attaching the
    signed PDF was still possible. Checked before the base transition, same
    guard shape as MaintenanceComplete's pre-check."""

    missing_pdf_message = None

    def post(self, request, pk):
        permission = get_object_or_404(self.model, pk=pk, is_active=True)
        if not has_dgac_authorization(permission):
            messages.error(request, self.missing_pdf_message)
            return redirect(permission)
        return super().post(request, pk)


class FlightPermissionApprove(RequireDgacPermitPdfMixin, StatusTransitionView):
    model = FlightPermission
    target_status = "approved"
    valid_from_statuses = ["requested"]
    success_message = gettext_lazy("Permission approved.")
    missing_pdf_message = gettext_lazy(
        "Upload the DGAC operation authorization (the signed SIGO PDF) "
        "before approving this permit."
    )


class FlightPermissionDeny(StatusTransitionView):
    model = FlightPermission
    target_status = "denied"
    valid_from_statuses = ["requested"]
    success_message = gettext_lazy("Permission denied.")


class FlightPermissionComplete(RequireDgacPermitPdfMixin, StatusTransitionView):
    model = FlightPermission
    target_status = "completed"
    valid_from_statuses = ["approved"]
    success_message = gettext_lazy("Permission completed.")
    missing_pdf_message = gettext_lazy(
        "Upload the DGAC operation authorization (the signed SIGO PDF) "
        "before completing this permit."
    )


class FlightPermissionCorrectStatus(ModelPermissionRequiredMixin, View):
    """LV-101: the front door for fixing a status that is wrong.

    The guarded transitions answer "what happens next". This answers "what was
    recorded is not what happened" -- a different act, and one that has to exist:
    the back door it replaces was found precisely because somebody used it to
    undo a mistaken "completed".

    Three things it does that the edit screen did not: it **demands a written
    reason**, it records **who** (so the history stops saying `system`), and it
    keeps the DGAC paperwork guard. That last one is deliberate: LV-51/LV-64 are
    about a fact in the world -- whether the signed authorization exists -- not
    about which screen the change came from. A correction that could reach
    "approved" with no PDF on file would be the same hole with one more click.
    """

    model = FlightPermission
    permission_action = "change"
    title = gettext_lazy("Correct the status")
    # The statuses whose paperwork guard applies, whatever route reaches them.
    GUARDED_STATUSES = ("approved", "completed")

    def _permission(self, pk):
        return get_object_or_404(
            scope_queryset_to_tenant(
                FlightPermission.objects.all(),
                self.request.user,
                "cost_center__tenant_id",
            ),
            pk=pk,
            is_active=True,
        )

    def _render(self, request, form, status=200):
        return render(
            request,
            "generic/_form_content.html",
            {"form": form, "title": self.title},
            status=status,
        )

    def get(self, request, pk):
        permission = self._permission(pk)
        return self._render(
            request, StatusCorrectionForm(current_status=permission.status)
        )

    def post(self, request, pk):
        permission = self._permission(pk)
        form = StatusCorrectionForm(request.POST, current_status=permission.status)
        if not form.is_valid():
            return self._render(request, form, status=422)

        target = form.cleaned_data["status"]
        if target in self.GUARDED_STATUSES and not has_dgac_authorization(permission):
            form.add_error(
                "status",
                _(
                    "Upload the DGAC operation authorization (the signed SIGO "
                    "PDF) before correcting this permit to that status."
                ),
            )
            set_audit_context(
                request,
                permission,
                action="status_correction_rejected",
                metadata={"from_status": permission.status, "to_status": target},
            )
            return self._render(request, form, status=422)

        previous = permission.status
        reason = form.cleaned_data["reason"]
        with transaction.atomic():
            permission.status = target
            permission._changed_by = request.user.get_username()
            permission._changed_by_user = request.user
            # Prefixed so the history row reads as a correction and not as a
            # transition that happened: the two mean different things to whoever
            # audits this, and the notes column is where they are told apart.
            permission._transition_notes = _("Correction: %(reason)s") % {
                "reason": reason
            }
            permission.save(update_fields=["status", "updated_at"])
        set_audit_context(
            request,
            permission,
            action="status_corrected",
            metadata={"from_status": previous, "to_status": target, "reason": reason},
        )
        if request.headers.get("HX-Request") == "true":
            return HttpResponse(
                status=204, headers={"HX-Trigger": "modal-form-success"}
            )
        messages.success(request, _("Status corrected."))
        return redirect(permission)


class FlightRecordList(OList):
    """LV-59: was the generic created_at/is_active columns (this was the
    only list in the area without its own), which is also how a Vuelos
    screenshot ended up showing "Nombre" as a column header. Real columns
    (LV-57 pattern) plus the flight duration, which was stored but never
    computed anywhere."""

    model = FlightRecord
    template_name = "operations/record_list.html"
    htmx_template_name = "operations/_record_rows.html"
    search_fields = [
        "permission__permission_number",
        "pilot__full_name",
        "aircraft__registration",
    ]

    def get_queryset(self):
        return super().get_queryset().select_related("permission", "pilot", "aircraft")


class DutyLimitWarningMixin:
    """R7.5: warn when a pilot's logged flight time for a day passes the limit.

    A warning, not a rejection. The limit is a fatigue control (ISO 45001
    6.1.2), and the record is written *after* the flight: refusing to save it
    would not un-fly the day, it would only leave the excess unrecorded --
    losing the very evidence the clause exists to produce. So the flight is
    always saved and the excess is said out loud, here and in the daily job.
    """

    def form_valid(self, response_or_form):
        response = super().form_valid(response_or_form)
        record = self.object
        if record.pilot_id and record.actual_date:
            total = duty_time_for(record.pilot, record.actual_date)
            if total > DAILY_FLIGHT_LIMIT:
                messages.warning(
                    self.request,
                    _(
                        "%(pilot)s now has %(total)s logged on %(date)s, over the "
                        "%(limit)s daily flight limit."
                    )
                    % {
                        "pilot": record.pilot,
                        "total": format_duration(total),
                        "date": record.actual_date.isoformat(),
                        "limit": format_duration(DAILY_FLIGHT_LIMIT),
                    },
                )
        return response


class FlightRecordCreate(DutyLimitWarningMixin, OCreate):
    model = FlightRecord
    form_class = FlightRecordForm
    template_name = "operations/flightrecord_form.html"
    success_url_name = "record-list"

    def get_initial(self):
        initial = super().get_initial()
        for field in ("permission", "pilot", "aircraft"):
            value = self.request.GET.get(field)
            if value:
                initial[field] = value
        return initial


class FlightRecordDetail(
    TenantScopedQuerysetMixin, ModelViewPermissionRequiredMixin, DetailView
):
    model = FlightRecord
    template_name = "operations/flightrecord_detail.html"
    context_object_name = "record"
    tenant_path = "aircraft__tenant_id"

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .filter(is_active=True)
            .select_related("permission", "pilot", "aircraft")
        )


class FlightRecordDelete(ModelPermissionRequiredMixin, DetailView):
    model = FlightRecord
    permission_action = "delete"
    context_object_name = "object"

    def post(self, request, *args, **kwargs):
        record = self.get_object()
        record.is_active = False
        record.save(update_fields=["is_active", "updated_at"])
        set_audit_context(request, record, action="archived")
        messages.success(request, _("Flight record archived."))
        return redirect("record-list")


class CalendarView(CalendarAccessMixin, ListView):
    template_name = "core/calendar.html"
    context_object_name = "events_by_date"

    def get_queryset(self):
        return []

    def filter_options(self, model, permission, order_field):
        """Active rows for a filter dropdown, empty without the permission."""
        if not self.request.user.has_perm(permission):
            return model.objects.none()
        return model.objects.filter(is_active=True).order_by(order_field)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.now().date()
        try:
            selected = datetime.strptime(
                self.request.GET.get("month", ""), "%Y-%m"
            ).date()
        except ValueError:
            selected = today.replace(day=1)
        year, month = selected.year, selected.month
        # __range instead of __year/__month: SQLite cannot use an index for the
        # extracted-part lookups, so each one was a full table scan.
        month_start = selected
        month_end = date(
            year + (month == 12), 1 if month == 12 else month + 1, 1
        ) - timedelta(days=1)

        from apps.maintenance.models import MaintenanceRecord
        from apps.workboard.selectors import visible_tasks_for_user

        allowed_types = allowed_calendar_types(self.request.user)
        events = {}
        if "permission" in allowed_types:
            # OPS-4: a permission spans a validity range, not a single day, so
            # an overlap test (not equality) selects it, and it is placed on
            # every day of the month it actually covers -- not just its
            # start. select_related -> prefetch_related: operators/aircraft
            # are now M2M, and select_related only ever worked on FK/O2O.
            for permission in FlightPermission.objects.filter(
                valid_from__lte=month_end, valid_until__gte=month_start, is_active=True
            ).prefetch_related("operators", "aircraft_fleet"):
                first_day = max(permission.valid_from, month_start)
                last_day = min(permission.valid_until, month_end)
                day = first_day
                while day <= last_day:
                    events.setdefault(day, []).append(("permission", permission))
                    day += timedelta(days=1)
        if "maintenance" in allowed_types:
            for record in MaintenanceRecord.objects.filter(
                scheduled_date__range=(month_start, month_end), is_active=True
            ).select_related("aircraft"):
                events.setdefault(record.scheduled_date, []).append(
                    ("maintenance", record)
                )
        if "task" in allowed_types:
            for task in (
                visible_tasks_for_user(self.request.user)
                .filter(due_date__range=(month_start, month_end))
                .select_related("board", "stage")
            ):
                events.setdefault(task.due_date, []).append(("task", task))

        previous = selected.replace(day=1)
        if month == 1:
            previous = previous.replace(year=year - 1, month=12)
        else:
            previous = previous.replace(month=month - 1)
        if month == 12:
            following = selected.replace(year=year + 1, month=1)
        else:
            following = selected.replace(month=month + 1)

        context.update(
            month_name=selected,
            month_days=calendar.Calendar(firstweekday=0).monthdayscalendar(year, month),
            events=events,
            month_value=selected.strftime("%Y-%m"),
            prev_month=previous.strftime("%Y-%m"),
            next_month=following.strftime("%Y-%m"),
            selected_calendar_types=self.request.GET.get("types", "all"),
            # R1.1: "all" used to be a literal list hardcoded in calendar.js
            # that drifted from the 9 real event types (it was missing the two
            # DGAC/JAC vigencia lanes) -- derive it from the same source of
            # truth CalendarAccessMixin already uses, so a new event type
            # can't silently go missing from "All events" again.
            calendar_all_types=",".join(
                event_type
                for event_type in CALENDAR_EVENT_PERMISSIONS
                if event_type in allowed_types
            ),
            selected_calendar_board=self.request.GET.get("board", ""),
            selected_calendar_cost_center=self.request.GET.get("cost_center", ""),
            selected_calendar_aircraft=self.request.GET.get("aircraft", ""),
            selected_calendar_operator=self.request.GET.get("operator", ""),
            # The filter dropdowns are a listing of the registry in their own
            # right, so each one needs the view permission of its model. Without
            # it they used to expose every cost center, registration and
            # operator to any authenticated user.
            calendar_cost_centers=self.filter_options(
                CostCenter, "registry.view_costcenter", "code"
            ),
            calendar_aircraft=self.filter_options(
                Aircraft, "registry.view_aircraft", "registration"
            ),
            calendar_operators=self.filter_options(
                Operator, "registry.view_operator", "full_name"
            ),
            current_language=getattr(self.request, "LANGUAGE_CODE", "es"),
            today=today,
            cal_year=year,
            cal_month=month,
        )
        return context


# ---------------------------------------------------------------------------
# R9.5: solicitudes de vuelo SIGO
# ---------------------------------------------------------------------------

# Los avisos del motor de secciones, redactados. El motor devuelve códigos a
# propósito (`apps.geo.sections`): la frase se traduce y vive acá, no allá.
SECTION_WARNINGS = {
    "no_circle": gettext_lazy(
        "No circle: this point has no circumference, so SIGO has nothing to draw."
    ),
    "no_center_point": gettext_lazy(
        "No centre point: this circle has no point of its own."
    ),
    "not_a_circle": gettext_lazy(
        "Not a circle: the polygon is not circular, and SIGO expects one."
    ),
    "duplicate_center": gettext_lazy(
        "Duplicate centre: another section has these same coordinates. "
        "Check the source table before filing."
    ),
}


class FlightRequestList(
    CsvExportMixin, SearchMixin, ModelViewPermissionRequiredMixin, ListView
):
    model = FlightRequest
    template_name = "operations/flight_request_list.html"
    htmx_template_name = "operations/_flight_request_rows.html"
    context_object_name = "objects"
    paginate_by = 25
    search_fields = ["title", "commune", "area_name"]

    def get_queryset(self):
        queryset = (
            super()
            .get_queryset()
            .select_related("cost_center", "amc", "flight_permission")
        )
        status = self.request.GET.get("status", "")
        if status in dict(FlightRequest.STATUS_CHOICES):
            queryset = queryset.filter(status=status)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            # Del `verbose_name_plural` del modelo, no de un literal propio:
            # "Flight requests" chocaría en mayúsculas con la entrada que ese
            # verbose_name ya puso en el catálogo.
            title=capfirst(FlightRequest._meta.verbose_name_plural),
            status_choices=FlightRequest.STATUS_CHOICES,
            current_status=self.request.GET.get("status", ""),
        )
        context["is_filtered"] = context["is_filtered"] or bool(
            self.request.GET.get("status")
        )
        return context


class FlightRequestDetail(
    TenantScopedQuerysetMixin, ModelViewPermissionRequiredMixin, DetailView
):
    model = FlightRequest
    template_name = "operations/flight_request_detail.html"
    context_object_name = "request_obj"

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("cost_center", "amc", "flight_permission", "source_plan")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        request_obj = self.object
        context["sheet"] = sigo_sheet(request_obj)
        context["note_form"] = FlightRequestNoteForm()
        context["work_item_form"] = FlightRequestWorkItemForm()
        context["notes"] = request_obj.change_notes.select_related("author")
        context["history"] = request_obj.history.select_related("changed_by_user")
        context["work_items"] = request_obj.work_items.select_related(
            "work_area", "objective"
        )
        # Sólo los permisos del mismo centro de costo y todavía abiertos: ofrecer
        # uno cerrado o de otra faena sería ofrecer un error.
        context["linkable_permissions"] = FlightPermission.objects.filter(
            cost_center=request_obj.cost_center, is_active=True
        ).exclude(status__in=FlightPermission.TERMINAL_STATUSES)
        return context


class FlightRequestUpdate(
    HtmxFormMixin, TenantScopedQuerysetMixin, ModelPermissionRequiredMixin, UpdateView
):
    model = FlightRequest
    form_class = FlightRequestForm
    template_name = "generic/form.html"
    permission_action = "change"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = _("Edit flight request")
        return context


class FlightRequestKmz(ModelViewPermissionRequiredMixin, View):
    """Descargar el KMZ de la sección: lo que se adjunta en SIGO."""

    model = FlightRequest

    def get(self, request, pk):
        obj = get_object_or_404(FlightRequest, pk=pk, is_active=True)
        if not obj.section_content:
            messages.error(request, _("This request has no geometry to export."))
            return redirect(obj)
        response = HttpResponse(
            section_kmz(obj), content_type="application/vnd.google-earth.kmz"
        )
        # `filename*` además del simple: el nombre lleva tildes ("Quebrada")
        # y sin la forma RFC 5987 algunos navegadores lo mutilan.
        name = slugify(obj.title) or "seccion"
        response["Content-Disposition"] = (
            f"attachment; filename=\"{name}.kmz\"; filename*=UTF-8''{quote(name)}.kmz"
        )
        return response


class FlightRequestAddNote(ModelPermissionRequiredMixin, View):
    model = FlightRequest
    permission_action = "change"

    def post(self, request, pk):
        obj = get_object_or_404(FlightRequest, pk=pk, is_active=True)
        form = FlightRequestNoteForm(request.POST)
        if form.is_valid():
            note = form.save(commit=False)
            note.request = obj
            note.author = request.user
            note.save()
            messages.success(request, _("Note added."))
        else:
            messages.error(request, _("Write the note before saving."))
        return redirect(obj)


class FlightRequestAddWorkItem(ModelPermissionRequiredMixin, View):
    """El botón "Agregar" del formulario de SIGO, de este lado."""

    model = FlightRequest
    permission_action = "change"

    def post(self, request, pk):
        obj = get_object_or_404(FlightRequest, pk=pk, is_active=True)
        form = FlightRequestWorkItemForm(request.POST)
        if form.is_valid():
            item = form.save(commit=False)
            item.request = obj
            # Consulta explícita y no `validate_unique()`: el formulario no
            # incluye `request` (lo pone la vista), así que la comprobación del
            # modelo no puede ver la tupla completa y el par repetido llegaba a
            # la base como un 500 contra la restricción. Repetirlo no es un
            # error del usuario, es un clic de más.
            if FlightRequestWorkItem.objects.filter(
                request=obj, work_area=item.work_area, objective=item.objective
            ).exists():
                messages.info(request, _("That pair is already on the list."))
                return redirect(obj)
            item.save()
            messages.success(request, _("Pair added."))
        else:
            messages.error(request, _("Choose a work area and an objective."))
        return redirect(obj)


class FlightRequestRemoveWorkItem(ModelPermissionRequiredMixin, View):
    model = FlightRequest
    permission_action = "change"

    def post(self, request, pk, item_pk):
        obj = get_object_or_404(FlightRequest, pk=pk, is_active=True)
        FlightRequestWorkItem.objects.filter(pk=item_pk, request=obj).delete()
        return redirect(obj)


class FlightRequestFile(StatusTransitionView):
    """Marcar la solicitud como presentada en SIGO."""

    model = FlightRequest
    target_status = FlightRequest.STATUS_FILED
    valid_from_statuses = [FlightRequest.STATUS_PREPARED]
    success_message = gettext_lazy("Recorded as filed in SIGO.")

    def post(self, request, pk):
        response = super().post(request, pk)
        # La fecha de presentación es lo que hace medible la espera
        # (`days_waiting`). Se pone acá y no en el formulario porque el acto de
        # presentar y la fecha en que ocurrió son el mismo hecho.
        obj = get_object_or_404(FlightRequest, pk=pk)
        if obj.status == FlightRequest.STATUS_FILED and not obj.filed_on:
            obj.filed_on = timezone.localdate()
            obj.save(update_fields=["filed_on", "updated_at"])
        return response


class FlightRequestClose(StatusTransitionView):
    model = FlightRequest
    target_status = FlightRequest.STATUS_CLOSED
    valid_from_statuses = [FlightRequest.STATUS_LINKED, FlightRequest.STATUS_FILED]
    success_message = gettext_lazy("Request closed.")


class FlightRequestLink(ModelPermissionRequiredMixin, View):
    """Vincular al permiso que la DGAC respondió."""

    model = FlightRequest
    permission_action = "change"

    def post(self, request, pk):
        obj = get_object_or_404(FlightRequest, pk=pk, is_active=True)
        permission = FlightPermission.objects.filter(
            pk=request.POST.get("permission"),
            cost_center=obj.cost_center,
            is_active=True,
        ).first()
        if permission is None:
            messages.error(request, _("Choose a permit from this cost center."))
            return redirect(obj)
        filled = link_to_permission(
            obj,
            permission,
            changed_by=request.user.get_username(),
            user=request.user,
        )
        set_audit_context(
            request,
            obj,
            action="flight_request_linked",
            metadata={"permission": permission.internal_folio, "filled": filled},
        )
        if filled:
            messages.success(
                request,
                _("Linked to %(folio)s; it filled in: %(fields)s.")
                % {"folio": permission.internal_folio, "fields": ", ".join(filled)},
            )
        else:
            # Decirlo importa: "no rellenó nada" no es un fallo, es que el
            # permiso ya traía todo -- y sin el mensaje parecería que no pasó.
            messages.success(
                request,
                _("Linked to %(folio)s. The permit already had its location.")
                % {"folio": permission.internal_folio},
            )
        return redirect(obj)


class GeoPlanSplitIntoRequests(ModelPermissionRequiredMixin, View):
    """Separar un plan multi-círculo en solicitudes, una por circunferencia.

    GET muestra la vista previa —cuántas secciones, con qué avisos— y POST las
    crea. La vista previa no es un adorno: el KMZ real trajo seis secciones con
    problema de dato, y crear cuarenta y siete filas sin haberlas mirado sería
    enterrar ese hallazgo.
    """

    model = FlightRequest
    permission_action = "add"

    def get(self, request, pk):
        plan = self._plan(pk)
        sections = split_sections(plan.current_version.content)
        return render(
            request,
            "operations/flight_request_split.html",
            {
                "plan": plan,
                "sections": [
                    {
                        "section": section,
                        "lat": format_dms(section.center[0], "lat"),
                        "lon": format_dms(section.center[1], "lon"),
                        "warnings": [
                            SECTION_WARNINGS.get(code, code)
                            for code in section.warnings
                        ],
                    }
                    for section in sections
                ],
                "existing": FlightRequest.objects.filter(
                    source_plan=plan, is_active=True
                ).count(),
            },
        )

    def post(self, request, pk):
        plan = self._plan(pk)
        requests, _sections = create_requests_from_plan(plan, created_by=request.user)
        set_audit_context(
            request,
            plan,
            action="geoplan_split_into_requests",
            metadata={"created": len(requests)},
        )
        messages.success(
            request,
            _("Created %(count)s flight requests from this plan.")
            % {"count": len(requests)},
        )
        return redirect("flight-request-list")

    @staticmethod
    def _plan(pk):
        plan = get_object_or_404(GeoPlan, pk=pk, is_active=True)
        if plan.current_version is None:
            raise Http404("The plan has no content to split.")
        return plan
