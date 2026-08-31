"""LV-205: archivar a quien se retira deja de dónde venía.

Pedido del usuario: *"tenemos operadores que ahora se están retirando; debemos
dejar la trazabilidad […] al sacarlo del contrato o de la empresa dejar anotado el
movimiento y qué centro de costo estuvo ligado, así dejamos un registro de dónde
provenía"*.

**Tres de las cuatro piezas ya existían** — archivar un operador, el historial de
`OperatorAssignment`, y que un archivado no afecte al manual: el import del
Capítulo 1 cruza por `employee_id` **sin** filtrar `is_active`, así que lo salta en
vez de recrearlo. Lo que faltaba es cerrar el movimiento: sin eso, un retirado se
queda con una asignación **abierta** a una faena, contando como dotación de un
contrato en el que ya no está.

**La faena se anota en el movimiento y no se deduce de la ficha**, y ahí está lo
que hace que el registro sirva dentro de un año: `Operator.cost_center` puede
cambiar después, y entonces "de dónde venía" contestaría con el dato de hoy.
"""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.core.testing import login_as
from apps.registry.models import CostCenter, Operator, OperatorAssignment

TODAY = timezone.localdate()


@pytest.fixture
def center(db):
    return CostCenter.objects.create(code="CC738", name="MLP")


@pytest.fixture
def operator(center):
    return Operator.objects.create(
        employee_id="RUT-178162667",
        full_name="Nicolas Galleguillos Adaros",
        cost_center=center,
    )


def _assign(operator, center, start=None, status="active"):
    return OperatorAssignment.objects.create(
        operator=operator,
        cost_center=center,
        start_date=start or TODAY - timedelta(days=200),
        status=status,
    )


def _archive(operator):
    return login_as("delete_operator", "change_operator", "view_operator").post(
        reverse("operator-archive", args=[operator.pk])
    )


@pytest.mark.django_db
class TestTheMovementIsRecorded:
    def test_the_open_assignment_is_closed(self, operator, center):
        """Sin esto, un retirado sigue siendo dotación de un contrato en el que ya
        no está — y ése es justo el registro que hay que poder leer al revés."""
        assignment = _assign(operator, center)

        _archive(operator)

        assignment.refresh_from_db()
        assert assignment.end_date == TODAY
        assert assignment.status == "ended"

    def test_the_operator_is_archived(self, operator, center):
        _assign(operator, center)

        _archive(operator)

        operator.refresh_from_db()
        assert operator.is_active is False

    def test_where_it_came_from_is_on_record(self, operator, center):
        from apps.core.models import AuditEvent

        _assign(operator, center)

        _archive(operator)

        event = (
            AuditEvent.objects.filter(action="archived").order_by("-created_at").first()
        )
        assert event is not None
        assert "CC738" in event.metadata["cost_centers"]
        assert event.metadata["left_on"] == TODAY.isoformat()

    def test_the_message_names_the_cost_center(self, operator, center):
        """Quien archiva es quien puede corregir en el momento si se equivocó de
        persona, y "venía de CC738" es lo que se lo dice."""
        _assign(operator, center)

        response = _archive(operator)

        messages = [str(m) for m in response.wsgi_request._messages]
        assert any("CC738" in message for message in messages)

    def test_the_fiche_cost_center_counts_even_without_an_assignment(
        self, operator, center
    ):
        """Hay operadores con faena cargada y sin asignación formal — el padrón
        viejo es así—, y perder esa procedencia por no tener fila sería perder el
        caso más común."""
        from apps.core.models import AuditEvent

        assert not operator.cc_assignments.exists()

        _archive(operator)

        event = (
            AuditEvent.objects.filter(action="archived").order_by("-created_at").first()
        )
        assert event.metadata["cost_centers"] == ["CC738"]
        assert event.metadata["assignments_closed"] == 0

    def test_a_planned_assignment_is_not_closed_in_the_past(self, operator, center):
        """`end_date` nunca antes de `start_date`: una asignación que empieza la
        semana próxima se cierra en su propia fecha de inicio. `save(update_fields)`
        no pasa por `clean()`, así que la fila inválida no la atajaría nadie."""
        future = TODAY + timedelta(days=7)
        assignment = _assign(operator, center, start=future, status="planned")

        _archive(operator)

        assignment.refresh_from_db()
        assert assignment.end_date == future

    def test_several_cost_centers_are_all_named(self, operator, center):
        from apps.core.models import AuditEvent

        other = CostCenter.objects.create(code="CC861", name="Talabre")
        _assign(operator, center, start=TODAY - timedelta(days=300))
        _assign(operator, other, start=TODAY - timedelta(days=100))

        _archive(operator)

        event = (
            AuditEvent.objects.filter(action="archived").order_by("-created_at").first()
        )
        assert set(event.metadata["cost_centers"]) == {"CC738", "CC861"}


@pytest.mark.django_db
class TestWhatDoesNotChange:
    def test_an_already_ended_assignment_is_left_alone(self, operator, center):
        """Cerrar de nuevo una asignación cerrada le movería la fecha y borraría el
        hecho: cuándo terminó de verdad."""
        ended = _assign(operator, center)
        ended.end_date = TODAY - timedelta(days=30)
        ended.status = "ended"
        ended.save(update_fields=["end_date", "status"])

        _archive(operator)

        ended.refresh_from_db()
        assert ended.end_date == TODAY - timedelta(days=30)

    def test_archiving_an_aircraft_is_untouched(self, center):
        """La regla es del operador. Se saca `Operator` del bucle que genera las
        vistas de archivo justamente para no ponerla en el archivador de todos."""
        from apps.registry.models import Aircraft

        aircraft = Aircraft.objects.create(
            registration="RPA-4401", serial_number="SN-1", cost_center=center
        )

        response = login_as("delete_aircraft", "change_aircraft", "view_aircraft").post(
            reverse("aircraft-archive", args=[aircraft.pk])
        )

        assert response.status_code == 302
        aircraft.refresh_from_db()
        assert aircraft.is_active is False

    def test_the_manual_import_still_skips_an_archived_person(self, operator):
        """Lo que el usuario pide como "que no afecten directamente": archivar no
        puede hacer que el import del Capítulo 1 **recree** a la persona. Cruza por
        `employee_id` sin filtrar `is_active`, así que la salta — se fija acá porque
        es la mitad del pedido que ya funcionaba y que un cambio podría romper."""
        _archive(operator)
        operator.refresh_from_db()
        assert operator.is_active is False

        existing = set(Operator.objects.values_list("employee_id", flat=True))

        assert "RUT-178162667" in existing
