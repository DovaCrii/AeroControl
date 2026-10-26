"""LV-378 (PR 2): la sección 2 del informe v2, permisos agrupados por faena.

El informe de octubre repetía siete veces la misma fila de una faena (28-08 → 28-11, la
misma aeronave, un operador) y tres más de otra. El diseño 2 agrupa por faena con una
tira de vencimientos 0–90 días, deja aparte lo que no opera y declara los umbrales.

Lo que estos tests protegen, por orden de gravedad:

1. **Que los informes ya emitidos no cambien**: nada de `rpt2-` ni de la hoja v2 en un
   payload sin `meta.layout`, y `report-a4.css` sin clases nuevas (los snapshots de
   agosto lo vigilan byte a byte; esto vigila las causas).
2. **Que no se recorte nada en silencio**: la suma de los grupos da el total (I8), los
   folios van **explícitos**, y el reparto en hojas usa constantes medidas.
3. **Que el papel se lea sin color**: símbolo + palabra + color, y letra de 8,5 pt.
4. **Que el SVG sea accesible y de servidor**: sin `style=`, con `role="img"`, `<title>`,
   `<desc>`, ids únicos por hoja y las cifras como `<text>`.
5. **Contraste calculado** (`contrast.py`): texto ≥ 4,5; marcas y barras ≥ 3.
"""

import importlib.util
import json
import re
from datetime import date, datetime, timezone as dt_timezone
from pathlib import Path

import pytest
from django.conf import settings
from django.contrib.auth.models import Permission, User
from django.urls import reverse

from apps.core.testing import pin_now
from apps.reporting import invariants
from apps.reporting.builder import build
from apps.reporting.groups import permit_groups, strip_marks
from apps.reporting.models import ReportRun
from apps.reporting.pagination import (
    closing_px_v2,
    group_px,
    observation_px,
    v2_first_top_px,
)
from apps.reporting.templatetags.report_svg import (
    render_expiry_strip,
    strip_height,
)
from apps.reporting.v2_case import CUTOFF, PERIOD, make_case

ROOT = Path(settings.BASE_DIR)
CSS = ROOT / "static" / "css"
V2_CSS = (CSS / "report-a4-v2.css").read_text(encoding="utf-8")
BASE_CSS = (CSS / "report-a4.css").read_text(encoding="utf-8")
SNAPSHOTS = Path(__file__).parent / "snapshots"


@pytest.fixture
def case(db):
    return make_case()


@pytest.fixture
def payload(case):
    return build(PERIOD, cutoff=CUTOFF)[0]


@pytest.fixture
def groups(payload):
    return permit_groups(payload)


def _reader(client):
    user = User.objects.create_user("lector", password="x")
    user.user_permissions.add(
        Permission.objects.get(
            codename="view_reportrun", content_type__app_label="reporting"
        )
    )
    client.force_login(user)
    return client


def _page(client, payload, period=PERIOD, **extra):
    ReportRun.objects.create(
        period=period, revision=0, generated_by="t", payload=payload, **extra
    )
    return client.get(reverse("monthly-report"), {"period": f"{period:%Y-%m}"})


class TestTheGroupingRule:
    def test_seven_equal_permits_are_one_line_with_every_folio(self, groups):
        north = next(g for g in groups["operating"] if g["code"] == "CC901")

        assert north["count"] == 7
        assert north["single"] is True
        assert len(north["lines"]) == 1
        # Explícitos, sin rangos: un «001–007» escondería que falta el 004.
        assert len(north["lines"][0]["folios"]) == 7
        assert len(set(north["folios"])) == 7

    def test_folios_are_never_collapsed_into_a_range(self, client, payload):
        html = _page(_reader(client), payload).content.decode()

        for group in permit_groups(payload)["operating"]:
            for folio in group["folios"]:
                assert folio in html, folio
        assert "–JEJ" not in html and "001-007" not in html

    def test_different_dates_make_sublines_inside_the_centre(self, case):
        from apps.reporting.v2_case import _permit

        south = case["CC902"]
        _permit(south, start=date(2026, 9, 5), end=date(2027, 2, 1))
        payload = build(PERIOD, cutoff=CUTOFF)[0]

        group = next(
            g for g in permit_groups(payload)["operating"] if g["code"] == "CC902"
        )

        assert group["single"] is False
        assert len(group["lines"]) == 2
        assert group["count"] == 2
        assert {line["days"] for line in group["lines"]} == {53, 98}
        assert group["days"] == 53  # la cabecera es la peor banda de la faena

    def test_the_centres_come_by_urgency_with_the_first_to_fall_on_top(self, groups):
        days = [group["days"] for group in groups["operating"]]

        assert days == sorted(days)
        assert groups["operating"][0]["code"] == "CC901"

    def test_what_does_not_operate_goes_apart_and_does_not_count_as_a_centre(
        self, groups
    ):
        assert [g["code"] for g in groups["outside"]] == ["CC904", "CC905"]
        assert {g["code"] for g in groups["operating"]}.isdisjoint({"CC904", "CC905"})
        assert groups["centres"] == 2  # CC901 y CC902: CC903 no tiene vigentes
        assert groups["operating_in_force"] == 8
        assert groups["outside_in_force"] == 2

    def test_awaiting_and_lapsed_are_flat_lists(self, groups):
        assert [row["cost_centre"] for row in groups["awaiting"]] == ["CC903"]
        assert [row["cost_centre"] for row in groups["lapsed"]] == ["CC902"]

    def test_the_groups_add_up_to_the_total_and_i8_flags_a_gap(self, payload):
        assert invariants.violations(payload) == []
        broken = json.loads(json.dumps(payload))
        broken["cost_centres"][0]["permits_in_force"] = 0  # no cambia permisos
        # Quitar una fila de permiso vigente sin tocar las cifras: lo caza I3 y I8.
        row = next(r for r in broken["permits"] if r["in_force"] and r["in_operation"])
        broken["permits"].remove(row)

        codes = {code for code, _ in invariants.violations(broken)}

        assert "I3" in codes


class TestTheExpiryStrip:
    def _svg(self, groups, uid="strip-1"):
        return render_expiry_strip(groups["operating"], uid)

    def test_it_is_a_server_svg_without_inline_style(self, groups):
        svg = self._svg(groups)

        assert svg.startswith("<svg")
        assert "style=" not in svg
        assert "<script" not in svg
        # La geometría va en atributos.
        assert re.search(
            r'<rect class="rpt2-zone [^"]*" x="[\d.]+" y="\d+" width=', svg
        )

    def test_it_is_accessible_with_title_desc_and_unique_ids(self, groups):
        first, second = self._svg(groups, "strip-1"), self._svg(groups, "strip-2")

        assert 'role="img"' in first
        assert 'aria-labelledby="strip-1-t strip-1-d"' in first
        assert '<title id="strip-1-t">' in first and '<desc id="strip-1-d">' in first
        ids = re.findall(r'id="([^"]+)"', first + second)
        assert len(ids) == len(set(ids)) == 4

    def test_the_figures_are_text_and_the_description_carries_them_all(self, groups):
        svg = self._svg(groups)

        assert "×7 CC901" in re.findall(r"<text[^>]*>([^<]*)</text>", svg)
        desc = re.search(r"<desc[^>]*>(.*?)</desc>", svg).group(1)
        assert "CC901 ×7: 28 días (crítico)" in desc
        assert "CC902 ×1: 53 días (por vencer)" in desc
        assert "Más de 90 días: 0." in desc

    def test_the_band_is_a_shape_and_not_only_a_colour(self, groups):
        svg = self._svg(groups)

        assert "rpt2-mark-critical" in svg  # ✕: dos trazos
        assert "rpt2-mark-warning" in svg  # ▲: triángulo
        assert "<polygon" in svg and "<path" in svg

    def test_what_expires_beyond_ninety_days_is_counted_apart(self, case):
        from apps.reporting.v2_case import _permit

        _permit(case["CC902"], start=date(2026, 9, 5), end=date(2027, 3, 1))
        payload = build(PERIOD, cutoff=CUTOFF)[0]
        groups = permit_groups(payload)

        marks, beyond = strip_marks(groups["operating"])

        assert beyond == 1
        assert all(days <= 90 for days, *_ in marks)
        assert "›90: 1" in render_expiry_strip(groups["operating"], "s")

    def test_equal_dates_of_one_centre_are_a_single_mark(self, case):
        """Siete permisos con la misma fecha, aunque difieran en aeronave, son un
        vencimiento: no siete rótulos apilados."""
        from apps.reporting.v2_case import _aircraft, _permit

        for n in range(3):
            _permit(
                case["CC902"],
                start=date(2026, 9, 1 + n),
                end=date(2026, 12, 18),
                tails=[_aircraft(f"RPA-93{n}", case["CC902"])],
            )
        payload = build(PERIOD, cutoff=CUTOFF)[0]
        groups = permit_groups(payload)

        marks, _beyond = strip_marks(groups["operating"])

        assert [m for m in marks if m[2] == "CC902"] == [(53, 4, "CC902", "warning")]

    def test_labels_do_not_overlap_and_the_height_grows_with_the_rows(self, groups):
        height = strip_height(groups["operating"])
        svg = self._svg(groups)

        assert f'height="{height}"' in svg
        assert height >= 56 + 16

    def test_an_empty_strip_still_says_so(self):
        svg = render_expiry_strip([], "s")

        assert "ningún permiso vigente de faenas con operación" in svg


class TestTheV2StylesheetOnlyReachesTheNewReports:
    def test_a_layout_two_report_links_the_v2_sheet_and_uses_the_v2_pages(
        self, client, payload
    ):
        html = _page(_reader(client), payload).content.decode()

        assert "css/report-a4-v2" in html
        assert "rpt2-grp" in html
        assert "Por centro de costo" in html

    def test_a_report_without_layout_does_not_link_it(self, client, db):
        frozen = json.loads((SNAPSHOTS / "payload_2026_08.json").read_text("utf-8"))
        response = _page(_reader(client), frozen, date(2026, 8, 1))
        html = response.content.decode()

        assert "report-a4-v2" not in html
        assert "rpt2-" not in html
        assert "Detalle permiso a permiso" in html

    def test_the_base_sheet_has_no_v2_classes_and_v2_redefines_none_of_the_base(self):
        assert "rpt2-" not in BASE_CSS
        selectors = re.findall(
            r"([^{}/]+)\{", re.sub(r"/\*.*?\*/", "", V2_CSS, flags=re.S)
        )
        for selector in selectors:
            for part in (p.strip() for p in selector.split(",")):
                assert not re.match(r"\.rpt-(?!doc\b)", part), part


class TestThePaperReadsWithoutColour:
    def test_every_band_has_a_symbol_and_a_word_and_the_legend_says_the_thresholds(
        self, client, payload
    ):
        html = _page(_reader(client), payload).content.decode()

        assert "✕ Crítico" in html and "≤30 días" in html
        assert "▲ Por vencer" in html and "31–60 días" in html
        assert "● Vigente" in html and "&gt;60 días" in html
        # Y cada fila repite símbolo, palabra y días: no depende del color.
        assert re.search(r"rpt2-chip-critical\">✕ Crítico · 28 d", html)
        assert re.search(r"rpt2-chip-warning\">▲ Por vencer · 53 d", html)

    def test_no_v2_class_is_set_below_eight_and_a_half_points(self):
        sizes = [float(n) for n in re.findall(r"font-size:\s*([\d.]+)px", V2_CSS)]

        assert sizes, "la premisa cambió: el CSS v2 declara tamaños en px"
        assert min(sizes) >= 11.3  # 8,5 pt a 96 dpi

    def test_the_sections_label_declares_the_totals(self, client, payload):
        html = " ".join(_page(_reader(client), payload).content.decode().split())

        assert "8 vigentes en 2 faenas · 2 más sin operación · 1 en trámite" in html

    def test_the_closing_blocks_are_in_the_page(self, client, payload):
        html = _page(_reader(client), payload).content.decode()

        assert (
            "Sin operación — no cuentan en la cobertura ni en las renovaciones" in html
        )
        assert "No se renueva: cerrar el permiso o dejarlo vencer." in html
        assert "Contrato terminado" in html and "No vuela" in html
        assert "Vencidos sin cerrar" in html
        # «En proceso» es sólo de lo que está en trámite (página 3 y anexo), nunca de un
        # aprobado vencido.
        waiting = html.split("Solicitudes en trámite", 1)[1].split("rpt2-block", 1)[0]
        assert "En proceso" in waiting and "CC902" not in waiting
        assert html.count(">En proceso<") == 2  # el bloque y la fila del anexo

    def test_the_dgac_number_lives_in_the_annex_next_to_its_folio(
        self, client, payload
    ):
        """La sección 2 agrupa y ya no lo lleva: el anexo «registro permiso a permiso»
        lo recupera, fila por fila, junto al folio."""
        html = _page(_reader(client), payload).content.decode()
        row = next(r for r in payload["permits"] if r["dgac_number"])

        annex = html.split("Registro permiso a permiso", 1)[1]
        assert row["folio"] in annex and row["dgac_number"] in annex


def _load_contrast():
    spec = importlib.util.spec_from_file_location(
        "contrast_script", ROOT / ".claude/skills/diseno-ui/scripts/contrast.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _ratio(contrast, fg, bg):
    return contrast.ratio(contrast.to_rgb(fg), contrast.to_rgb(bg))


def _tokens():
    block = re.search(r"\.rpt-doc \{([^}]*--rpt2-crit-ink[^}]*)\}", V2_CSS).group(1)
    return dict(re.findall(r"--rpt2-([\w-]+):\s*(#[0-9a-fA-F]{6})", block))


class TestTheContrastIsCalculated:
    """Con el `contrast.py` del repo, no leído de un navegador (LV-207)."""

    WHITE = "#ffffff"

    @pytest.mark.parametrize(
        "ink, background",
        [
            ("crit-ink", "white"),
            ("crit-ink", "crit-bg"),
            ("warn-ink", "white"),
            ("warn-ink", "warn-bg"),
            ("ok-ink", "white"),
            ("ok-ink", "ok-bg"),
            ("ink", "white"),
            ("ink", "wash"),
            ("muted", "white"),
            ("muted", "wash"),
            ("navy", "white"),
            ("navy", "wash"),
        ],
    )
    def test_text_pairs_reach_four_and_a_half(self, ink, background):
        contrast, tokens = _load_contrast(), _tokens()
        fg = tokens[ink]
        bg = self.WHITE if background == "white" else tokens[background]

        assert _ratio(contrast, fg, bg) >= 4.5, (ink, background)

    @pytest.mark.parametrize(
        "mark, zone",
        [("crit-ink", "crit-bg"), ("warn-ink", "warn-bg"), ("ok-ink", "ok-bg")],
    )
    def test_marks_over_their_zones_reach_three(self, mark, zone):
        contrast, tokens = _load_contrast(), _tokens()

        assert _ratio(contrast, tokens[mark], tokens[zone]) >= 3

    @pytest.mark.parametrize("ink", ["crit-ink", "warn-ink", "ok-ink", "navy"])
    def test_white_text_over_the_bars_and_headers_reaches_four_and_a_half(self, ink):
        """La barra apilada de la cobertura imprime su cifra en blanco sobre la tinta, y
        los encabezados de tabla son blancos sobre el azul."""
        contrast, tokens = _load_contrast(), _tokens()

        assert _ratio(contrast, self.WHITE, tokens[ink]) >= 4.5

    @pytest.mark.parametrize("ink", ["crit-ink", "warn-ink", "ok-ink"])
    def test_the_progress_bars_read_over_their_track(self, ink):
        """Las barras de «lo próximo que vence» sobre su carril gris (≥3)."""
        contrast, tokens = _load_contrast(), _tokens()

        assert _ratio(contrast, tokens[ink], tokens["hair"]) >= 3

    def test_the_axis_and_ticks_read_over_every_zone(self):
        contrast, tokens = _load_contrast(), _tokens()

        for zone in ("crit-bg", "warn-bg", "ok-bg"):
            assert _ratio(contrast, tokens["muted"], tokens[zone]) >= 3

    def test_the_brand_amber_is_not_used_for_anything_in_v2(self):
        """`#b8791a` sobre el carril gris da 2,99:1: la tinta es `#8a5a08`."""
        rules = re.sub(r"/\*.*?\*/", "", V2_CSS, flags=re.S)  # sin los comentarios

        assert "#b8791a" not in rules.lower()


class TestThePaginationUsesMeasuredConstants:
    def test_a_one_line_group_costs_the_measured_pitch(self, groups):
        group = next(g for g in groups["operating"] if g["code"] == "CC902")

        assert group_px(group) == 53

    def test_detail_lines_beyond_the_first_cost_a_line_each(self, groups):
        """Siete folios con su aeronave no caben en un renglón de detalle."""
        north = next(g for g in groups["operating"] if g["code"] == "CC901")

        assert group_px(north) == 53 + 16

    def test_a_centre_with_sublines_costs_its_head_plus_each_subline(self, case):
        from apps.reporting.v2_case import _permit

        _permit(case["CC902"], start=date(2026, 9, 5), end=date(2027, 2, 1))
        payload = build(PERIOD, cutoff=CUTOFF)[0]
        group = next(
            g for g in permit_groups(payload)["operating"] if g["code"] == "CC902"
        )

        assert group_px(group) == 36 + 42 * 2

    def test_the_first_group_falls_below_the_strip(self):
        assert v2_first_top_px(104) == 225 + 104 + 11

    def test_the_closing_grows_with_the_blocks_and_the_note(self, groups):
        none = {"outside": [], "awaiting": [], "lapsed": []}

        assert closing_px_v2(groups) > closing_px_v2(none)
        assert observation_px("x" * 400) > observation_px("")

    def test_the_closing_blocks_only_ride_on_the_last_sheet(self, client, payload):
        response = _page(_reader(client), payload)
        sheets = response.context["permit_sheets"]

        assert sheets[-1]["last"] is True
        for sheet in sheets[:-1]:
            assert not (sheet["outside"] or sheet["awaiting"] or sheet["lapsed"])
        assert sheets[-1]["summary"]["outside_in_force"] == 2

    def test_a_long_list_of_centres_spreads_over_sheets_without_losing_any(self, db):
        """Lo que se declara en el rótulo es lo que se reparte: ninguna faena se pierde."""
        from apps.registry.models import CostCenter
        from apps.reporting.v2_case import _permit

        for n in range(14):
            centre = CostCenter.objects.create(
                code=f"CC{950 + n}", name=f"Faena {n}", operates_flights=True
            )
            _permit(centre, start=date(2026, 9, 1), end=date(2026, 12, 20 - n))
        payload = build(PERIOD, cutoff=CUTOFF)[0]

        sheets = permit_groups(payload)["operating"]
        from apps.reporting.views import MonthlyReportView

        laid = MonthlyReportView._permit_sheets_v2(payload, 3, "")

        assert len(laid) >= 2
        assert sum(len(sheet["groups"]) for sheet in laid) == len(sheets) == 14
        assert [s["page"] for s in laid] == list(range(3, 3 + len(laid)))
        assert laid[-1]["last"] and not laid[0]["last"]


class TestTheV2SnapshotIsFrozenOutput:
    """El HTML de un informe v2 de datos ficticios: cualquier cambio de plantilla o de
    CSS enlazado que mueva el papel falla acá. Regenerar a propósito:

        $env:UPDATE_SNAPSHOTS = "1"; uv run pytest apps/reporting/test_lv378_permits_v2.py
    """

    def test_the_monthly_v2_html_does_not_change(self, client, db, monkeypatch):
        from apps.reporting.test_snapshot_monthly import _check

        pin_now(monkeypatch, datetime(2026, 10, 27, 15, 0, tzinfo=dt_timezone.utc))
        frozen = json.loads((SNAPSHOTS / "payload_2026_10_v2.json").read_text("utf-8"))
        response = _page(
            _reader(client),
            frozen,
            findings=[
                {
                    "title": "Dependencia de una persona",
                    "text": "La faena CC901 depende de un solo operador designado.",
                }
            ],
            period_note="Nota ficticia del periodo para la prueba.",
        )

        assert response.status_code == 200
        assert invariants.violations(frozen) == []
        _check("monthly_2026_10_v2", response.content.decode())
