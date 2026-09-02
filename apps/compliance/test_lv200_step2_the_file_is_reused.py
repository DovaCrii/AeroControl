"""LV-200 paso 2: la misma carta en varios permisos, un solo archivo.

Pedido del usuario, dicho dos veces: *"en ocasiones una carta puede estar ligada a
varios permisos; buscar una forma de optimizar y no subir/repetir el mismo archivo
muchas veces"*, y mirando el expediente: *"lo importante es ver para no repetir la
información, eso es la clave, ya que en permisos similares debo subir varias veces
la misma carta"*.

El paso 1 dejó la mitad: `content_sha256` se calcula al subir y el formulario deja
el documento idéntico en `duplicate_of`, pero eso sólo se avisaba. Ahora el
archivo **no se vuelve a escribir**: la fila nueva apunta al que ya existe.

**Se reutiliza el archivo y no se comparte la fila**, que es la decisión de fondo.
Un `Document` por permiso mantiene intacto lo que cuelga de esa relación: el
expediente, la atribución por faena (`LV-146`), el sujeto de cada documento
(`LV-186`) y los porcentajes del informe, donde un documento contado dos veces o
ninguna mueve una cifra que va a la DGAC. El pedido habla del archivo, y es el
archivo el que deja de repetirse.

⚠️ **La mitad de este archivo prueba la guarda de `cleanup_documents`**, y no es
celo de más: compartir `file_path` significa que archivar una fila podría borrar
el papel de otra, con diez años de retención de por medio y sin que nada avise.
"""

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.urls import reverse

from apps.compliance.models import Document, DocumentType
from apps.compliance.storage import get_document_storage
from apps.registry.models import Aircraft, CostCenter

CONTENT = b"%PDF-1.4\nla misma carta\n%%EOF\n"


@pytest.fixture
def scene(db, settings, tmp_path):
    settings.DOCUMENTS_ROOT = str(tmp_path)
    cost_center = CostCenter.objects.create(code="CC691", name="Uno")
    return {
        "cost_center": cost_center,
        "doc_type": DocumentType.objects.create(
            code="dgac-flight-permit",
            name="Carta del mandante (autorización para operar)",
            requires_expiry=False,
        ),
        "first": Aircraft.objects.create(
            registration="RPA-1",
            type="Multirotor",
            model="M3E",
            manufacturer="DJI",
            cost_center=cost_center,
        ),
        "second": Aircraft.objects.create(
            registration="RPA-2",
            type="Multirotor",
            model="M3E",
            manufacturer="DJI",
            cost_center=cost_center,
        ),
    }


def _upload(client, scene, record, name="carta.pdf", content=CONTENT):
    return client.post(
        reverse("document-create"),
        {
            "title": f"Carta de {record.registration}",
            "doc_type": scene["doc_type"].pk,
            "entity_type": ContentType.objects.get_for_model(Aircraft).pk,
            "object_id": str(record.pk),
            "issue_date": "2026-08-14",
            "file": SimpleUploadedFile(name, content, content_type="application/pdf"),
        },
    )


@pytest.fixture
def client_in(db):
    from apps.core.testing import login_as

    return login_as("add_document", "view_document")


class TestTheSameFileIsStoredOnce:
    @pytest.mark.django_db
    def test_two_records_share_one_stored_file(self, client_in, scene):
        """El caso del usuario: la misma carta para dos registros."""
        _upload(client_in, scene, scene["first"])
        _upload(client_in, scene, scene["second"])

        paths = set(Document.objects.values_list("file_path", flat=True))

        # Dos documentos, cada uno con su fila y su sujeto…
        assert Document.objects.count() == 2
        # …y un solo archivo.
        assert len(paths) == 1

    @pytest.mark.django_db
    def test_each_record_keeps_its_own_document_row(self, client_in, scene):
        """**Lo que la reutilización no puede romper.**

        El expediente, la atribución por faena y los porcentajes del informe se
        apoyan en que cada sujeto tenga su documento. Compartir la fila habría
        sido más "limpio" y habría movido cifras que van a la DGAC.
        """
        _upload(client_in, scene, scene["first"])
        _upload(client_in, scene, scene["second"])

        subjects = set(Document.objects.values_list("object_id", flat=True))

        assert subjects == {scene["first"].pk, scene["second"].pk}

    @pytest.mark.django_db
    def test_a_different_file_is_stored_apart(self, client_in, scene):
        """Sólo se reutiliza lo idéntico byte por byte."""
        _upload(client_in, scene, scene["first"])
        _upload(client_in, scene, scene["second"], content=b"%PDF-1.4\notra\n%%EOF\n")

        paths = set(Document.objects.values_list("file_path", flat=True))

        assert len(paths) == 2

    @pytest.mark.django_db
    def test_the_file_is_actually_readable_from_the_second_record(
        self, client_in, scene
    ):
        """Que apunte al mismo sitio no sirve si ese sitio no tiene el papel."""
        _upload(client_in, scene, scene["first"])
        _upload(client_in, scene, scene["second"])

        second = Document.objects.get(object_id=scene["second"].pk)
        assert get_document_storage().exists(second.file_path)


class TestCleanupDoesNotTakeTheSharedFile:
    @pytest.mark.django_db
    def test_archiving_one_does_not_delete_the_other_s_file(self, client_in, scene):
        """**La pérdida silenciosa que la guarda evita.**

        Sin ella: la fila viva conserva su `file_path`, el expediente sigue
        mostrando su renglón en verde, y el archivo ya no está. Se descubriría al
        intentar abrirlo, quizá en una auditoría.
        """
        _upload(client_in, scene, scene["first"])
        _upload(client_in, scene, scene["second"])
        archived = Document.objects.get(object_id=scene["first"].pk)
        alive = Document.objects.get(object_id=scene["second"].pk)
        archived.is_active = False
        archived.save(update_fields=["is_active", "updated_at"])

        call_command("cleanup_documents", "--older-than-days", "0", "--execute")

        alive.refresh_from_db()
        assert get_document_storage().exists(alive.file_path)

    @pytest.mark.django_db
    def test_it_says_why_it_kept_the_file(self, client_in, scene):
        """Un trabajo que decide no borrar tiene que decirlo, o parece que falló."""
        from io import StringIO

        _upload(client_in, scene, scene["first"])
        _upload(client_in, scene, scene["second"])
        archived = Document.objects.get(object_id=scene["first"].pk)
        archived.is_active = False
        archived.save(update_fields=["is_active", "updated_at"])
        out = StringIO()

        call_command(
            "cleanup_documents", "--older-than-days", "0", "--execute", stdout=out
        )

        assert "Kept (shared with 1 active document)" in out.getvalue()

    @pytest.mark.django_db
    def test_a_file_nobody_else_uses_is_still_removed(self, client_in, scene):
        """La guarda no puede convertirse en "no borrar nunca".

        `cleanup_documents` existe para que el almacenamiento no crezca con
        papeles de registros archivados hace una década.
        """
        _upload(client_in, scene, scene["first"])
        only = Document.objects.get(object_id=scene["first"].pk)
        path = only.file_path
        only.is_active = False
        only.save(update_fields=["is_active", "updated_at"])

        call_command("cleanup_documents", "--older-than-days", "0", "--execute")

        assert not get_document_storage().exists(path)


class TestTheUserIsStillToldAboutTheDuplicate:
    @pytest.mark.django_db
    def test_the_notice_from_step_one_survives(self, client_in, scene):
        """Reutilizar el archivo no calla el aviso.

        Que el sistema guarde una copia o reutilice la que tiene es una decisión
        de almacenamiento; que ese papel ya estuviera cargado en otro registro es
        información del trámite, y sigue diciéndose.
        """
        _upload(client_in, scene, scene["first"])

        response = _upload(client_in, scene, scene["second"])

        messages = [str(m) for m in response.wsgi_request._messages]
        assert any(
            "RPA-1" in message or "ya" in message.lower() for message in messages
        ), messages
