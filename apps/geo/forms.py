from pathlib import Path

from django import forms
from django.utils.translation import gettext_lazy as _

from apps.compliance.forms import ALLOWED_UPLOAD_SIGNATURES
from apps.compliance.security import scan_uploaded_file
from apps.operations.models import FlightPermission
from apps.registry.models import CostCenter

from .kml import parse_upload
from .kml.errors import KmlImportError

MAX_UPLOAD_BYTES = 20 * 1024 * 1024


class GeoPlanImportForm(forms.Form):
    """Import a KMZ/KML into a new plan.

    Reuses the compliance upload guards (extension whitelist, magic-byte
    signature, antivirus hook) and then parses the file so a malformed or
    unsafe KML is rejected here, before any row is written.
    """

    # LV-60: a plan imported against a permission is not a separate record that
    # happens to reference it -- it is that permission's flight area. Asking for
    # a fresh title and re-picking the cost center made two halves of one
    # request look like unrelated things. Both are derived from the permission
    # when there is one (same "leave it blank and we build it" shape as LV-2's
    # document titles), and the cost center is *checked* against it rather than
    # trusted, because a plan filed under a different contract than its own
    # permission is incoherent data nothing was rejecting before.
    title = forms.CharField(
        max_length=200,
        required=False,
        label=_("Title"),
        help_text=_(
            "Leave blank to generate it from the flight permission (or the "
            "cost center) and the file name."
        ),
    )
    cost_center = forms.ModelChoiceField(
        queryset=CostCenter.objects.none(),
        required=False,
        label=_("Cost center"),
        help_text=_("Taken from the flight permission when one is selected."),
    )
    flight_permission = forms.ModelChoiceField(
        queryset=FlightPermission.objects.none(),
        required=False,
        label=_("Flight permission"),
    )
    file = forms.FileField(label=_("KMZ/KML file"))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["cost_center"].queryset = CostCenter.objects.filter(
            is_active=True
        ).order_by("code")
        self.fields["flight_permission"].queryset = (
            FlightPermission.objects.filter(is_active=True)
            .select_related("cost_center")
            .order_by("-valid_from")
        )
        # Parsed canonical document, stashed by clean_file so the view does not
        # parse the upload a second time.
        self.canonical = None

    def clean(self):
        cleaned = super().clean()
        permission = cleaned.get("flight_permission")
        cost_center = cleaned.get("cost_center")

        if permission:
            if cost_center is None:
                cleaned["cost_center"] = cost_center = permission.cost_center
            elif cost_center != permission.cost_center:
                self.add_error(
                    "cost_center",
                    _(
                        "This cost center is not the one on the selected flight "
                        "permission (%(expected)s)."
                    )
                    % {"expected": permission.cost_center},
                )
        elif cost_center is None:
            # Without a permission to inherit from there is nothing to derive
            # it from, and GeoPlan.cost_center is not nullable.
            self.add_error("cost_center", _("Select a cost center."))

        if not cleaned.get("title"):
            uploaded = cleaned.get("file")
            anchor = permission or cost_center
            if anchor and uploaded:
                cleaned["title"] = self._autogenerate_title(anchor, uploaded.name)
        return cleaned

    @staticmethod
    def _autogenerate_title(anchor, file_name):
        """`<permission or cost center> · <file name>`.

        The anchor carries the identity the user already chose; the file name
        keeps two plans of the same permission apart (the link is 1:N).
        """
        return f"{anchor} · {Path(file_name).stem}"[:200]

    def clean_file(self):
        uploaded = self.cleaned_data["file"]
        extension = Path(uploaded.name).suffix.lower().lstrip(".")
        if extension not in {"kml", "kmz"}:
            raise forms.ValidationError(_("Only .kml and .kmz files can be imported."))
        if uploaded.size > MAX_UPLOAD_BYTES:
            raise forms.ValidationError(_("The maximum file size is 20 MB."))

        position = uploaded.tell()
        uploaded.seek(0)
        header = uploaded.read(16)
        uploaded.seek(position)
        signatures = ALLOWED_UPLOAD_SIGNATURES[extension]
        if not any(header.startswith(signature) for signature in signatures):
            raise forms.ValidationError(
                _("The uploaded file content does not match its extension.")
            )

        try:
            scan_uploaded_file(uploaded)
        except RuntimeError as exc:
            raise forms.ValidationError(str(exc))

        uploaded.seek(0)
        data = uploaded.read()
        uploaded.seek(0)
        try:
            self.canonical = parse_upload(data, uploaded.name)
        except KmlImportError as exc:
            # The message is safe to show: it never echoes file contents.
            raise forms.ValidationError(str(exc))
        return uploaded
