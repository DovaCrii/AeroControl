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

    title = forms.CharField(max_length=200, label=_("Title"))
    cost_center = forms.ModelChoiceField(
        queryset=CostCenter.objects.none(), label=_("Cost center")
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
        self.fields["flight_permission"].queryset = FlightPermission.objects.filter(
            is_active=True
        ).order_by("-valid_from")
        # Parsed canonical document, stashed by clean_file so the view does not
        # parse the upload a second time.
        self.canonical = None

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
