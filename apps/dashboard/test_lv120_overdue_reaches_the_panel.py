"""LV-120: el panel muestra lo vencido, no sólo lo por vencer.

Reportado por el usuario con captura el 2026-08-20: la tarjeta decía "5
faltantes o vencidos" y la lista de al lado, titulada *Próximos vencimientos*,
mostraba únicamente los dos del 2026-09-05. `RPA-5534` (vencido el 08-08) y
`RPA-2198` (el 05-20, tres meses atrás) no salían en ninguna parte del panel,
aunque sus alertas sí estaban en la bandeja.

Causa: las cinco consultas de `upcoming_expirations` filtraban
`expiry >= today`, así que **la rama `overdue` de la plantilla —escrita
completa, en rojo y en negrita— no podía dibujarse jamás**.

El piso no fue un descuido: lo puso un comentario que decía que sin él la lista
mostraba todas las habilitaciones históricamente vencidas en una página que se
abre en cada login. Lo que acota ahora es la misma regla que el motor de
alertas —el estado terminal del registro—, así que el panel y la bandeja no
pueden discrepar por construcción.
"""

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.dashboard.views import upcoming_expirations
from apps.operations.models import FlightPermission
from apps.registry.models import Aircraft, CostCenter, Operator, Qualification
from apps.registry.models import QualificationType

TODAY = timezone.localdate()
CUTOFF = TODAY + timedelta(days=30)


@pytest.fixture
def cost_center(db):
    return CostCenter.objects.create(code="CC1", name="One")


def _aircraft(cost_center, registration, expiry, status="active"):
    return Aircraft.objects.create(
        registration=registration,
        serial_number=f"SN-{registration}",
        cost_center=cost_center,
        insurance_expiry=expiry,
        insurance_status="active" if expiry >= TODAY else "missing",
        status=status,
    )


class TestWhatWasMissing:
    @pytest.mark.django_db
    def test_a_lapsed_insurance_reaches_the_panel(self, cost_center):
        """El caso exacto de la captura: `RPA-5534`, vencido hace 12 días."""
        _aircraft(cost_center, "RPA-5534", TODAY - timedelta(days=12))

        items = upcoming_expirations(TODAY, CUTOFF)

        assert [item["label"] for item in items] == ["RPA-5534"]
        assert items[0]["bucket"] == "overdue"

    @pytest.mark.django_db
    def test_three_months_late_still_counts(self, cost_center):
        """`RPA-2198` venció el 2026-05-20. Una ventana hacia atrás elegida a
        dedo lo habría dejado fuera justo por ser el peor caso de la flota."""
        _aircraft(cost_center, "RPA-2198", TODAY - timedelta(days=92))

        assert len(upcoming_expirations(TODAY, CUTOFF)) == 1

    @pytest.mark.django_db
    def test_the_worst_comes_first(self, cost_center):
        """Lo más atrasado arriba: es el orden en que hay que trabajarlo, y el
        que sobrevive al recorte de diez filas del panel."""
        _aircraft(cost_center, "RPA-4436", TODAY + timedelta(days=16))
        _aircraft(cost_center, "RPA-5534", TODAY - timedelta(days=12))
        _aircraft(cost_center, "RPA-2198", TODAY - timedelta(days=92))

        labels = [item["label"] for item in upcoming_expirations(TODAY, CUTOFF)]

        assert labels == ["RPA-2198", "RPA-5534", "RPA-4436"]


class TestWhatBoundsItNow:
    @pytest.mark.django_db
    def test_a_retired_aircraft_does_not_come_back(self, cost_center):
        """La misma exclusión que `generate_alerts` (`LV-90`/`LV-113`): sin
        ella, una aeronave dada de baja con el seguro vencido en 2024 se
        quedaría en el panel para siempre, que es el ruido histórico que el
        piso en `today` intentaba evitar."""
        _aircraft(cost_center, "RPA-0001", TODAY - timedelta(days=700), "retired")

        assert upcoming_expirations(TODAY, CUTOFF) == []

    @pytest.mark.django_db
    def test_a_closed_permit_does_not_come_back(self, cost_center):
        """Al caducar, un permiso queda en `expired`, que es terminal
        (`LV-83`). Antes lo tapaba el piso en la fecha; ahora lo tapa su estado,
        que es la razón correcta."""
        FlightPermission.objects.create(
            internal_folio="JEJ-2026-001",
            cost_center=cost_center,
            valid_from=TODAY - timedelta(days=40),
            valid_until=TODAY - timedelta(days=10),
            status=FlightPermission.STATUS_EXPIRED,
        )

        assert upcoming_expirations(TODAY, CUTOFF) == []

    @pytest.mark.django_db
    def test_an_open_permit_past_its_date_still_shows(self, cost_center):
        """El contrapeso del test de arriba: un permiso que venció y que nadie
        cerró es exactamente lo que el panel tiene que mostrar. Sin él, la
        exclusión por estado podría endurecerse hasta esconderlo todo."""
        FlightPermission.objects.create(
            internal_folio="JEJ-2026-002",
            cost_center=cost_center,
            valid_from=TODAY - timedelta(days=40),
            valid_until=TODAY - timedelta(days=10),
            status=FlightPermission.STATUS_APPROVED,
        )

        assert [item["label"] for item in upcoming_expirations(TODAY, CUTOFF)] == [
            "JEJ-2026-002"
        ]

    @pytest.mark.django_db
    def test_an_archived_operator_is_still_out(self, cost_center):
        """`is_active` ya filtraba, y sigue haciéndolo: quitar el piso de fecha
        no puede abrir la puerta al padrón archivado."""
        qtype = QualificationType.objects.create(code="mavic", name="Serie Mavic")
        operator = Operator.objects.create(
            employee_id="P1",
            full_name="Archivado",
            cost_center=cost_center,
            is_active=False,
        )
        Qualification.objects.create(
            operator=operator,
            qualification_type=qtype,
            expiry_date=TODAY - timedelta(days=5),
            is_active=False,
        )

        assert upcoming_expirations(TODAY, CUTOFF) == []


class TestTheTilesStayHonest:
    @pytest.mark.django_db
    def test_overdue_is_counted_apart_from_the_30_day_tile(self, cost_center):
        """Sumar lo vencido a "Vence en 30 días" habría vuelto falsa esa
        tarjeta: es la forma de defecto que `LV-118` y `LV-119` acaban de
        corregir en la bandeja y en los correos, no una para estrenar."""
        _aircraft(cost_center, "RPA-5534", TODAY - timedelta(days=12))
        _aircraft(cost_center, "RPA-2198", TODAY - timedelta(days=92))
        _aircraft(cost_center, "RPA-4436", TODAY + timedelta(days=16))
        _aircraft(cost_center, "RPA-4401", TODAY + timedelta(days=5))
        User.objects.create_superuser("admin", "a@test.com", "password")
        client = Client()
        assert client.login(username="admin", password="password")

        response = client.get(reverse("dashboard"))

        assert response.context["overdue_count"] == 2
        assert response.context["expiring_count"] == 2

    @pytest.mark.django_db
    def test_the_overdue_tile_is_absent_when_nothing_is_overdue(self, cost_center):
        """Una tarjeta en cero que aparece todos los días enseña a no mirar la
        fila de tarjetas."""
        _aircraft(cost_center, "RPA-4436", TODAY + timedelta(days=16))
        User.objects.create_superuser("admin", "a@test.com", "password")
        client = Client()
        assert client.login(username="admin", password="password")

        response = client.get(reverse("dashboard"))

        assert response.context["overdue_count"] == 0
        assert "Vencidos" not in response.content.decode()

    @pytest.mark.django_db
    def test_the_section_no_longer_promises_only_the_future(self, cost_center):
        """Se titulaba "Próximos vencimientos" y ahora lista lo ya vencido."""
        _aircraft(cost_center, "RPA-5534", TODAY - timedelta(days=12))
        User.objects.create_superuser("admin", "a@test.com", "password")
        client = Client()
        assert client.login(username="admin", password="password")

        content = client.get(reverse("dashboard")).content.decode()

        assert "Próximos vencimientos" not in content
        assert "Vencimientos" in content
