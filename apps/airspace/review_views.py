"""The review of a draft AIP snapshot, inside the administration (LV-361, phase 4).

* `ReviewList`      GET  /administracion/espacio-aereo/                       snapshots awaiting review
* `ReviewSnapshot`  GET  .../<snapshot>/                                       its zones, state and actions
* `ReviewZone`      GET/POST .../<snapshot>/zonas/<zone>/                      side by side; approve, reject, correct
* `ReviewBulk`      GET/POST .../<snapshot>/aprobar-limpias/                   approve the CLEAN zones, with confirmation
* `ReviewPublish`   GET/POST .../<snapshot>/publicar/                          publish when every zone is resolved

Everything needs `airspace.review_airspacesnapshot` (LV-268) and answers 403 without it. The rules
are in `aip_review`; these views only read the request, call it and write the audit entry
(`set_audit_context`), whose metadata carries zone codes, statuses and field NAMES: never the text of
the zone, which can hold what a person typed.

The PDF is not stored by the import and rendering a crop of its page would need a library the
project does not depend on (pdfplumber with pypdfium2), so the screen shows the cleaned extracted
text and the page number to open in the AIP.
"""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views import View
from django.views.generic import ListView

from apps.core.audit import add_audit_sibling, set_audit_context

from . import aip_review
from .models import (
    SOURCE_AIP_ENR51,
    AirspaceCrossCheck,
    AirspaceFeature,
    AirspaceSnapshot,
)
from .review_forms import CorrectionForm

FILTERS = ("all", "flagged", "clean", "pending", "decided")


class ReviewAccess(LoginRequiredMixin, PermissionRequiredMixin):
    permission_required = aip_review.REVIEW_PERMISSION
    raise_exception = True


def get_snapshot(pk):
    return get_object_or_404(AirspaceSnapshot, pk=pk, source_kind=SOURCE_AIP_ENR51)


def get_zone(snapshot, pk):
    return get_object_or_404(AirspaceFeature, pk=pk, snapshot=snapshot)


def _errors(request, error):
    for message in error.messages:
        messages.error(request, message)


def status_label(feature):
    return dict(AirspaceFeature._meta.get_field("review_status").choices)[
        feature.review_status
    ]


class ReviewList(ReviewAccess, ListView):
    template_name = "airspace/review_list.html"
    context_object_name = "snapshots"

    def get_queryset(self):
        return AirspaceSnapshot.objects.filter(
            source_kind=SOURCE_AIP_ENR51, status__in=aip_review.PENDING_STATUSES
        ).order_by("-fetched_at")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["rows"] = [
            {"snapshot": snapshot, "counts": aip_review.counts(snapshot)}
            for snapshot in context["snapshots"]
        ]
        context["current"] = AirspaceSnapshot.objects.filter(
            source_kind=SOURCE_AIP_ENR51, is_current=True
        ).first()
        return context


class ReviewSnapshot(ReviewAccess, View):
    def get(self, request, snapshot):
        snap = get_snapshot(snapshot)
        show = request.GET.get("show", "all")
        if show not in FILTERS:
            show = "all"
        checks = {
            c.aip_feature_id: c
            for c in AirspaceCrossCheck.objects.filter(
                snapshot=snap, aip_feature__isnull=False
            )
        }
        rows = []
        for feature in aip_review.zones_of(snap):
            flagged = aip_review.is_flagged(feature)
            keep = {
                "all": True,
                "flagged": flagged and not aip_review.is_resolved(feature),
                "clean": aip_review.is_bulk_candidate(feature),
                "pending": not aip_review.is_resolved(feature),
                "decided": aip_review.is_resolved(feature),
            }[show]
            if not keep:
                continue
            rows.append(
                {
                    "feature": feature,
                    "flagged": flagged,
                    "status": status_label(feature),
                    "warnings": len(feature.parse_warnings or []),
                    "check": checks.get(feature.pk),
                }
            )
        missing = AirspaceCrossCheck.objects.filter(
            snapshot=snap, aip_feature__isnull=True
        ).select_related("google_feature")
        context = {
            "snapshot": snap,
            "rows": rows,
            "show": show,
            "filters": FILTERS,
            "counts": aip_review.counts(snap),
            "blockers": aip_review.publish_blockers(snap),
            "open": snap.status in aip_review.PENDING_STATUSES,
            "google_missing": missing,
            "threshold": settings.AIRSPACE_CROSSCHECK_THRESHOLD_M,
        }
        return render(request, "airspace/review_snapshot.html", context)


class ReviewZone(ReviewAccess, View):
    def _context(self, snap, feature, form):
        check = (
            AirspaceCrossCheck.objects.filter(snapshot=snap, aip_feature=feature)
            .select_related("google_feature")
            .first()
        )
        google = check.google_feature if check else None
        zones = list(aip_review.zones_of(snap))
        unresolved = [z for z in zones if not aip_review.is_resolved(z)]
        following = next(
            (z for z in unresolved if (z.code, z.name) > (feature.code, feature.name)),
            None,
        ) or next((z for z in unresolved if z.pk != feature.pk), None)
        map_data = {
            "aip": feature.geometry if aip_review.has_geometry(feature) else None,
            "google": google.geometry if google else None,
            "labels": {"aip": _("AIP (proposed)"), "google": _("Google map")},
        }
        return {
            "snapshot": snap,
            "feature": feature,
            "form": form,
            "check": check,
            "google": google,
            "warnings": aip_review.warning_items(feature),
            "flagged": aip_review.is_flagged(feature),
            "status": status_label(feature),
            "open": snap.status in aip_review.PENDING_STATUSES,
            "crosses": aip_review.has_geometry(feature)
            and aip_review.crosses_itself(feature),
            "has_geometry": aip_review.has_geometry(feature),
            "vertices": [
                {"lat": f"{lat:.6f}", "lon": f"{lon:.6f}"}
                for lon, lat in aip_review.ring_of(feature)
            ],
            "page_label": feature.folder,
            "following": following,
            "map_data": map_data,
            "counts": aip_review.counts(snap),
        }

    def get(self, request, snapshot, zone):
        snap = get_snapshot(snapshot)
        feature = get_zone(snap, zone)
        form = CorrectionForm(feature=feature)
        return render(
            request, "airspace/review_zone.html", self._context(snap, feature, form)
        )

    def post(self, request, snapshot, zone):
        snap = get_snapshot(snapshot)
        feature = get_zone(snap, zone)
        action = request.POST.get("action")
        before = feature.review_status
        url = reverse("airspace-review-zone", args=[snap.pk, feature.pk])
        if action in ("approve", "reject"):
            try:
                if action == "approve":
                    aip_review.approve(feature, request.user)
                else:
                    aip_review.reject(feature, request.user)
            except ValidationError as error:
                _errors(request, error)
                return redirect(url)
            set_audit_context(
                request,
                feature,
                f"airspace_zone_{action}",
                {"code": feature.code, "from": before, "to": feature.review_status},
            )
            messages.success(
                request,
                _("%(code)s approved.") % {"code": feature.code or feature.name}
                if action == "approve"
                else _("%(code)s rejected.") % {"code": feature.code or feature.name},
            )
            return redirect(url)
        if action == "correct":
            form = CorrectionForm(request.POST, feature=feature)
            if form.is_valid():
                try:
                    _feature, changed = aip_review.correct(
                        feature,
                        request.user,
                        vertices=form.cleaned_data["vertices"],
                        texts=form.texts(),
                    )
                except ValidationError as error:
                    _errors(request, error)
                    return redirect(url)
                if not changed:
                    messages.info(request, _("Nothing was changed."))
                    return redirect(url)
                set_audit_context(
                    request,
                    feature,
                    "airspace_zone_correct",
                    {"code": feature.code, "fields": sorted(changed)},
                )
                messages.success(
                    request,
                    _("%(code)s corrected. It needs to be approved again.")
                    % {"code": feature.code or feature.name},
                )
                return redirect(url)
            return render(
                request,
                "airspace/review_zone.html",
                self._context(snap, feature, form),
                status=400,
            )
        raise Http404


class ReviewBulk(ReviewAccess, View):
    def get(self, request, snapshot):
        snap = get_snapshot(snapshot)
        return render(
            request,
            "airspace/review_bulk.html",
            {
                "snapshot": snap,
                "zones": aip_review.bulk_candidates(snap),
                "counts": aip_review.counts(snap),
                "open": snap.status in aip_review.PENDING_STATUSES,
            },
        )

    def post(self, request, snapshot):
        snap = get_snapshot(snapshot)
        back = reverse("airspace-review-snapshot", args=[snap.pk])
        if request.POST.get("confirm") != "yes":
            messages.error(request, _("Confirm the bulk approval to continue."))
            return redirect(reverse("airspace-review-bulk", args=[snap.pk]))
        try:
            approved = aip_review.approve_clean_in_bulk(snap, request.user)
        except ValidationError as error:
            _errors(request, error)
            return redirect(back)
        set_audit_context(
            request,
            snap,
            "airspace_bulk_approve",
            {"count": len(approved), "codes": [f.code for f in approved]},
        )
        for feature in approved:
            add_audit_sibling(request, feature, "airspace_zone_approve")
        messages.success(
            request,
            _(
                "%(n)s clean zone(s) approved. Zones with a warning still need your eyes one by one."
            )
            % {"n": len(approved)},
        )
        return redirect(back)


class ReviewPublish(ReviewAccess, View):
    def get(self, request, snapshot):
        snap = get_snapshot(snapshot)
        return render(
            request,
            "airspace/review_publish.html",
            {
                "snapshot": snap,
                "counts": aip_review.counts(snap),
                "blockers": aip_review.publish_blockers(snap),
                "current": AirspaceSnapshot.objects.filter(
                    source_kind=SOURCE_AIP_ENR51, is_current=True
                )
                .exclude(pk=snap.pk)
                .first(),
            },
        )

    def post(self, request, snapshot):
        snap = get_snapshot(snapshot)
        if request.POST.get("confirm") != "yes":
            messages.error(request, _("Confirm the publication to continue."))
            return redirect(reverse("airspace-review-publish", args=[snap.pk]))
        before = aip_review.counts(snap)
        try:
            published = aip_review.publish(snap, request.user)
        except ValidationError as error:
            _errors(request, error)
            return redirect(reverse("airspace-review-publish", args=[snap.pk]))
        set_audit_context(
            request,
            published,
            "airspace_publish",
            {
                "amdt": published.amdt_number,
                "zones": before["total"],
                "approved": before["approved"],
                "rejected": before["rejected"],
            },
        )
        messages.success(
            request,
            _(
                "Snapshot AMDT %(amdt)s published: %(n)s approved zone(s) are now the AIP copy."
            )
            % {"amdt": published.amdt_number or "?", "n": before["approved"]},
        )
        return redirect(reverse("airspace-review-list"))
