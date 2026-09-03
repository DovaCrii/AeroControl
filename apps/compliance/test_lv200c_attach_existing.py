"""LV-200, paso 3: adjuntar un papel ya cargado, sin volver a subirlo.

Pedido del usuario, textual: *"cómo resolvemos cuando ya tengo otro documento de
la carta en otro permiso del mismo período, para no tener que subirlos siempre"*.

Los pasos 1 y 2 resolvieron el **almacenamiento** —un archivo idéntico deja de
guardarse dos veces— pero no el **trabajo**: había que ir a buscar el archivo al
disco otra vez.
"""

import pytest
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.utils import timezone

from apps.compliance.models import Document, DocumentType
from apps.compliance.reuse import cost_centre_of, reusable_documents
from apps.core.testing import login_as
from apps.operations.models import FlightPermission
from apps.registry.models import CostCenter

LETTER = "dgac-flight-permit"


def _centre(code="CC691"):
    return CostCenter.objects.create(code=code, name=code, operates_flights=True)


def _permit(centre, location="Sector_3"):
    return FlightPermission.objects.create(
        cost_center=centre,
        purpose="photogrammetry",
        status=FlightPermission.STATUS_REQUESTED,
        location=location,
        area_type="unpopulated",
    )


def _letter(permit, *, code=LETTER, expiry=None, path="docs/carta.pdf", title="Carta"):
    doc_type, _created = DocumentType.objects.get_or_create(
        code=code, defaults={"name": code}
    )
    return Document.objects.create(
        content_type=ContentType.objects.get_for_model(FlightPermission),
        object_id=permit.pk,
        doc_type=doc_type,
        title=title,
        file_path=path,
        issue_date=timezone.localdate(),
        expiry_date=expiry,
    )


class TestWhatIsOfferedForReuse:
    @pytest.mark.django_db
    def test_a_letter_from_another_permit_of_the_same_cost_centre(self, db):
        centre = _centre()
        source, target = _permit(centre), _permit(centre, "Sector_9")
        letter = _letter(source)

        assert list(reusable_documents(target, LETTER)) == [letter]

    @pytest.mark.django_db
    def test_never_from_another_cost_centre(self, db):
        """⚠️ La condición que importa. Una carta que el mandante de `CC691`
        emitió no autoriza a operar en `CC410`: adjuntarla allá no sería un
        atajo, sería un documento falso en el expediente."""
        source = _permit(_centre("CC691"))
        target = _permit(_centre("CC410"))
        _letter(source)

        assert list(reusable_documents(target, LETTER)) == []

    @pytest.mark.django_db
    def test_not_the_ones_already_on_this_record(self, db):
        """Reutilizar sobre sí mismo daría dos filas del mismo papel en el mismo
        expediente — el defecto que `LV-230` acaba de sacar de esta pantalla."""
        centre = _centre()
        target = _permit(centre)
        _letter(target)

        assert list(reusable_documents(target, LETTER)) == []

    @pytest.mark.django_db
    def test_not_another_document_type(self, db):
        centre = _centre()
        source, target = _permit(centre), _permit(centre, "Sector_9")
        _letter(source, code="dgac-rpa-operation-authorization")

        assert list(reusable_documents(target, LETTER)) == []

    @pytest.mark.django_db
    def test_not_an_expired_one(self, db):
        """Una carta vencida no puede cubrir un permiso nuevo, y ofrecerla invita
        a adjuntar papel muerto."""
        centre = _centre()
        source, target = _permit(centre), _permit(centre, "Sector_9")
        _letter(source, expiry=timezone.localdate() - timezone.timedelta(days=1))

        assert list(reusable_documents(target, LETTER)) == []

    @pytest.mark.django_db
    def test_one_without_an_expiry_is_still_offered(self, db):
        """Sin vencimiento no es lo mismo que vencido: la mayoría de las cartas
        no llevan fecha de término."""
        centre = _centre()
        source, target = _permit(centre), _permit(centre, "Sector_9")
        letter = _letter(source, expiry=None)

        assert list(reusable_documents(target, LETTER)) == [letter]

    @pytest.mark.django_db
    def test_not_a_row_without_a_file(self, db):
        """Existen —`LV-101` deja una al corregir— y adjuntarlas daría un
        documento que al abrirlo no muestra nada."""
        centre = _centre()
        source, target = _permit(centre), _permit(centre, "Sector_9")
        _letter(source, path="")

        assert list(reusable_documents(target, LETTER)) == []

    @pytest.mark.django_db
    def test_the_cost_centre_comes_from_the_map_the_alerts_use(self, db):
        """Se lee de `ALERT_COST_CENTER_PATHS` y no de un segundo mapa: dos
        tablas que dicen dónde está la faena de cada modelo es cómo una se queda
        atrás, que es lo que `LV-204` ya tuvo que corregir."""
        centre = _centre()

        assert cost_centre_of(_permit(centre)) == centre


class TestAttaching:
    @pytest.mark.django_db
    def test_it_creates_a_row_that_shares_the_file(self, db):
        """**Fila nueva, archivo compartido.** De la relación uno-a-uno entre
        documento y registro cuelgan el expediente, la atribución por faena y los
        porcentajes del informe, donde un documento contado dos veces mueve una
        cifra que va a la DGAC."""
        centre = _centre()
        source, target = _permit(centre), _permit(centre, "Sector_9")
        letter = _letter(source)
        client = login_as("add_document", "view_flightpermission")

        client.post(
            reverse("document-attach-existing"),
            {
                "entity_type": ContentType.objects.get_for_model(FlightPermission).pk,
                "object_id": str(target.pk),
                "doc_type": LETTER,
                "document": str(letter.pk),
            },
        )

        attached = Document.objects.get(object_id=target.pk)
        assert attached.pk != letter.pk
        assert attached.file_path == letter.file_path
        assert attached.title == letter.title

    @pytest.mark.django_db
    def test_the_original_is_untouched(self, db):
        centre = _centre()
        source, target = _permit(centre), _permit(centre, "Sector_9")
        letter = _letter(source)
        client = login_as("add_document", "view_flightpermission")

        client.post(
            reverse("document-attach-existing"),
            {
                "entity_type": ContentType.objects.get_for_model(FlightPermission).pk,
                "object_id": str(target.pk),
                "doc_type": LETTER,
                "document": str(letter.pk),
            },
        )

        letter.refresh_from_db()
        assert letter.object_id == source.pk
        assert letter.is_active is True

    @pytest.mark.django_db
    def test_a_document_of_another_cost_centre_cannot_be_attached_by_pk(self, db):
        """⚠️ **El punto de seguridad de la vista.** El candidato se vuelve a
        resolver contra `reusable_documents` en el `POST`: sin eso, "adjuntar uno
        ya cargado" sería un camino para colgarle a un permiso **cualquier**
        documento de la base con sólo conocer su identificador — incluido el de
        otra faena, que es justo lo que la lista existe para impedir."""
        foreign = _letter(_permit(_centre("CC410")))
        target = _permit(_centre("CC691"))
        client = login_as("add_document", "view_flightpermission")

        client.post(
            reverse("document-attach-existing"),
            {
                "entity_type": ContentType.objects.get_for_model(FlightPermission).pk,
                "object_id": str(target.pk),
                "doc_type": LETTER,
                "document": str(foreign.pk),
            },
        )

        assert not Document.objects.filter(object_id=target.pk).exists()

    @pytest.mark.django_db
    def test_it_needs_the_add_permission(self, db):
        """Crea un `Document`, igual que subirlo. Que el archivo ya exista es una
        circunstancia del almacenamiento, no un permiso distinto."""
        centre = _centre()
        source, target = _permit(centre), _permit(centre, "Sector_9")
        letter = _letter(source)
        client = login_as("view_flightpermission")

        response = client.post(
            reverse("document-attach-existing"),
            {
                "entity_type": ContentType.objects.get_for_model(FlightPermission).pk,
                "object_id": str(target.pk),
                "doc_type": LETTER,
                "document": str(letter.pk),
            },
        )

        assert response.status_code in (302, 403)
        assert not Document.objects.filter(object_id=target.pk).exists()


class TestTheShortcutOnlyAppearsWhenItLeadsSomewhere:
    @pytest.mark.django_db
    def test_the_dossier_offers_it_when_there_is_something_to_reuse(self, db):
        centre = _centre()
        source, target = _permit(centre), _permit(centre, "Sector_9")
        _letter(source)
        client = login_as("view_flightpermission", "add_document", "view_document")

        body = client.get(
            reverse("permission-detail", args=[target.pk])
        ).content.decode()

        assert "document-attach-existing" in body or "document/attach" in body

    @pytest.mark.django_db
    def test_and_stays_quiet_when_there_is_not(self, db):
        """Un botón que abre una lista vacía enseña a no apretarlo, y entonces
        nadie lo aprieta el día que sí habría algo."""
        target = _permit(_centre())
        client = login_as("view_flightpermission", "add_document", "view_document")

        body = client.get(
            reverse("permission-detail", args=[target.pk])
        ).content.decode()

        assert "document/attach" not in body

    @pytest.mark.django_db
    def test_the_empty_list_explains_itself_instead_of_showing_a_dead_form(self, db):
        """Se puede llegar por URL con la lista ya vacía. "No hay ninguno" a
        secas manda a buscar un problema que no existe."""
        target = _permit(_centre())
        client = login_as("add_document")

        body = client.get(
            reverse("document-attach-existing"),
            {
                "entity_type": ContentType.objects.get_for_model(FlightPermission).pk,
                "object_id": str(target.pk),
                "doc_type": LETTER,
            },
        ).content.decode()

        assert "<form" not in body.split("card-body")[-1]
        assert "mismo tipo de documento" in body or "same document type" in body
