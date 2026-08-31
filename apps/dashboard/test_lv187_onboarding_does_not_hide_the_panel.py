"""LV-187: la tarjeta de bienvenida no puede esconder la operación.

Encontrado el 2026-08-31 al escribir el test de punta a punta que `LV-186` había
dejado pendiente: el ítem llegaba al contexto con su sujeto resuelto y **no
aparecía en el HTML**. La causa no estaba en `LV-186` sino un nivel más arriba:
`templates/dashboard/index.html` envuelve **todo** el contenido del panel en un
`{% if %}` de primera pantalla, y ese `if` mira aeronaves, operadores y alertas.

Como guard de instalación vacía es correcto y es su propósito. Los dos huecos:

1. **Los tres contadores respetan el filtro por faena y los vencimientos no
   entraban en la condición.** Elegir una faena sin flota ni padrón cumplía el
   guard, así que el panel entero desaparecía y con él los vencimientos de esa
   faena — con la tarjeta invitando a *"1. Crear un centro de costo"* a una
   operación que lleva 16 aeronaves y 42 operadores. Es la familia de `LV-120`
   (la rama `overdue` escrita y nunca dibujable) y de `LV-146`: el dato está y la
   pantalla no lo muestra.
2. **`stages` no existía en el contexto del panel.** El cuarto término del `if`
   era condición muerta: parecía proteger algo y no protegía nada.

La condición pasa a `views.py` como `show_onboarding`, donde cada término tiene
su razón escrita. Cinco términos en una plantilla no se leen de un vistazo, y es
exactamente donde se esconde un `stages`.
"""

from datetime import timedelta

import pytest
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.utils import timezone

from apps.compliance.models import Document, DocumentType
from apps.operations.models import FlightPermission
from apps.registry.models import Aircraft, CostCenter, Operator

TODAY = timezone.localdate()

ONBOARDING = "onboarding-title"


@pytest.fixture
def admin_client_(client, django_user_model):
    django_user_model.objects.create_superuser("admin", "a@test.com", "password")
    assert client.login(username="admin", password="password")
    return client


@pytest.fixture
def mine(db):
    return CostCenter.objects.create(code="CC738", name="MLP")


def _permit(cost_center, days=20):
    return FlightPermission.objects.create(
        internal_folio="JEJ-2026-004",
        cost_center=cost_center,
        purpose="survey",
        valid_from=TODAY,
        valid_until=TODAY + timedelta(days=days),
        location="Quebrada km 13",
        area_type="dan_91",
    )


def _document(subject, days=10):
    return Document.objects.create(
        title="Carta Permiso",
        doc_type=DocumentType.objects.get_or_create(
            code="permit-letter", defaults={"name": "Carta Permiso"}
        )[0],
        content_type=ContentType.objects.get_for_model(type(subject)),
        object_id=subject.pk,
        issue_date=TODAY - timedelta(days=1),
        expiry_date=TODAY + timedelta(days=days),
        is_current_version=True,
    )


@pytest.mark.django_db
class TestWhatWasHidden:
    def test_a_filtered_cost_center_with_no_fleet_still_shows_its_expirations(
        self, admin_client_, mine
    ):
        """El caso reproducido: la faena tiene un permiso y una carta por vencer,
        y su flota vive en otra faena. Antes: "Comienza tu operación" y la lista
        sin dibujar, con `expiring_count` diciendo que había algo."""
        _document(_permit(mine))
        otra = CostCenter.objects.create(code="CC861", name="Talabre")
        Aircraft.objects.create(
            registration="RPA-1", serial_number="S1", cost_center=otra, status="active"
        )

        response = admin_client_.get(reverse("dashboard"), {"cost_center": mine.pk})
        html = response.content.decode()

        assert response.context["expiring_count"] == 2
        assert ONBOARDING not in html
        assert "Carta Permiso" in html

    def test_an_empty_cost_center_says_so_instead_of_starting_over(
        self, admin_client_, mine
    ):
        """Una faena sin nada tampoco es "no tienes operación": es el panel con
        sus vacíos propios, que es la lectura honesta."""
        otra = CostCenter.objects.create(code="CC861", name="Talabre")
        Aircraft.objects.create(
            registration="RPA-1", serial_number="S1", cost_center=otra, status="active"
        )

        html = admin_client_.get(
            reverse("dashboard"), {"cost_center": mine.pk}
        ).content.decode()

        assert ONBOARDING not in html
        assert "Vencimientos" in html

    def test_documents_loaded_before_the_fleet_are_not_hidden(self, admin_client_):
        """Sin filtro, y sin flota ni padrón todavía: los documentos de empresa
        se cargan antes que las aeronaves, así que este orden es el real. El
        guard sin los vencimientos escondía lo único que había cargado."""
        centro = CostCenter.objects.create(code="CC738", name="MLP")
        _document(_permit(centro))

        html = admin_client_.get(reverse("dashboard")).content.decode()

        assert ONBOARDING not in html
        assert "Carta Permiso" in html


@pytest.mark.django_db
class TestWhenItStillBelongs:
    def test_a_fresh_install_still_gets_the_onboarding_card(self, admin_client_):
        """Lo que el guard vino a hacer, y sigue haciendo: sin un solo registro,
        un panel de ceros no le dice a nadie por dónde empezar."""
        html = admin_client_.get(reverse("dashboard")).content.decode()

        assert ONBOARDING in html
        assert admin_client_.get(reverse("dashboard")).context["show_onboarding"]

    def test_one_aircraft_is_enough_to_show_the_panel(self, admin_client_):
        Aircraft.objects.create(
            registration="RPA-1", serial_number="S1", status="active"
        )

        html = admin_client_.get(reverse("dashboard")).content.decode()

        assert ONBOARDING not in html

    def test_one_operator_is_enough_too(self, admin_client_, mine):
        Operator.objects.create(employee_id="E-1", full_name="Ana", cost_center=mine)

        html = admin_client_.get(reverse("dashboard")).content.decode()

        assert ONBOARDING not in html


@pytest.mark.django_db
class TestTheDeadTerm:
    def test_stages_never_existed_in_this_context(self, admin_client_):
        """`stages` era el cuarto término del `if` y la vista no lo define en
        ninguna parte, así que siempre fue falso: no cambiaba nunca la condición.
        Este test es el que impide que vuelva a colarse como algo que protege."""
        context = admin_client_.get(reverse("dashboard")).context

        assert "stages" not in context
