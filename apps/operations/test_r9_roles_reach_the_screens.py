"""R9: los roles reales alcanzan las pantallas nuevas.

Este archivo existe por un defecto que casi llega a producción. `ROLE_PERMISSIONS`
es una **lista explícita** de codenames, y un modelo nuevo no entra solo: al
terminar R9 ningún rol tenía `view_flightrequest`, así que la sección nueva del
menú habría dado 403 a todo el mundo salvo al administrador — y desde afuera eso
se lee como "el despliegue falló", que es exactamente lo que `HANDOFF` advierte
sobre `bootstrap_roles`.

Los tests de las pantallas (`test_r95_...`) no lo cazaron porque conceden los
permisos **uno por uno** para aislar el comportamiento de la vista. Eso está
bien y es lo que deben hacer; lo que faltaba es la otra pregunta, que no es
sobre la vista sino sobre el despliegue: **¿el rol que la gente tiene de verdad
llega a la pantalla?** Por eso acá el usuario entra a un grupo y nada más.
"""

import pytest
from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.operations.models import FlightRequest
from apps.registry.models import CostCenter


@pytest.fixture
def roles(db):
    call_command("bootstrap_roles")


def _member_of(role):
    user = User.objects.create_user(role.lower(), f"{role}@test.com", "password")
    user.groups.add(Group.objects.get(name=role))
    client = Client()
    assert client.login(username=role.lower(), password="password")
    return client


@pytest.fixture
def flight_request(db):
    cost_center = CostCenter.objects.create(code="CC738", name="MLP")
    return FlightRequest.objects.create(
        title="Quebrada km 13.760",
        cost_center=cost_center,
        center_lat="-31.894392",
        center_lon="-70.702208",
        radius_m=30,
    )


class TestOperationsCanWork:
    @pytest.mark.django_db
    def test_it_reaches_the_list(self, roles, flight_request):
        assert (
            _member_of("Operations").get(reverse("flight-request-list")).status_code
            == 200
        )

    @pytest.mark.django_db
    def test_it_reaches_the_detail(self, roles, flight_request):
        assert (
            _member_of("Operations")
            .get(reverse("flight-request-detail", args=[flight_request.pk]))
            .status_code
            == 200
        )

    @pytest.mark.django_db
    def test_it_can_add_a_note(self, roles, flight_request):
        """`change_flightrequest` es lo que la vista exige; el permiso sobre la
        nota existe además para el admin y para que el modelo no quede sin rol.
        """
        response = _member_of("Operations").post(
            reverse("flight-request-add-note", args=[flight_request.pk]),
            {"text": "Se corrige la comuna"},
        )

        assert response.status_code == 302
        assert flight_request.change_notes.count() == 1

    @pytest.mark.django_db
    def test_it_can_file_it(self, roles, flight_request):
        _member_of("Operations").post(
            reverse("flight-request-file", args=[flight_request.pk])
        )

        flight_request.refresh_from_db()
        assert flight_request.status == FlightRequest.STATUS_FILED

    @pytest.mark.django_db
    def test_it_can_download_the_kmz_route(self, roles, flight_request):
        """Sin geometría redirige, pero **no** con 403: lo que se comprueba acá
        es que el rol alcanza la vista, no lo que la vista decide después."""
        response = _member_of("Operations").get(
            reverse("flight-request-kmz", args=[flight_request.pk])
        )

        assert response.status_code != 403


class TestTheOtherRoles:
    @pytest.mark.django_db
    def test_compliance_reads_but_does_not_write(self, roles, flight_request):
        """Lee lo que se pidió como evidencia, igual que el plan geoespacial."""
        client = _member_of("Compliance")

        assert client.get(reverse("flight-request-list")).status_code == 200
        assert (
            client.post(
                reverse("flight-request-file", args=[flight_request.pk])
            ).status_code
            == 403
        )

    @pytest.mark.django_db
    def test_viewer_reads_the_operational_record(self, roles, flight_request):
        assert (
            _member_of("Viewer").get(reverse("flight-request-list")).status_code == 200
        )

    @pytest.mark.django_db
    def test_viewer_still_gets_no_administrative_permission(self, roles):
        """El catálogo de aeródromos es configuración de referencia, no registro
        operacional: la lección que esta lista lleva escrita desde que era
        "todo codename que empiece con view_"."""
        codenames = set(
            Group.objects.get(name="Viewer").permissions.values_list(
                "codename", flat=True
            )
        )

        assert "view_flightrequest" in codenames
        assert "view_aerodrome" not in codenames
        assert all(codename.startswith("view_") for codename in codenames)

    @pytest.mark.django_db
    def test_maintenance_has_no_business_here(self, roles, flight_request):
        assert (
            _member_of("Maintenance").get(reverse("flight-request-list")).status_code
            == 403
        )


class TestTheCatalogsCanBeExtendedWithoutADeploy:
    """Las dos listas de SIGO se sabe que están incompletas — las capturas
    venían cortadas —, así que agregar el valor que falte no puede exigir un
    despliegue. Eso sólo es cierto si el rol tiene el permiso."""

    @pytest.mark.django_db
    def test_operations_can_extend_them(self, roles):
        codenames = set(
            Group.objects.get(name="Operations").permissions.values_list(
                "codename", flat=True
            )
        )

        assert {"add_workareatype", "add_flightobjective"} <= codenames

    @pytest.mark.django_db
    def test_operations_can_fill_in_an_aerodrome_position(self, roles):
        """`seed_aerodromes` deja 44 de 50 sin coordenadas a propósito; alguien
        tiene que poder completarlas desde la ficha con la carta al frente."""
        codenames = set(
            Group.objects.get(name="Operations").permissions.values_list(
                "codename", flat=True
            )
        )

        assert "change_aerodrome" in codenames


@pytest.mark.django_db
def test_every_r9_permission_the_views_demand_belongs_to_some_role(roles):
    """El guardián de la clase de defecto, no de esta instancia.

    Un modelo nuevo no entra solo en `ROLE_PERMISSIONS`, y olvidarlo falla
    **en el despliegue** y no en la suite: las pantallas siguen verdes porque
    sus tests conceden permisos a mano. Esta afirmación es la que se rompe el
    día que alguien agregue un modelo a R9 y no toque `bootstrap_roles`.
    """
    granted = set()
    for role in ("Operations", "Compliance", "Viewer", "Maintenance"):
        granted |= set(
            Group.objects.get(name=role).permissions.values_list("codename", flat=True)
        )

    required = {
        "view_flightrequest",  # lista y ficha
        "add_flightrequest",  # separar un plan
        "change_flightrequest",  # notas, pares, transiciones, vínculo
    }
    assert required <= granted, f"sin rol: {sorted(required - granted)}"


@pytest.mark.django_db
def test_a_user_with_no_group_is_refused(roles, flight_request):
    """El contrapeso: conceder de más sería tan defecto como conceder de menos.
    Sin grupo no se llega, aunque haya sesión iniciada."""
    User.objects.create_user("nobody", "nobody@test.com", "password")
    client = Client()
    assert client.login(username="nobody", password="password")

    assert client.get(reverse("flight-request-list")).status_code == 403


@pytest.mark.django_db
def test_the_deploy_step_is_idempotent(roles, flight_request):
    """`bootstrap_roles` se corre en cada despliegue con permisos nuevos; una
    segunda corrida no puede dejar a Operations sin lo que acaba de recibir."""
    call_command("bootstrap_roles")

    assert (
        _member_of("Operations").get(reverse("flight-request-list")).status_code == 200
    )


@pytest.mark.django_db
def test_filing_a_request_still_records_who(roles, flight_request):
    """Que el permiso llegue no basta: la traza tiene que decir quién, y no
    `system` -- el defecto que `LV-101` encontró en producción."""
    _member_of("Operations").post(
        reverse("flight-request-file", args=[flight_request.pk])
    )

    row = flight_request.history.get()
    assert row.changed_by == "operations"
    assert row.new_status == FlightRequest.STATUS_FILED
    # Y la fecha de presentación quedó puesta, que es lo que hace medible la
    # espera en el panel.
    flight_request.refresh_from_db()
    assert flight_request.filed_on == timezone.localdate()
