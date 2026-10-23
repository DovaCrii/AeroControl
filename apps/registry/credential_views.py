"""LV-368 fase 3: subir la credencial DGAC de un operador, leerla y confirmarla.

Flujo en dos pasos, a propósito:

1. **Subir** (`OperatorCredentialUpload`): valida y **guarda** el documento, sin tocar
   al `Operator`. Quedar guardado es independiente de que se pueda leer.
2. **Confirmar** (`OperatorCredentialConfirm`): el servidor **vuelve a leer el documento
   guardado** (nada de la lectura viaja por el cliente), muestra qué propone y la
   persona marca «Usar» campo por campo. Recién al guardar se llama a
   `Operator.apply_credential`, que es donde viven las reglas de negocio.

Misma disciplina que LV-231 (el folio del permiso): proponer, nunca escribir solo.

⚠️ **Privacidad (repositorio público y dato personal).** El RUT y el titular leídos se
usan solo para compararlos con la ficha: la pantalla dice «coincide / no coincide / no
se leyó» y no muestra el valor; la auditoría lleva nombres de campo, no valores; el log
dice únicamente `credential_unreadable`.
"""

import hashlib
import logging
from contextlib import suppress
from datetime import date

from django.contrib import messages
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
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

from . import credential_reader as reader
from .models import Operator

logger = logging.getLogger(__name__)

CREDENTIAL_TYPE_CODE = "dgac-credential"

# `Operator.rut` y `Operator.full_name` se comparan con lo leído; estos son los
# resultados posibles, sin el valor leído.
MATCH, MISMATCH, UNREAD, NOT_ON_FILE = "match", "mismatch", "unread", "not_on_file"


class CredentialPermissionMixin(ModelPermissionRequiredMixin):
    """Subir un documento **y** cambiar al operador: las dos cosas, no una."""

    model = Operator
    permission_action = "change"

    def get_permission_required(self):
        return ("registry.change_operator", "compliance.add_document")


def _operator_or_404(request, pk):
    return get_object_or_404(
        scope_queryset_to_tenant(Operator.objects.all(), request.user),
        pk=pk,
        is_active=True,
    )


def _document_or_404(request, operator, document_pk):
    return get_object_or_404(
        scope_queryset_to_tenant(Document.objects.all(), request.user),
        pk=document_pk,
        is_active=True,
        content_type=ContentType.objects.get_for_model(Operator),
        object_id=operator.pk,
        doc_type__code=CREDENTIAL_TYPE_CODE,
    )


def _detail_url(operator):
    return f"{reverse('operator-detail', args=[operator.pk])}#tab-documents"


def read_stored_credential(document):
    """`{campo: Proposal}` del documento **guardado**, o `None` si no se pudo leer.

    Se lee del almacenamiento y no de lo que mande el cliente: el POST de confirmar
    también pasa por aquí, así que un valor inventado en el formulario no puede
    hacerse pasar por «leído del PDF».
    """
    extension = document.file_path.rsplit(".", 1)[-1] if document.file_path else ""
    if extension.lower() != "pdf":
        logger.info("credential_unreadable")
        return None
    try:
        stream = get_document_storage().open(document.file_path)
    except (DocumentStorageError, OSError):
        logger.info("credential_unreadable")
        return None
    try:
        data = stream.read()
    finally:
        with suppress(Exception):
            stream.close()
    return reader.credential_from_bytes(data, extension)


class OperatorCredentialUpload(CredentialPermissionMixin, View):
    """Paso 1: guarda el archivo como documento del operador y pasa a confirmar."""

    http_method_names = ["post", "options"]

    def post(self, request, pk):
        from apps.compliance.views import save_uploaded_file, uploaded_file_cleanup

        operator = _operator_or_404(request, pk)
        uploaded = request.FILES.get("file")
        if uploaded is None:
            messages.error(request, _("Choose the credential file to upload."))
            return redirect(_detail_url(operator))
        problems = upload_errors(uploaded)
        if problems:
            for problem in problems:
                messages.error(request, problem)
            return redirect(_detail_url(operator))
        doc_type = DocumentType.objects.filter(code=CREDENTIAL_TYPE_CODE).first()
        if doc_type is None:
            messages.error(
                request, _("The DGAC credential document type is not configured.")
            )
            return redirect(_detail_url(operator))

        digest = hashlib.sha256()
        for chunk in uploaded.chunks():
            digest.update(chunk)
        uploaded.seek(0)
        sha = digest.hexdigest()
        # Acotado al tenant del operador: el aviso nombra el documento que ya tiene el
        # archivo, y no puede nombrar el de otra organización.
        duplicate = (
            Document.objects.filter(
                tenant_id=operator.tenant_id, content_sha256=sha, is_active=True
            )
            .order_by("created_at")
            .first()
        )

        with uploaded_file_cleanup() as stored:
            with transaction.atomic():
                document = Document.objects.create(
                    tenant_id=operator.tenant_id,
                    content_type=ContentType.objects.get_for_model(Operator),
                    object_id=operator.pk,
                    doc_type=doc_type,
                    title=f"{doc_type} · {operator.full_name}"[:200],
                    file_path="",
                    # Provisorias hasta confirmar; el modelo exige una fecha de
                    # emisión y todavía no hay una confirmada.
                    issue_date=timezone.localdate(),
                    expiry_date=None,
                    # No es la versión vigente hasta que alguien confirme: subir no
                    # cambia nada de lo que el resto del sistema da por cierto.
                    is_current_version=False,
                    content_sha256=sha,
                )
                stored["path"] = save_uploaded_file(
                    document, uploaded, reuse_of=duplicate
                )
        if duplicate is not None:
            messages.warning(
                request,
                _(
                    "This file is byte-for-byte the same as %(title)s, already on "
                    "file. It was uploaded anyway: if it is the same paper covering "
                    "both records, that is expected."
                )
                % {"title": duplicate.title},
            )
        set_audit_context(
            request,
            document,
            action="operator_credential_uploaded",
            metadata={"operator": str(operator.pk)},
        )
        return redirect(
            "operator-credential-confirm", pk=operator.pk, document_pk=document.pk
        )


def _read_value(proposals, field):
    """El valor leído de un campo de solo cotejo, o `None`. Nunca va a la pantalla."""
    proposal = (proposals or {}).get(field)
    return proposal.value if proposal is not None else None


def _holder_state(operator, proposals):
    proposal = proposals.get(reader.HOLDER) if proposals else None
    if proposal is None:
        return UNREAD
    return MATCH if operator.holder_matches(proposal.value) else MISMATCH


def _rut_state(operator, proposals):
    proposal = proposals.get(reader.RUT) if proposals else None
    if proposal is None:
        return UNREAD
    if not operator.rut:
        return NOT_ON_FILE
    return MATCH if operator.rut_matches(proposal.value) else MISMATCH


class OperatorCredentialConfirm(CredentialPermissionMixin, View):
    """Paso 2 y 3: mostrar lo leído del documento guardado y aplicar lo confirmado."""

    template_name = "registry/operator_credential_confirm.html"

    @staticmethod
    def field_labels():
        # Un literal por etiqueta: `_(variable)` no lo extrae `makemessages`.
        return {
            reader.NUMBER: _("DGAC credential"),
            reader.ISSUE_DATE: _("Issue date"),
            reader.EXPIRY_DATE: _("DGAC credential expiry"),
        }

    def get(self, request, pk, document_pk):
        operator = _operator_or_404(request, pk)
        document = _document_or_404(request, operator, document_pk)
        proposals = read_stored_credential(document)
        return self._render(request, operator, document, proposals)

    def post(self, request, pk, document_pk):
        operator = _operator_or_404(request, pk)
        document = _document_or_404(request, operator, document_pk)
        # Se vuelve a leer: ni la propuesta ni su confianza vienen del cliente.
        proposals = read_stored_credential(document)

        posted, errors = {}, {}
        for field in reader.WRITABLE_FIELDS:
            if not request.POST.get(f"use_{field}"):
                continue
            raw = (request.POST.get(f"value_{field}") or "").strip()
            if field == reader.NUMBER:
                value = " ".join(raw.split())
            else:
                try:
                    value = date.fromisoformat(raw) if raw else None
                except ValueError:
                    value = None
            if not value:
                errors[field] = _("This field is required.")
                continue
            posted[field] = value

        if not posted and not errors:
            errors["__all__"] = _('Tick "Use" on at least one field to save.')
        if not errors:
            try:
                warnings = operator.apply_credential(
                    document,
                    posted,
                    user=request.user,
                    holder=_read_value(proposals, reader.HOLDER),
                    read_rut=_read_value(proposals, reader.RUT),
                )
            except ValidationError as exc:
                errors.update(
                    {
                        key: " ".join(messages_)
                        for key, messages_ in exc.message_dict.items()
                    }
                )
            else:
                from_pdf, typed = [], []
                for field, value in posted.items():
                    proposal = (proposals or {}).get(field)
                    same = proposal is not None and (
                        proposal.value == value
                        if field != reader.NUMBER
                        else str(proposal.value).casefold() == str(value).casefold()
                    )
                    (from_pdf if same else typed).append(field)
                set_audit_context(
                    request,
                    operator,
                    action="operator_credential_confirmed",
                    metadata={
                        "document": str(document.pk),
                        "fields_from_pdf": sorted(from_pdf),
                        "fields_typed": sorted(typed),
                    },
                )
                messages.success(request, _("Credential details saved."))
                for warning in warnings:
                    messages.warning(request, warning)
                return redirect(_detail_url(operator))
        return self._render(
            request, operator, document, proposals, posted=request.POST, errors=errors
        )

    def _render(self, request, operator, document, proposals, posted=None, errors=None):
        readable = proposals is not None
        proposals = proposals or {}
        errors = errors or {}
        current = {
            reader.NUMBER: operator.dgac_credential,
            reader.ISSUE_DATE: None,
            reader.EXPIRY_DATE: operator.credential_expiry,
        }
        labels = self.field_labels()
        rows = []
        for field in reader.WRITABLE_FIELDS:
            proposal = proposals.get(field)
            if posted is not None:
                input_value = posted.get(f"value_{field}", "")
                checked = bool(posted.get(f"use_{field}"))
            else:
                # Ninguna propuesta viene aceptada: la casilla arranca vacía.
                seed = proposal.value if proposal else current[field]
                input_value = (
                    seed.isoformat() if isinstance(seed, date) else (seed or "")
                )
                checked = False
            rows.append(
                {
                    "field": field,
                    "label": labels[field],
                    "is_date": field != reader.NUMBER,
                    "current": current[field],
                    "proposal": proposal,
                    "input_value": input_value,
                    "checked": checked,
                    "error": errors.get(field),
                }
            )
        context = {
            "operator": operator,
            "object": operator,
            "document": document,
            "readable": readable,
            "rows": rows,
            "class_proposal": proposals.get(reader.CLASS_),
            "restrictions_proposal": proposals.get(reader.RESTRICTIONS),
            # Solo el resultado de la comparación: nunca el valor leído.
            "holder_state": _holder_state(operator, proposals),
            "rut_state": _rut_state(operator, proposals),
            "form_error": errors.get("__all__"),
            "cancel_url": _detail_url(operator),
            "title": _("Confirm credential details"),
        }
        return render(request, self.template_name, context)
