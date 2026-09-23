"""LV-252: tres defectos chicos que se veían en pantalla todos los días.

Primera tanda de la Fase 2 del plan de mejora del 2026-09-23 ("experiencia
visible"). Los tres son de la misma familia que la revisión dejó a la vista: algo
que el código afirma hacer y la pantalla no muestra.
"""

from datetime import timedelta

import pytest
from django.contrib import messages
from django.urls import reverse
from django.utils import timezone


class TestAnErrorIsRed:
    def test_the_error_tag_maps_to_the_bootstrap_class(self):
        """`messages.error` lleva la etiqueta `error`, y `base.html` la dibuja como
        `alert-{{ message.tags }}`. `alert-error` no existe en Bootstrap —la clase
        es `alert-danger`— así que los 32 mensajes de error de la app salían sin
        color."""
        from django.contrib.messages.storage.base import Message

        assert Message(messages.ERROR, "x").tags == "danger"

    @pytest.mark.django_db
    def test_a_real_error_reaches_the_page_in_red(self, client, admin_user):
        """De punta a punta, con un error que la aplicación emite de verdad:
        intentar editar la narrativa de un informe **aprobado** se rechaza con
        `messages.error`, y la página a la que redirige tiene que dibujarlo como
        `alert-danger`."""
        from datetime import date

        from apps.reporting.models import ReportRun

        run, _created = ReportRun.freeze(date(2026, 8, 1), "lv252")
        run.approve(admin_user.username)
        client.force_login(admin_user)

        response = client.post(
            reverse("monthly-report-narrative", args=[run.pk]), {}, follow=True
        )
        content = response.content.decode()

        assert 'class="alert alert-danger' in content
        assert "alert-error" not in content


@pytest.mark.django_db
class TestTheMaintenanceListDoesNotQueryPerRow:
    def test_the_aircraft_is_joined(
        self, client, admin_user, django_assert_max_num_queries
    ):
        """Cada fila dibuja su aeronave, y sin `select_related` era una consulta por
        fila. Se cargan diez registros de diez aeronaves distintas: con el N+1, la
        página costaría al menos diez consultas más que con el join."""
        from apps.maintenance.models import MaintenanceRecord
        from apps.registry.models import Aircraft

        for index in range(10):
            aircraft = Aircraft.objects.create(
                registration=f"RPA-7{index:03d}",
                type="RPA",
                model="M3",
                manufacturer="DJI",
            )
            MaintenanceRecord.objects.create(
                aircraft=aircraft,
                maintenance_type="scheduled",
                status="pending",
                description="Revisión",
            )
        client.force_login(admin_user)
        client.get(reverse("maintenance-list"))

        with django_assert_max_num_queries(30) as captured:
            client.get(reverse("maintenance-list"))

        aircraft_selects = [
            q["sql"]
            for q in captured.captured_queries
            if q["sql"].lstrip().startswith("SELECT")
            and 'FROM "registry_aircraft"' in q["sql"]
            and "INNER JOIN" not in q["sql"]
        ]
        assert len(aircraft_selects) <= 1, len(aircraft_selects)


@pytest.mark.django_db
class TestTheHiddenCountIsTheRealOne:
    def test_the_panel_says_how_many_the_cut_hides(self, client, admin_user):
        """La plantilla restaba 10 fijo. Ahora la vista cuenta lo que el corte de
        verdad esconde."""
        from apps.registry.models import Aircraft

        today = timezone.localdate()
        for index in range(13):
            Aircraft.objects.create(
                registration=f"RPA-8{index:03d}",
                type="RPA",
                model="M3",
                manufacturer="DJI",
                status="active",
                insurance_expiry=today + timedelta(days=index + 1),
            )
        client.force_login(admin_user)

        response = client.get(reverse("dashboard"))

        assert response.context["expirations_hidden"] == (
            response.context["expirations_total"] - len(response.context["expirations"])
        )
        assert response.context["expirations_hidden"] == 3
