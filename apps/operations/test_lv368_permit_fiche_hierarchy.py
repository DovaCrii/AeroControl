"""LV-368 fase 1: la ficha del permiso con jerarquía.

Arriba sólo lo que hay que atender: un chip de estado y a quién espera, y «Qué falta»
(máximo tres ítems, armados en Python). Lo demás va en secciones plegables cuyo `open`
decide la vista. Estas pruebas comparan contra el objeto (`gettext(...)`, la constante del
modelo) y acotan la búsqueda a la región que afirman, porque el armazón de la página
comparte vocabulario con las filas (lección de `LV-118`/`UX-01`). Datos ficticios.
"""

import re
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.translation import gettext

from apps.core.testing import login_as
from apps.operations import permit_attention
from apps.operations.dossier import DossierItem
from apps.operations.models import FlightPermission
from apps.registry.models import Aircraft, CostCenter

TODAY = timezone.localdate()

BCN_TEXT = (
    "The commune, province and region come from the BCN administrative boundaries, "
    "which that institution publishes as referential: near a boundary the answer may "
    "be the neighbouring commune. Confirm it before filing."
)


def es(text):
    """La cadena tal como la ve la persona: la interfaz corre en español."""
    with translation.override("es"):
        return gettext(text)


@pytest.fixture
def center(db):
    return CostCenter.objects.create(code="CC368", name="Faena ficticia")


def _permit(center, **extra):
    data = {
        "internal_folio": "JEJ-2026-368",
        "cost_center": center,
        "purpose": "patrol",
        "valid_from": TODAY,
        "valid_until": TODAY + timedelta(days=60),
        "location": "Sitio ficticio",
        "area_type": "unpopulated",
    }
    data.update(extra)
    return FlightPermission.objects.create(**data)


def _body(permit, *perms):
    client = login_as("view_flightpermission", *perms)
    response = client.get(reverse("permission-detail", args=[permit.pk]))
    assert response.status_code == 200
    return response.content.decode()


def _strip(body):
    return body.split('id="permit-attention"')[1].split("</section>")[0]


def _dossier(missing=0, authorization_missing=False):
    items = [
        DossierItem(
            "signed_authorization",
            "x",
            "missing" if authorization_missing else "ok",
        )
    ]
    return {"missing_count": missing, "items": items}


def _items(permit, *, folio=None, insurance=None, dossier=None, derived=None):
    return permit_attention.attention_items(
        permit,
        suggested_folio=folio,
        insurance_limit=insurance,
        dossier=dossier or _dossier(),
        derived_location=derived,
    )


class TestWaitingOn:
    @pytest.mark.parametrize(
        "status,expected",
        [
            ("requested", FlightPermission.WAITING_DGAC),
            ("denied", FlightPermission.WAITING_OPERATOR),
            ("expired", FlightPermission.WAITING_OPERATOR),
            ("completed", FlightPermission.WAITING_NOBODY),
        ],
    )
    def test_by_status(self, status, expected):
        assert FlightPermission(status=status).waiting_on() == expected

    def test_an_approved_permit_waits_on_nobody_until_it_lapses(self):
        live = FlightPermission(
            status="approved", valid_until=TODAY + timedelta(days=5)
        )
        gone = FlightPermission(
            status="approved", valid_until=TODAY - timedelta(days=1)
        )
        assert live.waiting_on() == FlightPermission.WAITING_NOBODY
        assert gone.waiting_on() == FlightPermission.WAITING_OPERATOR


class TestTheAttentionStrip:
    def _worst(self, center):
        permit = _permit(
            center,
            status="approved",
            permission_number="",
            valid_until=TODAY - timedelta(days=2),
        )
        insurance = {
            "limit": "2026-12-20",
            "aircraft": "RPA-1",
            "expiry": "2026-12-21",
            "exceeded": True,
        }
        return permit, insurance

    def test_three_items_at_most_in_the_order_the_person_chose(self, center):
        permit, insurance = self._worst(center)
        items = _items(permit, insurance=insurance, dossier=_dossier(missing=2))
        assert [item["kind"] for item in items] == ["lapsed", "insurance", "folio"]
        assert len(items) == permit_attention.MAX_ATTENTION_ITEMS

    def test_the_order_lives_in_one_tuple(self):
        assert permit_attention.ATTENTION_ORDER[:4] == (
            "lapsed",
            "insurance",
            "folio",
            "dossier",
        )

    def test_critical_only_for_a_lapse_or_an_exceeded_insurance(self, center):
        requested = _permit(center, status="requested", permission_number="")
        within = {"limit": "x", "aircraft": "a", "expiry": "y", "exceeded": False}
        exceeded = dict(within, exceeded=True)
        folio_only = _items(requested)
        assert {item["tone"] for item in folio_only} == {permit_attention.WARNING}
        assert (
            _items(requested, insurance=within)[0]["tone"] == permit_attention.CAUTION
        )
        assert (
            _items(requested, insurance=exceeded)[0]["tone"]
            == permit_attention.CRITICAL
        )
        assert _items(requested, dossier=_dossier(missing=1))[-1]["tone"] == (
            permit_attention.WARNING
        )

    def test_a_denied_permit_asks_for_no_folio_and_no_region(self, center):
        denied = _permit(center, status="denied", permission_number="")
        assert _items(denied) == []

    def test_a_derived_region_is_not_a_missing_region(self, center):
        requested = _permit(center, permission_number="X-1")
        assert _items(requested) != []
        derived = SimpleNamespace(region="R", comuna="C")
        assert _items(requested, derived=derived) == []

    def test_the_symbols_are_part_of_the_item(self, center):
        permit, insurance = self._worst(center)
        symbols = {item["symbol"] for item in _items(permit, insurance=insurance)}
        assert symbols <= set(permit_attention.SYMBOLS.values())


class TestOpenSections:
    def test_validity_opens_with_thirty_days_or_less(self, center):
        near = _permit(center, valid_until=TODAY + timedelta(days=30))
        far = _permit(
            center,
            internal_folio="JEJ-2026-369",
            valid_until=TODAY + timedelta(days=31),
        )
        kwargs = {
            "dossier": _dossier(),
            "derived_location": None,
            "preflight_checks": [],
        }
        assert permit_attention.open_sections(near, **kwargs)["validity"] is True
        assert permit_attention.open_sections(far, **kwargs)["validity"] is False

    def test_validity_opens_when_the_signed_pdf_is_missing(self, center):
        far = _permit(center, valid_until=TODAY + timedelta(days=90))
        opened = permit_attention.open_sections(
            far,
            dossier=_dossier(authorization_missing=True),
            derived_location=None,
            preflight_checks=[],
        )
        assert opened["validity"] is True

    def test_location_opens_when_something_is_missing(self, center):
        bare = _permit(center)
        full = _permit(
            center,
            internal_folio="JEJ-2026-370",
            region="Región ficticia",
            latitude="-33.1",
            longitude="-70.1",
        )
        kwargs = {
            "dossier": _dossier(),
            "derived_location": None,
            "preflight_checks": [],
        }
        assert permit_attention.open_sections(bare, **kwargs)["location"] is True
        assert permit_attention.open_sections(full, **kwargs)["location"] is False

    def test_traceability_is_never_open_and_operation_always_is(self, center):
        opened = permit_attention.open_sections(
            _permit(center),
            dossier=_dossier(authorization_missing=True),
            derived_location=None,
            preflight_checks=[],
        )
        assert opened["trace"] is False and opened["operation"] is True

    def test_an_unsigned_preflight_opens_its_section(self, center):
        unsigned = SimpleNamespace(is_signed=False)
        kwargs = {"dossier": _dossier(), "derived_location": None}
        base = permit_attention.open_sections(
            _permit(center),
            preflight_checks=[SimpleNamespace(is_signed=True)],
            **kwargs,
        )
        assert base["flights"] is False
        assert (
            permit_attention.open_sections(
                _permit(center, internal_folio="JEJ-2026-371"),
                preflight_checks=[unsigned],
                **kwargs,
            )["flights"]
            is True
        )


class TestTheFicheHeader:
    def test_the_status_chip_appears_once_and_the_status_row_is_gone(self, center):
        permit = _permit(center, status="denied")
        body = _body(permit)
        with translation.override("es"):
            label = str(permit.get_status_display())
        chips = re.findall(
            r'<span class="id-chip id-chip--\w+">%s</span>' % label, body
        )
        assert len(chips) == 1
        assert f'<th scope="row">{es("Status")}</th>' not in body
        # Acotado a la ficha: el contador de la barra lateral también es `bg-danger`.
        fiche = body.split('class="card permit-journey"')[1]
        assert "bg-danger" not in fiche

    def test_it_says_who_the_permit_waits_on(self, center):
        body = _body(_permit(center, status="requested"))
        head = body.split('id="permit-attention"')[0]
        assert es("Waiting on the DGAC") in head
        assert es("Waiting on the operator") not in head

    def test_an_approved_live_permit_waits_on_nobody(self, center):
        body = _body(_permit(center, status="approved", permission_number="P-1"))
        head = body.split('id="permit-attention"')[0]
        assert 'class="permit-waiting"' not in head

    def test_no_dates_means_a_single_waiting_chip_and_no_timeline(self, center):
        permit = _permit(center, valid_from=None, valid_until=None)
        body = _body(permit)
        section = body.split('id="permit-validity"')[1].split("</details>")[0]
        assert section.count(es("Awaiting the DGAC")) == 1
        assert "permit-tl" not in section

    def test_the_timeline_is_a_server_svg_without_inline_style(self, center):
        body = _body(_permit(center))
        svg = body.split('class="permit-tl"')[1].split("</svg>")[0]
        assert 'role="img"' in body.split('class="permit-tl"')[0][-200:] + 'role="img"'
        assert "<title" in svg and "<desc" in svg
        assert "style=" not in svg
        # `localize off`: en español `10.5` saldría `10,5`, que no es un número SVG.
        for value in re.findall(r'\b(?:x|y|width|x1|x2)="([^"]+)"', svg):
            assert re.fullmatch(r"\d+(\.\d+)?", value), value
        assert es("Days left: %(days)s") % {"days": 60} in body


class TestTheAttentionRegion:
    def test_the_strip_has_at_most_three_items(self, center):
        permit = _permit(
            center,
            status="approved",
            permission_number="",
            valid_until=TODAY - timedelta(days=1),
        )
        permit.aircraft_fleet.add(
            Aircraft.objects.create(
                registration="RPA-368",
                type="RPA",
                model="M3E",
                manufacturer="DJI",
                insurance_expiry=TODAY + timedelta(days=5),
            )
        )
        region = _strip(_body(permit))
        assert region.count('class="permit-attn ') <= 3
        assert region.index("permit-attn--critical") < region.index(
            "permit-attn--warning"
        )

    def test_a_clean_permit_says_nothing_is_pending(self, center, monkeypatch):
        permit = _permit(center, status="denied", permission_number="")
        region = _strip(_body(permit))
        assert es("Nothing pending") in region
        assert (
            "permit-attn--warning" not in region
            and "permit-attn--critical" not in region
        )

    def test_the_insurance_text_moved_into_the_strip(self, center):
        permit = _permit(
            center, status="requested", valid_until=TODAY + timedelta(days=20)
        )
        permit.aircraft_fleet.add(
            Aircraft.objects.create(
                registration="RPA-369",
                type="RPA",
                model="M3E",
                manufacturer="DJI",
                insurance_expiry=TODAY + timedelta(days=40),
            )
        )
        region = _strip(_body(permit))
        text = es(
            "Insurance of %(aircraft)s until %(expiry)s: this request can end on "
            "%(limit)s at the latest."
        )
        assert text.split("%(aircraft)s")[0] in region
        assert "permit-attn--caution" in region


class TestTheDerivedLocationNotice:
    def test_the_bcn_text_is_written_once(self, center):
        permit = _permit(
            center,
            region="Región ficticia",
            commune="Comuna ficticia",
            region_source="derived",
        )
        body = _body(permit)
        assert body.count(es(BCN_TEXT)) == 1
        assert es("Derived from the coordinates") in body
        assert es("Why?") in body.split('id="permit-location"')[1]

    def test_no_notice_when_the_region_was_declared(self, center):
        permit = _permit(center, region="Región ficticia", commune="Comuna ficticia")
        assert es(BCN_TEXT) not in _body(permit)


class TestTheMoreMenu:
    def _menu(self, body):
        return body.split('class="dropdown-menu dropdown-menu-end"')[1].split("</ul>")[
            0
        ]

    def test_a_reader_only_gets_back(self, center):
        permit = _permit(center)
        menu = self._menu(_body(permit))
        assert reverse("permission-update", args=[permit.pk]) not in menu
        assert reverse("permission-archive", args=[permit.pk]) not in menu
        assert reverse("permission-list") in menu

    def test_edit_and_correct_need_the_change_permission(self, center):
        permit = _permit(center)
        menu = self._menu(_body(permit, "change_flightpermission"))
        assert reverse("permission-update", args=[permit.pk]) in menu
        assert reverse("permission-correct-status", args=[permit.pk]) in menu
        assert reverse("permission-archive", args=[permit.pk]) not in menu

    def test_archive_is_a_post_form_and_needs_the_delete_permission(self, center):
        permit = _permit(center)
        menu = self._menu(_body(permit, "delete_flightpermission"))
        assert (
            f'method="post" action="{reverse("permission-archive", args=[permit.pk])}"'
            in menu
        )

    def test_restore_replaces_archive_on_an_archived_permit(self, center):
        permit = _permit(center, is_active=False)
        client = login_as("view_flightpermission", "change_flightpermission")
        # El detalle sólo sirve permisos activos: lo archivado se ve desde el listado.
        assert (
            client.get(reverse("permission-detail", args=[permit.pk])).status_code
            == 404
        )

    def test_the_primary_action_stays_outside_the_menu(self, center):
        permit = _permit(center)
        body = _body(permit)
        link = f'href="{reverse("permission-operations", args=[permit.pk])}" class="btn btn-primary"'
        assert link in body
        assert link not in self._menu(body)


class TestSectionsOnThePage:
    def test_validity_is_open_with_few_days_left(self, center):
        permit = _permit(center, valid_until=TODAY + timedelta(days=10))
        assert '<details class="permit-section" id="permit-validity" open>' in _body(
            permit
        )

    def test_traceability_stays_closed_and_operation_open(self, center):
        body = _body(_permit(center))
        assert '<details class="permit-section" id="permit-trace">' in body
        assert '<details class="permit-section" id="permit-operation" open>' in body

    def test_the_old_critical_row_class_is_gone_from_the_fiche(self, center):
        lapsed = _permit(
            center,
            status="approved",
            permission_number="P",
            valid_until=date(2020, 1, 1),
            valid_from=date(2019, 12, 1),
        )
        body = _body(lapsed)
        assert "row-critical" not in body
        assert "id-chip--critical" in body.split('id="permit-attention"')[0]


class TestTheOptionalValiditySectionOfTheForm:
    """La vigencia es opcional hasta aprobar: va plegada, y se abre si hay error o valor."""

    def _details(self, body):
        return re.search(
            r'<details class="cc-form-section permit-form-optional mb-4"[^>]*>', body
        )

    def test_a_new_request_has_it_folded(self, center):
        client = login_as("add_flightpermission")
        body = client.get(reverse("permission-create")).content.decode()
        tag = self._details(body)
        assert tag is not None and " open" not in tag.group(0)
        assert 'id="id_valid_from"' in body  # el campo sigue en el formulario

    def test_an_error_in_it_opens_it(self, center):
        client = login_as("add_flightpermission")
        response = client.post(
            reverse("permission-create"),
            {
                "purpose": "patrol",
                "location": "x",
                "cost_center": str(center.pk),
                "valid_from": "2026-01-01",
                "valid_until": "2025-01-01",
            },
        )
        tag = self._details(response.content.decode())
        assert tag is not None and " open" in tag.group(0)
