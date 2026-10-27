"""LV-378 (PR 3): resumen, cobertura y anexo del informe v2.

El informe de octubre decía «13 vencen en 60 días» en rojo por una faena terminada,
«dependen de una sola persona: CC716, CC738», un Total de 15 sobre filas que sumaban 14
y no recordaba qué había cambiado desde septiembre. Esto vigila el rediseño:

1. **Lo que mide renovación cuenta sólo las faenas con operación** (y el rojo no lo
   provoca una faena terminada), mientras «permisos vigentes» cuenta todos (el hecho
   legal) y se desglosa «N en operación + M sin operación».
2. **El Total suma las filas visibles**, y lo que no opera va aparte.
3. **El anexo recupera el detalle individual** (folio, N° DGAC, CC, vigencia, operadores)
   que la sección 2 agrupa, con todas las filas.
4. **«Página N de M» va en una línea y el documento tiene las páginas que el reparto
   predice** (con Edge, si está instalado): lo que se estimó es lo que se imprime.
"""

import json
import re
import shutil
import subprocess
import time
from datetime import date, datetime, timedelta, timezone as dt_timezone
from pathlib import Path

import pytest
from django.conf import settings
from django.contrib.auth.models import Permission, User
from django.urls import reverse

from apps.core.testing import pin_now
from apps.reporting import invariants
from apps.reporting.builder import build
from apps.reporting.models import ReportRun
from apps.reporting.pagination import (
    V2_ROSTER_CHARS_PER_LINE,
    plan_fits_with_coverage_v2,
    roster_row_px_v2,
)
from apps.reporting.summary import changes_view, executive_summary_v2
from apps.reporting.templatetags.report_svg import (
    coverage_state,
    render_coverage_bar,
)
from apps.reporting.v2_case import (
    CLOSING_CUTOFF,
    CUTOFF,
    PERIOD,
    _permit,
    make_case,
    make_closing_case,
)
from apps.reporting.views import MonthlyReportView

ROOT = Path(settings.BASE_DIR)
SNAPSHOTS = Path(__file__).parent / "snapshots"
V2_CSS = (ROOT / "static" / "css" / "report-a4-v2.css").read_text(encoding="utf-8")


@pytest.fixture
def case(db):
    return make_case()


@pytest.fixture
def payload(case):
    return build(PERIOD, cutoff=CUTOFF)[0]


def _reader(client):
    user = User.objects.create_user("lector", password="x")
    user.user_permissions.add(
        Permission.objects.get(
            codename="view_reportrun", content_type__app_label="reporting"
        )
    )
    client.force_login(user)
    return client


def _html(client, payload, period=PERIOD, **extra):
    ReportRun.objects.create(
        period=period, revision=0, generated_by="t", payload=payload, **extra
    )
    response = _reader(client).get(
        reverse("monthly-report"), {"period": f"{period:%Y-%m}"}
    )
    assert response.status_code == 200
    return response.content.decode()


def _text(html):
    """El texto visible de un trozo de HTML, con los espacios normalizados."""
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


def _page(html, number):
    """El HTML de una hoja del documento (entre sus `rpt-page`)."""
    return html.split('<div class="rpt-page')[number]


class TestRenewalCountsOnlyTheCentresWithOperation:
    def test_the_summary_separates_the_legal_total_from_the_renewal_figures(
        self, payload
    ):
        s = executive_summary_v2(payload)

        assert s["in_force_total"] == 10
        assert (s["in_force_operating"], s["in_force_outside"]) == (8, 2)
        assert (s["within_30"], s["within_60"]) == (7, 8)  # sin CC905 (a 2 días)
        assert s["cost_centres_total"] == 3
        assert s["without_permit"] == ["CC903"]
        assert s["enabled"] == 2

    def test_a_terminated_centre_does_not_turn_the_card_red(self, case):
        """**El rojo de octubre**: lo provocaba una faena terminada, CC716. Con todos
        los permisos de las faenas con operación a más de 60 días, la tarjeta queda en
        verde aunque un permiso sin operación venza en dos días."""
        from apps.operations.models import FlightPermission

        FlightPermission.objects.filter(
            cost_center__code__in=["CC901", "CC902"]
        ).update(valid_until=CUTOFF + timedelta(days=120))
        payload = build(PERIOD, cutoff=CUTOFF)[0]

        s = executive_summary_v2(payload)

        assert (
            payload["kpis"]["permits_expiring_30d"]["value"] == 1
        )  # clave vieja: CC905
        assert (s["within_30"], s["within_60"]) == (0, 0)
        assert s["kpis"]["expiring"] == "good"

    def test_the_first_to_expire_is_never_a_centre_without_operation(self, case):
        from apps.operations.models import FlightPermission

        FlightPermission.objects.filter(cost_center__code="CC901").update(
            valid_until=CUTOFF + timedelta(days=90)
        )
        payload = build(PERIOD, cutoff=CUTOFF)[0]

        s = executive_summary_v2(payload)

        # CC905 vence en 2 días, pero no opera: el primero es de CC902 (53 días).
        assert s["first_to_expire"]["cost_centre"] == "CC902"
        assert s["first_to_expire"]["days_remaining"] == 53

    def test_next_to_expire_is_one_row_per_centre_with_the_later_ones_in_brackets(
        self, case
    ):
        _permit(case["CC902"], start=date(2026, 9, 5), end=date(2027, 2, 1))
        payload = build(PERIOD, cutoff=CUTOFF)[0]

        rows = executive_summary_v2(payload)["next_centres"]

        assert [row["code"] for row in rows] == ["CC901", "CC902"]
        assert rows[0]["count"] == 7 and rows[0]["later_count"] == 0
        assert rows[1]["later_count"] == 1
        assert rows[1]["later_until"] == "2027-02-01"
        assert rows[0]["band"] == "critical" and rows[1]["band"] == "warning"

    def test_the_concentration_is_only_of_the_operating_centres(self, payload):
        c = payload["concentration"]

        assert c["cost_centres_on_one_person_operating"] == ["CC901"]
        assert (
            c["permits_with_one_operator_operating"],
            c["permits_in_force_operating"],
        ) == (7, 8)


class TestTheSummaryPage:
    def test_the_conclusion_has_symbols_and_the_outside_line(self, client, payload):
        html = _html(client, payload)
        summary = _page(html, 2)

        assert 'class="rpt2-verdict"' in summary
        assert "1 de 3 Centros de Costo sin permiso vigente" in summary
        assert "CC903" in summary
        assert "El primer permiso en vencer es" in summary
        assert "contando sólo los Centros de Costo con operación" in summary
        # Los dos permisos de faenas sin operación, cada uno con su aviso.
        assert summary.count("de un Centro de Costo sin operación") == 2
        assert "no se renueva; cerrar el permiso o dejarlo vencer" in summary
        assert "✕" in summary and "○" in summary

    def test_the_cards_split_the_legal_total(self, client, payload):
        summary = " ".join(_page(_html(client, payload), 2).split())

        assert "8 en operación + 2 sin operación" in summary
        assert "7 en 30 días o menos" in summary
        assert "Centros de Costo habilitados" in summary
        # Tarjeta de vencimientos con su símbolo (no sólo color).
        assert re.search(
            r"rpt2-tone-critical\">\s*<div class=\"rpt2-kpi-value\">✕ 8<", summary
        )

    def test_the_next_to_expire_block_says_per_centre(self, client, payload):
        summary = _page(_html(client, payload), 2)

        assert "Lo próximo que vence — por centro de costo" in summary
        assert summary.count('class="rpt2-next-cc"') == 2  # una fila por faena

    def test_the_old_per_permit_block_is_gone(self, client, payload):
        summary = _page(_html(client, payload), 2)

        assert "rpt-next-folio" not in summary
        assert "Y 4 más en la sección 2, permiso a permiso" not in summary


class TestChangesSinceTheLastReport:
    def test_without_a_previous_report_it_says_there_is_nothing_to_compare(
        self, client, payload
    ):
        summary = _page(_html(client, payload), 2)

        assert "Cambios desde el informe anterior" in summary
        assert "No hay informe del mes anterior con el que comparar" in summary

    def test_entered_left_awaiting_and_without_permit_are_listed(self, case, client):
        def edit(before):
            before["permits"] = [
                r for r in before["permits"] if r["cost_centre"] != "CC905"
            ]
            before["permits"].append(
                {
                    "folio": "JEJ-OLD-001",
                    "status": "approved",
                    "in_force": True,
                    "cost_centre": "CC901",
                }
            )
            before["cost_centres"][0]["permits_in_force"] = 0

        base = build(PERIOD, cutoff=CUTOFF)[0]
        previous = json.loads(json.dumps(base))
        edit(previous)
        ReportRun.objects.create(
            period=date(2026, 9, 1), revision=0, generated_by="t", payload=previous
        )
        html = _html(client, build(PERIOD, cutoff=CUTOFF)[0])
        summary = " ".join(_page(html, 2).split())

        assert "Contra el informe de 2026-09 (revisión 0" in summary
        assert "Entraron como vigentes:" in summary
        assert "Salieron de vigentes: JEJ-OLD-001" in summary
        assert "Recuperaron habilitación: CC901" in summary

    def test_no_changes_is_said_as_no_changes(self, case, client):
        base = build(PERIOD, cutoff=CUTOFF)[0]
        ReportRun.objects.create(
            period=date(2026, 9, 1), revision=0, generated_by="t", payload=base
        )
        payload = build(PERIOD, cutoff=CUTOFF)[0]

        view = changes_view(payload)

        assert view["unchanged"] is True
        assert "Sin cambios en los permisos vigentes" in _page(
            _html(client, payload), 2
        )

    def test_it_is_read_from_the_frozen_payload_and_never_recomputed(
        self, client, payload
    ):
        """Un informe congelado dice lo mismo el día que se reabra: la comparación es
        del payload, no de la base de hoy."""
        payload["changes"] = {
            "against": {
                "period": "2026-09",
                "revision": 3,
                "cutoff": "2026-09-30",
                "layout": 1,
            },
            "in_force": {"added": ["JEJ-X-1"], "removed": []},
            "awaiting": {"added": [], "removed": []},
            "without_permit": {"added": [], "removed": []},
            "kpis": {},
        }

        summary = _page(_html(client, payload), 2)

        assert "revisión 3, corte 30-09-2026" in summary
        assert "Entraron como vigentes: JEJ-X-1" in summary


class TestTheCoveragePage:
    def test_it_declares_its_universe(self, client, payload):
        cover = " ".join(_page(_html(client, payload), 4).split())

        assert "3 Centros de Costo con operación RPA y contrato vigente" in cover
        assert "van aparte, debajo de la tabla" in cover

    def test_the_total_adds_up_the_visible_rows_and_the_outside_block_completes_it(
        self, client, payload
    ):
        cover = _page(_html(client, payload), 4)
        rows = payload["cost_centres"]

        shown = sum(row["permits_in_force"] for row in rows)
        total = cover.split("rpt2-cov-total", 1)[1].split("rpt2-outside", 1)[0]
        assert shown == 8
        assert re.search(r"rpt2-c rpt2-strong rpt2-navy\">8<", total)
        assert (
            "+ Sin operación:" in cover and "CC905" in cover and "(terminado)" in cover
        )
        assert "CC904" in cover and "(no vuela)" in cover
        assert "Total de permisos vigentes:" in cover
        assert (
            "Total de permisos vigentes: 10 = 8 en Centros de Costo con operación + 2"
            in _text(cover)
        )

    def test_every_state_has_a_symbol_and_a_word(self, client, payload):
        cover = _page(_html(client, payload), 4)

        assert "✕ Renovar ahora" in cover  # CC901, a 28 días
        assert "▲ Por vencer" in cover  # CC902, a 53
        assert "✕ Sin habilitación" in cover  # CC903

    def test_the_concentration_is_corrected(self, client, payload):
        cover = _text(_page(_html(client, payload), 4))

        assert "7 de 8" in cover
        assert "Dependen de una sola persona: CC901" in cover
        assert "CC904" not in cover.split("Dependen de una sola persona", 1)[1]

    def test_the_stacked_bar_prints_its_figures(self, client, payload):
        cover = _page(_html(client, payload), 4)

        assert 'class="rpt2-covbar"' in cover
        assert "1 sin habilitación, 1 con permiso a ≤30 d" in cover

    def test_the_old_per_permit_total_is_gone(self, client, payload):
        cover = _page(_html(client, payload), 4)

        assert (
            "rpt-grid" not in cover
            and "Permisos con un único operador designado" in cover
        )


class TestTheCoverageBar:
    ROWS = [
        {"permits_in_force": 1, "band": "nominal"},
        {"permits_in_force": 2, "band": "warning"},
        {"permits_in_force": 1, "band": "critical"},
        {"permits_in_force": 0, "band": "critical"},
        {"permits_in_force": 0, "band": "critical"},
    ]

    def test_the_states_are_classified_by_the_worst_permit(self):
        assert [coverage_state(r) for r in self.ROWS] == [
            "nominal",
            "warning",
            "renew",
            "none",
            "none",
        ]

    def test_it_is_a_server_svg_with_the_figures_as_text(self):
        svg = render_coverage_bar(self.ROWS, "cov-1")

        assert "style=" not in svg and "<script" not in svg
        assert 'role="img"' in svg and 'aria-labelledby="cov-1-t cov-1-d"' in svg
        texts = re.findall(r"<text[^>]*>([^<]*)</text>", svg)
        assert (
            "1" in texts
            and "3 críticos: 2 sin habilitación, 1 con permiso a ≤30 d"
            in " ".join(texts)
        )
        desc = re.search(r"<desc[^>]*>(.*?)</desc>", svg).group(1)
        assert "Cobertura de 5 Centros de Costo" in desc
        assert (
            "3 críticos (2 sin habilitación y 1 con permiso a 30 días o menos)" in desc
        )

    def test_it_draws_a_segment_per_band_and_nothing_for_an_empty_one(self):
        svg = render_coverage_bar(self.ROWS[:2], "c")

        assert "rpt2-seg-nominal" in svg and "rpt2-seg-warning" in svg
        assert 'class="rpt2-seg rpt2-seg-critical"' not in svg

    def test_no_centres_still_says_so_without_dividing_by_zero(self):
        svg = render_coverage_bar([], "c")

        assert "Cobertura de 0 Centros de Costo" in svg


class TestTheAnnex:
    def test_it_lists_every_permit_with_its_dgac_number_and_operators(
        self, client, payload
    ):
        html = _html(client, payload)
        annex = html.split("Anexo · Registro permiso a permiso", 1)[1]

        for row in payload["permits"]:
            assert row["folio"] in annex
            if row["dgac_number"]:
                assert row["dgac_number"] in annex
        assert "Operador Uno" in annex and "Operador Dos" in annex
        assert annex.count("rpt2-reg-folio") == len(payload["permits"]) == 12
        assert "12 permisos: vigentes, en trámite y vencidos sin cerrar" in annex
        assert "En proceso" in annex and "Sin vigencia resuelta" in annex

    def test_the_outside_centres_are_flagged_in_the_annex(self, client, payload):
        annex = _html(client, payload).split("Anexo · Registro permiso a permiso", 1)[1]

        assert annex.count("rpt2-reg-flag") == 2  # CC904 y CC905
        assert "faena sin operación" in annex

    def test_a_permit_without_operators_is_still_in_the_register(self, case):
        """El anexo de siempre se omitía sin ningún nombre; el registro lista todo."""
        from apps.operations.models import FlightPermission

        for permit in FlightPermission.objects.all():
            permit.operators.clear()
        payload = build(PERIOD, cutoff=CUTOFF)[0]

        sheets = MonthlyReportView._sheets(payload)

        assert sum(len(s["rows"]) for s in sheets["roster_sheets"]) == 12

    def test_the_annex_total_is_declared_on_every_sheet(self):
        rows = [
            {
                "folio": f"JEJ-{n:03d}",
                "cost_centre": "CC1",
                "in_force": True,
                "in_operation": True,
                "status": "approved",
                "operators": [
                    "Nombre Apellido Largo",
                    "Otro Nombre Largo",
                    "Tercer Nombre",
                ],
                "aircraft": [],
                "valid_from": "2026-09-01",
                "valid_until": "2026-12-01",
                "days_remaining": 40,
            }
            for n in range(60)
        ]
        payload = {"meta": {"layout": 2}, "permits": rows, "cost_centres": []}

        sheets = MonthlyReportView._sheets(payload)["roster_sheets"]

        assert len(sheets) >= 2
        assert all(s["total"] == 60 for s in sheets)
        assert sum(len(s["rows"]) for s in sheets) == 60


class TestTheRosterEstimateIsByCharacters:
    def test_one_short_name_is_one_line(self):
        assert roster_row_px_v2({"operators": ["Ana Ruiz"]}) == 26

    def test_long_names_add_lines_where_two_would_not_fit(self):
        two_long = {"operators": ["Fabián Jorquera Toro", "Alejandra Contreras Pinto"]}

        assert sum(len(n) for n in two_long["operators"]) + 3 > V2_ROSTER_CHARS_PER_LINE
        assert roster_row_px_v2(two_long) == 26 + 15

    def test_no_operators_is_still_a_row(self):
        assert roster_row_px_v2({"operators": []}) == 26


class TestThePlanSharesTheSheetOnlyWhenItFits:
    def test_a_short_padron_lets_the_plan_ride_under_the_coverage(self):
        assert plan_fits_with_coverage_v2(3, 4) is True

    def test_eleven_centres_do_not_leave_room(self):
        """El caso de octubre: 11 faenas con la tabla del diseño 2 (letra de 8,5 pt) no
        dejan lugar al plan, que va a su hoja."""
        assert plan_fits_with_coverage_v2(11, 4) is False

    def test_the_outside_block_takes_room_too(self):
        edge = next(n for n in range(1, 12) if not plan_fits_with_coverage_v2(n, 4))

        assert plan_fits_with_coverage_v2(edge - 1, 4) is True
        assert plan_fits_with_coverage_v2(edge - 1, 4, outside_rows=3) is False

    def test_the_sheets_use_the_v2_section_names(self, case):
        payload = build(PERIOD, cutoff=CUTOFF)[0]

        sheets = MonthlyReportView._sheets(payload)

        # Con las dos faenas sin operación del caso, el bloque de debajo quita el lugar.
        assert sheets["plan_joins_coverage"] is False
        assert sheets["coverage_section"] == "coverage_v2"

    def test_a_tiny_padron_without_outside_centres_joins_the_plan(self):
        payload = {
            "meta": {"layout": 2},
            "permits": [],
            "cost_centres": [{"code": "CC1"}, {"code": "CC2"}],
        }

        sheets = MonthlyReportView._sheets(payload)

        assert sheets["plan_joins_coverage"] is True
        assert sheets["coverage_section"] == "coverage_plan_v2"


class TestTheDocumentHasTheSixPagesOfTheClosing:
    """El cierre de octubre (11 faenas, 6 con permisos): portada, resumen, permisos,
    cobertura, plan y anexo = **6** páginas, como el diseño."""

    def _closing(self):
        make_closing_case()
        return build(PERIOD, cutoff=CLOSING_CUTOFF)[0]

    def test_the_closing_shaped_report_is_six_pages(self, db):
        payload = self._closing()

        sheets = MonthlyReportView._sheets(payload, "x" * 200)

        assert len(sheets["permit_sheets"]) == 1
        assert sheets["plan_joins_coverage"] is False
        assert sheets["total_pages"] == 6
        assert [s["page"] for s in sheets["roster_sheets"]] == [6]

    def test_the_closing_has_no_outside_block_and_the_invariants_hold(self, db):
        payload = self._closing()

        assert payload["outside_centres"] == []
        assert invariants.violations(payload) == []
        assert payload["kpis"]["permits_in_force"]["value"] == 15
        assert payload["kpis"]["permits_expiring_30d_operating"]["value"] == 7
        assert payload["kpis"]["permits_expiring_60d_operating"]["value"] == 12

    def test_every_page_says_page_n_of_the_total(self, db, client):
        payload = self._closing()
        html = _html(client, payload, period=PERIOD)
        ids = re.findall(r'<div class="rpt-foot-id">\s*(.*?)\s*</div>', html, re.S)

        assert len(ids) == 6
        for index, text in enumerate(ids, 1):
            assert f"Página {index} de 6" in " ".join(text.split())
        # Una línea: el rótulo no se parte (`white-space: nowrap`, en la hoja base).
        base = (ROOT / "static" / "css" / "report-a4.css").read_text(encoding="utf-8")
        assert re.search(r"\.rpt-foot-id \{[^}]*white-space: nowrap", base)

    def test_the_foot_of_the_redesigned_sheets_is_not_below_eight_and_a_half_points(
        self,
    ):
        match = re.search(
            r"\.rpt2-page \.rpt-foot \{[^}]*font-size:\s*([\d.]+)px", V2_CSS
        )

        assert match and float(match.group(1)) >= 11.3


def _edge():
    for candidate in (
        shutil.which("msedge"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        shutil.which("google-chrome"),
        shutil.which("chromium"),
    ):
        if candidate and Path(candidate).exists():
            return candidate
    return None


def _pdf_of(html, directory):
    """El PDF que Edge sin cabeza imprime de `html` (con el CSS en línea): el método de
    `LV-263`, el mismo que usa quien descarga el informe."""

    def inline(match):
        href = re.search(r'href="([^"]+)"', match.group(0)).group(1)
        media = re.search(r'media="([^"]+)"', match.group(0))
        path = ROOT / "static" / href.split("/static/", 1)[1].split("?")[0]
        tag = f' media="{media.group(1)}"' if media else ""
        return f"<style{tag}>{path.read_text(encoding='utf-8')}</style>"

    page = re.sub(r'<link[^>]*rel="stylesheet"[^>]*>', inline, html)
    page = re.sub(r"<script\b[^>]*>.*?</script>", "", page, flags=re.S)
    source = Path(directory) / "report.html"
    source.write_text(page, encoding="utf-8")
    pdf = Path(directory) / "report.pdf"
    subprocess.run(
        [
            _edge(),
            "--headless=new",
            "--disable-gpu",
            f"--user-data-dir={Path(directory) / 'profile'}",
            "--no-pdf-header-footer",
            f"--print-to-pdf={pdf}",
            source.as_uri(),
        ],
        check=True,
        timeout=180,
    )
    # Edge devuelve antes de terminar de escribir: se espera al archivo.
    for _attempt in range(80):
        if pdf.exists() and pdf.stat().st_size > 0:
            time.sleep(1)
            break
        time.sleep(0.5)
    return pdf


@pytest.mark.skipif(_edge() is None, reason="sin Edge/Chrome para imprimir a PDF")
class TestThePrintedPdfIsWhatTheSheetsPredict:
    """Con un navegador sin cabeza (`--print-to-pdf`) y `pypdf`: lo que `_sheets`
    estima es lo que se imprime. Si una estimación queda corta, una fila se recorta
    contra el pie sin avisar; acá se vería como un folio que falta en el PDF."""

    @pytest.fixture(autouse=True)
    def _pypdf(self):
        return pytest.importorskip("pypdf")

    def _check(self, client, payload, tmp_path, expected_pages=None):
        pytest.importorskip("pypdf")
        from pypdf import PdfReader

        html = _html(client, payload)
        predicted = MonthlyReportView._sheets(payload)["total_pages"]
        reader = PdfReader(str(_pdf_of(html, tmp_path)))
        pages = [page.extract_text() for page in reader.pages]

        assert len(pages) == predicted
        if expected_pages is not None:
            assert len(pages) == expected_pages
        for index, text in enumerate(pages, 1):
            flat = " ".join(text.split())
            assert len(re.findall(r"Página \d+ de \d+", flat)) == 1, index
            assert f"Página {index} de {predicted}" in flat
        full = " ".join(" ".join(pages).split())
        for row in payload["permits"]:
            assert row["folio"] in full, row["folio"]
        self._every_group_is_printed_above_the_foot(reader, payload)
        return pages

    @staticmethod
    def _every_group_is_printed_above_the_foot(reader, payload):
        """Que cada faena de cada hoja de permisos se imprima **sobre el pie**.

        ⚠️ El cuerpo es `overflow: hidden`: una faena de más se **recorta** del dibujo, y
        su texto puede quedar en el PDF o no, así que «el folio está» no prueba nada (el
        anexo los lleva todos). Lo que prueba es **dónde** cae el detalle de cada faena,
        en la hoja que `_sheets` le asignó: el pie empieza a 1055,5 px de 1123 (50,6 pt
        desde el borde de abajo) y ningún folio de la sección 2 puede estar más abajo ni
        faltar. Es lo que falla si una estimación del reparto queda corta.
        """
        limit = (1123 - 1055.5) * 0.75
        for sheet in MonthlyReportView._sheets(payload)["permit_sheets"]:
            seen = {}

            def visit(text, cm, tm, _font, _size, seen=seen):
                for folio in re.findall(r"JEJ-\d{4}-\d{3}", text or ""):
                    y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
                    seen[folio] = min(y, seen.get(folio, y))

            reader.pages[sheet["page"] - 1].extract_text(visitor_text=visit)
            expected = {f for group in sheet["groups"] for f in group["folios"]}
            assert expected <= set(seen), (sheet["page"], sorted(expected - set(seen)))
            low = {f: y for f, y in seen.items() if f in expected and y <= limit}
            assert not low, (sheet["page"], low, limit)

    def test_the_closing_shaped_report_prints_six_pages_without_losing_a_folio(
        self, db, client, tmp_path
    ):
        make_closing_case()
        payload = build(PERIOD, cutoff=CLOSING_CUTOFF)[0]

        self._check(client, payload, tmp_path, expected_pages=6)

    def test_the_case_with_everything_prints_the_predicted_pages(
        self, case, client, tmp_path
    ):
        payload = build(PERIOD, cutoff=CUTOFF)[0]

        pages = self._check(client, payload, tmp_path)

        assert any("vencidos sin cerrar" in p.lower() for p in pages)

    def test_the_eleven_centre_snapshot_payload_prints_the_predicted_pages(
        self, db, client, tmp_path, monkeypatch
    ):
        pin_now(monkeypatch, datetime(2026, 10, 27, 15, 0, tzinfo=dt_timezone.utc))
        payload = json.loads((SNAPSHOTS / "payload_2026_10_v2.json").read_text("utf-8"))

        self._check(client, payload, tmp_path)

    def test_a_long_list_of_centres_spreads_without_clipping_a_single_row(
        self, db, client, tmp_path
    ):
        """El caso que **sí** desborda si la estimación queda corta: catorce faenas con
        un permiso y sus folios no caben en una hoja (1082 px contra 1055)."""
        from apps.registry.models import CostCenter

        for n in range(14):
            centre = CostCenter.objects.create(
                code=f"CC9{40 + n}", name=f"Faena {n}", operates_flights=True
            )
            _permit(
                centre, start=date(2026, 9, 1), end=date(2026, 12, 1) + timedelta(n)
            )
        payload = build(PERIOD, cutoff=CUTOFF)[0]

        pages = self._check(client, payload, tmp_path)

        assert len(pages) >= 5  # portada, resumen, 2 hojas de permisos, cobertura...

    def test_august_prints_five_pages_as_always(self, db, client, tmp_path):
        from pypdf import PdfReader

        payload = json.loads((SNAPSHOTS / "payload_2026_08.json").read_text("utf-8"))
        html = _html(client, payload, period=date(2026, 8, 1))
        reader = PdfReader(str(_pdf_of(html, tmp_path)))

        assert len(reader.pages) == 5
