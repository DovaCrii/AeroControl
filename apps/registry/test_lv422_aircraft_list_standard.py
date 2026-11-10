"""LV-422: la lista de aeronaves al estándar visual de la app (padrón de operadores, LV-413).

El estado era `badge bg-*`, la ubicación una insignia por cada valor, el seguro y el trámite
mezclaban estilos, y no había filtros más que `?insurance=` desde el panel. Ahora: chips de
identidad con glifo, faena en `cc-chip`, menú «⋯» por fila, tres filtros combinables y cuatro
atajos con conteo.

Las afirmaciones de presentación comparan contra el objeto (`status_tone`) y se acotan al
cuerpo de la tabla, porque el armazón de la página comparte vocabulario con las filas
(lección de LV-118). Datos ficticios.
"""

import re
from datetime import timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext

from apps.core.models import OperationalTenant
from apps.core.templatetags.aero_tags import status_tone
from apps.core.testing import login_as
from apps.registry.models import Aircraft, CostCenter

URL = reverse("aircraft-list")
VIEW = "view_aircraft"


def _today():
    return timezone.localdate()


def _aircraft(registration, **extra):
    extra.setdefault("insurance_status", Aircraft.INSURANCE_STATUS_ACTIVE)
    extra.setdefault("insurance_expiry", _today() + timedelta(days=400))
    return Aircraft.objects.create(
        registration=registration,
        type="RPA",
        model="M3",
        manufacturer="DJI",
        **extra,
    )


def _regs(response):
    return {a.registration for a in response.context["objects"]}


def _rows(response):
    return response.content.decode().split('id="table-body"')[-1]


@pytest.fixture
def fleet(db):
    today = _today()
    cc = CostCenter.objects.create(code="CC738", name="Faena Norte")
    other = CostCenter.objects.create(code="CC21", name="Faena Sur")
    return {
        "cc": cc,
        "other": other,
        "ok": _aircraft("RPA-OK", cost_center=cc),
        "lapsed": _aircraft(
            "RPA-LAPSED", cost_center=cc, insurance_expiry=today - timedelta(days=2)
        ),
        "soon": _aircraft(
            "RPA-SOON", cost_center=other, insurance_expiry=today + timedelta(days=10)
        ),
        "damaged": _aircraft("RPA-DMG", cost_center=cc, status="damaged"),
        "maint": _aircraft("RPA-MNT", status="maintenance"),
        "retired": _aircraft("RPA-OLD", cost_center=cc, status="retired"),
        "archived": _aircraft("RPA-ARC", cost_center=cc, is_active=False),
    }


QUICK = [
    ({"insurance": "lapsed"}, "Insurance lapsed"),
    ({"insurance": "soon"}, "Insurance due ≤30 days"),
    ({"condition": "grounded"}, "Out of service"),
    ({"cost_center": "none"}, "No cost center"),
]


@pytest.mark.django_db
class TestFilters:
    def test_condition_each_status(self, fleet):
        client = login_as(VIEW)
        assert _regs(client.get(URL, {"condition": "damaged"})) == {"RPA-DMG"}
        assert _regs(client.get(URL, {"condition": "maintenance"})) == {"RPA-MNT"}
        assert _regs(client.get(URL, {"condition": "retired"})) == {"RPA-OLD"}

    def test_grounded_is_damaged_plus_maintenance(self, fleet):
        response = login_as(VIEW).get(URL, {"condition": "grounded"})
        assert _regs(response) == {"RPA-DMG", "RPA-MNT"}

    def test_insurance_reuses_the_dashboard_criterion(self, fleet):
        client = login_as(VIEW)
        assert _regs(client.get(URL, {"insurance": "lapsed"})) == {"RPA-LAPSED"}
        assert _regs(client.get(URL, {"insurance": "soon"})) == {"RPA-SOON"}

    def test_cost_center_none_and_pk(self, fleet):
        client = login_as(VIEW)
        assert _regs(client.get(URL, {"cost_center": "none"})) == {"RPA-MNT"}
        assert _regs(client.get(URL, {"cost_center": fleet["other"].pk})) == {
            "RPA-SOON"
        }

    def test_filters_combine(self, fleet):
        response = login_as(VIEW).get(
            URL, {"condition": "grounded", "cost_center": fleet["cc"].pk}
        )
        assert _regs(response) == {"RPA-DMG"}

    def test_search_reaches_serial_number_and_cost_center_code(self, fleet):
        Aircraft.objects.filter(pk=fleet["ok"].pk).update(serial_number="SN-9X77")
        client = login_as(VIEW)
        assert _regs(client.get(URL, {"q": "9x77"})) == {"RPA-OK"}
        assert _regs(client.get(URL, {"q": "CC21"})) == {"RPA-SOON"}

    def test_an_unknown_key_filters_nothing(self, fleet):
        client = login_as(VIEW)
        everything = _regs(client.get(URL))
        response = client.get(URL, {"colour": "red"})
        assert _regs(response) == everything
        assert not response.context["is_filtered"]

    @pytest.mark.parametrize(
        "params",
        [
            {"cost_center": "not-a-uuid"},
            {"condition": "banana"},
            {"insurance": "banana"},
            {"cost_center": "%00"},
        ],
    )
    def test_a_malformed_value_is_not_a_500(self, fleet, params):
        response = login_as(VIEW).get(URL, params)
        assert response.status_code == 200

    def test_a_malformed_cost_center_is_an_empty_list(self, fleet):
        response = login_as(VIEW).get(URL, {"cost_center": "not-a-uuid"})
        assert _regs(response) == set()

    def test_other_company_cost_center_is_empty_and_not_offered(self, db):
        a = OperationalTenant.objects.create(name="A", slug="a-422")
        b = OperationalTenant.objects.create(name="B", slug="b-422")
        cc_a = CostCenter.objects.create(code="CC1", name="Propia", tenant=a)
        cc_b = CostCenter.objects.create(code="CC999", name="Ajena", tenant=b)
        _aircraft("RPA-A", tenant=a, cost_center=cc_a)
        _aircraft("RPA-B", tenant=b, cost_center=cc_b)
        client = login_as(VIEW, member_of=a)
        assert _regs(client.get(URL)) == {"RPA-A"}
        response = client.get(URL, {"cost_center": cc_b.pk})
        assert _regs(response) == set()
        assert cc_b not in list(response.context["cost_center_options"])
        assert cc_a in list(response.context["cost_center_options"])

    def test_403_without_view_aircraft(self, fleet):
        client = login_as()
        assert client.get(URL).status_code == 403
        assert client.get(URL, HTTP_HX_REQUEST="true").status_code == 403


@pytest.mark.django_db
class TestQuickFilters:
    @pytest.mark.parametrize("params, label", QUICK)
    def test_the_count_is_the_rows_the_click_brings(self, fleet, params, label):
        client = login_as(VIEW)
        chips = {c["label"]: c for c in client.get(URL).context["quick_filters"]}
        chip = chips[gettext(label)]
        assert chip["count"] > 0
        brought = client.get(URL + chip["url"])
        assert chip["count"] == len(brought.context["objects"])
        assert chip["count"] == len(_regs(client.get(URL, params)))

    @pytest.mark.parametrize("params, label", QUICK)
    def test_a_second_click_turns_it_off(self, fleet, params, label):
        client = login_as(VIEW)
        ((key, value),) = params.items()
        response = client.get(URL, params)
        chip = {c["label"]: c for c in response.context["quick_filters"]}[
            gettext(label)
        ]
        assert chip["active"]
        assert f"{key}=" not in chip["url"]
        off = client.get(URL + chip["url"])
        assert not off.context["filters"][key]

    def test_the_htmx_response_carries_the_chips_out_of_band(self, fleet):
        response = login_as(VIEW).get(
            URL, {"condition": "grounded"}, HTTP_HX_REQUEST="true"
        )
        assert response.templates[0].name == "registry/_aircraft_rows.html"
        content = response.content.decode()
        assert 'id="op-quick"' in content and 'hx-swap-oob="true"' in content
        assert 'id="pagination-container"' in content

    def test_chips_count_on_top_of_the_other_filters(self, fleet):
        response = login_as(VIEW).get(URL, {"cost_center": fleet["other"].pk})
        chips = {c["label"]: c["count"] for c in response.context["quick_filters"]}
        assert chips[gettext("Out of service")] == 0
        assert chips[gettext("Insurance due ≤30 days")] == 1


@pytest.mark.django_db
class TestPresentation:
    @pytest.mark.parametrize(
        "key, status, glyph",
        [
            ("ok", "active", "✓"),
            ("damaged", "damaged", "✕"),
            ("maint", "maintenance", "●"),
            ("retired", "retired", "▣"),
        ],
    )
    def test_the_status_is_an_identity_chip_with_a_glyph(
        self, fleet, key, status, glyph
    ):
        rows = _rows(login_as(VIEW).get(URL, {"q": fleet[key].registration}))
        assert f"id-chip--{status_tone(status)}" in rows
        assert f'<span aria-hidden="true">{glyph}</span>' in rows
        assert "badge bg-" not in rows

    def test_no_legacy_badge_or_unsanctioned_colour_survives(self, fleet):
        rows = _rows(login_as(VIEW).get(URL))
        for legacy in ("bg-success", "bg-danger", "bg-warning", "bg-info-subtle"):
            assert legacy not in rows
        assert "sev-caution" not in rows

    def test_an_archived_row_says_so_next_to_the_status(self, fleet):
        rows = _rows(login_as(VIEW).get(URL, {"is_active": "archived"}))
        assert "id-chip id-chip--neutral" in rows
        assert gettext("Archived") in rows

    def test_the_insurance_process_is_the_info_chip_not_a_green_one(self, fleet):
        Aircraft.objects.filter(pk=fleet["ok"].pk).update(
            insurance_status=Aircraft.INSURANCE_STATUS_FILED
        )
        rows = _rows(login_as(VIEW).get(URL, {"q": "RPA-OK"}))
        label = Aircraft.objects.get(pk=fleet["ok"].pk).get_insurance_status_display()
        assert (
            f'<span class="id-chip id-chip--info"><span aria-hidden="true">◆</span> {label}'
            in rows
        )

    def test_on_site_shows_the_site_code_chip_and_the_name_in_the_title(self, fleet):
        Aircraft.objects.filter(pk=fleet["ok"].pk).update(
            current_location="on_site", current_site=fleet["other"]
        )
        rows = _rows(login_as(VIEW).get(URL, {"q": "RPA-OK"}))
        assert f'<span class="cc-chip" title="{fleet["other"]}">CC21</span>' in rows
        assert gettext("On site") in rows

    def test_headquarters_is_plain_text(self, fleet):
        rows = _rows(login_as(VIEW).get(URL, {"q": "RPA-OK"}))
        assert gettext("Headquarters") in rows
        assert "badge" not in rows.split("<td")[4]

    def test_cost_center_chip_and_the_empty_one(self, fleet):
        client = login_as(VIEW)
        assert '<span class="cc-chip" title="' in _rows(
            client.get(URL, {"q": "RPA-OK"})
        )
        empty = _rows(client.get(URL, {"q": "RPA-MNT"}))
        assert f'<span class="cc-chip is-empty">{gettext("Unassigned")}</span>' in empty

    def test_colspan_is_the_exact_number_of_cols(self, db):
        content = login_as(VIEW).get(URL, {"q": "nothing-like-this"}).content.decode()
        cols = len(
            re.findall(
                r"<col class=", content.split("<colgroup>")[1].split("</colgroup>")[0]
            )
        )
        spans = re.findall(r'colspan="(\d+)"', _rows_from(content))
        assert cols == 6
        assert spans == [str(cols)]

    def test_the_header_order(self, fleet):
        head = (
            login_as(VIEW)
            .get(URL)
            .content.decode()
            .split("<thead>")[1]
            .split("</thead>")[0]
        )
        order = [
            gettext(n)
            for n in ("Registration", "Status", "Insurance", "Location", "Cost center")
        ]
        positions = [head.index(label) for label in order]
        assert positions == sorted(positions)

    def test_sort_keys_are_the_same_as_before(self):
        from apps.registry.views import AircraftList

        assert set(AircraftList.sortable_columns) == {
            "registration",
            "cost_center",
            "status",
            "location",
            "insurance",
        }


def _rows_from(content):
    return content.split('id="table-body"')[-1]


@pytest.mark.django_db
class TestRowMenu:
    def test_without_permissions_there_is_no_archive_or_restore(self, fleet):
        client = login_as(VIEW)
        rows = _rows(client.get(URL, {"is_active": "archived"}))
        assert "id-rowmenu" not in rows
        rows = _rows(client.get(URL))
        assert reverse("aircraft-archive", args=[fleet["ok"].pk]) not in rows

    def test_the_menu_offers_archive_with_delete_permission(self, fleet):
        rows = _rows(login_as(VIEW, "delete_aircraft").get(URL, {"q": "RPA-OK"}))
        assert reverse("aircraft-archive", args=[fleet["ok"].pk]) in rows
        assert reverse("aircraft-restore", args=[fleet["ok"].pk]) not in rows

    def test_the_menu_offers_restore_on_archived_rows_with_change_permission(
        self, fleet
    ):
        client = login_as(VIEW, "change_aircraft")
        rows = _rows(client.get(URL, {"is_active": "archived"}))
        assert reverse("aircraft-restore", args=[fleet["archived"].pk]) in rows
        assert reverse("aircraft-archive", args=[fleet["archived"].pk]) not in rows

    def test_the_can_it_fly_link_preselects_the_aircraft(self, fleet):
        rows = _rows(login_as(VIEW).get(URL, {"q": "RPA-OK"}))
        assert f"{reverse('can-i-fly')}?aircraft={fleet['ok'].pk}" in rows

    def test_edit_still_opens_the_modal(self, fleet):
        rows = _rows(login_as(VIEW, "change_aircraft").get(URL, {"q": "RPA-OK"}))
        pk = fleet["ok"].pk
        assert f'hx-get="{pk}/edit/" hx-target="#modal-content"' in rows
        assert 'class="id-rowactions"' in rows

    def test_the_page_loads_the_menu_script_and_styles(self, fleet):
        content = login_as(VIEW).get(URL).content.decode()
        assert "js/row-menu.js" in content
        assert "css/operators.css" in content


@pytest.mark.django_db
def test_query_count_does_not_grow_with_the_fleet(db):
    cc = CostCenter.objects.create(code="CC1", name="Uno")
    client = login_as(VIEW)
    _aircraft("RPA-1", cost_center=cc, current_location="on_site", current_site=cc)
    client.get(URL)  # calienta ContentType y la sesión

    def measure():
        with CaptureQueriesContext(connection) as ctx:
            assert client.get(URL).status_code == 200
        return len(ctx)

    one = measure()
    for i in range(2, 6):
        _aircraft(
            f"RPA-{i}", cost_center=cc, current_location="on_site", current_site=cc
        )
    assert measure() == one
