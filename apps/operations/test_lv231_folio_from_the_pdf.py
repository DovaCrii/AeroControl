"""LV-231: el folio sale de la autorización DGAC, en vez de teclearse.

Pedido del usuario, textual, con la captura del PDF a la vista: *"que el número
del permiso de vuelo lo pueda sacar de la autorización DGAC; es el mismo PDF que
siempre sube la DGAC, de ahí que sea automático"*. Su captura muestra el
encabezado invariable: **"Autorización de Operación RPA DAN 151 / Número: 6551"**.

⚠️ Lo que estos tests fijan **no** es que la extracción acierte -- eso depende de
que la DGAC no cambie su encabezado, y no está bajo nuestro control. Fijan las
tres cosas que sí lo están: que proponga y no escriba sola, que se calle cuando
la respuesta es dudosa, y que confirmar no sea un camino para escribir cualquier
número.
"""

import io

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core.files.base import ContentFile
from django.urls import reverse

from apps.compliance.models import Document, DocumentType
from apps.compliance.storage import get_document_storage
from apps.core.testing import login_as
from apps.registry.models import CostCenter

from .dgac_pdf import folio_from_pdf
from .models import FlightPermission

AUTHORIZATION = "dgac-rpa-operation-authorization"


def _pdf(*lines):
    """Un PDF de verdad, con `reportlab`, que es lo que el proyecto ya trae.

    Se genera en vez de guardarse como binario fijo a propósito: un PDF de
    muestra en el repo se vuelve indescifrable en la primera revisión, y lo que
    este test necesita es controlar **qué texto** lleva.
    """
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    page = canvas.Canvas(buffer)
    for index, line in enumerate(lines):
        page.drawString(70, 750 - index * 20, line)
    page.save()
    return buffer.getvalue()


def _permit_with(*lines, code=AUTHORIZATION, **extra):
    cost_center = CostCenter.objects.create(
        code="CC1", name="Uno", operates_flights=True
    )
    permit = FlightPermission.objects.create(
        cost_center=cost_center,
        purpose="photogrammetry",
        status=FlightPermission.STATUS_REQUESTED,
        location="Tranque el Mauro",
        area_type="unpopulated",
        **extra,
    )
    doc_type, _created = DocumentType.objects.get_or_create(
        code=code, defaults={"name": code}
    )
    # `save` devuelve `None` (guarda bajo la clave que se le da), así que la ruta
    # se arma acá. Lleva el pk del permiso porque un test que cree dos permisos
    # compartiría el archivo si la clave fuera sólo el código del tipo.
    path = f"test/{permit.pk}-{code}.pdf"
    get_document_storage().save(
        path, ContentFile(_pdf(*lines) if lines else b"not a pdf")
    )
    Document.objects.create(
        content_type=ContentType.objects.get_for_model(FlightPermission),
        object_id=permit.pk,
        doc_type=doc_type,
        title="Autorizacion",
        file_path=path,
        issue_date="2026-09-01",
    )
    return permit


class TestReadingTheNumberOutOfThePdf:
    def test_it_finds_the_number_in_the_header_the_dgac_uses(self):
        stream = io.BytesIO(
            _pdf("Autorizacion de Operacion RPA DAN 151", "Numero: 6551")
        )

        assert folio_from_pdf(stream) == "6551"

    def test_a_missing_accent_does_not_lose_the_folio(self):
        """Un PDF generado con una fuente sin acentos, o pasado por una capa OCR,
        los pierde. Fallar por una tilde sería fallar por la razón más tonta."""
        stream = io.BytesIO(_pdf("Número: 6551"))

        assert folio_from_pdf(stream) == "6551"

    def test_two_different_numbers_produce_no_suggestion(self):
        """Es el caso que más importa: ahí no hay una respuesta, hay dos
        candidatas, y elegir una sería inventar cuál manda. Sin sugerencia, la
        persona teclea el que dice el papel -- que es lo que hacía antes."""
        stream = io.BytesIO(_pdf("Numero: 6551", "Numero: 7002"))

        assert folio_from_pdf(stream) is None

    def test_the_same_number_twice_is_still_one_answer(self):
        """Un encabezado repetido en el pie no es una contradicción."""
        stream = io.BytesIO(_pdf("Numero: 6551", "Numero: 6551"))

        assert folio_from_pdf(stream) == "6551"

    def test_a_header_without_a_number_produces_nothing(self):
        stream = io.BytesIO(_pdf("Autorizacion de Operacion RPA DAN 151"))

        assert folio_from_pdf(stream) is None

    def test_a_file_that_is_not_a_pdf_does_not_raise(self):
        """Quien llama está dibujando una ficha: un permiso no puede dejar de
        mostrarse porque su adjunto esté roto."""
        assert folio_from_pdf(io.BytesIO(b"esto no es un PDF")) is None


class TestTheFicheProposesAndDoesNotWrite:
    @pytest.mark.django_db
    def test_the_suggestion_appears_when_the_box_is_empty(self, db):
        permit = _permit_with("Numero: 6551")
        client = login_as("view_flightpermission", "change_flightpermission")

        body = client.get(
            reverse("permission-detail", args=[permit.pk])
        ).content.decode()

        assert "6551" in body
        # Y **rotulado**: el número no puede parecer un dato declarado.
        assert "Leído de la autorización DGAC" in body or "Read from the DGAC" in body

    @pytest.mark.django_db
    def test_drawing_the_fiche_does_not_write_the_folio(self, db):
        """La mitad que separa "propone" de "escribe": abrir la ficha no puede
        dejar el permiso con un folio que nadie confirmó."""
        permit = _permit_with("Numero: 6551")
        client = login_as("view_flightpermission", "change_flightpermission")

        client.get(reverse("permission-detail", args=[permit.pk]))

        permit.refresh_from_db()
        assert permit.permission_number is None or permit.permission_number == ""

    @pytest.mark.django_db
    def test_a_permit_that_already_has_a_folio_gets_no_suggestion(self, db):
        """Sobreponerle una lectura del PDF sería reemplazar un dato que alguien
        verificó por una heurística."""
        permit = _permit_with("Numero: 6551", permission_number="9999")
        client = login_as("view_flightpermission", "change_flightpermission")

        body = client.get(
            reverse("permission-detail", args=[permit.pk])
        ).content.decode()

        assert "9999" in body
        assert "Read from the DGAC" not in body
        assert "Leído de la autorización DGAC" not in body

    @pytest.mark.django_db
    def test_a_letter_to_the_dgac_is_not_an_authorization(self, db):
        """`dgac-flight-permit` es la carta que va **hacia** la DGAC como parte de
        la solicitud, y puede existir mucho antes de cualquier aprobación. Leerle
        un folio sería presentar como autorizado algo que sólo fue pedido -- la
        misma distinción que `LV-51` fija para la compuerta de aprobación."""
        permit = _permit_with("Numero: 6551", code="dgac-flight-permit")
        client = login_as("view_flightpermission", "change_flightpermission")

        body = client.get(
            reverse("permission-detail", args=[permit.pk])
        ).content.decode()

        assert "Read from the DGAC" not in body
        assert "Leído de la autorización DGAC" not in body


class TestConfirmingIsNotAWayToWriteAnything:
    @pytest.mark.django_db
    def test_confirming_writes_the_number_the_pdf_states(self, db):
        permit = _permit_with("Numero: 6551")
        client = login_as("view_flightpermission", "change_flightpermission")

        client.post(reverse("permission-folio-from-pdf", args=[permit.pk]))

        permit.refresh_from_db()
        assert permit.permission_number == "6551"

    @pytest.mark.django_db
    def test_a_number_sent_by_the_client_is_ignored(self, db):
        """⚠️ El punto de seguridad de la vista. Si el botón llevara el valor en
        un campo oculto, "confirmar la sugerencia" sería un camino para escribir
        cualquier folio -- y encima uno que la ficha presentaría después como
        leído del papel."""
        permit = _permit_with("Numero: 6551")
        client = login_as("view_flightpermission", "change_flightpermission")

        client.post(
            reverse("permission-folio-from-pdf", args=[permit.pk]),
            {"folio": "0000", "permission_number": "0000", "suggested_folio": "0000"},
        )

        permit.refresh_from_db()
        assert permit.permission_number == "6551"

    @pytest.mark.django_db
    def test_it_does_not_overwrite_a_folio_that_is_already_there(self, db):
        permit = _permit_with("Numero: 6551", permission_number="9999")
        client = login_as("view_flightpermission", "change_flightpermission")

        client.post(reverse("permission-folio-from-pdf", args=[permit.pk]))

        permit.refresh_from_db()
        assert permit.permission_number == "9999"

    @pytest.mark.django_db
    def test_an_unreadable_pdf_says_so_instead_of_writing_something(self, db):
        permit = _permit_with()  # sin líneas: el archivo no es un PDF
        client = login_as("view_flightpermission", "change_flightpermission")

        client.post(reverse("permission-folio-from-pdf", args=[permit.pk]))

        permit.refresh_from_db()
        assert permit.permission_number is None or permit.permission_number == ""

    @pytest.mark.django_db
    def test_it_needs_the_change_permission(self, db):
        """Escribe en el permiso, así que pide lo mismo que editarlo. Sólo
        `view_` no alcanza -- una compuerta de lectura sobre una acción que
        escribe es la clase de defecto que `LV-142` cerró en el padrón."""
        permit = _permit_with("Numero: 6551")
        client = login_as("view_flightpermission")

        response = client.post(reverse("permission-folio-from-pdf", args=[permit.pk]))

        assert response.status_code in (302, 403)
        permit.refresh_from_db()
        assert permit.permission_number is None or permit.permission_number == ""
