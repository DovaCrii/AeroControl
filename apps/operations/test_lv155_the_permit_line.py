"""LV-155: la línea del permiso es solicitado → aprobado → caducado → archivado.

Textual del usuario, mirando `JEJ-2026-003` en producción: *"no entiendo esto
que aparece completado"*, y la regla: *"completado no debe salir luego de
aprobado; es caducado y final se archiva, o se deja en el filtro con vuelos ya
terminado el período y listo, esa es la línea"*.

Revierte la mitad de `LV-83` que distinguía completado de caducado, y lo hace
como paso 1 de un retiro (`LV-78`, `LV-103`): **fuera de la pantalla, nada se
borra**. El valor sigue en `STATUS_CHOICES` porque hay filas que lo tienen y el
filtro del listado tiene que poder encontrarlas; la vista, su URL y su compuerta
del PDF siguen enteras. Sin migración de datos.

El caso que este archivo protege y que es fácil de arruinar: un permiso legado
en `completed` no puede quedar con la ficha diciendo que no ha empezado.
"""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.core.testing import login_as
from apps.operations.models import FlightPermission
from apps.registry.models import CostCenter

TODAY = timezone.localdate()


def _permission(status="approved", **kwargs):
    return FlightPermission.objects.create(
        cost_center=CostCenter.objects.create(code="CC738", name="MLP"),
        purpose="photogrammetry",
        area_type="unpopulated",
        status=status,
        permission_number=kwargs.pop("permission_number", "6405"),
        valid_from=TODAY,
        valid_until=TODAY + timedelta(days=30),
        **kwargs,
    )


@pytest.mark.django_db
class TestTheApprovedPermitHasNoNextButton:
    def test_an_approved_permit_offers_no_status_action(self):
        permission = _permission()
        client = login_as("view_flightpermission", "change_flightpermission")

        response = client.get(reverse("permission-detail", args=[permission.pk]))

        assert response.context["status_actions"] == []

    def test_a_requested_permit_still_offers_approve_and_deny(self):
        # El retiro es de "Completar", no del flujo: aprobar y denegar siguen.
        permission = _permission(status="requested")
        client = login_as("view_flightpermission", "change_flightpermission")

        response = client.get(reverse("permission-detail", args=[permission.pk]))
        labels = [str(label) for label, _url in response.context["status_actions"]]

        assert len(labels) == 2

    def test_the_complete_url_is_still_alive(self):
        # Paso 1 del retiro: fuera de la pantalla, no del código. Revertir tiene
        # que costar descomentar, no volver a escribir la vista.
        permission = _permission()
        client = login_as("view_flightpermission", "change_flightpermission")

        response = client.post(reverse("permission-complete", args=[permission.pk]))

        assert response.status_code in (302, 403)


@pytest.mark.django_db
class TestTheStepperTellsTheTruth:
    def test_the_flow_is_requested_then_approved(self):
        assert FlightPermission.STATUS_FLOW == ["requested", "approved"]

    def test_an_approved_permit_is_at_the_last_step(self):
        steps = _permission().status_steps()

        assert [step["state"] for step in steps] == ["done", "current"]

    def test_an_expired_permit_shows_where_it_stopped(self):
        permission = _permission(status="expired")

        steps = permission.status_steps()

        assert steps[-1]["code"] == "expired"
        assert steps[-1]["state"] == "blocked"

    def test_a_legacy_completed_permit_does_not_look_like_it_never_started(self):
        # El caso que se arruina solo: al salir `completed` del flujo, si no
        # entrara en STATUS_BLOCKED `status_steps_for` dibujaría todos los pasos
        # en "pendiente" -- la ficha diría que un permiso terminado no ha
        # empezado.
        permission = _permission(status="completed")

        steps = permission.status_steps()

        assert [step["state"] for step in steps][:1] == ["done"]
        assert steps[-1]["code"] == "completed"
        assert steps[-1]["state"] == "blocked"


@pytest.mark.django_db
class TestTheFilterStillFindsThem:
    def test_completed_is_still_a_status_the_list_can_filter_by(self):
        # "o se deja en el filtro con vuelos ya terminado el período": las filas
        # que ya están completadas tienen que seguir siendo encontrables.
        codes = {code for code, _label in FlightPermission.STATUS_CHOICES}

        assert "completed" in codes

    def test_filtering_by_completed_returns_the_legacy_row(self):
        permission = _permission(status="completed")
        client = login_as("view_flightpermission")

        response = client.get(reverse("permission-list"), {"status": "completed"})

        assert permission in response.context["objects"]
