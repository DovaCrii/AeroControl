"""`UX-29` · La lista de chequeo prevuelo, firmada y adjunta al vuelo.

Es el estándar universal del mercado y la única brecha funcional grande que **no**
depende de la telemetría. El chequeo se hace —quien vuela lo hace— pero no
quedaba por escrito, así que ante una fiscalización no había con qué demostrarlo.

Las tres decisiones que estos tests fijan, por orden de gravedad:

1. **La respuesta copia el texto del punto.** Es la lección de `LV-233` aplicada
   antes de que duela: editar la plantilla el mes que viene reescribiría lo que
   alguien firmó el mes pasado, y el papel diría que se comprobó algo que ese día
   no estaba en la lista.
2. **Firmado se congela.** Un chequeo editable no es evidencia de nada — el mismo
   motivo por el que `ReportRun.freeze` existe.
3. **Un «no conforme» no impide firmar.** La lista registra lo que se comprobó;
   no decide si se vuela. Impedir la firma habría tenido el efecto contrario: la
   gente vuela igual y no firma nada, y se pierde el registro entero.
"""

from datetime import date, time, timedelta

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.core.testing import login_as
from apps.operations.models import (
    FlightPermission,
    FlightRecord,
    PreflightAnswer,
    PreflightCheck,
    PreflightChecklist,
    PreflightChecklistItem,
)
from apps.registry.models import Aircraft, CostCenter, Operator

TODAY = date(2026, 9, 7)


@pytest.fixture
def centre(db):
    return CostCenter.objects.create(code="CC738", name="MLP", operates_flights=True)


@pytest.fixture
def record(centre):
    permit = FlightPermission.objects.create(
        cost_center=centre,
        purpose="photogrammetry",
        status=FlightPermission.STATUS_APPROVED,
        permission_number="P-1",
        location="Sector 3",
        area_type="unpopulated",
        valid_from=TODAY - timedelta(days=10),
        valid_until=TODAY + timedelta(days=90),
    )
    return FlightRecord.objects.create(
        permission=permit,
        actual_date=TODAY,
        aircraft=Aircraft.objects.create(
            registration="RPA-2019",
            type="RPA",
            model="Mavic 3 Enterprise",
            manufacturer="DJI",
            cost_center=centre,
        ),
        pilot=Operator.objects.create(full_name="Piloto", cost_center=centre),
        departure_time=time(9, 0),
        arrival_time=time(10, 0),
    )


def _checklist(name="General", keywords="", items=("Hélices", "Batería")):
    checklist = PreflightChecklist.objects.create(name=name, model_keywords=keywords)
    for order, text in enumerate(items):
        PreflightChecklistItem.objects.create(
            checklist=checklist, text=text, order=order
        )
    return checklist


class TestWhichChecklistApplies:
    @pytest.mark.django_db
    def test_one_without_keywords_applies_to_everything(self, record):
        """Es el caso normal y no un descuido: una flota chica tiene una sola
        lista, y obligar a enumerar cada modelo habría dejado sin chequeo a la
        primera aeronave nueva, en silencio."""
        checklist = _checklist()

        assert PreflightChecklist.for_aircraft(record.aircraft) == checklist

    @pytest.mark.django_db
    def test_the_keywords_match_the_model_and_not_the_type(self, record):
        """`Aircraft.type` vale "RPA" en toda la flota real y no distingue nada.
        Se compara contra `model`, igual que `QualificationType.model_keywords`
        — la misma pregunta contestada del mismo modo."""
        _checklist(name="Matrice", keywords="matrice")

        assert PreflightChecklist.for_aircraft(record.aircraft) is None

    @pytest.mark.django_db
    def test_the_specific_one_wins_over_the_general(self, record):
        """⚠️ Sin este orden, una flota con una lista genérica y otra para el
        Mavic dependería de cuál devolviera la base primero — y un chequeo cuyo
        contenido cambia entre dos vuelos del mismo día no es evidencia de
        nada."""
        _checklist(name="General")
        specific = _checklist(name="Mavic", keywords="mavic")

        assert PreflightChecklist.for_aircraft(record.aircraft) == specific

    @pytest.mark.django_db
    def test_an_archived_checklist_does_not_apply(self, record):
        checklist = _checklist()
        PreflightChecklist.objects.filter(pk=checklist.pk).update(is_active=False)

        assert PreflightChecklist.for_aircraft(record.aircraft) is None


class TestTheAnswersCopyTheItem:
    """⚠️ La decisión más importante del módulo."""

    @pytest.mark.django_db
    def test_editing_the_template_does_not_rewrite_what_was_answered(self, record):
        """Es `LV-233` aplicado antes de que duela: el papel diría que se
        comprobó algo que ese día no estaba en la lista."""
        checklist = _checklist(items=("Revisar hélices",))
        client = login_as("view_flightrecord", "change_flightrecord")
        client.get(reverse("preflight-check", args=[record.pk]))

        PreflightChecklistItem.objects.filter(checklist=checklist).update(
            text="Otra cosa completamente distinta"
        )

        answer = PreflightAnswer.objects.get()
        assert answer.text == "Revisar hélices"

    @pytest.mark.django_db
    def test_and_neither_does_renaming_the_checklist(self, record):
        _checklist(name="Prevuelo v1")
        client = login_as("view_flightrecord", "change_flightrecord")
        client.get(reverse("preflight-check", args=[record.pk]))

        PreflightChecklist.objects.update(name="Prevuelo v2")

        assert PreflightCheck.objects.get().checklist_name == "Prevuelo v1"


class TestSigning:
    @pytest.mark.django_db
    def test_an_unanswered_item_blocks_the_signature(self, record, django_user_model):
        """Un punto en blanco no dice «estaba bien», dice «no se miró», y una
        firma sobre eso afirma algo que nadie comprobó."""
        _checklist()
        client = login_as("view_flightrecord", "change_flightrecord")
        client.get(reverse("preflight-check", args=[record.pk]))
        check = PreflightCheck.objects.get()

        with pytest.raises(ValidationError):
            check.sign(client.user)

    @pytest.mark.django_db
    def test_answered_it_can_be_signed(self, record):
        _checklist()
        client = login_as("view_flightrecord", "change_flightrecord")
        client.get(reverse("preflight-check", args=[record.pk]))
        PreflightAnswer.objects.update(value=PreflightAnswer.OK)
        check = PreflightCheck.objects.get()

        check.sign(client.user)

        assert check.is_signed
        assert check.signed_by == client.user

    @pytest.mark.django_db
    def test_a_not_conforming_item_does_not_block_it(self, record):
        """⚠️ La lista registra lo que se comprobó; no decide si se vuela. Eso lo
        decide quien opera, y a veces con razón — un punto malo con mitigación
        acordada es una operación normal en aviación. Lo que el sistema hace es
        dejarlo escrito. Impedir la firma habría tenido el efecto contrario: la
        gente vuela igual y no firma nada."""
        _checklist(items=("Hélices",))
        client = login_as("view_flightrecord", "change_flightrecord")
        client.get(reverse("preflight-check", args=[record.pk]))
        PreflightAnswer.objects.update(value=PreflightAnswer.NOT_OK)
        check = PreflightCheck.objects.get()

        check.sign(client.user)

        assert check.is_signed
        # Y queda a la vista de quien revise, que es la mitad que importa.
        assert len(check.blocking_answers) == 1

    @pytest.mark.django_db
    def test_it_cannot_be_signed_twice(self, record):
        _checklist()
        client = login_as("view_flightrecord", "change_flightrecord")
        client.get(reverse("preflight-check", args=[record.pk]))
        PreflightAnswer.objects.update(value=PreflightAnswer.OK)
        check = PreflightCheck.objects.get()
        check.sign(client.user)

        with pytest.raises(ValidationError):
            check.sign(client.user)


class TestTheScreen:
    @pytest.mark.django_db
    def test_it_needs_the_flight_record_permission(self, record):
        """El chequeo **es** parte del expediente del vuelo. Un permiso separado
        habría creado la situación de alguien que puede editar la bitácora pero
        no su chequeo — dos mitades del mismo hecho con dos llaves distintas."""
        client = login_as("view_flightrecord")

        response = client.get(reverse("preflight-check", args=[record.pk]))

        assert response.status_code == 403

    @pytest.mark.django_db
    def test_without_a_checklist_it_says_so_instead_of_inventing_one(self, record):
        """Una instalación recién puesta no tiene listas, y eso es un caso real.
        Inventar una lista vacía dejaría que alguien la firmara creyendo que
        comprobó algo."""
        client = login_as("view_flightrecord", "change_flightrecord")

        response = client.get(reverse("preflight-check", args=[record.pk]))

        assert response.status_code == 200
        assert response.context["check"] is None
        assert not PreflightCheck.objects.exists()

    @pytest.mark.django_db
    def test_opening_it_materialises_the_list_once(self, record):
        """⚠️ Se materializa al abrir y no al crear el vuelo: una señal en
        `FlightRecord.save` habría dejado sin chequeo a todo lo cargado hasta
        hoy. Abrir dos veces no duplica nada."""
        _checklist(items=("A", "B", "C"))
        client = login_as("view_flightrecord", "change_flightrecord")

        client.get(reverse("preflight-check", args=[record.pk]))
        client.get(reverse("preflight-check", args=[record.pk]))

        assert PreflightCheck.objects.count() == 1
        assert PreflightAnswer.objects.count() == 3

    @pytest.mark.django_db
    def test_answers_are_born_unanswered(self, record):
        """Lo que se crea es el formulario en blanco, no una declaración."""
        _checklist()
        client = login_as("view_flightrecord", "change_flightrecord")

        client.get(reverse("preflight-check", args=[record.pk]))

        assert set(PreflightAnswer.objects.values_list("value", flat=True)) == {
            PreflightAnswer.PENDING
        }

    @pytest.mark.django_db
    def test_answering_saves_the_value_and_the_comment(self, record):
        _checklist(items=("Hélices",))
        client = login_as("view_flightrecord", "change_flightrecord")
        client.get(reverse("preflight-check", args=[record.pk]))
        answer = PreflightAnswer.objects.get()

        client.post(
            reverse("preflight-check", args=[record.pk]),
            {
                f"value-{answer.pk}": PreflightAnswer.NOT_OK,
                f"comment-{answer.pk}": "Una con marca",
            },
        )

        answer.refresh_from_db()
        assert answer.value == PreflightAnswer.NOT_OK
        assert answer.comment == "Una con marca"

    @pytest.mark.django_db
    def test_a_made_up_value_is_ignored_instead_of_stored(self, record):
        """Los nombres de los campos vienen del POST, o sea de fuera. Un valor
        que no está en las opciones no se guarda: una respuesta con un código
        inventado se dibujaría en blanco y se leería como «no contestado»."""
        _checklist(items=("Hélices",))
        client = login_as("view_flightrecord", "change_flightrecord")
        client.get(reverse("preflight-check", args=[record.pk]))
        answer = PreflightAnswer.objects.get()

        client.post(
            reverse("preflight-check", args=[record.pk]),
            {f"value-{answer.pk}": "inventado"},
        )

        answer.refresh_from_db()
        assert answer.value == PreflightAnswer.PENDING

    @pytest.mark.django_db
    def test_a_signed_check_stops_accepting_answers(self, record):
        """⚠️ El guard vive en la vista y no en la plantilla: esconder el botón
        no impide un POST."""
        _checklist(items=("Hélices",))
        client = login_as("view_flightrecord", "change_flightrecord")
        client.get(reverse("preflight-check", args=[record.pk]))
        PreflightAnswer.objects.update(value=PreflightAnswer.OK)
        check = PreflightCheck.objects.get()
        check.sign(client.user)
        answer = PreflightAnswer.objects.get()

        client.post(
            reverse("preflight-check", args=[record.pk]),
            {f"value-{answer.pk}": PreflightAnswer.NOT_OK},
        )

        answer.refresh_from_db()
        assert answer.value == PreflightAnswer.OK

    @pytest.mark.django_db
    def test_signing_through_the_screen(self, record):
        _checklist(items=("Hélices",))
        client = login_as("view_flightrecord", "change_flightrecord")
        client.get(reverse("preflight-check", args=[record.pk]))
        PreflightAnswer.objects.update(value=PreflightAnswer.OK)

        client.post(reverse("preflight-sign", args=[record.pk]))

        assert PreflightCheck.objects.get().is_signed


class TestTheEvidenceIsNotEditableFromTheAdmin:
    def test_only_the_template_is_registered(self):
        """⚠️ Un chequeo firmado es evidencia; dejarlo editable desde el
        administrador sería dejar una puerta trasera a lo que la propia clase
        prohíbe. El administrador de Django no es «modo experto»: es la misma
        base, sin los guardias."""
        from django.contrib import admin

        registered = set(admin.site._registry)

        assert PreflightChecklist in registered
        assert PreflightCheck not in registered
        assert PreflightAnswer not in registered
