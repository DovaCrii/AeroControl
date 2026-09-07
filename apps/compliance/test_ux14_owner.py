"""UX-14: asignar un responsable, que es lo que convierte una lista en trabajo.

Del plan: *"es el patrón que AirHub ya tiene (investigador asignado) y lo que
convierte una lista en trabajo. **Criterio:** «Mis pendientes» filtra por
persona"*.

Lo que estos tests protegen:

1. **Que el responsable sea un usuario de la aplicación.** La alternativa era
   `Operator`, y con ella "Mis pendientes" habría quedado vacío justo para
   Cumplimiento, que no vuela y es quien más trabaja la bandeja.
2. **Que "sin asignar" sea visible**, porque la ausencia de dueño es el hecho que
   hay que ver.
3. **Que desasignar sea posible** sin un botón aparte.
"""

import pytest
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.utils import timezone

from apps.compliance.models import Alert, AlertRule, NonConformity
from apps.core.testing import login_as
from apps.registry.models import Aircraft, CostCenter


@pytest.fixture
def rule(db):
    return AlertRule.objects.create(
        name="Seguro por vencer",
        entity_type="aircraft",
        field_to_watch="insurance_expiry",
        days_before_expiry=30,
    )


def _alert(rule, registration="RPA-4025"):
    """Una alerta sobre una aeronave.

    La faena se reusa —`get_or_create`— porque su código es único por tenant y
    varios tests crean dos alertas: la matrícula es lo que cambia, no la faena.
    """
    centre, _made = CostCenter.objects.get_or_create(
        code="CC738", defaults={"name": "MLP"}
    )
    aircraft = Aircraft.objects.create(registration=registration, cost_center=centre)
    return Alert.objects.create(
        alert_rule=rule,
        content_type=ContentType.objects.get_for_model(Aircraft),
        object_id=aircraft.pk,
        message="Seguro por vencer",
    )


class TestTheOwnerIsAnApplicationUser:
    @pytest.mark.django_db
    def test_an_alert_can_be_assigned(self, rule):
        """⚠️ **A un `User` y no a un `Operator`, y la alternativa era real.** La
        alerta ya derivaba un operador para su tarea de seguimiento, pero esa
        pregunta es otra —*de quién es la credencial que vence*—; ésta es *quién
        se hace cargo de resolverla*, y quien resuelve es alguien con permiso
        acá."""
        alert = _alert(rule)
        client = login_as("change_alert", "view_alert")

        client.post(
            reverse("alert-assign", args=[alert.pk]),
            {"assigned_to": str(client.user.pk)},
        )

        alert.refresh_from_db()
        assert alert.assigned_to == client.user

    @pytest.mark.django_db
    def test_a_non_conformity_too_and_through_the_same_view(self, db):
        """Una sola vista para los dos, porque es la misma acción sobre el mismo
        campo: dos copias es cómo una deja de registrar la auditoría."""
        nc = NonConformity.objects.create(
            title="Re-vuelo",
            source=NonConformity.SOURCE_REFLIGHT,
            detected_on=timezone.localdate(),
            description="x",
        )
        client = login_as("change_nonconformity", "view_nonconformity")

        client.post(
            reverse("nonconformity-assign", args=[nc.pk]),
            {"assigned_to": str(client.user.pk)},
        )

        nc.refresh_from_db()
        assert nc.assigned_to == client.user

    @pytest.mark.django_db
    def test_emptying_the_field_unassigns(self, rule):
        """Vaciar **desasigna**, que es una acción legítima —alguien se va, o se
        asignó por error— y no necesita un botón aparte."""
        alert = _alert(rule)
        someone = User.objects.create_user("otro", password="x")
        alert.assigned_to = someone
        alert.save(update_fields=["assigned_to"])
        client = login_as("change_alert", "view_alert")

        client.post(reverse("alert-assign", args=[alert.pk]), {"assigned_to": ""})

        alert.refresh_from_db()
        assert alert.assigned_to is None

    @pytest.mark.django_db
    def test_it_needs_the_change_permission(self, rule):
        """Asignar modifica el registro, así que pide lo mismo que editarlo."""
        alert = _alert(rule)
        client = login_as("view_alert")

        response = client.post(
            reverse("alert-assign", args=[alert.pk]),
            {"assigned_to": str(client.user.pk)},
        )

        assert response.status_code in (302, 403)
        alert.refresh_from_db()
        assert alert.assigned_to is None

    @pytest.mark.django_db
    def test_a_deactivated_account_is_not_offered(self, rule):
        """Asignarle trabajo a alguien dado de baja deja la fila sin dueño con
        aspecto de tenerlo."""
        from apps.compliance.forms import OwnerForm

        User.objects.create_user("baja", password="x", is_active=False)

        usernames = [
            user.username for user in OwnerForm().fields["assigned_to"].queryset
        ]

        assert "baja" not in usernames


class TestMyPendingItems:
    @pytest.mark.django_db
    def test_it_filters_by_the_person_asking(self, rule):
        """El criterio literal de la fila."""
        mine, theirs = _alert(rule, "RPA-1"), _alert(rule, "RPA-2")
        client = login_as("view_alert")
        mine.assigned_to = client.user
        mine.save(update_fields=["assigned_to"])

        body = client.get(reverse("alert-list"), {"owner": "me"}).content.decode()
        rows = body.split('id="table-body"')[-1]

        assert str(mine.pk) in rows
        assert str(theirs.pk) not in rows

    @pytest.mark.django_db
    def test_unassigned_is_its_own_answer(self, rule):
        """La otra pregunta que se hace todos los días: qué no tiene dueño."""
        assigned, orphan = _alert(rule, "RPA-1"), _alert(rule, "RPA-2")
        client = login_as("view_alert")
        assigned.assigned_to = client.user
        assigned.save(update_fields=["assigned_to"])

        body = client.get(
            reverse("alert-list"), {"owner": "unassigned"}
        ).content.decode()
        rows = body.split('id="table-body"')[-1]

        assert str(orphan.pk) in rows
        assert str(assigned.pk) not in rows

    @pytest.mark.django_db
    def test_without_the_filter_both_are_there(self, rule):
        """O los dos anteriores pasarían con una lista siempre vacía."""
        mine, theirs = _alert(rule, "RPA-1"), _alert(rule, "RPA-2")
        client = login_as("view_alert")
        mine.assigned_to = client.user
        mine.save(update_fields=["assigned_to"])

        rows = (
            client.get(reverse("alert-list"))
            .content.decode()
            .split('id="table-body"')[-1]
        )

        assert str(mine.pk) in rows
        assert str(theirs.pk) in rows


class TestTheRowShowsIt:
    @pytest.mark.django_db
    def test_unassigned_says_so_instead_of_being_blank(self, rule):
        """Una celda vacía se lee como dato que no cargó, y acá la ausencia de
        dueño es el hecho que hay que ver."""
        from django.utils.translation import gettext

        _alert(rule)
        client = login_as("view_alert")

        rows = (
            client.get(reverse("alert-list"))
            .content.decode()
            .split('id="table-body"')[-1]
        )

        assert gettext("Unassigned") in rows

    @pytest.mark.django_db
    def test_the_column_can_be_sorted(self, rule):
        """Al revés que la faena: `assigned_to` es una columna de verdad, no una
        relación genérica resuelta en Python."""
        from apps.compliance.views import AlertList

        assert "owner" in AlertList.sortable_columns
