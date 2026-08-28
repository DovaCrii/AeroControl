"""LV-178: por qué se cerró el plan, para poder contarlo.

Pedido del usuario: *"poder clasificar igual cuando fallan"*, y los dos motivos
los puso él: *"existe rechazo por ejemplo casos por la DGAC, modificación
interna"*.

**Son cosas distintas y por eso se cuentan aparte.** Diez rechazos de la
autoridad dicen que estamos presentando mal; diez modificaciones internas son
trabajo normal. Un solo número que sume las dos no sirve para decidir nada, que
es lo que pasa hoy: los cierres no se distinguen entre sí.

**No se cuelga del estado.** `GeoPlan.rejected` y `FlightPermission.denied` ya
existen y significan otra cosa — el resultado del trámite, no el motivo del
cierre. Un plan **aprobado** puede archivarse por modificación interna, y ese
caso se perdería entero si el motivo se dedujera del estado.

Las propiedades que estos tests sostienen:

- **Se pregunta donde ya se preguntaba.** No se fuerza una confirmación nueva
  para los planes sin nada colgando: `LV-135` decidió que ésos se archivan de
  una, con la razón escrita, y sigue valiendo.
- **"Otro" sin decir cuál no clasifica nada**, así que se rechaza.
- **Los planes archivados antes de esta fila quedan sin motivo**, y eso es
  correcto: inventarles uno haría mentir a cualquier informe que los cuente.
- **El motivo llega a la auditoría del permiso** que se cerró en el mismo acto.
"""

from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from apps.core.models import AuditEvent
from apps.core.testing import login_as
from apps.geo.models import GeoPlan, GeoPlanVersion
from apps.operations.models import FlightPermission
from apps.registry.models import CostCenter

TODAY = timezone.localdate()


@pytest.fixture
def plan(db, django_user_model):
    author = django_user_model.objects.create_user("planner", password="x")
    center = CostCenter.objects.create(code="CC1", name="Faena")
    permit = FlightPermission.objects.create(
        internal_folio="JEJ-2026-001",
        cost_center=center,
        purpose="survey",
        valid_from=TODAY,
        valid_until=TODAY + timedelta(days=60),
        location="Quebrada km 13",
        area_type="dan_91",
    )
    plan = GeoPlan.objects.create(
        title="CG-01", cost_center=center, flight_permission=permit, created_by=author
    )
    # Una versión: es lo que hace que el plan tenga "algo colgando" y pase por la
    # pantalla de confirmación, como pasa con cualquier plan importado de verdad.
    GeoPlanVersion.objects.create(
        plan=plan, source="import", content={}, created_by=author, version_number=1
    )
    return plan


def _archive(client, plan, **data):
    return client.post(reverse("geo-plan-archive", args=[plan.pk]), data)


def test_the_screen_asks_why(plan):
    client = login_as("delete_geoplan", "view_geoplan")

    body = _archive(client, plan).content.decode()

    assert 'name="close_reason"' in body
    assert 'value="dgac_rejected"' in body
    assert 'value="internal_change"' in body


def test_confirming_without_a_reason_does_not_archive(plan):
    client = login_as("delete_geoplan", "view_geoplan")

    response = _archive(client, plan, confirm="1")

    plan.refresh_from_db()
    assert response.status_code == 200, "vuelve a la pantalla, no archiva"
    assert plan.is_active


def test_the_reason_is_stored_on_the_plan(plan):
    client = login_as("delete_geoplan", "view_geoplan")

    _archive(client, plan, confirm="1", close_reason="dgac_rejected")

    plan.refresh_from_db()
    assert not plan.is_active
    assert plan.close_reason == GeoPlan.CLOSE_DGAC_REJECTED


def test_the_two_reasons_are_counted_apart(plan, django_user_model):
    """Es el punto entero de la fila: sumar los dos daría un número inútil."""
    other = GeoPlan.objects.create(
        title="CG-02",
        cost_center=plan.cost_center,
        created_by=plan.created_by,
        is_active=False,
        close_reason=GeoPlan.CLOSE_INTERNAL_CHANGE,
    )
    client = login_as("delete_geoplan", "view_geoplan")
    _archive(client, plan, confirm="1", close_reason="dgac_rejected")

    assert GeoPlan.objects.filter(close_reason=GeoPlan.CLOSE_DGAC_REJECTED).count() == 1
    assert (
        GeoPlan.objects.filter(close_reason=GeoPlan.CLOSE_INTERNAL_CHANGE).get()
        == other
    )


def test_other_without_saying_which_is_refused(plan):
    """Un "otro" en blanco informa exactamente lo mismo que no preguntar."""
    client = login_as("delete_geoplan", "view_geoplan")

    response = _archive(client, plan, confirm="1", close_reason="other")

    plan.refresh_from_db()
    assert response.status_code == 200
    assert plan.is_active


def test_other_with_its_detail_is_accepted(plan):
    client = login_as("delete_geoplan", "view_geoplan")

    _archive(
        client,
        plan,
        confirm="1",
        close_reason="other",
        close_reason_detail="Se cargó dos veces el mismo KMZ",
    )

    plan.refresh_from_db()
    assert not plan.is_active
    assert plan.close_reason_detail == "Se cargó dos veces el mismo KMZ"


def test_the_detail_is_dropped_when_the_reason_has_a_name(plan):
    """Si la categoría ya lo dice, el detalle sólo sería ruido divergente."""
    client = login_as("delete_geoplan", "view_geoplan")

    _archive(
        client,
        plan,
        confirm="1",
        close_reason="dgac_rejected",
        close_reason_detail="algo que nadie va a leer",
    )

    plan.refresh_from_db()
    assert plan.close_reason_detail == ""


def test_the_model_refuses_other_without_detail_too():
    """La regla vale para el admin y para un import, no sólo para la pantalla."""
    plan = GeoPlan(title="X", close_reason=GeoPlan.CLOSE_OTHER)

    with pytest.raises(ValidationError) as error:
        plan.clean()

    assert "close_reason_detail" in error.value.error_dict


def test_a_plan_archived_before_this_row_has_no_reason(plan):
    """Inventarles uno haría mentir a cualquier informe que los cuente."""
    plan.is_active = False
    plan.save(update_fields=["is_active"])

    plan.refresh_from_db()
    assert plan.close_reason == ""


def test_the_reason_reaches_the_audit_of_the_permit_closed_with_it(plan):
    client = login_as("delete_geoplan", "delete_flightpermission", "view_geoplan")

    _archive(
        client,
        plan,
        confirm="1",
        close_reason="dgac_rejected",
        archive_permission=str(plan.flight_permission_id),
    )

    event = AuditEvent.objects.get(
        object_id=str(plan.flight_permission_id), action="archived"
    )
    assert event.metadata["close_reason"] == "dgac_rejected"
