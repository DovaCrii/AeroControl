"""LV-358 (E3): la celda de espacio aéreo de la franja y el tercer renglón de la «Situación del día».

El dato es UNO (`airspace_near.airspace_near_fact`) y lo leen la franja del panel y la cabecera de «Entorno»:
cuántas zonas prohibidas, restringidas o peligrosas de la foto vigente quedan a `AIRSPACE_NEAR_KM` o menos de
una faena con permiso vigente. Se fija: permisos de cada fuente (la celda cruza dos), aislamiento entre
tenants, qué zonas y qué permisos cuentan, el techo de consultas, el ámbar de la foto vieja, hechos sin
veredicto (palabras prohibidas) y sin rojo, y que la cifra sea la misma en los dos sitios.

Zonas del KML sintético (prohibida SC-P30, restringidas SC-R41 y SC-R54, peligrosa SC-D66): una faena en
Santiago (-33.45, -70.66) tiene a P30 y R54 a menos de 10 km; una dentro de D66 tiene a D66 y R41.
"""

import re
import socket
import urllib.request
from datetime import timedelta
from pathlib import Path

import pytest
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone, translation

from apps.airspace.models import AirspaceSnapshot
from apps.core.models import OperationalTenant
from apps.core.testing import login_as as _login_as
from apps.environment import airspace_near, strip as strip_module
from apps.environment.summary import airspace_text, build_summary
from apps.environment.templatetags import environment_tags
from apps.operations.models import FlightPermission
from apps.registry.models import CostCenter

KML = (
    Path(__file__).resolve().parents[1]
    / "airspace"
    / "test_data"
    / "synthetic_airspace.kml"
)
AIR, PERMITS, WEATHER = (
    "view_airspacefeature",
    "view_flightpermission",
    "view_userweatherlocation",
)
STRIP = reverse("environment-strip")
FORBIDDEN = (
    "puede volar",
    "no puede volar",
    "apto",
    "go/no-go",
    "no-go",
    "can fly",
    "cannot fly",
    "safe to fly",
    "cleared to fly",
)
SANTIAGO_SITE = ("-33.4500", "-70.6600")  # P30 y R54 a <10 km
D66_SITE = ("-33.1900", "-70.4200")  # dentro de D66; R41 a ~7,5 km
FAR_SITE = ("-23.6500", "-70.4000")  # nada cerca
NAVAL_SITE = (
    "-33.0000",
    "-71.6000",
)  # sólo un aeródromo, una zona naval y ayudas de dibujo


@pytest.fixture(autouse=True)
def english():
    with translation.override("en"):
        yield


@pytest.fixture(autouse=True)
def quiet(settings, monkeypatch):
    """Sin pronóstico (el tiempo apagado) y sin red: la celda no necesita ninguno."""
    settings.WEATHER_ENABLED = False
    settings.GNSS_SCINTILLATION_ENABLED = True
    settings.WEATHER_DEFAULT_LABEL = ""
    settings.AIRSPACE_NEAR_KM = 10

    def refuse(*args, **kwargs):
        raise AssertionError("la celda de espacio aéreo no puede salir a la red")

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)


def login_as(*codenames, member_of=None):
    client = _login_as(*codenames, member_of=member_of)
    client.defaults["HTTP_ACCEPT_LANGUAGE"] = "en"
    return client


@pytest.fixture
def snapshot(db):
    call_command("import_airspace_zones", "--file", str(KML), verbosity=0)
    return AirspaceSnapshot.objects.get(is_current=True)


@pytest.fixture
def tenants(db):
    return (
        OperationalTenant.objects.create(name="Mi empresa", slug="mi-empresa"),
        OperationalTenant.objects.create(name="Otra empresa", slug="otra-empresa"),
    )


def site(tenant, code, coords, status=FlightPermission.STATUS_APPROVED, **extra):
    """Una faena con un permiso (vigente por omisión) puesto en `coords`."""
    today = timezone.localdate()
    lat, lon = coords
    center = CostCenter.objects.create(tenant=tenant, code=code, name=code)
    data = {
        "internal_folio": f"F-{code}",
        "cost_center": center,
        "purpose": "patrol",
        "valid_from": today - timedelta(days=2),
        "valid_until": today + timedelta(days=20),
        "location": "x",
        "area_type": "unpopulated",
        "status": status,
        "latitude": lat,
        "longitude": lon,
    }
    data.update(extra)
    return FlightPermission.objects.create(**data)


def fact_for(user, **kwargs):
    return airspace_near.airspace_near_fact(user, **kwargs)


@pytest.mark.django_db
class TestTheFact:
    def test_a_site_in_santiago_has_two_zones_near(self, snapshot, tenants):
        site(tenants[0], "CC-A", SANTIAGO_SITE)
        fact = fact_for(login_as(AIR, PERMITS, member_of=tenants[0]).user)
        assert (fact["state"], fact["count"], fact["sites"]) == ("ok", 2, 1)
        assert fact["km"] == 10 and fact["stale"] is False

    def test_a_site_inside_a_danger_zone_counts_it_and_the_point_zone(
        self, snapshot, tenants
    ):
        site(tenants[0], "CC-A", D66_SITE)
        fact = fact_for(login_as(AIR, PERMITS, member_of=tenants[0]).user)
        assert fact["count"] == 2  # SC-D66 (dentro) y SC-R41 (punto a ~7,5 km)

    def test_a_far_site_has_none(self, snapshot, tenants):
        site(tenants[0], "CC-A", FAR_SITE)
        fact = fact_for(login_as(AIR, PERMITS, member_of=tenants[0]).user)
        assert (fact["count"], fact["sites"]) == (0, 1)

    def test_aerodromes_naval_zones_and_drawing_aids_do_not_count(
        self, snapshot, tenants
    ):
        site(tenants[0], "CC-A", NAVAL_SITE)
        fact = fact_for(login_as(AIR, PERMITS, member_of=tenants[0]).user)
        assert fact["count"] == 0

    def test_a_zone_near_two_sites_counts_once(self, snapshot, tenants):
        site(tenants[0], "CC-A", SANTIAGO_SITE)
        site(tenants[0], "CC-B", ("-33.4600", "-70.6500"))
        fact = fact_for(login_as(AIR, PERMITS, member_of=tenants[0]).user)
        assert (fact["count"], fact["sites"]) == (2, 2)

    def test_the_near_distance_is_the_setting(self, snapshot, tenants, settings):
        site(tenants[0], "CC-A", SANTIAGO_SITE)
        user = login_as(AIR, PERMITS, member_of=tenants[0]).user
        settings.AIRSPACE_NEAR_KM = 1
        assert fact_for(user)["count"] == 0
        settings.AIRSPACE_NEAR_KM = 50
        assert fact_for(user)["count"] == 4

    def test_the_circle_of_the_permit_widens_the_reach(self, snapshot, tenants):
        site(tenants[0], "CC-A", SANTIAGO_SITE, radius_km="30.00")
        user = login_as(AIR, PERMITS, member_of=tenants[0]).user
        assert fact_for(user)["count"] == 4  # 10 + 30 km alcanza a D66 y a R41

    def test_only_approved_permits_in_force_today_make_a_site(self, snapshot, tenants):
        today = timezone.localdate()
        site(tenants[0], "CC-REQ", SANTIAGO_SITE, FlightPermission.STATUS_REQUESTED)
        site(tenants[0], "CC-OLD", SANTIAGO_SITE, valid_until=today - timedelta(days=1))
        site(
            tenants[0],
            "CC-FUT",
            SANTIAGO_SITE,
            valid_from=today + timedelta(days=1),
            valid_until=today + timedelta(days=9),
        )
        site(tenants[0], "CC-OFF", SANTIAGO_SITE, is_active=False)
        fact = fact_for(login_as(AIR, PERMITS, member_of=tenants[0]).user)
        assert (fact["sites"], fact["count"]) == (0, 0)

    def test_a_permit_without_a_point_falls_back_to_its_cost_centre(
        self, snapshot, tenants
    ):
        permit = site(tenants[0], "CC-A", (None, None))
        center = permit.cost_center
        center.latitude, center.longitude = SANTIAGO_SITE
        center.save()
        fact = fact_for(login_as(AIR, PERMITS, member_of=tenants[0]).user)
        assert (fact["sites"], fact["count"]) == (1, 2)

    def test_a_permit_with_no_coordinates_anywhere_makes_no_site(
        self, snapshot, tenants
    ):
        site(tenants[0], "CC-A", (None, None))
        assert fact_for(login_as(AIR, PERMITS, member_of=tenants[0]).user)["sites"] == 0

    def test_another_tenants_site_is_never_measured(self, snapshot, tenants):
        site(tenants[0], "CC-A", FAR_SITE)
        site(tenants[1], "CC-B", SANTIAGO_SITE)  # del otro tenant: no debe contar
        mine = fact_for(login_as(AIR, PERMITS, member_of=tenants[0]).user)
        theirs = fact_for(
            login_as(AIR, PERMITS, "view_aircraft", member_of=tenants[1]).user
        )
        assert (mine["sites"], mine["count"]) == (1, 0)
        assert (theirs["sites"], theirs["count"]) == (1, 2)

    def test_a_superuser_measures_every_tenant(self, snapshot, tenants):
        site(tenants[0], "CC-A", FAR_SITE)
        site(tenants[1], "CC-B", SANTIAGO_SITE)
        client = login_as(AIR, PERMITS)
        client.user.is_superuser = True
        client.user.save()
        fact = fact_for(client.user)
        assert (fact["sites"], fact["count"]) == (2, 2)

    def test_without_a_snapshot_it_says_so(self, tenants):
        assert fact_for(login_as(AIR, PERMITS, member_of=tenants[0]).user) == {
            "state": "nosnapshot"
        }

    def test_the_photo_older_than_30_days_is_stale(self, snapshot, tenants):
        site(tenants[0], "CC-A", SANTIAGO_SITE)
        AirspaceSnapshot.objects.filter(pk=snapshot.pk).update(
            fetched_at=timezone.now() - timedelta(days=45)
        )
        fact = fact_for(login_as(AIR, PERMITS, member_of=tenants[0]).user)
        assert fact["stale"] is True and fact["age_days"] >= 45

    @pytest.mark.parametrize("codes", [(), (AIR,), (PERMITS,), (WEATHER,)])
    def test_it_needs_both_permissions(self, snapshot, tenants, codes):
        site(tenants[0], "CC-A", SANTIAGO_SITE)
        assert fact_for(login_as(*codes, member_of=tenants[0]).user) is None

    def test_it_runs_three_queries_however_many_sites_there_are(
        self, snapshot, tenants, django_assert_num_queries
    ):
        for index in range(6):
            site(tenants[0], f"CC-{index}", SANTIAGO_SITE)
        user = login_as(AIR, PERMITS, member_of=tenants[0]).user
        fact_for(user)  # calienta cachés de proceso (permisos del usuario)
        user = type(user).objects.get(
            pk=user.pk
        )  # permisos frescos: se cuentan los suyos
        user.has_perm(f"airspace.{AIR}")
        user.has_perm(f"operations.{PERMITS}")
        # La foto, el tenant del usuario, los permisos y las zonas: cuatro, y no una por faena.
        with django_assert_num_queries(4):
            fact_for(user)


@pytest.mark.django_db
class TestTheSingleFunction:
    def test_the_header_line_and_the_strip_cell_are_the_same_text(
        self, snapshot, tenants
    ):
        site(tenants[0], "CC-A", SANTIAGO_SITE)
        client = login_as(AIR, PERMITS, WEATHER, member_of=tenants[0])
        context = strip_module.strip_context(client.user)
        cell = context["airspace"]["line"]
        fact = fact_for(client.user)
        assert cell.text == airspace_text(fact)
        summary = build_summary(timezone.now(), None, [], "", airspace=fact)
        assert summary.airspace_line.text == cell.text
        assert summary.lines[-1] is summary.airspace_line

    def test_both_places_show_the_figure_and_the_photo_date(self, snapshot, tenants):
        site(tenants[0], "CC-A", SANTIAGO_SITE)
        client = login_as(AIR, PERMITS, WEATHER, member_of=tenants[0])
        date = timezone.localtime(snapshot.fetched_at).strftime("%d-%m")
        expected = (
            f"2 zones at ≤10 km from sites with a current permit · snapshot of {date}"
        )
        cell = client.get(STRIP).content.decode()
        header = client.get(reverse("environment-gnss")).content.decode()
        assert cell.count(expected) == 1
        assert header.count(expected) == 1

    def test_the_cell_links_to_the_map_and_names_itself(self, snapshot, tenants):
        site(tenants[0], "CC-A", SANTIAGO_SITE)
        html = login_as(AIR, PERMITS, member_of=tenants[0]).get(STRIP).content.decode()
        cell = html.split("env-cell--airspace")[1].split("</div>")[0]
        assert 'href="/environment/airspace/"' in cell and ">Airspace</h3>" in cell
        assert "Open the map" in cell
        assert "env-lvl--info" in cell

    def test_a_single_zone_uses_the_singular(self, snapshot, tenants):
        site(tenants[0], "CC-A", NAVAL_SITE)
        site(
            tenants[0], "CC-B", ("-33.6000", "-70.7000")
        )  # sólo R54 queda a menos de 10 km
        fact = fact_for(login_as(AIR, PERMITS, member_of=tenants[0]).user)
        assert fact["count"] == 1
        assert airspace_text(fact).startswith("1 zone at ≤10 km")

    def test_no_sites_is_said_as_a_fact(self, snapshot, tenants):
        fact = fact_for(login_as(AIR, PERMITS, member_of=tenants[0]).user)
        assert airspace_text(fact).startswith(
            "No sites with a current permit and coordinates to compare"
        )

    def test_without_a_snapshot_the_cell_still_draws_and_says_so(self, tenants):
        html = login_as(AIR, PERMITS, member_of=tenants[0]).get(STRIP).content.decode()
        assert "No airspace snapshot has been imported yet" in html

    def test_the_spanish_line_is_translated(self, snapshot, tenants):
        site(tenants[0], "CC-A", SANTIAGO_SITE)
        fact = fact_for(login_as(AIR, PERMITS, member_of=tenants[0]).user)
        with translation.override("es"):
            text = airspace_text(fact)
        assert text.startswith(
            "2 zonas a ≤10 km de faenas con permiso vigente · foto del "
        )
        with translation.override("es"):
            assert airspace_text({"state": "nosnapshot"}) == (
                "Aún no se ha importado ninguna foto del espacio aéreo"
            )


@pytest.mark.django_db
class TestAmberWhenOld:
    def test_an_old_photo_is_attention_and_says_how_old(self, snapshot, tenants):
        site(tenants[0], "CC-A", SANTIAGO_SITE)
        AirspaceSnapshot.objects.filter(pk=snapshot.pk).update(
            fetched_at=timezone.now() - timedelta(days=31)
        )
        client = login_as(AIR, PERMITS, member_of=tenants[0])
        line = strip_module.strip_context(client.user)["airspace"]["line"]
        assert line.level == "attention" and line.symbol == "▲"
        assert line.text.endswith("snapshot is more than 30 days old")
        html = client.get(STRIP).content.decode()
        assert "env-lvl--attention" in html.split("env-cell--airspace")[1]

    def test_a_fresh_photo_is_info(self, snapshot, tenants):
        site(tenants[0], "CC-A", SANTIAGO_SITE)
        client = login_as(AIR, PERMITS, member_of=tenants[0])
        assert (
            strip_module.strip_context(client.user)["airspace"]["line"].level == "info"
        )

    def test_exactly_30_days_is_not_yet_old(self, snapshot, tenants):
        site(tenants[0], "CC-A", SANTIAGO_SITE)
        AirspaceSnapshot.objects.filter(pk=snapshot.pk).update(
            fetched_at=timezone.now() - timedelta(days=30, hours=1)
        )
        client = login_as(AIR, PERMITS, member_of=tenants[0])
        assert (
            strip_module.strip_context(client.user)["airspace"]["line"].level == "info"
        )


@pytest.mark.django_db
class TestFactsNotAVerdict:
    @pytest.mark.parametrize("language", ["en", "es"])
    def test_no_state_of_the_line_says_whether_a_flight_can_happen(
        self, snapshot, tenants, language
    ):
        site(tenants[0], "CC-A", SANTIAGO_SITE)
        base = fact_for(login_as(AIR, PERMITS, member_of=tenants[0]).user)
        facts = [
            base,
            {**base, "stale": True},
            {**base, "count": 1},
            {**base, "count": 0},
            {**base, "sites": 0, "count": 0},
            {"state": "nosnapshot"},
        ]
        with translation.override(language):
            for fact in facts:
                text = airspace_text(fact).lower()
                for word in FORBIDDEN:
                    assert word not in text, (language, word, text)

    def test_the_rendered_cell_and_header_never_use_the_critical_red(
        self, snapshot, tenants
    ):
        site(tenants[0], "CC-A", D66_SITE)
        AirspaceSnapshot.objects.filter(pk=snapshot.pk).update(
            fetched_at=timezone.now() - timedelta(days=90)
        )
        client = login_as(AIR, PERMITS, WEATHER, member_of=tenants[0])
        cell = client.get(STRIP).content.decode().split("env-cell--airspace")[1]
        cell = cell.split("</div>")[0]
        header = client.get(reverse("environment-gnss")).content.decode()
        lines = header.split('class="env-lines"')[1].split("</ul>")[0]
        assert "snapshot of" in cell and "snapshot of" in lines
        for part in (cell, lines):
            assert "env-lvl--strong" not in part
            assert not re.search(r"critical|danger|\bred\b", part, re.I)

    def test_the_line_is_never_a_strong_level(self, snapshot, tenants):
        site(tenants[0], "CC-A", D66_SITE)
        base = fact_for(login_as(AIR, PERMITS, member_of=tenants[0]).user)
        for fact in (
            base,
            {**base, "stale": True},
            {**base, "count": 0},
            {"state": "nosnapshot"},
        ):
            summary = build_summary(timezone.now(), None, [], "", airspace=fact)
            assert summary.airspace_line.level in ("info", "attention")


@pytest.mark.django_db
class TestThePermissionsOfTheCell:
    def test_each_cell_is_listed_only_with_the_permission_of_its_source(
        self, snapshot, settings
    ):
        settings.WEATHER_ENABLED = True
        both = login_as(AIR, PERMITS, WEATHER).user
        assert strip_module.cells_for(both) == ["weather", "gnss", "airspace"]
        for codes, expected in (
            ((WEATHER,), ["weather", "gnss"]),
            ((AIR,), []),
            ((PERMITS,), []),
            ((AIR, PERMITS), ["airspace"]),
        ):
            user = login_as(*codes).user
            assert strip_module.cells_for(user) == expected, codes

    def test_a_person_with_only_the_airspace_pair_still_gets_the_strip(
        self, snapshot, tenants
    ):
        client = login_as(AIR, PERMITS, member_of=tenants[0])
        assert client.get(STRIP).status_code == 200
        request = type("R", (), {"user": client.user})()
        assert environment_tags.environment_strip_enabled({"request": request}) is True

    def test_airspace_permission_alone_gets_403_from_the_strip(self, snapshot):
        assert login_as(AIR).get(STRIP).status_code == 403
        assert login_as(PERMITS).get(STRIP).status_code == 403

    def test_the_weather_person_does_not_see_the_airspace_cell(self, snapshot, tenants):
        html = login_as(WEATHER, member_of=tenants[0]).get(STRIP).content.decode()
        assert "env-cell--airspace" not in html and "Airspace" not in html

    def test_the_cell_does_not_reveal_another_tenants_sites(self, snapshot, tenants):
        site(tenants[1], "CC-B", SANTIAGO_SITE)
        html = login_as(AIR, PERMITS, member_of=tenants[0]).get(STRIP).content.decode()
        assert "No sites with a current permit and coordinates to compare" in html
        assert "CC-B" not in html


@pytest.mark.django_db
class TestTheCostOfTheStrip:
    def test_the_strip_with_the_airspace_cell_keeps_its_ceiling(
        self, snapshot, tenants, django_assert_num_queries
    ):
        # El techo propio de la franja (`STRIP_QUERY_BUDGET` = 13, en test_lv358_strip) se midió con la celda
        # de espacio aéreo: cuatro consultas más que la franja sin ella, y ninguna por faena (hay cinco).
        from apps.environment.test_lv358_strip import STRIP_QUERY_BUDGET

        for index in range(5):
            site(tenants[0], f"CC-{index}", SANTIAGO_SITE)
        client = login_as(AIR, PERMITS, WEATHER, member_of=tenants[0])
        client.get(STRIP)  # calienta cachés de proceso
        with django_assert_num_queries(STRIP_QUERY_BUDGET):
            assert client.get(STRIP).status_code == 200

    def test_the_panel_budget_is_untouched(self):
        from apps.dashboard import test_lv237_panel_query_budget as budget

        assert (budget.PANEL_QUERY_BUDGET, budget.PANEL_FILTERED_QUERY_BUDGET) == (
            49,
            50,
        )

    def test_building_the_panel_does_not_run_the_airspace_queries(
        self, snapshot, tenants
    ):
        # La franja se pide aparte (htmx): armar el panel no cruza zonas ni permisos.
        site(tenants[0], "CC-A", SANTIAGO_SITE)
        client = login_as(AIR, PERMITS, WEATHER, member_of=tenants[0])
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        client.get(reverse("dashboard"))
        with CaptureQueriesContext(connection) as queries:
            client.get(reverse("dashboard"))
        sql = " ".join(q["sql"] for q in queries)
        assert "airspace_airspacefeature" not in sql
        assert "airspace_airspacesnapshot" not in sql
