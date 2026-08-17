"""LV-107: el expediente operativo del permiso.

Contesta *"¿esta operación está completa y documentada?"* leyendo lo que ya
existe, en vez de obligar a abrir la ficha del permiso, la de cada aeronave, la
de cada operador, el plan geoespacial y el repositorio de documentos.

Lo que estos tests fijan no es el dibujo, son las tres decisiones que lo hacen
útil en vez de decorativo:

* un faltante **se nombra** (qué aeronave, qué operador), porque "faltan
  vigencias" no dice qué hacer;
* **sin dato no es lo mismo que vencido** -- `LV-29` decidió que un nulo
  significa "nunca se ingresó", así que pintarlo de verde o de rojo miente;
* el expediente **no bloquea nada**: las compuertas reales viven en la vista, y
  duplicarlas acá sería una segunda copia de la regla.
"""

from datetime import date, timedelta

import pytest
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from apps.compliance.models import Document, DocumentType
from apps.operations.dossier import (
    MISSING,
    OK,
    PERMIT_LETTER,
    SIGNED_AUTHORIZATION,
    UNKNOWN,
    operational_dossier,
)
from apps.operations.models import FlightPermission
from apps.registry.models import Aircraft, CostCenter, Operator

TODAY = timezone.localdate()
PAST = TODAY - timedelta(days=30)
FUTURE = TODAY + timedelta(days=300)


@pytest.fixture
def cost_center(db):
    return CostCenter.objects.create(code="CC107", name="Faena")


@pytest.fixture
def permission(cost_center):
    return FlightPermission.objects.create(
        internal_folio="JEJ-2026-107",
        cost_center=cost_center,
        purpose="other",
        # La constraint `ops_flightpermission_other_purpose_requires_detail`
        # exige el detalle cuando el propósito es "otro" (R3.1).
        purpose_detail="Levantamiento de prueba",
        area_type="unpopulated",
        valid_from=TODAY,
        valid_until=FUTURE,
        location="Faena de prueba",
    )


def _aircraft(registration, insurance_expiry):
    return Aircraft.objects.create(
        registration=registration,
        type="RPA",
        model="M3",
        manufacturer="DJI",
        insurance_expiry=insurance_expiry,
    )


def _operator(name, cost_center, credential_expiry):
    return Operator.objects.create(
        employee_id=name,
        full_name=name,
        cost_center=cost_center,
        credential_expiry=credential_expiry,
    )


def _attach(permission, code):
    doc_type, _made = DocumentType.objects.get_or_create(
        code=code, defaults={"name": code, "requires_expiry": False}
    )
    return Document.objects.create(
        title=code,
        doc_type=doc_type,
        content_type=ContentType.objects.get_for_model(FlightPermission),
        object_id=permission.pk,
        issue_date=date(2026, 8, 14),
        file_path=f"{code}/x.pdf",
    )


def _item(permission, key):
    """Por clave, nunca por el texto de la etiqueta.

    La etiqueta se traduce: buscarla por su texto en inglés hacía pasar estos
    tests en aislado y fallar los ocho al correr la suite completa, donde otro
    test deja el español activo. Es la misma trampa de `LV-95`.
    """
    for item in operational_dossier(permission)["items"]:
        if item.key == key:
            return item
    raise AssertionError(f"no hay renglón con clave {key!r}")


@pytest.mark.django_db
class TestAFaultIsNamed:
    def test_it_says_which_aircraft_has_lapsed_insurance(self, permission):
        permission.aircraft_fleet.add(
            _aircraft("RPA-OK", FUTURE), _aircraft("RPA-VENCIDA", PAST)
        )

        item = _item(permission, "insurance")

        assert item.status == MISSING
        assert item.offenders == ["RPA-VENCIDA"]

    def test_it_says_which_operator_has_a_lapsed_credential(
        self, permission, cost_center
    ):
        permission.operators.add(
            _operator("Al dia", cost_center, FUTURE),
            _operator("Vencido", cost_center, PAST),
        )

        item = _item(permission, "credential")

        assert item.status == MISSING
        assert item.offenders == ["Vencido"]


@pytest.mark.django_db
class TestMissingDataIsNotTheSameAsExpired:
    """LV-29: un nulo significa "nunca se ingresó", no "vencido"."""

    def test_an_aircraft_with_no_expiry_on_file_is_to_confirm_not_missing(
        self, permission
    ):
        permission.aircraft_fleet.add(_aircraft("RPA-SIN-DATO", None))

        item = _item(permission, "insurance")

        assert item.status == UNKNOWN
        assert item.offenders == ["RPA-SIN-DATO"]

    def test_a_lapsed_one_outranks_one_with_no_data(self, permission):
        """Con las dos cosas presentes manda lo vencido: es el incumplimiento."""
        permission.aircraft_fleet.add(
            _aircraft("RPA-SIN", None), _aircraft("RPA-VEN", PAST)
        )

        assert _item(permission, "insurance").status == MISSING


@pytest.mark.django_db
class TestTheTwoDgacPapersAreDifferentDocuments:
    """LV-64: la carta va *hacia* la DGAC; la autorización firmada es la que
    vuelve con folio y es la única que certifica la aprobación."""

    def test_the_letter_alone_does_not_satisfy_the_signed_authorization(
        self, permission
    ):
        _attach(permission, PERMIT_LETTER)

        assert _item(permission, "signed_authorization").status == MISSING
        assert _item(permission, "permit_letter").status == OK

    def test_the_signed_authorization_is_recognised(self, permission):
        _attach(permission, SIGNED_AUTHORIZATION)

        assert _item(permission, "signed_authorization").status == OK


@pytest.mark.django_db
class TestFlightsAgainstThePermit:
    def test_a_completed_permit_with_no_flights_is_a_contradiction(self, permission):
        permission.status = "completed"
        permission.save(update_fields=["status"])

        assert _item(permission, "flights").status == MISSING

    def test_an_open_permit_with_no_flights_is_merely_pending(self, permission):
        assert _item(permission, "flights").status == UNKNOWN


@pytest.mark.django_db
def test_a_fully_documented_permit_reads_as_complete(permission, cost_center):
    permission.aircraft_fleet.add(_aircraft("RPA-BIEN", FUTURE))
    permission.operators.add(_operator("Piloto", cost_center, FUTURE))
    _attach(permission, SIGNED_AUTHORIZATION)
    _attach(permission, PERMIT_LETTER)

    dossier = operational_dossier(permission)

    # Sin plan geo ni vuelos, "completo" no puede ser cierto -- y ese es el
    # punto: el expediente cuenta lo que falta, no lo que uno quiere oír.
    assert not dossier["is_complete"]
    assert dossier["missing_count"] == 0
    assert dossier["unknown_count"] > 0


@pytest.mark.django_db
def test_the_permit_page_shows_it(permission, client, django_user_model):
    from django.contrib.auth.models import Permission as AuthPermission
    from django.urls import reverse

    user = django_user_model.objects.create_user("u-dossier", password="pw")
    user.user_permissions.add(
        *AuthPermission.objects.filter(
            codename__in=["view_flightpermission", "view_document"]
        )
    )
    assert client.login(username="u-dossier", password="pw")
    permission.aircraft_fleet.add(_aircraft("RPA-VENCIDA", PAST))

    html = client.get(
        reverse("permission-detail", args=[permission.pk])
    ).content.decode()

    assert "RPA-VENCIDA" in html
