"""UX-15 a UX-18: lo que cierra la fase C del plan.

Cuatro filas chicas y ninguna con modelo nuevo:

- **`UX-15`** — el pulso del día en el panel: *"N operaciones hoy · M permisos
  vigentes"*. Su criterio es literal: *"sale de datos existentes, sin modelo
  nuevo"*.
- **`UX-16`** — *"ningún dato de terceros se presenta sin marca de tiempo"*.
- **`UX-17`** — el filtro de faena, recordado.
- **`UX-18`** — el vacío de la bandeja de alertas como **buena noticia**.
"""

from datetime import time, timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.core.testing import login_as
from apps.operations.models import FlightPermission, FlightRecord
from apps.registry.models import Aircraft, CostCenter, Operator


@pytest.fixture
def centre(db):
    return CostCenter.objects.create(code="CC738", name="MLP", operates_flights=True)


def _flight(centre, when):
    permit = FlightPermission.objects.create(
        cost_center=centre,
        purpose="photogrammetry",
        status=FlightPermission.STATUS_APPROVED,
        permission_number=f"P{when:%m%d}",
        location="Sector 3",
        area_type="unpopulated",
        valid_from=when - timedelta(days=10),
        valid_until=when + timedelta(days=30),
    )
    return FlightRecord.objects.create(
        permission=permit,
        actual_date=when,
        aircraft=Aircraft.objects.create(
            registration=f"RPA-{when:%m%d}", cost_center=centre
        ),
        pilot=Operator.objects.create(full_name="Piloto", cost_center=centre),
        departure_time=time(9, 0),
        arrival_time=time(10, 0),
    )


class TestTodaysPulse:
    """`UX-15`. Es lo que distingue un panel de cumplimiento de un centro de
    operaciones: todo lo demás de esa pantalla contesta por vigencias y trabajo
    pendiente, y ninguna tarjeta decía si hoy voló alguien."""

    @pytest.mark.django_db
    def test_a_flight_today_is_counted(self, centre):
        _flight(centre, timezone.localdate())
        client = login_as("view_flightrecord", "view_flightpermission")

        body = client.get(reverse("dashboard")).content.decode()

        assert "1 operaciones hoy" in body or "1 operations today" in body

    @pytest.mark.django_db
    def test_yesterdays_flight_is_not(self, centre):
        _flight(centre, timezone.localdate() - timedelta(days=1))
        client = login_as("view_flightrecord", "view_flightpermission")

        body = client.get(reverse("dashboard")).content.decode()

        assert "0 operaciones hoy" in body or "0 operations today" in body

    @pytest.mark.django_db
    def test_it_counts_by_the_day_flown_and_not_by_the_day_logged(self, centre):
        """⚠️ La bitácora se escribe **después** del vuelo, a veces al día
        siguiente. Contar por fecha de carga diría "0 operaciones hoy" en una
        jornada que sí voló — el mismo error que `LV-234` acaba de dejar caro."""
        flight = _flight(centre, timezone.localdate())
        # Se carga "mañana", como pasa de verdad.
        FlightRecord.objects.filter(pk=flight.pk).update(
            created_at=timezone.now() + timedelta(days=1)
        )
        client = login_as("view_flightrecord", "view_flightpermission")

        body = client.get(reverse("dashboard")).content.decode()

        assert "1 operaciones hoy" in body or "1 operations today" in body


class TestExternalDataDeclaresItsAge:
    """`UX-16`: *"ningún dato de terceros se presenta sin marca de tiempo"*."""

    def test_the_forecast_carries_the_moment_it_was_fetched(self):
        """⚠️ Y se sella **al consultar**, no al dibujar. El pronóstico se guarda
        en caché una hora, así que uno leído a las 15:00 puede haberse traído a
        las 14:05: sellarlo en la plantilla afirmaría una frescura que no tiene.
        """
        from apps.core import weather

        parsed = weather._parse(
            {
                "daily": {
                    "time": ["2026-09-07"],
                    "wind_speed_10m_max": [12.0],
                }
            },
            "2026-09-07",
        )

        assert parsed is not None
        assert parsed["fetched_at"]

    def test_an_empty_payload_is_still_nothing(self):
        """La marca se agrega **después** de la comprobación de vacío: un
        pronóstico sin medidas sigue sin ser nada que mostrar, y sellarlo lo
        convertiría en un dato con fecha y sin contenido."""
        from apps.core import weather

        assert weather._parse({"daily": {"time": ["2026-09-07"]}}, "2026-09-07") is None

    def test_the_filter_survives_something_that_is_not_a_timestamp(self):
        """Quien lo usa está dibujando una tarjeta de contexto: un pronóstico
        raro no puede tumbar la ficha del plan."""
        from apps.core.templatetags.aero_tags import as_datetime

        assert as_datetime("no es una fecha") == "no es una fecha"
        assert as_datetime(None) is None


class TestTheCostCentreFilterIsRemembered:
    """`UX-17`. Quien trabaja una faena la vuelve a elegir en cada login, y el
    panel es la primera pantalla del día."""

    @pytest.mark.django_db
    def test_choosing_one_and_coming_back_keeps_it(self, centre):
        client = login_as("view_flightpermission")

        client.get(reverse("dashboard"), {"cost_center": str(centre.pk)})
        response = client.get(reverse("dashboard"))

        assert response.context["selected_cost_center"] == centre

    @pytest.mark.django_db
    def test_asking_for_all_of_them_forgets_it(self, centre):
        """`?cost_center=` vacío es "quitar el filtro", y tiene que borrar el
        recuerdo: si no, la única forma de volver a verlo todo sería cerrar
        sesión."""
        client = login_as("view_flightpermission")
        client.get(reverse("dashboard"), {"cost_center": str(centre.pk)})

        client.get(reverse("dashboard"), {"cost_center": ""})
        response = client.get(reverse("dashboard"))

        assert response.context["selected_cost_center"] is None

    @pytest.mark.django_db
    def test_an_archived_one_stops_being_remembered(self, centre):
        """Se recuerda la que resolvió de verdad, así que una faena archivada
        deja de recordarse sola en vez de fijar un filtro que ya no existe."""
        client = login_as("view_flightpermission")
        client.get(reverse("dashboard"), {"cost_center": str(centre.pk)})

        CostCenter.objects.filter(pk=centre.pk).update(is_active=False)
        response = client.get(reverse("dashboard"))

        assert response.context["selected_cost_center"] is None


class TestTheEmptyAlertTrayIsGoodNews:
    """`UX-18`: decía *"No alerts found."*, que se lee como si la búsqueda
    hubiera fallado — y en la pantalla que contesta *"¿hay algo que atender?"*
    ésa es exactamente la lectura equivocada."""

    @pytest.mark.django_db
    def test_no_alerts_reads_as_good_news(self, db):
        from django.utils.translation import gettext

        client = login_as("view_alert")

        body = client.get(reverse("alert-list")).content.decode()

        assert gettext("Nothing pending.") in body
        assert "No alerts found." not in body

    @pytest.mark.django_db
    def test_and_offers_the_resolved_ones(self, db):
        """Para quien venía a mirar historia y no a atender nada."""
        client = login_as("view_alert")

        body = client.get(reverse("alert-list")).content.decode()

        assert "?is_resolved=true" in body

    @pytest.mark.django_db
    def test_a_filter_that_matches_nothing_says_something_else(self, db):
        """Los dos vacíos no son el mismo hecho: con filtros puede haber mucho
        pendiente y este recorte no alcanzarlo, así que lo que corresponde
        ofrecer es quitarlos, no celebrar."""
        from django.utils.translation import gettext

        client = login_as("view_alert")

        body = client.get(reverse("alert-list"), {"q": "nada"}).content.decode()

        assert gettext("Nothing pending.") not in body
        assert gettext("Clear filters") in body
