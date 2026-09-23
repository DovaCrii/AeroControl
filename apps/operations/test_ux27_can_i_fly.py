"""`UX-27` · «¿Puedo volar?»: una respuesta para una terna, hoy.

La regla que estos tests fijan, y que es la decisión de negocio de la fila:
**vencido bloquea, por vencer avisa**. No es un criterio nuevo — es la escala de
severidad que la aplicación ya usa (`UX-01`): rojo es *no se puede*, ámbar es *se
puede y hay que ocuparse*. Que el panel, la bandeja y esta pantalla respondan
igual sobre el mismo hecho importa más que la elección en sí: dos pantallas que
discrepan enseñan a desconfiar de las dos.

Y las dos excepciones, las dos escritas a propósito:

- **La brecha de compatibilidad avisa y no bloquea**, porque se acordó con el
  usuario el 2026-07-30 y está en `registry.selectors`. Es una coincidencia de
  palabras clave contra el modelo: darle la última palabra sobre un despegue
  sería darle demasiada.
- **La fecha ausente bloquea.** Sin fecha nadie puede afirmar que la vigencia
  está al día, y una pantalla que contesta «sí» porque *no sabe* es peor que una
  que no contesta.
"""

from datetime import date, timedelta

import pytest
from django.urls import reverse

from apps.core.testing import login_as
from apps.operations.models import FlightPermission
from apps.operations.readiness import can_fly
from apps.registry.models import (
    Aircraft,
    CostCenter,
    Operator,
    Qualification,
    QualificationType,
)

TODAY = date(2026, 9, 7)


@pytest.fixture
def centre(db):
    return CostCenter.objects.create(code="CC738", name="MLP", operates_flights=True)


@pytest.fixture
def aircraft(centre):
    return Aircraft.objects.create(
        registration="RPA-2019",
        type="RPA",
        model="Mavic 3 Enterprise",
        manufacturer="DJI",
        cost_center=centre,
        insurance_expiry=TODAY + timedelta(days=200),
    )


@pytest.fixture
def operator(centre):
    person = Operator.objects.create(
        employee_id="E1",
        full_name="Nicolas Galleguillos",
        cost_center=centre,
        credential_expiry=TODAY + timedelta(days=200),
    )
    kind = QualificationType.objects.create(
        code="mavic", name="Serie Mavic", model_keywords="mavic"
    )
    Qualification.objects.create(
        operator=person,
        qualification_type=kind,
        issue_date=TODAY - timedelta(days=100),
        expiry_date=TODAY + timedelta(days=200),
    )
    return person


def _permit(centre, operators=(), fleet=(), **kwargs):
    permit = FlightPermission.objects.create(
        cost_center=centre,
        purpose="photogrammetry",
        status=FlightPermission.STATUS_APPROVED,
        location="Sector 3",
        area_type="unpopulated",
        valid_from=kwargs.pop("valid_from", TODAY - timedelta(days=10)),
        valid_until=kwargs.pop("valid_until", TODAY + timedelta(days=90)),
        **kwargs,
    )
    permit.operators.set(operators)
    permit.aircraft_fleet.set(fleet)
    return permit


@pytest.fixture
def permit(centre, aircraft, operator):
    """⚠️ **El permiso nombra a los dos, y el que no lo hacía era el defecto.**

    La primera versión de esta fixture creaba el permiso con el padrón vacío, y
    todos los tests pasaban igual — porque la comprobación tampoco lo miraba. El
    test compartía el punto ciego del código que probaba, que es cómo un defecto
    llega a producción con la suite en verde. Lo encontró el usuario el
    2026-09-08 usando la pantalla.
    """
    return _permit(centre, operators=[operator], fleet=[aircraft])


def verdict(aircraft, operator, centre):
    return can_fly(aircraft, operator, centre, TODAY)


class TestTheHappyAnswer:
    @pytest.mark.django_db
    def test_everything_in_force_says_yes(self, aircraft, operator, centre, permit):
        result = verdict(aircraft, operator, centre)

        assert result.can_fly
        assert result.blockers == []

    @pytest.mark.django_db
    def test_and_still_lists_what_it_checked(self, aircraft, operator, centre, permit):
        """Un «sí» sin decir qué se miró no se puede contrastar, y quien opera
        necesita poder decir ante una fiscalización qué dio por comprobado."""
        result = verdict(aircraft, operator, centre)

        assert len(result.checks) == 4
        assert all(check.passed for check in result.checks)


class TestExpiredBlocks:
    @pytest.mark.django_db
    def test_the_insurance(self, aircraft, operator, centre, permit):
        aircraft.insurance_expiry = TODAY - timedelta(days=1)

        result = verdict(aircraft, operator, centre)

        assert not result.can_fly
        assert any("07-09-2026" not in item.detail for item in result.blockers)

    @pytest.mark.django_db
    def test_the_dgac_credential(self, aircraft, operator, centre, permit):
        operator.credential_expiry = TODAY - timedelta(days=1)

        assert not verdict(aircraft, operator, centre).can_fly

    @pytest.mark.django_db
    def test_a_qualification(self, aircraft, operator, centre, permit):
        Qualification.objects.filter(operator=operator).update(
            expiry_date=TODAY - timedelta(days=1)
        )

        assert not verdict(aircraft, operator, centre).can_fly

    @pytest.mark.django_db
    @pytest.mark.parametrize("status", ["damaged", "maintenance"])
    def test_an_airframe_that_is_not_flyable(
        self, aircraft, operator, centre, permit, status
    ):
        """El estado del fuselaje va **antes** que cualquier papel: una aeronave
        en mantención no vuela aunque tenga todo al día."""
        aircraft.status = status

        result = verdict(aircraft, operator, centre)

        assert not result.can_fly
        assert result.checks[0].blockers[0].label

    @pytest.mark.django_db
    def test_no_permit_covering_today(self, aircraft, operator, centre):
        result = verdict(aircraft, operator, centre)

        assert not result.can_fly

    @pytest.mark.django_db
    def test_a_permit_that_has_not_started_yet_does_not_count(
        self, aircraft, operator, centre, permit
    ):
        """«Aprobado» no es «vigente»: un permiso que empieza el mes que viene no
        cubre el vuelo de hoy, y contarlo sería el mismo error que `LV-233`
        encontró en el informe."""
        FlightPermission.objects.filter(pk=permit.pk).update(
            valid_from=TODAY + timedelta(days=5)
        )

        assert not verdict(aircraft, operator, centre).can_fly


class TestThePermitHasToNameThem:
    """⚠️ **El defecto que el usuario encontró en producción el 2026-09-08.**

    La pantalla contestaba «Sí» para `RPA-7126` con un operador que el permiso no
    nombra, porque la comprobación se quedaba en *"¿la faena tiene algún permiso
    vigente?"*. Un permiso DGAC no autoriza a la faena: autoriza a un **padrón**
    concreto de operadores y de aeronaves, y volar bajo uno que no lo nombra es
    exactamente el incumplimiento que esta pantalla existe para atajar.

    Por eso **bloquea**, y es la única regla de este módulo que bloquea por algo
    que no es una fecha.
    """

    @pytest.mark.django_db
    def test_an_operator_outside_the_roster_blocks(self, aircraft, operator, centre):
        _permit(centre, operators=[], fleet=[aircraft])

        result = verdict(aircraft, operator, centre)

        assert not result.can_fly
        assert any(str(operator) in item.detail for item in result.blockers)

    @pytest.mark.django_db
    def test_an_aircraft_outside_the_fleet_blocks(self, aircraft, operator, centre):
        _permit(centre, operators=[operator], fleet=[])

        result = verdict(aircraft, operator, centre)

        assert not result.can_fly
        assert any(aircraft.registration in item.detail for item in result.blockers)

    @pytest.mark.django_db
    def test_it_says_which_half_is_missing(self, aircraft, operator, centre):
        """«No autorizado» a secas deja a quien lo lee sin saber si hay que
        agregar a la persona, la aeronave o las dos — y esto se lee en faena, con
        el equipo en la mano."""
        _permit(centre, operators=[], fleet=[])

        detail = verdict(aircraft, operator, centre).blockers[0].detail

        assert str(operator) in detail
        assert aircraft.registration in detail

    @pytest.mark.django_db
    def test_naming_both_in_the_same_permit_lets_it_fly(
        self, aircraft, operator, centre
    ):
        _permit(centre, operators=[operator], fleet=[aircraft])

        assert verdict(aircraft, operator, centre).can_fly

    @pytest.mark.django_db
    def test_two_permits_that_split_them_is_not_enough(
        self, aircraft, operator, centre
    ):
        """⚠️ Uno autoriza a la persona y el otro a la aeronave, y ninguno a los
        dos. Es un caso real cuando una faena parte sus permisos por sector, y
        `any()` sobre cada padrón por separado habría dicho que sí: se vuela
        **bajo un** permiso, no bajo la unión de todos."""
        _permit(centre, operators=[operator], fleet=[], permission_number="A")
        _permit(centre, operators=[], fleet=[aircraft], permission_number="B")

        result = verdict(aircraft, operator, centre)

        assert not result.can_fly

    @pytest.mark.django_db
    def test_but_one_permit_that_does_authorise_is_enough(
        self, aircraft, operator, centre
    ):
        """Que otro permiso de la misma faena no los nombre no es problema de
        nadie: se vuela bajo el que sí."""
        _permit(centre, operators=[], fleet=[], permission_number="A")
        _permit(centre, operators=[operator], fleet=[aircraft], permission_number="B")

        assert verdict(aircraft, operator, centre).can_fly

    @pytest.mark.django_db
    def test_the_warning_follows_the_permit_that_authorises(
        self, aircraft, operator, centre
    ):
        """⚠️ El aviso de vencimiento sale del que **autoriza este vuelo**, no del
        que vence primero de la faena. Uno ajeno que caduca mañana no le importa
        a nadie acá, y mostrarlo escondería el que sí corre."""
        _permit(
            centre,
            operators=[],
            fleet=[],
            permission_number="AJENO",
            valid_until=TODAY + timedelta(days=2),
        )
        mine = _permit(
            centre,
            operators=[operator],
            fleet=[aircraft],
            permission_number="MIO",
            valid_until=TODAY + timedelta(days=20),
        )

        result = verdict(aircraft, operator, centre)

        assert result.can_fly
        assert any(mine.internal_folio in item.label for item in result.warnings)

    @pytest.mark.django_db
    def test_belonging_to_another_cost_centre_still_only_warns(
        self, aircraft, operator, centre
    ):
        """⚠️ La distinción que parece contradictoria y no lo es. «Pertenece a
        otra faena» es administrativo —dónde está anotado el recurso, y los
        recursos se prestan—; «no está en el permiso» es de autorización. Un
        equipo prestado de CC110 que **sí** figura en el permiso de CC738 vuela
        sin problema, y la faena de origen no autoriza nada."""
        other = CostCenter.objects.create(code="CC110", name="Casa matriz")
        aircraft.cost_center = other
        _permit(centre, operators=[operator], fleet=[aircraft])

        result = verdict(aircraft, operator, centre)

        assert result.can_fly
        assert any("CC110" in item.detail for item in result.warnings)


class TestTheMissingDateBlocks:
    """⚠️ La decisión menos obvia y la más importante. En el resto de la
    aplicación un nulo se dibuja como hueco; acá el hueco tiene que pesar, porque
    de esto sale un despegue."""

    @pytest.mark.django_db
    def test_an_aircraft_with_no_insurance_date(
        self, aircraft, operator, centre, permit
    ):
        aircraft.insurance_expiry = None

        result = verdict(aircraft, operator, centre)

        assert not result.can_fly

    @pytest.mark.django_db
    def test_an_operator_with_no_credential_date(
        self, aircraft, operator, centre, permit
    ):
        operator.credential_expiry = None

        assert not verdict(aircraft, operator, centre).can_fly


class TestExpiringOnlyWarns:
    @pytest.mark.django_db
    def test_an_insurance_inside_the_horizon(self, aircraft, operator, centre, permit):
        aircraft.insurance_expiry = TODAY + timedelta(days=10)

        result = verdict(aircraft, operator, centre)

        assert result.can_fly
        assert result.warnings

    @pytest.mark.django_db
    def test_and_beyond_the_horizon_says_nothing(
        self, aircraft, operator, centre, permit
    ):
        """Avisar por todo es no avisar: el horizonte es el mismo de
        `panel_readiness`, así que un vencimiento que el panel todavía no llama
        próximo tampoco puede ser noticia acá."""
        aircraft.insurance_expiry = TODAY + timedelta(days=200)

        assert verdict(aircraft, operator, centre).warnings == []


class TestTheWholeVerdictIsForTheSameDay:
    @pytest.mark.django_db
    def test_the_model_qualification_is_judged_on_the_day_asked(
        self, aircraft, operator, centre, permit
    ):
        """`LV-257`: `can_fly` recibe el día y lo pasaba a todo **menos** a la
        habilitación por modelo, que miraba el día real. Se encontró porque este
        mismo archivo empezaba a fallar a partir de 2027-03-26 (vence la
        habilitación de la fixture) corriendo la suite con el reloj movido.

        La habilitación vence el 2026-09-15: vigente el día que se pregunta
        (`TODAY`, 2026-09-07) y vencida para cualquier día real en que corra esto.
        Con la fecha real, el veredicto de un día en que sí estaba vigente avisaba
        que no lo estaba.
        """
        Qualification.objects.filter(operator=operator).update(
            expiry_date=date(2026, 9, 15)
        )

        from django.utils.translation import gettext

        warnings = verdict(aircraft, operator, centre).warnings

        labels = [str(w.label) for w in warnings]
        assert gettext("Model qualification") not in labels, labels


class TestWhatDeliberatelyNeverBlocks:
    @pytest.mark.django_db
    def test_the_compatibility_gap_only_warns(self, aircraft, operator, centre, permit):
        """⚠️ Acordado con el usuario el 2026-07-30 y escrito en
        `registry.selectors`: *"a warning, not a validation error"*. La
        comparación es por palabras clave contra el modelo de la aeronave, o sea
        una heurística — convertirla en bloqueo le daría a una coincidencia de
        texto la última palabra sobre si se vuela."""
        aircraft.model = "Matrice 300"

        result = verdict(aircraft, operator, centre)

        assert result.can_fly
        assert any("Matrice 300" in item.detail for item in result.warnings)

    @pytest.mark.django_db
    def test_belonging_to_another_cost_centre_only_warns(
        self, aircraft, operator, centre, permit
    ):
        """Prestar un equipo entre faenas es una operación normal: lo que
        corresponde es que quede dicho, no que se impida."""
        other = CostCenter.objects.create(code="CC110", name="Casa matriz")
        aircraft.cost_center = other

        result = verdict(aircraft, operator, centre)

        assert result.can_fly
        assert any("CC110" in item.detail for item in result.warnings)


class TestEveryFindingLeadsSomewhere:
    @pytest.mark.django_db
    def test_a_blocker_carries_the_link_to_resolve_it(self, aircraft, operator, centre):
        """Decirle a alguien en faena que la credencial está vencida y dejarlo
        buscando dónde se renueva es la mitad de un aviso."""
        aircraft.insurance_expiry = None
        operator.credential_expiry = None

        result = verdict(aircraft, operator, centre)

        assert result.blockers
        assert all(item.url.startswith("/") for item in result.blockers)


class TestTheScreen:
    @pytest.mark.django_db
    def test_it_needs_a_session(self, client):
        response = client.get(reverse("can-i-fly"))

        assert response.status_code == 302

    @pytest.mark.django_db
    def test_without_the_roster_permission_the_picker_comes_back_empty(
        self, aircraft, operator, centre
    ):
        """⚠️ El control está en los desplegables, no en la vista entera. Alguien
        sin `registry.view_operator` no puede elegir una persona, así que no hay
        terna y no hay veredicto que filtre nada. Se devuelve **vacío y no se
        omite**: un hueco silencioso se lee como pantalla rota (`LV-130`)."""
        client = login_as("view_aircraft")

        context = client.get(reverse("can-i-fly")).context

        assert list(context["rosters"]["aircraft"])
        assert not list(context["rosters"]["operator"])

    @pytest.mark.django_db
    def test_half_a_set_has_no_verdict(self, aircraft, operator, centre, permit):
        """Dar un veredicto parcial invitaría a leerlo como completo."""
        client = login_as(
            "view_aircraft",
            "view_operator",
            "view_costcenter",
        )

        response = client.get(reverse("can-i-fly"), {"aircraft": str(aircraft.pk)})

        assert "verdict" not in response.context

    @pytest.mark.django_db
    def test_the_full_set_answers(self, aircraft, operator, centre, permit):
        client = login_as(
            "view_aircraft",
            "view_operator",
            "view_costcenter",
        )

        response = client.get(
            reverse("can-i-fly"),
            {
                "aircraft": str(aircraft.pk),
                "operator": str(operator.pk),
                "cost_center": str(centre.pk),
            },
        )

        assert response.context["verdict"] is not None

    @pytest.mark.django_db
    def test_it_says_it_does_not_authorise(self, aircraft, operator, centre, permit):
        """⚠️ La frase va **siempre**, también cuando la respuesta es que sí, y
        ahí es donde más falta hace: si la pantalla se leyera como permiso, el
        día que un dato esté sin cargar habría autorizado un vuelo por omisión.
        """
        from django.utils.translation import gettext

        client = login_as(
            "view_aircraft",
            "view_operator",
            "view_costcenter",
        )

        body = client.get(
            reverse("can-i-fly"),
            {
                "aircraft": str(aircraft.pk),
                "operator": str(operator.pk),
                "cost_center": str(centre.pk),
            },
        ).content.decode()

        assert (
            gettext("This screen reads the records; it does not authorise the flight.")
            in body
        )

    @pytest.mark.django_db
    def test_it_writes_nothing(self):
        """La pantalla lee. Un `POST` acá abriría la puerta a que consultar
        «¿puedo volar?» dejara rastro de haber autorizado algo."""
        from pathlib import Path

        from django.conf import settings

        source = (
            Path(settings.BASE_DIR) / "apps" / "operations" / "readiness.py"
        ).read_text(encoding="utf-8")

        for forbidden in (".save(", ".update(", ".delete(", ".create("):
            assert forbidden not in source, forbidden
