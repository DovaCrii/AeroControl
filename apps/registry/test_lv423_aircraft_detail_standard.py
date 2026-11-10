"""LV-423: ficha y formulario de aeronave al estándar visual (PR B del diseño).

La ficha pierde la imagen duplicada de la cabecera y el «Estado» repetido, gana la faena, la
ubicación y las horas de vuelo en el héroe, una franja de disponibilidad (la regla de
«¿Puedo volar?», sin reimplementarla) y «Volver a la lista» conserva los filtros. El formulario
va en secciones: **todo campo de `AircraftForm` tiene que dibujarse** (lección de LV-211).

Las afirmaciones se acotan a su región (lección de LV-118) y comparan contra el objeto
(`aircraft_check`, `gettext`). Datos ficticios; el día se fija con `pin_today_mid_month`.
"""

import re
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils.translation import gettext

from apps.core.testing import login_as, pin_today_mid_month
from apps.operations.readiness import aircraft_check
from apps.registry.forms import AircraftForm
from apps.registry.models import Aircraft, CostCenter, Operator

LIST_URL = reverse("aircraft-list")
VIEW = "view_aircraft"


@pytest.fixture
def today(monkeypatch):
    return pin_today_mid_month(monkeypatch)


def _aircraft(today, registration="RPA-423", **extra):
    extra.setdefault("insurance_status", Aircraft.INSURANCE_STATUS_ACTIVE)
    extra.setdefault("insurance_expiry", today + timedelta(days=400))
    return Aircraft.objects.create(
        registration=registration,
        type="RPA",
        model="M3",
        manufacturer="DJI",
        serial_number=f"SN-{registration}",
        **extra,
    )


def _detail(aircraft, *perms, **params):
    return login_as(VIEW, *perms).get(
        reverse("aircraft-detail", args=[aircraft.pk]), params
    )


def _region(response):
    """Sólo la franja de disponibilidad: el resto de la ficha comparte vocabulario."""
    content = response.content.decode()
    match = re.search(
        r"<section[^>]*data-aircraft-readiness.*?</section>", content, re.S
    )
    return match.group(0) if match else ""


def _between(content, start, end):
    return content.split(start, 1)[1].split(end, 1)[0]


@pytest.mark.django_db
class TestReadinessStrip:
    def test_nothing_blocks_shows_the_ok_chip_and_the_link(self, today):
        aircraft = _aircraft(today)
        region = _region(_detail(aircraft))
        assert "id-chip id-chip--ok" in region
        assert (
            gettext("Nothing blocks this aircraft according to the records") in region
        )
        assert "can-fly-item" not in region
        assert f"{reverse('can-i-fly')}?aircraft={aircraft.pk}" in region

    def test_every_blocker_label_of_the_rule_is_in_the_strip(self, today):
        aircraft = _aircraft(today, status="damaged", insurance_expiry=None)
        blockers = aircraft_check(aircraft, today).blockers
        assert len(blockers) == 2
        region = _region(_detail(aircraft))
        for finding in blockers:
            assert str(finding.label) in region
        assert region.count("can-fly-item-blocker") == 2
        assert "id-chip--ok" not in region

    def test_a_damaged_aircraft_is_a_blocker_on_its_own(self, today):
        aircraft = _aircraft(today, status="damaged")
        region = _region(_detail(aircraft))
        assert region.count("can-fly-item-blocker") == 1
        assert gettext("Airframe status") in region
        assert "can-fly-item-warning" not in region

    def test_no_insurance_date_is_a_blocker_on_its_own(self, today):
        aircraft = _aircraft(today, insurance_expiry=None)
        region = _region(_detail(aircraft))
        assert region.count("can-fly-item-blocker") == 1
        assert gettext("JAC insurance") in region
        assert "id-chip--ok" not in region

    def test_insurance_in_ten_days_is_a_warning_not_a_blocker(self, today):
        aircraft = _aircraft(today, insurance_expiry=today + timedelta(days=10))
        region = _region(_detail(aircraft))
        assert "can-fly-item-warning" in region
        assert "can-fly-item-blocker" not in region
        assert "id-chip--ok" not in region

    def test_a_retired_aircraft_has_no_strip(self, today):
        aircraft = _aircraft(today, status="retired")
        assert _region(_detail(aircraft)) == ""

    def test_an_archived_aircraft_has_no_strip(self, today):
        aircraft = _aircraft(today, is_active=False)
        assert _region(_detail(aircraft)) == ""


@pytest.mark.django_db
class TestHeroAndTable:
    def test_status_is_not_repeated_in_the_hero_nor_the_table(self, today):
        aircraft = _aircraft(today)
        content = _detail(aircraft).content.decode()
        hero = _between(content, 'class="fleet-hero-facts"', "</dl>")
        table = _between(content, '<table class="table table-bordered">', "</table>")
        assert f"<dt>{gettext('Status')}</dt>" not in hero
        assert f">{gettext('Status')}</th>" not in table
        # La tabla ya no repite lo que dice el héroe.
        for label in ("Model", "Manufacturer", "Serial number", "Cost Center"):
            assert f">{gettext(label)}</th>" not in table

    def test_hero_has_cost_center_location_and_site(self, today):
        cc = CostCenter.objects.create(code="CC738", name="Faena Norte")
        site = CostCenter.objects.create(code="CC21", name="Faena Sur")
        aircraft = _aircraft(
            today, cost_center=cc, current_location="on_site", current_site=site
        )
        hero = _between(
            _detail(aircraft).content.decode(), 'class="fleet-hero-facts"', "</dl>"
        )
        assert 'class="cc-chip" title="CC738' in hero
        assert aircraft.get_current_location_display() in hero
        assert 'class="cc-chip" title="CC21' in hero

    def test_hero_without_cost_center_shows_the_empty_chip(self, today):
        aircraft = _aircraft(today)
        hero = _between(
            _detail(aircraft).content.decode(), 'class="fleet-hero-facts"', "</dl>"
        )
        assert "cc-chip is-empty" in hero

    def test_flight_hours_move_to_the_hero_with_permission(self, today):
        aircraft = _aircraft(today)
        with_perm = _detail(aircraft, "view_flightrecord").content.decode()
        without = _detail(aircraft).content.decode()
        hero = _between(with_perm, 'class="fleet-hero-facts"', "</dl>")
        assert f"<dt>{gettext('Flight hours')}</dt>" in hero
        assert "section-hours" not in with_perm
        assert f"<dt>{gettext('Flight hours')}</dt>" not in without

    def test_the_header_carries_no_art_tile(self, today):
        aircraft = _aircraft(today)
        content = _detail(aircraft).content.decode()
        header = _between(content, '<header class="entity-bar">', "</header>")
        assert "illus-tile" not in header
        assert "fleet-hero-art" in content


@pytest.mark.django_db
class TestBackToList:
    def test_the_aircraft_row_carries_the_list_query(self, today):
        aircraft = _aircraft(today)
        response = login_as(VIEW).get(LIST_URL, {"q": "RPA", "page": "1"})
        rows = response.content.decode().split('id="table-body"')[-1]
        assert f"{aircraft.pk}/?back=q%3DRPA%26page%3D1" in rows

    def test_aircraft_detail_goes_back_to_the_same_search(self, today):
        aircraft = _aircraft(today)
        response = _detail(aircraft, back="q=RPA&page=2&export=csv")
        assert response.context["list_url"] == f"{LIST_URL}?q=RPA&page=2"

    def test_operator_detail_still_goes_back_to_the_same_search(self, db):
        operator = Operator.objects.create(full_name="Persona Ficticia")
        response = login_as("view_operator").get(
            reverse("operator-detail", args=[operator.pk]),
            {"back": "credential=soon&page=1"},
        )
        assert (
            response.context["list_url"]
            == f"{reverse('operator-list')}?credential=soon&page=1"
        )

    @pytest.mark.parametrize("evil", ["//evil.com", "https://evil.com/x?y=1"])
    def test_back_cannot_leave_the_list(self, today, evil):
        aircraft = _aircraft(today)
        response = _detail(aircraft, back=evil)
        list_url = response.context["list_url"]
        assert list_url.split("?")[0] == LIST_URL
        assert not list_url.startswith(("//", "http"))

    def test_without_back_the_plain_list(self, today):
        aircraft = _aircraft(today)
        assert _detail(aircraft).context["list_url"] == LIST_URL


@pytest.mark.django_db
class TestForm:
    @pytest.mark.parametrize("name", AircraftForm._meta.fields)
    def test_every_form_field_is_drawn_on_the_full_page(self, today, name):
        aircraft = _aircraft(today)
        response = login_as("view_aircraft", "change_aircraft").get(
            reverse("aircraft-update", args=[aircraft.pk])
        )
        assert f'name="{name}"' in response.content.decode()

    @pytest.mark.parametrize("name", AircraftForm._meta.fields)
    def test_every_form_field_is_drawn_in_the_modal(self, today, name, monkeypatch):
        # UX-20 manda los formularios largos a página completa; para ver el fragmento del
        # modal se sube el umbral (es el fragmento que sigue sirviendo si alguien lo abre).
        monkeypatch.setattr("apps.core.views.UX20_FIELD_THRESHOLD", 99)
        aircraft = _aircraft(today)
        response = login_as("view_aircraft", "change_aircraft").get(
            reverse("aircraft-update", args=[aircraft.pk]), HTTP_HX_REQUEST="true"
        )
        content = response.content.decode()
        assert f'name="{name}"' in content
        assert "<html" not in content

    def test_the_four_sections_are_there_on_create(self, today):
        response = login_as("add_aircraft").get(reverse("aircraft-create"))
        content = response.content.decode()
        legends = re.findall(
            r'<legend class="h6 section-title mb-3">(.*?)</legend>', content
        )
        assert legends == [
            gettext("Identification"),
            gettext("Technical data"),
            gettext("JAC insurance"),
            gettext("Assignment and status"),
        ]

    def test_saving_through_the_sectioned_form_keeps_every_value(self, today):
        aircraft = _aircraft(
            today, year=2021, authorized_services="Servicio X", vlos="VLOS"
        )
        client = login_as("view_aircraft", "change_aircraft")
        response = client.get(reverse("aircraft-update", args=[aircraft.pk]))
        form = response.context["form"]
        data = {
            name: ("" if form[name].value() is None else form[name].value())
            for name in AircraftForm._meta.fields
        }
        data["model"] = "M3E"
        post = client.post(reverse("aircraft-update", args=[aircraft.pk]), data)
        assert post.status_code == 302
        aircraft.refresh_from_db()
        assert aircraft.model == "M3E"
        assert aircraft.year == 2021
        assert aircraft.authorized_services == "Servicio X"


@pytest.mark.django_db
def test_detail_requires_view_permission(today):
    aircraft = _aircraft(today)
    response = login_as().get(reverse("aircraft-detail", args=[aircraft.pk]))
    assert response.status_code == 403
