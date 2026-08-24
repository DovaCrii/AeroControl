"""LV-135: filtrar el listado de planes, y poder archivar uno.

Dos pedidos del usuario en la misma pantalla. Primero: *"¿existe la opción de
borrar?, pero de ser así con un doble verificador para no tener problemas de pasar
a llevar"*. No existía — ni borrar ni archivar, para el plan ni para el permiso—,
así que siete borradores de una carga de prueba se quedaban a la vista para
siempre y la única salida era el admin de Django. Después: *"al momento de tener
muchas planificaciones se podría dejar también un filtro […] y ahí se prende y
apaga el filtro y se deja ver lo necesario, además si estaba archivada"*.

Las dos cosas son una: sin el filtro, un plan archivado no tendría desde dónde
restaurarse.
"""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from apps.core.testing import login_as
from apps.geo.models import GeoPlan
from apps.registry.models import CostCenter


@pytest.fixture
def cost_center(db):
    return CostCenter.objects.create(code="CC135", name="Faena Choapa")


@pytest.fixture
def other_center(db):
    return CostCenter.objects.create(code="CC999", name="Otra faena")


@pytest.fixture
def owner(db):
    """Un autor para los planes, creado **una vez**.

    `login_as()` deriva el nombre de usuario de los permisos que recibe, así que
    llamarlo sin permisos dos veces choca en la restricción de unicidad -- y el
    autor del plan no necesita cliente ni permisos, sólo existir.
    """
    return User.objects.create_user("owner-135", "owner135@test.com", "pw")  # nosec B106


def _plan(cost_center, owner, title, *, status="draft", is_active=True):
    return GeoPlan.objects.create(
        title=title,
        cost_center=cost_center,
        created_by=owner,
        status=status,
        is_active=is_active,
    )


class TestTheFilters:
    @pytest.mark.django_db
    def test_an_archived_plan_is_out_of_the_way_by_default(self, cost_center, owner):
        _plan(cost_center, owner, "PLAN-EN-USO")
        _plan(cost_center, owner, "PLAN-GUARDADO", is_active=False)

        body = login_as("view_geoplan").get(reverse("geo-plan-list")).content.decode()

        assert "PLAN-EN-USO" in body
        assert "PLAN-GUARDADO" not in body

    @pytest.mark.django_db
    def test_the_archived_filter_shows_only_those(self, cost_center, owner):
        _plan(cost_center, owner, "PLAN-EN-USO")
        _plan(cost_center, owner, "PLAN-GUARDADO", is_active=False)

        body = (
            login_as("view_geoplan")
            .get(reverse("geo-plan-list"), {"is_active": "archived"})
            .content.decode()
        )

        assert "PLAN-GUARDADO" in body
        assert "PLAN-EN-USO" not in body

    @pytest.mark.django_db
    def test_it_searches_by_title_and_by_cost_center(
        self, cost_center, other_center, owner
    ):
        _plan(cost_center, owner, "CG-01 circunferencia grande")
        _plan(other_center, owner, "Otro plan cualquiera")
        client = login_as("view_geoplan")

        por_titulo = client.get(reverse("geo-plan-list"), {"q": "CG-01"})
        por_centro = client.get(reverse("geo-plan-list"), {"q": "CC999"})

        assert "CG-01" in por_titulo.content.decode()
        assert "Otro plan" not in por_titulo.content.decode()
        assert "Otro plan" in por_centro.content.decode()

    @pytest.mark.django_db
    def test_it_filters_by_status(self, cost_center, owner):
        _plan(cost_center, owner, "Es borrador", status="draft")
        _plan(cost_center, owner, "Ya aprobado", status="approved")

        body = (
            login_as("view_geoplan")
            .get(reverse("geo-plan-list"), {"status": "approved"})
            .content.decode()
        )

        assert "Ya aprobado" in body
        assert "Es borrador" not in body


class TestArchiving:
    @pytest.mark.django_db
    def test_a_plan_with_nothing_attached_is_archived_at_once(self, cost_center, owner):
        """Sin dependientes no hay nada que mirar, y una confirmación vacía sólo
        enseña a apretar "sí" sin leer."""
        plan = _plan(cost_center, owner, "Sin nada colgando")

        response = login_as("view_geoplan", "delete_geoplan").post(
            reverse("geo-plan-archive", args=[plan.pk])
        )

        assert response.status_code == 302
        plan.refresh_from_db()
        assert plan.is_active is False

    @pytest.mark.django_db
    def test_a_plan_with_versions_asks_first_and_archives_nothing(
        self, cost_center, owner
    ):
        """El doble verificador que pidió el usuario: la primera vez responde con
        la pantalla de confirmación, no con el archivado."""
        from apps.geo.models import GeoPlanVersion

        plan = _plan(cost_center, owner, "Con versiones")
        GeoPlanVersion.objects.create(
            plan=plan,
            version_number=1,
            content={"kind": "document", "children": []},
            content_checksum="x" * 64,
            source="import",
            created_by=plan.created_by,
        )

        response = login_as("view_geoplan", "delete_geoplan").post(
            reverse("geo-plan-archive", args=[plan.pk])
        )

        assert response.status_code == 200  # la confirmación, no una redirección
        plan.refresh_from_db()
        assert plan.is_active is True

    @pytest.mark.django_db
    def test_the_confirmation_names_a_request_already_filed_in_sigo(
        self, cost_center, owner
    ):
        """Lo que hace útil a la pantalla: no dice "tiene dependientes", dice
        cuáles y cuántos ya están presentados en SIGO."""
        from decimal import Decimal

        from apps.operations.models import FlightRequest

        plan = _plan(cost_center, owner, "Con solicitud presentada")
        FlightRequest.objects.create(
            title="CG-01",
            cost_center=cost_center,
            source_plan=plan,
            center_lat=Decimal("-31.906392"),
            center_lon=Decimal("-70.717982"),
            status=FlightRequest.STATUS_FILED,
        )

        response = login_as("view_geoplan", "delete_geoplan").post(
            reverse("geo-plan-archive", args=[plan.pk])
        )

        assert response.status_code == 200
        assert response.context["dependents"]["requests"] == 1
        assert response.context["dependents"]["filed_requests"] == 1

    @pytest.mark.django_db
    def test_confirming_archives_it(self, cost_center, owner):
        from apps.geo.models import GeoPlanVersion

        plan = _plan(cost_center, owner, "Con versiones")
        GeoPlanVersion.objects.create(
            plan=plan,
            version_number=1,
            content={"kind": "document", "children": []},
            content_checksum="y" * 64,
            source="import",
            created_by=plan.created_by,
        )

        response = login_as("view_geoplan", "delete_geoplan").post(
            reverse("geo-plan-archive", args=[plan.pk]), {"confirm": "1"}
        )

        assert response.status_code == 302
        plan.refresh_from_db()
        assert plan.is_active is False

    @pytest.mark.django_db
    def test_archiving_needs_the_delete_permission(self, cost_center, owner):
        """Archivar es el borrar de este proyecto, así que cuesta el permiso de
        borrado -- mismo criterio que `RegistryArchive`."""
        plan = _plan(cost_center, owner, "Protegido")

        response = login_as("view_geoplan", "change_geoplan").post(
            reverse("geo-plan-archive", args=[plan.pk])
        )

        assert response.status_code == 403
        plan.refresh_from_db()
        assert plan.is_active is True


class TestRestoring:
    @pytest.mark.django_db
    def test_it_comes_back(self, cost_center, owner):
        plan = _plan(cost_center, owner, "PLAN-GUARDADO", is_active=False)

        response = login_as("view_geoplan", "change_geoplan").post(
            reverse("geo-plan-restore", args=[plan.pk])
        )

        assert response.status_code == 302
        plan.refresh_from_db()
        assert plan.is_active is True

    @pytest.mark.django_db
    def test_restoring_an_active_plan_is_a_404_and_not_a_silent_no_op(
        self, cost_center, owner
    ):
        plan = _plan(cost_center, owner, "PLAN-EN-USO")

        response = login_as("view_geoplan", "change_geoplan").post(
            reverse("geo-plan-restore", args=[plan.pk])
        )

        assert response.status_code == 404
