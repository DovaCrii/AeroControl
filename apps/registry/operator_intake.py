"""LV-405: dar de alta un operador **con** su credencial DGAC (PDF).

«Nuevo: operador» ofrece, arriba, cargar la credencial. El flujo reutiliza el lector
de `credential_reader` y el patrón del ingreso a servicio técnico
(`maintenance/intake_views.py`):

1. **Cargar** (`OperatorCredentialIntakeUpload`): valida el PDF, lo guarda en una ruta
   **provisional** y entrega un token firmado (`django.core.signing`, sal propia, una
   hora, atado a la persona, con ruta y sha256). El cliente nunca elige una ruta.
2. **Alta prellenada** (`OperatorCreate`): el servidor **vuelve a leer** el archivo
   provisional y propone nombre, RUT, número y vencimiento. Es una propuesta: la persona
   revisa y confirma con «Guardar». Si no se pudo leer, el formulario sirve igual a mano.
3. **Guardar**: en una sola transacción se crea el operador y el `Document` de
   credencial colgado de él (con la empresa del operador y el sha256); recién entonces
   se mueve el archivo a su ruta definitiva y se borra el provisional. Si el formulario
   trae errores, el token se conserva y no se pide el PDF otra vez.
4. **Descartar** (`OperatorCredentialIntakeCancel`): borra el provisional.

⚠️ **Privacidad (repositorio público y dato personal).** Lo leído (nombre, RUT) sólo
llega al formulario de la misma persona que subió el archivo: no va a la auditoría ni a
los logs (el log dice únicamente `credential_unreadable`).
"""

import hashlib
import logging
from contextlib import suppress
from dataclasses import dataclass
from uuid import uuid4

from django.contrib import messages
from django.contrib.contenttypes.models import ContentType
from django.core import signing
from django.core.files.uploadedfile import SimpleUploadedFile
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views import View

from apps.compliance.forms import upload_errors
from apps.compliance.models import Document, DocumentType
from apps.compliance.storage import DocumentStorageError, get_document_storage
from apps.core.audit import set_audit_context
from apps.core.views import ModelPermissionRequiredMixin

from . import credential_reader as reader
from .credential_views import CREDENTIAL_TYPE_CODE

logger = logging.getLogger(__name__)

# Sal propia: un token de otra parte del sistema no sirve acá, ni éste en otra.
INTAKE_SALT = "registry.operator-credential-intake.v1"
INTAKE_MAX_AGE = 3600  # una hora
# Bajo la carpeta provisional que `backup_documents` ya excluye (LV-401): una subida
# sin confirmar no es un documento del sistema.
PENDING_PREFIX = "workshop-intake-pending/operator-credential/"


class CredentialIntakePermissionMixin(ModelPermissionRequiredMixin):
    """Crea un operador **y** guarda un documento: las dos cosas, no una."""

    permission_action = "add"

    def get_permission_required(self):
        return ("registry.add_operator", "compliance.add_document")


class IntakeTokenError(Exception):
    """El token no es válido (alterado, vencido, de otra persona) o el archivo cambió."""


@dataclass
class PendingCredential:
    path: str
    sha: str
    data: bytes
    proposals: object  # {campo: Proposal} | None si no se pudo leer


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
    if ".." in path or not isinstance(sha, str):
        raise IntakeTokenError
    return path, sha


def load_pending(token, user):
    """Relee el archivo provisional y lo lee: **nada** de esto viene del cliente."""
    path, sha = read_token(token or "", user)
    try:
        stream = get_document_storage().open(path)
    except (DocumentStorageError, OSError) as exc:
        raise IntakeTokenError from exc
    try:
        data = stream.read()
    finally:
        with suppress(Exception):
            stream.close()
    if hashlib.sha256(data).hexdigest() != sha:
        raise IntakeTokenError
    proposals = reader.credential_from_bytes(data, "pdf")
    return PendingCredential(path=path, sha=sha, data=data, proposals=proposals)


def pending_or_none(token, user):
    """`PendingCredential` o `None`: un token malo nunca rompe la pantalla."""
    if not token:
        return None
    try:
        return load_pending(token, user)
    except IntakeTokenError:
        return None


def initial_from(proposals):
    """Valores iniciales del alta con lo leído. Es una propuesta, no un dato."""
    initial = {}
    for key, field in (
        (reader.HOLDER, "full_name"),
        (reader.RUT, "rut"),
        (reader.NUMBER, "dgac_credential"),
        (reader.EXPIRY_DATE, "credential_expiry"),
    ):
        proposal = (proposals or {}).get(key)
        if proposal is not None:
            initial[field] = proposal.value
    return initial


def read_summary(proposals):
    """Etiquetas de lo leído y de lo dudoso, **sin los valores**."""
    labels = (
        (reader.HOLDER, _("Full name")),
        (reader.RUT, _("RUT")),
        (reader.NUMBER, _("DGAC credential")),
        (reader.EXPIRY_DATE, _("DGAC credential expiry")),
    )
    read, doubtful = [], []
    for key, label in labels:
        proposal = (proposals or {}).get(key)
        if proposal is None:
            continue
        read.append(label)
        if proposal.confidence != reader.EXACT:
            doubtful.append(label)
    return read, doubtful


def delete_pending(path):
    with suppress(DocumentStorageError, OSError):
        get_document_storage().delete(path)


def attach_credential(operator, pending, user):
    """Crea el `Document` de credencial del operador recién creado y guarda el archivo.

    Se llama **dentro** de la transacción del alta (con `uploaded_file_cleanup`): si algo
    falla después, se deshace el operador y se borra el archivo ya movido.
    """
    from apps.compliance.views import save_uploaded_file

    doc_type = DocumentType.objects.filter(code=CREDENTIAL_TYPE_CODE).first()
    if doc_type is None:
        return None, None
    issue = (pending.proposals or {}).get(reader.ISSUE_DATE)
    issue_date = issue.value if issue is not None else None
    expiry = operator.credential_expiry
    if issue_date is None or (expiry is not None and issue_date >= expiry):
        issue_date = timezone.localdate()
    document = Document.objects.create(
        tenant_id=operator.tenant_id,
        content_type=ContentType.objects.get_for_model(type(operator)),
        object_id=operator.pk,
        doc_type=doc_type,
        title=f"{doc_type} · {operator.full_name}"[:200],
        file_path="",
        issue_date=issue_date,
        expiry_date=expiry,
        is_current_version=True,
        content_sha256=pending.sha,
    )
    stored = save_uploaded_file(
        document,
        SimpleUploadedFile(
            "credential.pdf", pending.data, content_type="application/pdf"
        ),
    )
    return document, stored


class OperatorCredentialIntakeUpload(CredentialIntakePermissionMixin, View):
    """Paso 1: guarda el PDF provisional y vuelve al alta, ya prellenada."""

    http_method_names = ["post", "options"]

    def post(self, request):
        from apps.compliance.views import uploaded_file_cleanup

        create_url = reverse("operator-create")
        uploaded = request.FILES.get("file")
        if uploaded is None:
            messages.error(request, _("Choose the credential file to upload."))
            return redirect(create_url)
        problems = upload_errors(uploaded)
        if not problems and not uploaded.name.lower().endswith(".pdf"):
            problems = [_("Only PDF documents are accepted here.")]
        if problems:
            for problem in problems:
                messages.error(request, problem)
            return redirect(create_url)
        if not DocumentType.objects.filter(code=CREDENTIAL_TYPE_CODE).exists():
            messages.error(
                request, _("The DGAC credential document type is not configured.")
            )
            return redirect(create_url)

        uploaded.seek(0)
        sha = hashlib.sha256(uploaded.read()).hexdigest()
        uploaded.seek(0)
        from apps.core import intake_pending

        intake_pending.purge_stale_pending_safely()
        with uploaded_file_cleanup() as stored:
            path = f"{PENDING_PREFIX}{uuid4()}.pdf"
            get_document_storage().save(path, uploaded)
            stored["path"] = path
            token = make_token(path, sha, request.user)
        set_audit_context(
            request,
            request.user,
            action="operator_credential_intake_uploaded",
            metadata={},
        )
        return redirect(f"{create_url}?credential={token}")


class OperatorCredentialIntakeCancel(CredentialIntakePermissionMixin, View):
    """Descartar: borra el PDF provisional y vuelve a la lista.

    Un token inválido, vencido o de otra persona **no falla**: sólo no borra nada.
    `read_token` exige `PENDING_PREFIX`, así que nunca alcanza archivos de fuera.
    """

    http_method_names = ["post", "options"]

    def post(self, request):
        with suppress(IntakeTokenError):
            path, _sha = read_token(request.POST.get("token", ""), request.user)
            delete_pending(path)
            set_audit_context(
                request,
                request.user,
                action="operator_credential_intake_cancelled",
                metadata={},
            )
        messages.info(request, _("Credential discarded; nothing was saved."))
        return redirect("operator-list")
