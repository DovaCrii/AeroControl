"""LV-179: del clima del panel a donde ese clima queda registrado.

Pregunta del usuario mirando el panel: *"sumar al plan si es necesario la
temperatura acá o dejarlo de lado sólo para el plan de vuelo"*. La respuesta fue
**dejarlo de lado, porque el plan ya lo tiene**: `R8.1` muestra el pronóstico
sobre el área dibujada para el día en que empieza el permiso, y ahí se puede
archivar como evidencia (`WeatherReview`).

**Por qué un enlace y no repetir las cifras.** La tarjeta del panel se recalcula
en cada visita y no guarda nada — su propio pie lo declara: *"sólo de referencia,
no reemplaza el chequeo preoperacional"*. La ficha del plan sí guarda, y eso
importa porque **un pronóstico no es reproducible después**: preguntarle al
proveedor por una fecha pasada devuelve otra corrida del modelo, o nada. Dos
pantallas mostrando el mismo pronóstico y **una sola que deja constancia** es una
invitación a mirar la que no registra y creer que se hizo el chequeo.

Lo que estos tests sostienen:

- **El puente existe** cuando el permiso tiene un plan ligado.
- **No se dibuja cuando no lo hay.** Un botón que lleva a ninguna parte enseña a
  no apretar botones.
- **Un plan archivado no cuenta**: llevaría a una ficha retirada de la lista.
"""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.dashboard.views import _weather_plan_url
from apps.geo.models import GeoPlan
from apps.operations.models import FlightPermission
from apps.registry.models import CostCenter

TODAY = timezone.localdate()


@pytest.fixture
def permit(db):
    center = CostCenter.objects.create(code="CC1", name="Faena")
    return FlightPermission.objects.create(
        internal_folio="JEJ-2026-001",
        cost_center=center,
        purpose="survey",
        valid_from=TODAY,
        valid_until=TODAY + timedelta(days=30),
        location="Quebrada km 13",
        area_type="dan_91",
    )


def _plan(permit, author, **kwargs):
    return GeoPlan.objects.create(
        title="CG-01",
        cost_center=permit.cost_center,
        flight_permission=permit,
        created_by=author,
        **kwargs,
    )


@pytest.mark.django_db
def test_it_points_at_the_plan_of_that_permit(permit, django_user_model):
    author = django_user_model.objects.create_user("planner", password="x")
    plan = _plan(permit, author)

    assert _weather_plan_url(permit) == reverse("geo-plan-detail", args=[plan.pk])


@pytest.mark.django_db
def test_without_a_linked_plan_there_is_no_link(permit):
    """Un botón que lleva a ninguna parte enseña a no apretar botones."""
    assert _weather_plan_url(permit) is None


@pytest.mark.django_db
def test_an_archived_plan_is_not_offered(permit, django_user_model):
    """Llevaría a una ficha que se retiró de la lista a propósito."""
    author = django_user_model.objects.create_user("planner", password="x")
    _plan(permit, author, is_active=False)

    assert _weather_plan_url(permit) is None


@pytest.mark.django_db
def test_the_most_recent_plan_wins(permit, django_user_model):
    """La tarjeta es un atajo, no un índice: lleva a uno, el último."""
    author = django_user_model.objects.create_user("planner", password="x")
    _plan(permit, author)
    newest = _plan(permit, author)

    assert _weather_plan_url(permit) == reverse("geo-plan-detail", args=[newest.pk])
