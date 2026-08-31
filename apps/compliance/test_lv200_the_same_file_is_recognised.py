"""LV-200 (paso 1): el mismo archivo se reconoce al subirlo otra vez.

Pedido del usuario: *"en ocasiones una carta puede estar ligada a varios permisos;
buscar una forma de optimizar y no subir/repetir el mismo archivo muchas veces"*.

**`content_sha256` ya existía y estaba a medias**: lo escribía únicamente el
importador del repositorio `Z:` (`R4.2`), así que todo lo subido desde la app lo
tenía vacío — el campo servía para detectar una reimportación y para nada más.
Llenarlo al subir es lo que vuelve posible cualquier cosa que quiera reconocer un
archivo repetido, y por eso es el paso 1: sin la huella, "no repetir el archivo"
no tiene con qué compararse.

**Avisa y no bloquea**, decisión tomada acá: un archivo idéntico ya cargado es
casi siempre lo que el usuario describe —la misma carta cubriendo varios
permisos— y no un error. El aviso nombra el documento que ya lo tiene, porque
"ya existe" sin el nombre manda a buscarlo a mano por toda la app.

**Lo que este paso NO hace, y por qué se separó**: que un documento cuelgue de
varios sujetos, o que dos registros compartan un archivo en el almacenamiento. Lo
primero es una migración que toca `document_subjects` (`LV-186`),
`cost_centers_for_refs` (`LV-204`), el expediente y el informe de cumplimiento —
donde un documento contado dos veces o ninguna mueve porcentajes. Lo segundo pone
dos filas apuntando al mismo blob, con lo que eso implica el día que una se borre.
Ninguna de las dos se decide de paso.
"""

import hashlib

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.compliance.forms import DocumentForm
from apps.compliance.models import Document, DocumentType
from apps.registry.models import Aircraft

TODAY = timezone.localdate()
CONTENT = b"%PDF-1.4 la misma carta de permiso, byte por byte"


@pytest.fixture
def doc_type(db):
    return DocumentType.objects.create(code="permit-letter", name="Carta Permiso")


@pytest.fixture
def aircraft(db):
    return Aircraft.objects.create(registration="RPA-4401", serial_number="SN-1")


def _upload(content=CONTENT, name="carta.pdf"):
    return SimpleUploadedFile(name, content, content_type="application/pdf")


def _form(doc_type, aircraft, upload):
    return DocumentForm(
        data={
            "entity_type": ContentType.objects.get_for_model(Aircraft).pk,
            "object_id": str(aircraft.pk),
            "doc_type": str(doc_type.pk),
            "title": "Carta Permiso",
            "issue_date": TODAY.isoformat(),
            # `DocumentType.requires_expiry` es `True` por defecto, y una carta de
            # permiso vence de verdad: se manda la fecha en vez de aflojar el tipo.
            "expiry_date": (TODAY + timezone.timedelta(days=90)).isoformat(),
        },
        files={"file": upload},
    )


@pytest.mark.django_db
class TestTheFingerprint:
    def test_it_is_computed_on_upload(self, doc_type, aircraft):
        """Antes de esta fila, todo lo subido por la app llegaba sin huella."""
        form = _form(doc_type, aircraft, _upload())

        assert form.is_valid(), form.errors
        assert form.content_sha256 == hashlib.sha256(CONTENT).hexdigest()

    def test_it_reaches_the_saved_record(self, doc_type, aircraft):
        """Si el cálculo no viajara al registro, el campo seguiría vacío y la
        comparación de la próxima subida no tendría contra qué mirar."""
        form = _form(doc_type, aircraft, _upload())
        assert form.is_valid(), form.errors

        document = form.save()

        assert document.content_sha256 == hashlib.sha256(CONTENT).hexdigest()

    def test_the_file_is_still_readable_afterwards(self, doc_type, aircraft):
        """Se hashea por trozos y **se rebobina**: quien guarda el archivo lee el
        mismo objeto, y dejarlo consumido habría escrito cero bytes en disco — un
        defecto que no se ve hasta que alguien abre el PDF."""
        upload = _upload()
        form = _form(doc_type, aircraft, upload)
        assert form.is_valid(), form.errors

        assert upload.read() == CONTENT


@pytest.mark.django_db
class TestRecognisingTheSameFile:
    def test_it_names_the_document_that_already_has_it(self, doc_type, aircraft):
        first = Document.objects.create(
            title="Carta Permiso · JEJ-2026-001",
            doc_type=doc_type,
            content_type=ContentType.objects.get_for_model(Aircraft),
            object_id=aircraft.pk,
            issue_date=TODAY,
            content_sha256=hashlib.sha256(CONTENT).hexdigest(),
        )

        form = _form(doc_type, aircraft, _upload())
        assert form.is_valid(), form.errors

        assert form.duplicate_of == first

    def test_a_different_file_is_not_a_duplicate(self, doc_type, aircraft):
        Document.objects.create(
            title="Otra carta",
            doc_type=doc_type,
            content_type=ContentType.objects.get_for_model(Aircraft),
            object_id=aircraft.pk,
            issue_date=TODAY,
            content_sha256=hashlib.sha256(b"otro contenido").hexdigest(),
        )

        form = _form(doc_type, aircraft, _upload())
        assert form.is_valid(), form.errors

        assert form.duplicate_of is None

    def test_the_same_name_with_other_content_is_not_a_duplicate(
        self, doc_type, aircraft
    ):
        """El caso real que `R4.2` documenta: dos archivos con **igual nombre** y
        contenido distinto, un PDF de póliza archivado en dos carpetas. La huella
        es del contenido, y por eso ese caso no se confunde."""
        Document.objects.create(
            title="carta.pdf",
            doc_type=doc_type,
            content_type=ContentType.objects.get_for_model(Aircraft),
            object_id=aircraft.pk,
            issue_date=TODAY,
            content_sha256=hashlib.sha256(b"contenido distinto").hexdigest(),
        )

        form = _form(doc_type, aircraft, _upload(name="carta.pdf"))
        assert form.is_valid(), form.errors

        assert form.duplicate_of is None

    def test_an_archived_document_does_not_count(self, doc_type, aircraft):
        """Avisar de un archivo que ya se sacó de la app mandaría a buscar algo
        que no está en ningún listado."""
        Document.objects.create(
            title="Carta archivada",
            doc_type=doc_type,
            content_type=ContentType.objects.get_for_model(Aircraft),
            object_id=aircraft.pk,
            issue_date=TODAY,
            content_sha256=hashlib.sha256(CONTENT).hexdigest(),
            is_active=False,
        )

        form = _form(doc_type, aircraft, _upload())
        assert form.is_valid(), form.errors

        assert form.duplicate_of is None

    def test_it_warns_and_lets_the_upload_through(self, doc_type, aircraft):
        """**La decisión de la fila**: es información, no una puerta cerrada. La
        misma carta cubriendo dos permisos es el caso que el usuario describió."""
        Document.objects.create(
            title="Carta Permiso · JEJ-2026-001",
            doc_type=doc_type,
            content_type=ContentType.objects.get_for_model(Aircraft),
            object_id=aircraft.pk,
            issue_date=TODAY,
            content_sha256=hashlib.sha256(CONTENT).hexdigest(),
        )

        form = _form(doc_type, aircraft, _upload())

        # Válido: el duplicado no es un error de validación.
        assert form.is_valid(), form.errors
        assert form.duplicate_of is not None
