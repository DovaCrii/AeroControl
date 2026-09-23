"""LV-246: el plan aprobado cuyo permiso ya no autoriza a volar.

Pedido del usuario mirando la lista de planificación geoespacial en producción:
*"mostrar también cuando el permiso que se cruza con el geoespacial está vencido"*.
Quince planes decían «Aprobado» en verde y la pantalla no nombraba el permiso DGAC
en ninguna parte, así que un área aprobada sobre un permiso caducado se veía lista
para volar.
"""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.geo.models import GeoPlan
from apps.operations.models import FlightPermission
from apps.registry.models import CostCenter

TODAY = timezone.localdate()


@pytest.fixture
def centre(db):
    return CostCenter.objects.create(code="CC684", name="Faena", operates_flights=True)


def _plan(centre, user, permit=None):
    return GeoPlan.objects.create(
        title="Área", cost_center=centre, created_by=user, flight_permission=permit
    )


def _permit(centre, status, valid_until):
    return FlightPermission.objects.create(
        cost_center=centre,
        purpose="photogrammetry",
        status=status,
        location="Sector",
        area_type="unpopulated",
        valid_from=valid_until - timedelta(days=60),
        valid_until=valid_until,
    )


@pytest.mark.django_db
class TestThePlanKnowsItsPermitLapsed:
    def test_a_lapsed_permit_marks_the_plan(self, centre, admin_user):
        permit = _permit(
            centre, FlightPermission.STATUS_EXPIRED, TODAY - timedelta(days=5)
        )

        assert _plan(centre, admin_user, permit).permit_has_lapsed

    def test_a_permit_in_force_does_not(self, centre, admin_user):
        permit = _permit(
            centre, FlightPermission.STATUS_APPROVED, TODAY + timedelta(days=30)
        )

        assert not _plan(centre, admin_user, permit).permit_has_lapsed

    def test_no_permit_is_not_lapsed(self, centre, admin_user):
        """Un plan que todavía no tiene papel no perdió nada: marcarlo en rojo
        enseñaría a ignorar el rojo."""
        assert not _plan(centre, admin_user).permit_has_lapsed


@pytest.mark.django_db
class TestTheScreensSayIt:
    def test_the_list_shows_the_mark(self, client, centre, admin_user):
        permit = _permit(
            centre, FlightPermission.STATUS_EXPIRED, TODAY - timedelta(days=5)
        )
        _plan(centre, admin_user, permit)
        client.force_login(admin_user)

        content = client.get(reverse("geo-plan-list")).content.decode()

        assert "⚠ Permiso vencido" in content

    def test_the_fiche_shows_it_next_to_the_folio(self, client, centre, admin_user):
        permit = _permit(
            centre, FlightPermission.STATUS_EXPIRED, TODAY - timedelta(days=5)
        )
        plan = _plan(centre, admin_user, permit)
        client.force_login(admin_user)

        content = client.get(plan.get_absolute_url()).content.decode()

        assert "⚠ Permiso vencido" in content

    def test_asking_does_not_cost_a_query_per_row(
        self, client, centre, admin_user, django_assert_max_num_queries
    ):
        """`flight_permission` entra al `select_related` de la lista: sin él, la
        pregunta de cada fila sería una consulta, y la página trae 25."""
        for index in range(8):
            permit = _permit(
                centre,
                FlightPermission.STATUS_EXPIRED,
                TODAY - timedelta(days=index + 1),
            )
            _plan(centre, admin_user, permit)
        client.force_login(admin_user)
        client.get(reverse("geo-plan-list"))

        with django_assert_max_num_queries(20) as captured:
            client.get(reverse("geo-plan-list"))

        permit_selects = [
            q["sql"]
            for q in captured.captured_queries
            if 'FROM "operations_flightpermission"' in q["sql"]
        ]
        assert not permit_selects
