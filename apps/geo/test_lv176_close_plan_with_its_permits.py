"""LV-176: cerrar el plan geoespacial junto con sus permisos, sin cascada.

Pedido del usuario: *"la planificación geoespacial poder cerrarlo en conjunto
con los permisos que están ligados"*. Se le plantearon dos formas y eligió la
recomendada: **cierre acompañado, no en cascada**. La pantalla de archivar el
plan ofrece los permisos ligados y deja marcar cuáles se cierran con él.

La diferencia no es de comodidad. Un permiso es un papel de la DGAC: cerrarlo
por arrastre le cambia el estado a un trámite que puede seguir vivo, y un cambio
de estado que nadie eligió es el que después nadie puede explicar. Es la misma
lección de `LV-173` con los intentos de la prueba.

Las propiedades que estos tests sostienen:

- **Sin marcar nada, no pasa nada.** Es lo que separa "acompañado" de "cascada".
- **Se ofrecen los permisos de los dos caminos**: el del plan y los de las
  solicitudes SIGO nacidas de él. Mirar sólo el primero dejaría fuera el plan
  multi-círculo, que es justo donde hay varios papeles.
- **El permiso de archivar permisos se comprueba en el servidor**, no sólo al
  dibujar las casillas: quien archiva planes no necesariamente puede cerrar
  papeles del Estado.
- **Cada permiso deja su propia entrada de auditoría**, en su propio registro.
"""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.core.models import AuditEvent
from apps.core.testing import login_as
from apps.geo.models import GeoPlan
from apps.operations.models import FlightPermission, FlightRequest
from apps.registry.models import CostCenter


TODAY = timezone.localdate()


def _permit(center, folio):
    return FlightPermission.objects.create(
        internal_folio=folio,
        cost_center=center,
        purpose="survey",
        valid_from=TODAY,
        valid_until=TODAY + timedelta(days=60),
        location="Quebrada km 13",
        area_type="dan_91",
    )


@pytest.fixture
def world(db, django_user_model):
    author = django_user_model.objects.create_user("planner", password="x")
    center = CostCenter.objects.create(code="CC1", name="Faena")
    permit = _permit(center, "JEJ-2026-001")
    plan = GeoPlan.objects.create(
        title="CG-01", cost_center=center, flight_permission=permit, created_by=author
    )
    return {"center": center, "permit": permit, "plan": plan}


def _archive(client, plan, **data):
    return client.post(reverse("geo-plan-archive", args=[plan.pk]), data)


def test_the_screen_offers_the_linked_permit(world):
    client = login_as("delete_geoplan", "delete_flightpermission", "view_geoplan")

    body = _archive(client, world["plan"]).content.decode()

    assert "JEJ-2026-001" in body
    assert 'name="archive_permission"' in body


def test_a_permit_of_a_request_born_from_the_plan_is_offered_too(world):
    """El caso multi-círculo: varios papeles colgando del mismo plan."""
    other = _permit(world["center"], "JEJ-2026-002")
    FlightRequest.objects.create(
        source_plan=world["plan"],
        flight_permission=other,
        cost_center=world["center"],
        center_lat=-22.5,
        center_lon=-68.9,
        radius_m=300,
    )
    client = login_as("delete_geoplan", "delete_flightpermission", "view_geoplan")

    body = _archive(client, world["plan"]).content.decode()

    assert "JEJ-2026-002" in body


def test_ticking_nothing_leaves_every_permit_open(world):
    """Es lo que separa "acompañado" de "cascada"."""
    client = login_as("delete_geoplan", "delete_flightpermission", "view_geoplan")

    _archive(client, world["plan"], confirm="1")

    world["plan"].refresh_from_db()
    world["permit"].refresh_from_db()
    assert not world["plan"].is_active
    assert world["permit"].is_active, "un permiso no se cierra por arrastre"


def test_ticking_a_permit_closes_it_with_the_plan(world):
    client = login_as("delete_geoplan", "delete_flightpermission", "view_geoplan")

    _archive(
        client,
        world["plan"],
        confirm="1",
        archive_permission=str(world["permit"].pk),
    )

    world["plan"].refresh_from_db()
    world["permit"].refresh_from_db()
    assert not world["plan"].is_active
    assert not world["permit"].is_active


def test_each_closed_permit_leaves_its_own_audit_entry(world):
    """La respuesta a "por qué se cerró" tiene que estar en el permiso."""
    client = login_as("delete_geoplan", "delete_flightpermission", "view_geoplan")

    _archive(
        client,
        world["plan"],
        confirm="1",
        archive_permission=str(world["permit"].pk),
    )

    assert AuditEvent.objects.filter(
        object_id=str(world["permit"].pk), action="archived"
    ).exists()


def test_the_plan_and_its_permits_are_recorded_as_one_act(world):
    """Comparten `request_id`: fue un solo POST, y así se puede reconstruir.

    Es la razón por la que las entradas hermanas las escribe el middleware y no
    la vista: ahí todavía no se conoce ni el `request_id` ni el código de estado.
    """
    client = login_as("delete_geoplan", "delete_flightpermission", "view_geoplan")

    _archive(
        client,
        world["plan"],
        confirm="1",
        archive_permission=str(world["permit"].pk),
    )

    events = AuditEvent.objects.filter(action="archived")
    assert events.count() == 2
    assert len({event.request_id for event in events}) == 1


def test_without_the_permit_permission_nothing_is_offered(world):
    client = login_as("delete_geoplan", "view_geoplan")

    body = _archive(client, world["plan"]).content.decode()

    assert 'name="archive_permission"' not in body


def test_without_the_permit_permission_a_forged_post_changes_nothing(world):
    """El formulario que llega no decide qué permisos puede cerrar quien envía."""
    client = login_as("delete_geoplan", "view_geoplan")

    _archive(
        client,
        world["plan"],
        confirm="1",
        archive_permission=str(world["permit"].pk),
    )

    world["plan"].refresh_from_db()
    world["permit"].refresh_from_db()
    assert not world["plan"].is_active, "el plan sí se archiva: eso sí puede"
    assert world["permit"].is_active, "el papel de la DGAC no"


def test_an_already_archived_permit_is_not_offered_again(world):
    world["permit"].is_active = False
    world["permit"].save(update_fields=["is_active"])
    client = login_as("delete_geoplan", "delete_flightpermission", "view_geoplan")

    body = _archive(client, world["plan"]).content.decode()

    assert 'name="archive_permission"' not in body
