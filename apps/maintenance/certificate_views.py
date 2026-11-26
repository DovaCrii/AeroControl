"""LV-460: «Cargar certificado de mantención» — cerrar una mantención desde el PDF del taller.

Mismo patrón que el ingreso a taller (`intake_views.py`, LV-383) y la credencial del
operador: **proponer → confirmar**, y el servidor **vuelve a leer los archivos
guardados** en cada paso; nada de la lectura viaja por el cliente.

1. **Subir** (`MaintenanceCertificateUpload`): uno o dos PDF (el certificado y/o el
   informe técnico). Se validan, se guardan en la zona provisional (la misma que purga
   `apps.core.intake_pending`) y se entrega un token firmado con sus rutas y sha256.
2. **Vista previa**: `read_closure` lee cada archivo y `merge_closures` une lo leído
   (el certificado manda). La aeronave sale de la **coincidencia exacta** de la serie
   dentro de la empresa de la persona (ADR-0002); si no hay una sola, la elige ella, y
   si elige una cuya serie no es la del papel tiene que confirmarlo.
3. **Confirmar** (`MaintenanceCertificateConfirm`): `MaintenanceRecord.register_certificate`
   (donde vive la regla) cierra la mantención abierta o registra una nueva, y los PDF
   quedan como documentos de la **aeronave** (tipo `maintenance-certificate`).

⚠️ **Privacidad (repositorio público).** Los PDF traen contacto, teléfono, correo y RUT
del cliente y el nombre del técnico. Los lectores no los guardan, y a la auditoría y a
los logs sólo llegan el número del taller, el resultado y el nombre del lector.
"""

import hashlib
import logging
from contextlib import ExitStack, suppress
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from django.contrib import messages
from django.contrib.contenttypes.models import ContentType
from django.core import signing
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views import View

from apps.compliance.forms import upload_errors
from apps.compliance.models import Document, DocumentType
from apps.compliance.storage import DocumentStorageError, get_document_storage
from apps.core.audit import set_audit_context
from apps.core.views import ModelPermissionRequiredMixin
from apps.registry.models import Aircraft

from .forms import MaintenanceCertificateForm
from .intake_readers.closure import REPORT, merge_closures, read_closure
from .intake_readers.pdf import intake_text
from .intake_views import PENDING_PREFIX, _scoped_aircraft, aircraft_matches
from .models import MaintenanceProgram, MaintenanceRecord, add_months

logger = logging.getLogger(__name__)

# Sal propia: un token del ingreso a taller no sirve acá, ni éste allá.
CERTIFICATE_SALT = "maintenance.certificate.v1"
CERTIFICATE_MAX_AGE = 3600  # una hora
CERTIFICATE_TYPE_CODE = "maintenance-certificate"
MAX_FILES = 2


class CertificatePermissionMixin(ModelPermissionRequiredMixin):
    """Crea **o cierra** una mantención y guarda documentos: las tres cosas."""

    model = MaintenanceRecord
    permission_action = "add"

    def get_permission_required(self):
        return (
            "maintenance.add_maintenancerecord",
            "maintenance.change_maintenancerecord",
            "compliance.add_document",
        )


class CertificateTokenError(Exception):
    """El token no es válido (alterado, vencido, de otra persona) o un archivo cambió."""


@dataclass
class PendingFile:
    path: str
    sha: str
    data: bytes
    proposal: object  # ClosureProposal | None


def make_token(files, user):
    payload = {"f": [[path, sha] for path, sha in files], "u": str(user.pk)}
    return signing.dumps(payload, salt=CERTIFICATE_SALT, compress=False)


def read_token(token, user):
    """`[(ruta, sha256)]` de un token válido **de esta persona**; si no, el error."""
    try:
        payload = signing.loads(
            token, salt=CERTIFICATE_SALT, max_age=CERTIFICATE_MAX_AGE
        )
    except signing.BadSignature as exc:  # incluye SignatureExpired
        raise CertificateTokenError from exc
    if not isinstance(payload, dict) or payload.get("u") != str(user.pk):
        raise CertificateTokenError
    files = payload.get("f")
    if not isinstance(files, list) or not 1 <= len(files) <= MAX_FILES:
        raise CertificateTokenError
    result = []
    for item in files:
        if not isinstance(item, list) or len(item) != 2:
            raise CertificateTokenError
        path, sha = item
        if not isinstance(path, str) or not path.startswith(PENDING_PREFIX):
            raise CertificateTokenError
        if not isinstance(sha, str):
            raise CertificateTokenError
        result.append((path, sha))
    return result


def _stored_bytes(path):
    try:
        stream = get_document_storage().open(path)
    except (DocumentStorageError, OSError) as exc:
        raise CertificateTokenError from exc
    try:
        return stream.read()
    finally:
        with suppress(Exception):
            stream.close()


def load_pending(token, user):
    """Relee y lee cada archivo provisional: **nada** de esto viene del cliente."""
    pending = []
    for path, sha in read_token(token, user):
        data = _stored_bytes(path)
        if hashlib.sha256(data).hexdigest() != sha:
            raise CertificateTokenError
        text = intake_text(data)
        proposal = read_closure(text) if text else None
        if proposal is None:
            logger.info("certificate_unreadable")
        pending.append(PendingFile(path=path, sha=sha, data=data, proposal=proposal))
    return pending


def _proposal_notes(merged):
    """Lo que el papel dice y no tiene campo propio, como texto para las notas."""
    if merged is None:
        return ""
    lines = []
    if merged.verdict:
        lines.append(_("Workshop verdict: %(verdict)s") % {"verdict": merged.verdict})
    if merged.maintenance_kind:
        lines.append(
            _("Maintenance type on the document: %(kind)s")
            % {"kind": merged.maintenance_kind}
        )
    if merged.interval_hours or merged.interval_months:
        lines.append(
            _(
                "Interval certified by the workshop: %(hours)s flight hours or "
                "%(months)s months"
            )
            % {
                "hours": merged.interval_hours or "—",
                "months": merged.interval_months or "—",
            }
        )
    if merged.received_on:
        lines.append(
            _("Received at the workshop on %(date)s")
            % {"date": merged.received_on.strftime("%d-%m-%Y")}
        )
    return "\n".join(lines)


def _proposed_type(merged):
    """«Programada» cuando el papel habla de una mantención periódica; si no, «No programada»."""
    if merged is None:
        return "scheduled"
    kind = (merged.maintenance_kind or "").casefold()
    if "preventiv" in kind or merged.interval_months or merged.interval_hours:
        return "scheduled"
    return "unscheduled"


def _initial(merged, aircraft):
    """Los valores leídos como datos iniciales, y el nivel propuesto (o `None`)."""
    initial = {"maintenance_type": _proposed_type(merged)}
    level = None
    if merged is not None:
        values = {
            "completed_date": merged.issued_on,
            "certificate_number": merged.workshop_order,
            "hours_at": merged.hours,
            "performed_by": merged.workshop_name,
            "notes": _proposal_notes(merged),
        }
        initial.update({k: v for k, v in values.items() if v not in (None, "")})
        if aircraft is not None:
            level = MaintenanceProgram.level_for_interval(
                aircraft, merged.interval_months
            )
            if level:
                initial["level"] = level
    return initial, level


def _serial_state(merged, matches):
    if merged is None or not merged.serial_number:
        return "unread"
    if not matches:
        return "none"
    return "match" if len(matches) == 1 else "multiple"


def _render_upload(request, errors=(), aircraft=""):
    return render(
        request,
        "maintenance/certificate_upload.html",
        {
            "title": _("Upload maintenance certificate"),
            "errors": list(errors),
            "aircraft": aircraft,
            "cancel_url": reverse("maintenance-list"),
        },
    )


def _render_preview(request, pending, token, form, aircraft=None, proposed_level=None):
    merged = merge_closures(p.proposal for p in pending)
    serial = getattr(merged, "serial_number", "") or ""
    matches = aircraft_matches(request.user, serial)
    number = getattr(merged, "workshop_order", "") or ""
    existing = (
        MaintenanceRecord.find_certificate(aircraft, number)
        if aircraft is not None and number
        else None
    )
    context = {
        "title": _("Review the maintenance certificate"),
        "form": form,
        "token": token,
        "files": [
            {
                "kind": getattr(p.proposal, "document_kind", "") or "",
                "readable": p.proposal is not None,
            }
            for p in pending
        ],
        "readable": merged is not None,
        "merged": merged,
        "serial": serial,
        "serial_state": _serial_state(merged, matches),
        "serial_mismatch": form.serial_mismatch(aircraft),
        "proposed_level": proposed_level,
        "interval_months": getattr(merged, "interval_months", None),
        "existing": existing,
        "cancel_url": reverse("maintenance-list"),
    }
    return render(request, "maintenance/certificate_preview.html", context)


def _certificate_type():
    """El tipo de documento: lo crea la vista si el sembrado todavía no corrió."""
    from apps.compliance.management.commands.seed_document_types import (
        DOCUMENT_TYPE_GUIDE,
        DOCUMENT_TYPES,
        requires_issue_date,
    )

    (_code, name, requires_expiry, is_insurance, is_record, category) = next(
        row for row in DOCUMENT_TYPES if row[0] == CERTIFICATE_TYPE_CODE
    )
    description, reference_code, sort_order = DOCUMENT_TYPE_GUIDE[CERTIFICATE_TYPE_CODE]
    doc_type, _created = DocumentType.objects.get_or_create(
        code=CERTIFICATE_TYPE_CODE,
        defaults={
            "name": name,
            "requires_expiry": requires_expiry,
            "requires_issue_date": requires_issue_date(CERTIFICATE_TYPE_CODE),
            "is_insurance": is_insurance,
            "is_operational_record": is_record,
            "category": category,
            "description": description,
            "reference_code": reference_code,
            "sort_order": sort_order,
        },
    )
    return doc_type


class MaintenanceCertificateUpload(CertificatePermissionMixin, View):
    """Paso 1 y 2: guardar los PDF en la zona provisional y mostrar la vista previa."""

    def get(self, request):
        aircraft = _scoped_aircraft(request.user, request.GET.get("aircraft"))
        return _render_upload(request, aircraft=aircraft.pk if aircraft else "")

    def post(self, request):
        preselected = _scoped_aircraft(request.user, request.POST.get("aircraft"))
        aircraft_pk = preselected.pk if preselected else ""
        uploads = request.FILES.getlist("files")
        if not uploads:
            return _render_upload(
                request,
                [_("Choose the certificate and/or the technical report to upload.")],
                aircraft_pk,
            )
        if len(uploads) > MAX_FILES:
            return _render_upload(
                request,
                [_("Upload at most two documents: the certificate and the report.")],
                aircraft_pk,
            )
        problems = []
        for uploaded in uploads:
            if Path(uploaded.name).suffix.lower() != ".pdf":
                problems.append(_("Only PDF documents are accepted here."))
            else:
                problems += upload_errors(uploaded)
        if problems:
            return _render_upload(request, sorted(set(problems)), aircraft_pk)

        from apps.core import intake_pending

        intake_pending.purge_stale_pending_safely()
        stored = []
        try:
            for uploaded in uploads:
                uploaded.seek(0)
                sha = hashlib.sha256(uploaded.read()).hexdigest()
                uploaded.seek(0)
                path = f"{PENDING_PREFIX}{uuid4()}.pdf"
                get_document_storage().save(path, uploaded)
                stored.append((path, sha))
            token = make_token(stored, request.user)
            pending = load_pending(token, request.user)
        except Exception:
            for path, _sha in stored:
                with suppress(Exception):
                    get_document_storage().delete(path)
            raise

        merged = merge_closures(p.proposal for p in pending)
        matches = aircraft_matches(request.user, getattr(merged, "serial_number", ""))
        aircraft = matches[0] if len(matches) == 1 else preselected
        initial, level = _initial(merged, aircraft)
        form = MaintenanceCertificateForm(
            user=request.user,
            serial=getattr(merged, "serial_number", "") or "",
            initial_aircraft=aircraft,
            initial=initial,
        )
        set_audit_context(
            request,
            request.user,
            action="maintenance_certificate_uploaded"
            if merged is not None
            else "certificate_unreadable",
            metadata={"reader": getattr(merged, "reader", "") or ""},
        )
        return _render_preview(
            request, pending, token, form, aircraft=aircraft, proposed_level=level
        )


class MaintenanceCertificateCancel(CertificatePermissionMixin, View):
    """Cancelar: borra los PDF provisionales y vuelve a la lista.

    Un token inválido, vencido o de otra persona **no falla**: sólo no borra nada.
    """

    http_method_names = ["post", "options"]

    def post(self, request):
        with suppress(CertificateTokenError):
            for path, _sha in read_token(request.POST.get("token", ""), request.user):
                with suppress(DocumentStorageError, OSError):
                    get_document_storage().delete(path)
            set_audit_context(
                request,
                request.user,
                action="maintenance_certificate_cancelled",
                metadata={},
            )
        messages.info(request, _("Certificate upload cancelled; nothing was saved."))
        return redirect("maintenance-list")


class MaintenanceCertificateConfirm(CertificatePermissionMixin, View):
    """Paso 3: validar, cerrar o registrar la mantención y adjuntar los documentos."""

    http_method_names = ["post", "options"]

    def post(self, request):
        token = request.POST.get("token", "")
        try:
            pending = load_pending(token, request.user)
        except CertificateTokenError:
            messages.error(
                request,
                _(
                    "The upload expired or is no longer valid. Upload the document again."
                ),
            )
            return redirect("maintenance-certificate-new")

        merged = merge_closures(p.proposal for p in pending)
        form = MaintenanceCertificateForm(
            request.POST,
            user=request.user,
            serial=getattr(merged, "serial_number", "") or "",
        )
        if not form.is_valid():
            return _render_preview(
                request, pending, token, form, form.cleaned_data.get("aircraft")
            )

        aircraft = form.cleaned_data["aircraft"]
        data = form.certificate_data(getattr(merged, "workshop_name", "") or "")
        try:
            with ExitStack() as cleanups, transaction.atomic():
                record, outcome = MaintenanceRecord.register_certificate(
                    aircraft, data, user=request.user
                )
                attached = self._attach(cleanups, aircraft, pending, data, merged)
        except ValidationError as exc:
            for message in exc.messages:
                form.add_error(None, message)
            return _render_preview(request, pending, token, form, aircraft)

        for item in pending:
            with suppress(Exception):
                get_document_storage().delete(item.path)
        set_audit_context(
            request,
            record,
            action="maintenance_certificate_registered",
            metadata={
                "certificate_number": record.certificate_number,
                "outcome": outcome,
                "reader": getattr(merged, "reader", "") or "",
                "documents": attached,
            },
        )
        self._report(request, record, outcome, attached)
        return redirect(record)

    @staticmethod
    def _report(request, record, outcome, attached):
        number = {"number": record.certificate_number}
        if outcome == MaintenanceRecord.CERTIFICATE_ALREADY:
            messages.warning(
                request,
                _(
                    "Certificate %(number)s was already registered on this aircraft; "
                    "the maintenance was not changed."
                )
                % number,
            )
            if attached:
                messages.info(request, _("The missing documents were attached."))
            return
        if outcome == MaintenanceRecord.CERTIFICATE_CLOSED:
            messages.success(
                request,
                _(
                    "Certificate %(number)s registered: the open maintenance was completed."
                )
                % number,
            )
        else:
            messages.success(
                request,
                _("Certificate %(number)s registered as a completed maintenance.")
                % number,
            )

    @staticmethod
    def _attach(cleanups, aircraft, pending, data, merged):
        """Cuelga cada PDF de la aeronave, salvo el que ya está (mismo sha256)."""
        from apps.compliance.views import save_uploaded_file, uploaded_file_cleanup

        doc_type = _certificate_type()
        aircraft_type = ContentType.objects.get_for_model(Aircraft)
        on_file = set(
            Document.objects.filter(
                content_type=aircraft_type,
                object_id=aircraft.pk,
                is_active=True,
            ).values_list("content_sha256", flat=True)
        )
        issued = data["completed_date"]
        months = getattr(merged, "interval_months", None)
        expiry = (
            add_months(issued, months) if doc_type.requires_expiry and months else None
        )
        workshop = data.get("performed_by") or ""
        number = data["certificate_number"]
        attached = 0
        for item in pending:
            if item.sha in on_file:
                continue
            is_report = getattr(item.proposal, "document_kind", "") == REPORT
            head = _("Maintenance report") if is_report else doc_type.name
            stored = cleanups.enter_context(uploaded_file_cleanup())
            document = Document.objects.create(
                tenant_id=aircraft.tenant_id,
                content_type=aircraft_type,
                object_id=aircraft.pk,
                doc_type=doc_type,
                title=f"{head} · {workshop} {number}".strip()[:200],
                file_path="",
                issue_date=(
                    getattr(item.proposal, "issued_on", None) if is_report else None
                )
                or issued,
                expiry_date=expiry,
                content_sha256=item.sha,
            )
            stored["path"] = save_uploaded_file(
                document,
                SimpleUploadedFile(
                    "maintenance-certificate.pdf",
                    item.data,
                    content_type="application/pdf",
                ),
            )
            on_file.add(item.sha)
            attached += 1
        return attached
