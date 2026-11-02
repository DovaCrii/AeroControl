"""LV-383 (PR 3 de 4): la pantalla «Registrar ingreso a servicio técnico».

Subir el PDF del taller (recepción o cotización), revisar lo que se leyó y confirmar.
Mismo patrón que la credencial del operador (`registry/credential_views.py`): el
servidor **vuelve a leer el archivo guardado** y nada de la lectura viaja por el
cliente.

1. **Subir** (`WorkshopIntakeUpload`): valida el archivo, lo guarda en una ruta
   **provisional** del almacenamiento y entrega un token firmado (`django.core.signing`,
   sal propia, vigencia de una hora) con la ruta, el sha256 y el usuario. El cliente
   no elige ninguna ruta: sólo devuelve el token.
2. **Vista previa**: el servidor relee el archivo con `intake_text` y `read_intake` y
   pre-llena `WorkshopIntakeForm`. La aeronave sale de la **coincidencia exacta** de la
   serie (`normalize_serial`, ADR-0002: nunca difusa, nunca O/0) dentro de las
   aeronaves de la empresa de la persona; sin coincidencia, la elige ella.
3. **Confirmar** (`WorkshopIntakeConfirm`): relee, valida, llama a
   `MaintenanceRecord.register_workshop_intake` (donde vive la regla) y cuelga el
   documento de la mantención.

⚠️ **Privacidad (repositorio público).** `delivered_by` es un dato personal: no va a la
auditoría ni a los logs. El log dice únicamente `intake_unreadable`.
"""

import hashlib
import logging
from contextlib import suppress
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
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views import View

from apps.compliance.forms import upload_errors
from apps.compliance.models import Document, DocumentType
from apps.compliance.storage import DocumentStorageError, get_document_storage
from apps.core.audit import set_audit_context
from apps.core.tenancy import scope_queryset_to_tenant
from apps.core.views import ModelPermissionRequiredMixin
from apps.registry.models import Aircraft, normalize_serial

from .forms import WorkshopIntakeForm
from .intake_readers import read_intake
from .intake_readers.pdf import intake_text
from .models import MaintenanceRecord

logger = logging.getLogger(__name__)

# Sal propia: un token de otra parte del sistema no sirve acá, ni éste en otra.
INTAKE_SALT = "maintenance.workshop-intake.v1"
INTAKE_MAX_AGE = 3600  # una hora
PENDING_PREFIX = "workshop-intake-pending/"
RECEIPT_TYPE_CODE = "workshop-intake-receipt"
QUOTE_READER = "geocom_quote"


class IntakePermissionMixin(ModelPermissionRequiredMixin):
    """Crea una mantención **y** guarda un documento: las dos cosas, no una."""

    model = MaintenanceRecord
    permission_action = "add"

    def get_permission_required(self):
        return ("maintenance.add_maintenancerecord", "compliance.add_document")


class IntakeTokenError(Exception):
    """El token no es válido (alterado, vencido, de otra persona) o el archivo cambió."""


@dataclass
class PendingIntake:
    path: str
    sha: str
    data: bytes
    proposal: object  # IntakeProposal | None


def make_token(path, sha, user):
    payload = {"p": path, "h": sha, "u": str(user.pk)}
    return signing.dumps(payload, salt=INTAKE_SALT, compress=False)


def read_token(token, user):
    """`(ruta, sha256)` de un token válido **de esta persona**; si no, `IntakeTokenError`."""
    try:
        payload = signing.loads(token, salt=INTAKE_SALT, max_age=INTAKE_MAX_AGE)
    except signing.BadSignature as exc:  # incluye SignatureExpired
        raise IntakeTokenError from exc
    if not isinstance(payload, dict) or payload.get("u") != str(user.pk):
        raise IntakeTokenError
    path, sha = payload.get("p"), payload.get("h")
    if not isinstance(path, str) or not path.startswith(PENDING_PREFIX):
        raise IntakeTokenError
    if not isinstance(sha, str):
        raise IntakeTokenError
    return path, sha


def _stored_bytes(path):
    try:
        stream = get_document_storage().open(path)
    except (DocumentStorageError, OSError) as exc:
        raise IntakeTokenError from exc
    try:
        return stream.read()
    finally:
        with suppress(Exception):
            stream.close()


def load_pending(token, user):
    """Relee el archivo provisional y lo lee: **nada** de esto viene del cliente."""
    path, sha = read_token(token, user)
    data = _stored_bytes(path)
    if hashlib.sha256(data).hexdigest() != sha:
        raise IntakeTokenError
    text = intake_text(data)
    proposal = read_intake(text) if text else None
    if proposal is None:
        logger.info("intake_unreadable")
    return PendingIntake(path=path, sha=sha, data=data, proposal=proposal)


def aircraft_matches(user, serial):
    """Aeronaves de la empresa cuya serie es **exactamente** la leída (ADR-0002)."""
    wanted = normalize_serial(serial)
    if not wanted:
        return []
    queryset = Aircraft.objects.filter(is_active=True, serial_number=wanted)
    return list(scope_queryset_to_tenant(queryset, user))


def _scoped_aircraft(user, raw):
    """La aeronave `raw` (pk) si es de la empresa de la persona; si no, `None`."""
    if not raw:
        return None
    try:
        return (
            scope_queryset_to_tenant(Aircraft.objects.filter(is_active=True), user)
            .filter(pk=raw)
            .first()
        )
    except (ValueError, ValidationError):
        return None


def _receipt_type():
    """El tipo del documento: lo crea la vista si el sembrado todavía no corrió."""
    from apps.compliance.management.commands.seed_document_types import (
        DOCUMENT_TYPE_GUIDE,
        DOCUMENT_TYPES,
    )

    (_code, name, requires_expiry, is_insurance, is_record, category) = next(
        row for row in DOCUMENT_TYPES if row[0] == RECEIPT_TYPE_CODE
    )
    description, reference_code, sort_order = DOCUMENT_TYPE_GUIDE[RECEIPT_TYPE_CODE]
    doc_type, _created = DocumentType.objects.get_or_create(
        code=RECEIPT_TYPE_CODE,
        defaults={
            "name": name,
            "requires_expiry": requires_expiry,
            "is_insurance": is_insurance,
            "is_operational_record": is_record,
            "category": category,
            "description": description,
            "reference_code": reference_code,
            "sort_order": sort_order,
        },
    )
    return doc_type


def _serial_state(proposal, matches):
    if proposal is None or not proposal.serial_number:
        return "unread"
    if not matches:
        return "none"
    return "match" if len(matches) == 1 else "multiple"


def _render_preview(request, pending, token, form):
    proposal = pending.proposal
    state = _serial_state(
        proposal, aircraft_matches(request.user, getattr(proposal, "serial_number", ""))
    )
    existing = form.existing
    context = {
        "title": _("Review the workshop intake"),
        "form": form,
        "token": token,
        "readable": proposal is not None,
        "serial": getattr(proposal, "serial_number", "") or "",
        "serial_state": state,
        "existing": existing,
        "existing_url": existing.record.get_absolute_url() if existing else "",
        "is_quote": getattr(proposal, "reader", "") == QUOTE_READER,
        "cancel_url": reverse("maintenance-list"),
    }
    return render(request, "maintenance/intake_preview.html", context)


def _render_upload(request, errors=(), aircraft=""):
    return render(
        request,
        "maintenance/intake_upload.html",
        {
            "title": _("Register workshop intake"),
            "errors": list(errors),
            "aircraft": aircraft,
            "cancel_url": reverse("maintenance-list"),
        },
    )


class WorkshopIntakeUpload(IntakePermissionMixin, View):
    """Paso 1 y 2: guardar el PDF en una ruta provisional y mostrar la vista previa."""

    def get(self, request):
        aircraft = _scoped_aircraft(request.user, request.GET.get("aircraft"))
        return _render_upload(request, aircraft=aircraft.pk if aircraft else "")

    def post(self, request):
        from apps.compliance.views import uploaded_file_cleanup

        preselected = _scoped_aircraft(request.user, request.POST.get("aircraft"))
        aircraft_pk = preselected.pk if preselected else ""
        uploaded = request.FILES.get("file")
        if uploaded is None:
            return _render_upload(
                request,
                [_("Choose the workshop document to upload.")],
                aircraft_pk,
            )
        if Path(uploaded.name).suffix.lower() != ".pdf":
            return _render_upload(
                request, [_("Only PDF documents are accepted here.")], aircraft_pk
            )
        problems = upload_errors(uploaded)
        if problems:
            return _render_upload(request, problems, aircraft_pk)

        uploaded.seek(0)
        sha = hashlib.sha256(uploaded.read()).hexdigest()
        with uploaded_file_cleanup() as stored:
            path = f"{PENDING_PREFIX}{uuid4()}.pdf"
            get_document_storage().save(path, uploaded)
            stored["path"] = path
            token = make_token(path, sha, request.user)
            pending = load_pending(token, request.user)
            proposal = pending.proposal
            matches = aircraft_matches(
                request.user, getattr(proposal, "serial_number", "")
            )
            form = WorkshopIntakeForm(
                user=request.user,
                proposal=proposal,
                aircraft_matches=matches,
                preselected=preselected,
            )
            if proposal is None:
                set_audit_context(
                    request,
                    request.user,
                    action="intake_unreadable",
                    metadata={"reader": ""},
                )
            else:
                set_audit_context(
                    request,
                    request.user,
                    action="workshop_intake_uploaded",
                    metadata={"reader": proposal.reader or ""},
                )
            return _render_preview(request, pending, token, form)


class WorkshopIntakeCancel(IntakePermissionMixin, View):
    """Cancelar el ingreso: borra el PDF provisional y vuelve a la lista.

    Un token inválido, vencido o de otra persona **no falla**: sólo no borra nada.
    `read_token` ya exige `PENDING_PREFIX`, así que el token nunca alcanza archivos
    fuera de la zona provisional.
    """

    http_method_names = ["post", "options"]

    def post(self, request):
        token = request.POST.get("token", "")
        with suppress(IntakeTokenError):
            path, _sha = read_token(token, request.user)
            with suppress(DocumentStorageError, OSError):
                get_document_storage().delete(path)
            # Sin datos personales: ni la ruta, ni el taller, ni quien entrega.
            set_audit_context(
                request,
                request.user,
                action="workshop_intake_cancelled",
                metadata={},
            )
        messages.info(request, _("Intake cancelled; nothing was saved."))
        return redirect("maintenance-list")


class WorkshopIntakeConfirm(IntakePermissionMixin, View):
    """Paso 3: validar, registrar el ingreso y colgar el documento de la mantención."""

    http_method_names = ["post", "options"]

    def post(self, request):
        from apps.compliance.views import save_uploaded_file, uploaded_file_cleanup

        token = request.POST.get("token", "")
        try:
            pending = load_pending(token, request.user)
        except IntakeTokenError:
            messages.error(
                request,
                _(
                    "The upload expired or is no longer valid. Upload the document again."
                ),
            )
            return redirect("maintenance-intake-new")

        proposal = pending.proposal
        matches = aircraft_matches(request.user, getattr(proposal, "serial_number", ""))
        form = WorkshopIntakeForm(
            request.POST,
            user=request.user,
            proposal=proposal,
            aircraft_matches=matches,
        )
        if not form.is_valid():
            return _render_preview(request, pending, token, form)

        aircraft = form.cleaned_data["aircraft"]
        data = form.register_data()
        data["reader"] = getattr(proposal, "reader", "") or ""
        is_quote = data["reader"] == QUOTE_READER

        try:
            with uploaded_file_cleanup() as stored, transaction.atomic():
                intake = MaintenanceRecord.register_workshop_intake(
                    aircraft, data, user=request.user
                )
                doc_type = _receipt_type()
                document = Document.objects.create(
                    tenant_id=aircraft.tenant_id,
                    # LV-388: el documento es del equipo (la aeronave), no de
                    # una mantención; la mantención lo apunta con
                    # `source_document`/`quote_document`.
                    content_type=ContentType.objects.get_for_model(Aircraft),
                    object_id=aircraft.pk,
                    doc_type=doc_type,
                    title=self._title(doc_type, intake, is_quote),
                    file_path="",
                    issue_date=self._issue_date(intake, is_quote),
                    expiry_date=None,
                    content_sha256=pending.sha,
                )
                stored["path"] = save_uploaded_file(
                    document,
                    SimpleUploadedFile(
                        "workshop-document.pdf",
                        pending.data,
                        content_type="application/pdf",
                    ),
                )
                field = "quote_document" if is_quote else "source_document"
                if getattr(intake, f"{field}_id") is None:
                    setattr(intake, field, document)
                    intake.save(update_fields=[field, "updated_at"])
        except ValidationError as exc:
            for message in exc.messages:
                form.add_error(None, message)
            return _render_preview(request, pending, token, form)

        with suppress(Exception):
            get_document_storage().delete(pending.path)
        set_audit_context(
            request,
            intake.record,
            action="workshop_intake_registered",
            metadata={
                "order": intake.workshop_order,
                "reader": data["reader"],
                "sent_by": intake.sent_by,
            },
        )
        messages.success(request, _("Workshop intake saved."))
        return redirect(intake.record)

    @staticmethod
    def _title(doc_type, intake, is_quote):
        head = _("Workshop quote") if is_quote else doc_type.name
        suffix = f" · {intake.workshop_order}" if intake.workshop_order else ""
        return f"{head}{suffix}"[:200]

    @staticmethod
    def _issue_date(intake, is_quote):
        if is_quote and intake.quote_date:
            return intake.quote_date
        if intake.received_at:
            return timezone.localtime(intake.received_at).date()
        return timezone.localdate()
