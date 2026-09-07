"""UX-13: la bandeja de trabajo, todo lo pendiente en una lista.

Del plan: *"vista unificada sobre alertas, no conformidades, mantención por
definir, permisos esperando respuesta y entregables sin liberar, con dueño,
severidad y acción en la fila"*.

⚠️ **Su criterio es una restricción, no un adorno:** *"resolver desde la bandeja
produce exactamente la misma evidencia ISO 10.2 que resolver desde la lista de
alertas — es la misma vista, no un segundo camino"*. El primer test de este
archivo es el que lo fija.
"""

import pytest
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.utils import timezone

from apps.compliance.models import Alert, AlertRule, Deliverable, NonConformity
from apps.core.testing import login_as
from apps.core.tray import pending_for
from apps.operations.models import FlightPermission
from apps.registry.models import Aircraft, CostCenter

TRAY = "work-tray"


@pytest.fixture
def centre(db):
    return CostCenter.objects.create(code="CC738", name="MLP", operates_flights=True)


@pytest.fixture
def rule(db):
    return AlertRule.objects.create(
        name="Seguro por vencer",
        entity_type="aircraft",
        field_to_watch="insurance_expiry",
        days_before_expiry=30,
    )


def _alert(rule, centre, registration="RPA-4025"):
    aircraft = Aircraft.objects.create(registration=registration, cost_center=centre)
    return Alert.objects.create(
        alert_rule=rule,
        content_type=ContentType.objects.get_for_model(Aircraft),
        object_id=aircraft.pk,
        message="Seguro por vencer",
    )


class TestItIsNotASecondPathToResolve:
    """El criterio de la fila, y lo único que no se puede negociar.

    Un segundo camino para resolver sería un segundo lugar donde registrar —o no
    registrar— la causa raíz, y ahí la evidencia ISO 10.2 no se pierde de golpe
    sino en la mitad de los casos.
    """

    def test_the_tray_module_never_writes(self):
        """Se fija sobre el código y no sobre el render: lo que importa es que
        este módulo no pueda resolver, no que hoy no haya un botón."""
        from pathlib import Path

        from django.conf import settings

        source = (Path(settings.BASE_DIR) / "apps" / "core" / "tray.py").read_text(
            encoding="utf-8"
        )

        for forbidden in (".save(", ".update(", ".delete(", ".resolve("):
            assert forbidden not in source

    @pytest.mark.django_db
    def test_every_row_links_to_an_existing_screen(self, rule, centre):
        _alert(rule, centre)
        client = login_as("view_alert")

        rows = pending_for(client.user)

        assert rows
        assert all(row["url"] for row in rows)


class TestWhatItGathers:
    @pytest.mark.django_db
    def test_an_open_alert(self, rule, centre):
        _alert(rule, centre)
        client = login_as("view_alert")

        assert [row["source"] for row in pending_for(client.user)] == ["alert"]

    @pytest.mark.django_db
    def test_a_resolved_alert_is_not_pending(self, rule, centre):
        alert = _alert(rule, centre)
        alert.is_resolved = True
        alert.save(update_fields=["is_resolved"])
        client = login_as("view_alert")

        assert pending_for(client.user) == []

    @pytest.mark.django_db
    def test_an_open_finding(self, db, centre):
        NonConformity.objects.create(
            title="Re-vuelo",
            source=NonConformity.SOURCE_REFLIGHT,
            cost_center=centre,
            detected_on=timezone.localdate(),
            description="x",
        )
        client = login_as("view_nonconformity")

        assert [row["source"] for row in pending_for(client.user)] == ["nonconformity"]

    @pytest.mark.django_db
    def test_a_permit_awaiting_the_dgac(self, db, centre):
        FlightPermission.objects.create(
            cost_center=centre,
            purpose="photogrammetry",
            status=FlightPermission.STATUS_REQUESTED,
            location="Sector 3",
            area_type="unpopulated",
        )
        client = login_as("view_flightpermission")

        assert [row["source"] for row in pending_for(client.user)] == ["permit"]

    @pytest.mark.django_db
    def test_an_approved_permit_is_not_pending(self, db, centre):
        """Un permiso aprobado no espera a nadie: ya resolvió la DGAC."""
        FlightPermission.objects.create(
            cost_center=centre,
            purpose="photogrammetry",
            status=FlightPermission.STATUS_APPROVED,
            permission_number="6551",
            location="Sector 3",
            area_type="unpopulated",
        )
        client = login_as("view_flightpermission")

        assert pending_for(client.user) == []

    @pytest.mark.django_db
    def test_a_deliverable_not_released(self, db, centre):
        Deliverable.objects.create(
            title="Levantamiento agosto", cost_center=centre, status="validated"
        )
        client = login_as("view_deliverable")

        assert [row["source"] for row in pending_for(client.user)] == ["deliverable"]

    @pytest.mark.django_db
    def test_a_released_one_is_not(self, db, centre):
        Deliverable.objects.create(
            title="Ya liberado", cost_center=centre, status="released"
        )
        client = login_as("view_deliverable")

        assert pending_for(client.user) == []


class TestEachSourceIsGatedOnItsOwnPermission:
    """⚠️ La bandeja cruza cuatro aplicaciones. Sin esto le mostraría a un rol el
    nombre de faenas, aeronaves y personas que sus permisos le niegan en la
    pantalla propia de cada módulo — la lección de `LV-191`."""

    @pytest.mark.django_db
    def test_without_view_alert_no_alerts(self, rule, centre):
        _alert(rule, centre)
        client = login_as("view_nonconformity")

        assert pending_for(client.user) == []

    @pytest.mark.django_db
    def test_with_it_they_appear(self, rule, centre):
        """La otra mitad, o el anterior pasaría con una bandeja siempre vacía."""
        _alert(rule, centre)
        client = login_as("view_alert")

        assert pending_for(client.user)

    @pytest.mark.django_db
    def test_the_screen_needs_a_session(self, client, db):
        response = client.get(reverse(TRAY))

        assert response.status_code == 302
        assert "/accounts/login/" in response["Location"]


class TestSeverityIsNeverInvented:
    @pytest.mark.django_db
    def test_an_alert_carries_the_scale_it_already_has(self, rule, centre):
        """La misma que la píldora de la bandeja de alertas y que el digest
        diario: dos escalas para el mismo hecho es cómo dos pantallas empiezan a
        discrepar."""
        alert = _alert(rule, centre)
        # `triggering_date` es una **propiedad** que lee el valor congelado
        # (`LV-118`), no un campo: se escribe `watched_value`, que es el dato
        # que la alerta guardó al dispararse.
        alert.watched_value = (
            timezone.localdate() - timezone.timedelta(days=1)
        ).isoformat()
        alert.save(update_fields=["watched_value"])
        client = login_as("view_alert")

        assert pending_for(client.user)[0]["severity"] == "critical"

    @pytest.mark.django_db
    def test_a_permit_awaiting_carries_none(self, db, centre):
        """Esperar a la autoridad no es incumplimiento de nadie. Pintarlo
        enseñaría a ignorar el color, que es el daño que `LV-118` documentó."""
        FlightPermission.objects.create(
            cost_center=centre,
            purpose="photogrammetry",
            status=FlightPermission.STATUS_REQUESTED,
            location="Sector 3",
            area_type="unpopulated",
        )
        client = login_as("view_flightpermission")

        assert pending_for(client.user)[0]["severity"] == ""


class TestMyPendingItems:
    @pytest.mark.django_db
    def test_it_filters_by_the_person_asking(self, rule, centre):
        mine = _alert(rule, centre, "RPA-1")
        _alert(rule, centre, "RPA-2")
        client = login_as("view_alert")
        mine.assigned_to = client.user
        mine.save(update_fields=["assigned_to"])

        body = client.get(reverse(TRAY), {"owner": "me"}).content.decode()
        rows = body.split('id="table-body"')[-1]

        assert "RPA-1" in rows
        assert "RPA-2" not in rows

    @pytest.mark.django_db
    def test_unassigned_only_covers_what_can_have_an_owner(self, db, centre):
        """Un permiso esperando a la DGAC **no** está "sin asignar": es que no se
        asigna, y contarlo ahí inventaría un pendiente de gestión que no
        existe."""
        FlightPermission.objects.create(
            cost_center=centre,
            purpose="photogrammetry",
            status=FlightPermission.STATUS_REQUESTED,
            location="Sector 3",
            area_type="unpopulated",
        )
        client = login_as("view_flightpermission")

        body = client.get(reverse(TRAY), {"owner": "unassigned"}).content.decode()

        assert "Sector 3" not in body.split('id="table-body"')[-1]

    @pytest.mark.django_db
    def test_the_key_is_the_same_as_in_the_alert_list(self, rule, centre):
        """`?owner=me` en las dos pantallas: dos nombres para el mismo filtro es
        cómo alguien copia un enlace y obtiene otra cosa."""
        client = login_as("view_alert")

        assert client.get(reverse(TRAY), {"owner": "me"}).status_code == 200
        assert client.get(reverse("alert-list"), {"owner": "me"}).status_code == 200


class TestTheEmptyStateIsGoodNews:
    @pytest.mark.django_db
    def test_nothing_pending_says_so(self, db):
        """`UX-18` adelantado acá porque es la pantalla donde más importa: un "no
        results found" en la bandeja de trabajo se lee como si algo hubiera
        fallado."""
        from django.utils.translation import gettext

        client = login_as("view_alert")

        body = client.get(reverse(TRAY)).content.decode()

        assert gettext("Nothing pending.") in body
