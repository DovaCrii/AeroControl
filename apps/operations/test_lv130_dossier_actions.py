"""LV-130 y LV-131: el expediente deja de informar y empieza a resolver.

Pedido del usuario mirando la ficha de `JEJ-2026-002` con cuatro renglones en
ámbar: *"en el expediente de cada uno […] buscar un workflow mejor o cómo para ir
cubriendo y confirmando lo faltante para que esté completo"*. La pantalla decía
qué faltaba y ahí terminaba; cerrar cada cosa exigía saber **dónde** se cierra,
que es justo el conocimiento que este expediente existe para no exigir.

Los tests afirman **la URL de destino**, nunca la etiqueta del botón: la etiqueta
se traduce, y un test que la fije pasa en aislado y falla en la suite completa
donde otro test dejó el español activo (`LV-95`, y `LV-107` ya lo pagó).
"""

from datetime import timedelta

import pytest
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.utils import timezone

from apps.compliance.models import DocumentType
from apps.core.testing import login_as
from apps.geo.models import GeoPlan
from apps.operations.dossier import (
    SIGNED_AUTHORIZATION,
    _flight_record_item,
    _flight_request_item,
    operational_dossier,
)
from apps.operations.models import FlightPermission
from apps.registry.models import Aircraft, CostCenter, Operator

TODAY = timezone.localdate()
FUTURE = TODAY + timedelta(days=300)


@pytest.fixture
def cost_center(db):
    return CostCenter.objects.create(code="CC130", name="Faena")


@pytest.fixture
def permission(cost_center):
    return FlightPermission.objects.create(
        internal_folio="JEJ-2026-130",
        cost_center=cost_center,
        purpose="other",
        purpose_detail="Levantamiento de prueba",
        area_type="unpopulated",
        valid_from=TODAY,
        valid_until=FUTURE,
        location="Faena de prueba",
    )


def _item(permission, key, user=None):
    dossier = operational_dossier(permission, user)
    return next(item for item in dossier["items"] if item.key == key)


def _aircraft(registration):
    """Sin vigencia de seguro: el caso ámbar de `LV-29`, "nunca se ingresó"."""
    return Aircraft.objects.create(
        registration=registration, type="RPA", model="M3", manufacturer="DJI"
    )


class TestWhereEachGapIsClosed:
    @pytest.mark.django_db
    def test_a_missing_document_links_to_the_upload_form_with_its_type(
        self, permission
    ):
        """El atajo lleva los tres datos que la persona tendría que elegir: la
        entidad, el registro y **cuál de los dieciocho tipos** es el correcto --
        que es lo que `LV-64` demostró que se confunde."""
        doc_type = DocumentType.objects.create(
            code=SIGNED_AUTHORIZATION, name="Autorización DGAC"
        )
        content_type = ContentType.objects.get_for_model(FlightPermission)

        item = _item(permission, "signed_authorization")

        assert item.action_url.startswith(reverse("document-create"))
        assert f"entity_type={content_type.pk}" in item.action_url
        assert f"object_id={permission.pk}" in item.action_url
        assert f"doc_type={doc_type.pk}" in item.action_url

    @pytest.mark.django_db
    def test_the_upload_link_survives_a_type_missing_from_the_catalog(self, permission):
        """Sin la fila de catálogo el enlace va igual, sin prellenar el tipo:
        dejar a alguien sin forma de subir el papel porque falta un seed sería
        peor que ofrecerle el formulario a medio llenar."""
        assert not DocumentType.objects.filter(code=SIGNED_AUTHORIZATION).exists()

        item = _item(permission, "signed_authorization")

        assert item.action_url.startswith(reverse("document-create"))
        assert "doc_type=" not in item.action_url

    @pytest.mark.django_db
    def test_one_aircraft_without_insurance_links_to_that_aircraft(self, permission):
        aircraft = _aircraft("RPA-130")
        permission.aircraft_fleet.add(aircraft)

        item = _item(permission, "insurance")

        assert item.action_url == reverse("aircraft-detail", args=[aircraft.pk])

    @pytest.mark.django_db
    def test_several_aircraft_link_to_the_fleet_and_not_to_the_first(self, permission):
        """Llevar al primero de tres escondería los otros dos detrás de un botón
        que parece haber resuelto el renglón."""
        first, second = _aircraft("RPA-131"), _aircraft("RPA-132")
        permission.aircraft_fleet.add(first, second)

        item = _item(permission, "insurance")

        assert item.action_url == reverse("aircraft-list")

    @pytest.mark.django_db
    def test_an_operator_without_credential_links_to_that_operator(
        self, permission, cost_center
    ):
        operator = Operator.objects.create(
            employee_id="E130", full_name="Sin credencial", cost_center=cost_center
        )
        permission.operators.add(operator)

        item = _item(permission, "credential")

        assert item.action_url == reverse("operator-detail", args=[operator.pk])

    @pytest.mark.django_db
    def test_no_plan_links_to_the_import_with_the_permit_prefilled(self, permission):
        item = _item(permission, "geo_plan")

        assert item.action_url == (
            f"{reverse('geo-plan-import')}?flight_permission={permission.pk}"
        )

    @pytest.mark.django_db
    def test_a_plan_without_weather_review_links_to_that_plan(
        self, permission, cost_center
    ):
        """La revisión se registra con un botón que vive en la ficha del plan
        (R8.1), así que el atajo lleva ahí en vez de duplicar el registro de
        evidencia en un segundo lugar."""
        owner = login_as().user
        plan = GeoPlan.objects.create(
            title="Plan sin revisión",
            cost_center=cost_center,
            created_by=owner,
            flight_permission=permission,
        )

        item = _item(permission, "weather")

        assert item.action_url == reverse("geo-plan-detail", args=[plan.pk])

    @pytest.mark.django_db
    def test_no_request_links_to_the_requests_list(self, permission):
        """No vincula desde acá: el vínculo se hace en la solicitud, donde están
        las coordenadas presentadas que hay que comparar antes de afirmar que
        este permiso responde a esa solicitud.

        **LV-194 retiró este renglón del expediente**, así que el atajo se
        comprueba sobre la función: el retiro es reversible y su atajo tiene que
        seguir llevando donde llevaba.
        """
        item = _flight_request_item(permission)

        assert item.action_url == reverse("flight-request-list")

    @pytest.mark.django_db
    def test_no_flights_links_to_the_log_form_with_the_permit_prefilled(
        self, permission
    ):
        """Igual que el de arriba: renglón retirado por `LV-194`, atajo probado
        sobre la función."""
        item = _flight_record_item(permission)

        assert item.action_url == (
            f"{reverse('record-create')}?permission={permission.pk}"
        )


class TestWhenThereIsNoActionToOffer:
    @pytest.mark.django_db
    def test_a_row_in_green_carries_no_action(self, permission, cost_center):
        """Un renglón resuelto no necesita atajo, y ponerle uno llenaría la
        columna de botones que no hay que apretar."""
        operator = Operator.objects.create(
            employee_id="E133",
            full_name="Con credencial",
            cost_center=cost_center,
            credential_expiry=FUTURE,
        )
        permission.operators.add(operator)

        item = _item(permission, "credential")

        assert item.is_ok
        assert item.action_url == ""
        assert item.action_label == ""

    @pytest.mark.django_db
    def test_an_action_the_user_cannot_perform_is_not_offered(self, permission):
        """Un botón que termina en 403 es peor que ninguno: enseña a desconfiar
        de la pantalla."""
        sin_permiso = login_as("view_flightpermission").user
        con_permiso = login_as("view_flightpermission", "add_document").user

        assert _item(permission, "signed_authorization", sin_permiso).action_url == ""
        assert _item(permission, "signed_authorization", con_permiso).action_url != ""

    @pytest.mark.django_db
    def test_without_a_user_nothing_is_filtered(self, permission):
        """La firma de un argumento es un contrato: `operational_dossier` sin
        usuario devuelve todos los atajos, que es lo que necesitan los tests del
        renglón y lo que mantiene compatible a quien ya la llamaba.

        Se comprueba sobre la autorización firmada y no sobre los vuelos, que es
        el renglón que usaba antes de que `LV-194` lo retirara: lo que este test
        afirma es el contrato de la firma, así que sirve cualquier renglón con
        atajo — y uno que siga en el expediente lo prueba de punta a punta.
        """
        assert _item(permission, "signed_authorization").action_url != ""


class TestTheRequestsListStopsPretendingToSplit:
    """LV-131: *"Solicitud SIGO te mueve a planificación geoespacial, es
    redundante"*. El encabezado tenía un botón "Separar un plan" que no separaba
    nada: llevaba al listado de planes.

    Se lee **el archivo** y no una página renderizada, igual que el test de
    iconos de `R10.3`: lo que se afirma es que el botón no volvió al encabezado,
    y una página no distingue ese enlace del que ahora vive en el estado vacío.
    """

    def _template(self, name):
        from django.conf import settings

        return (settings.BASE_DIR / "templates" / "operations" / name).read_text(
            encoding="utf-8"
        )

    def test_the_header_no_longer_links_to_the_plan_list(self):
        source = self._template("flight_request_list.html")
        header = source.split("{% block list_primary_actions %}")[1].split(
            "{% endblock %}"
        )[0]

        assert "geo-plan-list" not in header

    def test_the_screen_says_what_it_is_for(self):
        source = self._template("flight_request_list.html")

        assert "{% block list_intro %}" in source

    def test_the_empty_state_is_where_the_origin_is_explained(self):
        source = self._template("_flight_request_rows.html")

        assert "geo-plan-list" in source
