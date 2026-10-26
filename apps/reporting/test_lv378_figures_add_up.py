"""LV-378 (PR 1): las cifras del informe cuadran entre sí.

El informe de octubre (emitido con corte anticipado) salió con un Total de 15 sobre
filas que sumaban 14, una cobertura «5/11» que no contaba a la faena que el resumen sí
contaba y una observación que hablaba de permisos vigentes de una faena con cero.
Todo sale del mismo payload: lo que se prueba acá es que sus partes **no se
contradicen** (`invariants.py`) y que los cuatro defectos de fondo están cerrados:

1. los conteos por faena salen de las filas de permisos (una sola fuente);
2. lo que mide renovación cuenta sólo las faenas con operación, y las demás van aparte;
3. un permiso vigente al corte que se cierra **después** de él no desaparece
   (el caso del 1-nov: `expire_permissions` corre a las 05:30, el cierre a las 06:30);
4. un aprobado vencido sin cerrar no se imprime como «en trámite».

El caso ficticio (centro terminado con permiso, otro que no vuela, siete permisos
iguales, un vencido, uno en trámite) está en `v2_case.py`. Datos ficticios.
"""

import copy
import json
from datetime import date, datetime, timezone as dt_timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.contrib.auth.models import Permission, User
from django.core.management import call_command
from django.urls import reverse

from apps.core.testing import pin_now
from apps.operations.models import FlightPermission
from apps.registry.models import CostCenter
from apps.reporting import invariants
from apps.reporting.builder import build, collect_permits
from apps.reporting.checks import narrative_vs_figures, pre_issue_warnings
from apps.reporting.models import ReportRun
from apps.reporting.v2_case import CUTOFF, PERIOD, _permit, make_case

SNAPSHOTS = Path(__file__).parent / "snapshots"


@pytest.fixture
def case(db):
    return make_case()


@pytest.fixture
def payload(case):
    return build(PERIOD, cutoff=CUTOFF)[0]


def _kpi(payload, key):
    return payload["kpis"][key]["value"]


def _codes(rows):
    return [row["code"] for row in rows]


class TestTheLayoutIsOnlyWrittenInNewReports:
    def test_a_new_payload_declares_layout_two(self, payload):
        assert payload["meta"]["layout"] == 2

    def test_a_closed_months_payload_has_no_layout(self):
        """Agosto se vuelve a dibujar desde su payload con las plantillas de hoy: si
        el payload congelado trajera la llave, cambiaría de papel."""
        frozen = json.loads((SNAPSHOTS / "payload_2026_08.json").read_text("utf-8"))

        assert "layout" not in frozen["meta"]
        assert invariants.violations(frozen) == []  # no se juzga con cuentas nuevas


class TestPermitsKnowTheirCentre:
    def test_each_permit_says_whether_its_centre_is_in_the_coverage(self, payload):
        by_centre = {}
        for row in payload["permits"]:
            by_centre.setdefault(row["cost_centre"], set()).add(row["in_operation"])

        assert by_centre == {
            "CC901": {True},
            "CC902": {True},
            "CC903": {True},
            "CC904": {False},
            "CC905": {False},
        }

    def test_the_outside_centres_carry_their_reason(self, payload):
        outside = {row["code"]: row for row in payload["outside_centres"]}

        assert list(outside) == ["CC904", "CC905"]
        assert outside["CC904"]["reason"] == "not_flying"
        assert outside["CC905"]["reason"] == "closed"
        assert outside["CC905"]["name"] == "Faena Terminada"
        assert outside["CC905"]["permits_in_force"] == 1
        assert outside["CC905"]["days_remaining"] == 2
        assert outside["CC905"]["band"] == "critical"
        assert len(outside["CC905"]["folios"]) == 1

    def test_an_archived_centre_is_outside_too(self, case):
        CostCenter.objects.filter(code="CC901").update(is_active=False)

        payload = build(PERIOD, cutoff=CUTOFF)[0]

        reasons = {r["code"]: r["reason"] for r in payload["outside_centres"]}
        assert reasons["CC901"] == "archived"
        assert "CC901" not in _codes(payload["cost_centres"])


class TestTheFiguresComeFromTheRows:
    def test_the_rows_of_the_coverage_add_up_to_the_operating_permits(self, payload):
        rows = payload["cost_centres"]

        assert sum(row["permits_in_force"] for row in rows) == _kpi(
            payload, "permits_in_force_operating"
        )
        assert _kpi(payload, "permits_in_force") == 10
        assert _kpi(payload, "permits_in_force_operating") == 8
        assert _kpi(payload, "permits_in_force_outside") == 2

    def test_the_total_is_the_sum_of_the_rows_plus_the_outside_block(self, payload):
        """**El defecto de octubre**: el Total decía 15 y las filas sumaban 14."""
        inside = sum(row["permits_in_force"] for row in payload["cost_centres"])
        outside = sum(row["permits_in_force"] for row in payload["outside_centres"])

        assert inside + outside == _kpi(payload, "permits_in_force")

    def test_the_coverage_denominator_is_the_listed_centres(self, payload):
        assert _kpi(payload, "cost_centres_with_operation") == 3
        assert _codes(payload["cost_centres"]) == ["CC901", "CC902", "CC903"]
        assert _kpi(payload, "cost_centres_without_permit") == 1

    def test_the_centre_rows_use_the_state_at_the_cutoff(self, payload):
        rows = {row["code"]: row for row in payload["cost_centres"]}

        assert rows["CC901"]["permits_in_force"] == 7
        assert rows["CC901"]["days_remaining"] == 28
        assert rows["CC901"]["permits_expiring_30d"] == 7
        assert rows["CC902"]["permits_in_force"] == 1
        assert rows["CC902"]["permits_lapsed"] == 1
        assert rows["CC902"]["days_remaining"] == 53
        assert rows["CC903"]["permits_in_force"] == 0
        assert rows["CC903"]["permits_awaiting"] == 1
        assert rows["CC903"]["band"] == "critical"  # no poder volar es lo peor

    def test_renewal_figures_count_only_the_centres_with_operation(self, payload):
        """Sin CC905 (que vence en 2 días y se deja vencer) el rojo es legítimo
        sólo si hay vencimientos en operación."""
        assert _kpi(payload, "permits_expiring_30d") == 8  # clave vieja: todos
        assert _kpi(payload, "permits_expiring_30d_operating") == 7
        assert _kpi(payload, "permits_expiring_60d") == 9
        assert _kpi(payload, "permits_expiring_60d_operating") == 8

    def test_the_old_keys_keep_their_meaning(self, payload):
        """El comparador y los informes emitidos dependen de ellas."""
        assert _kpi(payload, "permits_awaiting") == 1
        assert _kpi(payload, "permits_lapsed") == 1
        assert payload["concentration"]["permits_in_force"] == 10
        assert payload["concentration"]["cost_centres_on_one_person"] == [
            "CC901",
            "CC904",
            "CC905",
        ]

    def test_concentration_counts_only_the_operating_centres(self, payload):
        concentration = payload["concentration"]

        assert concentration["permits_in_force_operating"] == 8
        assert concentration["permits_with_one_operator_operating"] == 7
        assert concentration["cost_centres_on_one_person_operating"] == ["CC901"]


class TestTheInvariantsHoldOnTheCase:
    def test_the_builder_output_breaks_none(self, payload):
        assert invariants.violations(payload) == []
        assert invariants.check(payload) == []


def _broken(payload, mutate):
    changed = copy.deepcopy(payload)
    mutate(changed)
    return {code for code, _data in invariants.violations(changed)}


class TestEveryInvariantIsBrokenOnPurpose:
    """«Rompe cada arreglo una vez»: una invariante que no se ve fallar no vigila."""

    def test_i1_the_denominator_must_be_the_listed_centres(self, payload):
        def mutate(p):
            p["kpis"]["cost_centres_with_operation"]["value"] += 1

        assert "I1" in _broken(payload, mutate)

    def test_i2_without_permit_must_match_the_rows_at_zero(self, payload):
        def mutate(p):
            p["kpis"]["cost_centres_without_permit"]["value"] = 0

        assert "I2" in _broken(payload, mutate)

    def test_i3_the_total_must_be_the_rows_plus_the_outside_block(self, payload):
        """El defecto de octubre, reproducido: el Total dice una cosa y las filas otra."""

        def mutate(p):
            p["kpis"]["permits_in_force"]["value"] += 1

        assert "I3" in _broken(payload, mutate)

    def test_i3_a_row_that_gains_a_permit_in_the_table_only(self, payload):
        def mutate(p):
            p["cost_centres"][0]["permits_in_force"] += 1

        assert "I3" in _broken(payload, mutate)

    def test_i4_the_awaiting_must_add_up_too(self, payload):
        def mutate(p):
            p["cost_centres"][2]["permits_awaiting"] = 0

        assert "I4" in _broken(payload, mutate)

    def test_i5_no_permit_without_a_home(self, payload):
        def mutate(p):
            p["permits"][0]["cost_centre"] = "CC999"

        assert "I5" in _broken(payload, mutate)

    def test_i5_the_operation_mark_must_match_the_membership(self, payload):
        def mutate(p):
            p["permits"][0]["in_operation"] = False

        assert "I5" in _broken(payload, mutate)

    def test_i6_the_first_expiry_is_the_minimum_of_the_centre(self, payload):
        def mutate(p):
            p["cost_centres"][0]["days_remaining"] = 99

        assert "I6" in _broken(payload, mutate)

    def test_i7_the_renewal_figures_are_recounted_from_the_rows(self, payload):
        def mutate(p):
            p["kpis"]["permits_expiring_30d_operating"]["value"] = 8

        assert "I7" in _broken(payload, mutate)

    def test_i7_the_concentration_names_only_covered_centres(self, payload):
        def mutate(p):
            p["concentration"]["cost_centres_on_one_person_operating"] = ["CC905"]

        assert "I7" in _broken(payload, mutate)

    def test_i8_every_row_fits_a_block(self, payload):
        def mutate(p):
            p["permits"][0]["in_force"] = False
            p["permits"][0]["status"] = "denied"

        assert "I8" in _broken(payload, mutate)


class TestTheScreenWarnsWhenTheFiguresDoNotAddUp:
    def test_the_pre_issue_warnings_carry_the_invariant_messages(self, payload):
        payload["kpis"]["permits_in_force"]["value"] += 1

        warnings = pre_issue_warnings(payload, None)

        assert any("no cuadran" in warning for warning in warnings)

    def test_a_consistent_payload_adds_no_invariant_warning(self, payload):
        warnings = pre_issue_warnings(payload, None)

        assert not any("no cuadran" in warning for warning in warnings)


class TestAPermitLiveAtTheCutoffDoesNotVanish:
    """**El caso del 1 de noviembre.** `expire_permissions` corre a las 05:30 y pasa a
    `expired` el permiso vigente hasta el 31-10; el cierre corre a las 06:30. La
    consulta filtraba por el estado de **hoy** y lo dejaba fuera."""

    CLOSING_CUTOFF = date(2026, 10, 31)

    @pytest.fixture
    def closing_day(self, db, monkeypatch):
        centre = CostCenter.objects.create(
            code="CC906", name="Faena Cierre", operates_flights=True
        )
        # Vigente hasta el último día del mes.
        until_the_end = _permit(centre, start=date(2026, 8, 1), end=self.CLOSING_CUTOFF)
        # Aprobado, venció el día 29 y nadie lo cerró antes del corte.
        lapsed = _permit(centre, start=date(2026, 7, 1), end=date(2026, 10, 29))
        # Venció y se cerró el día 12, mucho antes del corte: es historia.
        history = _permit(centre, start=date(2026, 7, 1), end=date(2026, 10, 10))
        pin_now(monkeypatch, datetime(2026, 10, 12, 8, 0, tzinfo=dt_timezone.utc))
        call_command("expire_permissions")
        # El timer de las 05:30 del 1 de noviembre.
        pin_now(monkeypatch, datetime(2026, 11, 1, 8, 30, tzinfo=dt_timezone.utc))
        call_command("expire_permissions")
        return SimpleNamespace(
            until_the_end=until_the_end, lapsed=lapsed, history=history
        )

    def test_the_job_really_closed_them(self, closing_day):
        for permit in (
            closing_day.until_the_end,
            closing_day.lapsed,
            closing_day.history,
        ):
            permit.refresh_from_db()
            assert permit.status == FlightPermission.STATUS_EXPIRED

    def test_a_permit_valid_through_the_cutoff_is_still_in_force(self, closing_day):
        rows = {row["folio"]: row for row in collect_permits(self.CLOSING_CUTOFF)}

        row = rows[closing_day.until_the_end.internal_folio]
        assert row["status"] == "approved"
        assert row["in_force"] is True
        assert row["days_remaining"] == 0

    def test_one_that_had_lapsed_before_the_cutoff_is_listed_as_lapsed(
        self, closing_day
    ):
        rows = {row["folio"]: row for row in collect_permits(self.CLOSING_CUTOFF)}

        row = rows[closing_day.lapsed.internal_folio]
        assert (row["status"], row["in_force"]) == ("approved", False)
        assert row["days_remaining"] == -2

    def test_history_does_not_grow_the_report(self, closing_day):
        """Lo que se cerró antes del corte no vuelve: sin esto cada informe
        arrastraría todos los vencidos de siempre."""
        folios = {row["folio"] for row in collect_permits(self.CLOSING_CUTOFF)}

        assert closing_day.history.internal_folio not in folios

    def test_the_payload_still_counts_it_and_the_figures_add_up(self, closing_day):
        payload = build(date(2026, 10, 1), cutoff=self.CLOSING_CUTOFF)[0]

        assert _kpi(payload, "permits_in_force") == 1
        assert _kpi(payload, "permits_lapsed") == 1
        assert invariants.violations(payload) == []


@pytest.mark.parametrize("layout", [1, 2], ids=["v1", "v2"])
class TestALapsedPermitIsNotAwaitingTheDgac:
    """Los dos diseños: el informe de siempre (payload sin `layout`) y el nuevo."""

    @pytest.fixture
    def paper(self, case, client, layout):
        payload = build(PERIOD, cutoff=CUTOFF)[0]
        if layout == 1:
            payload["meta"].pop("layout")  # como un informe emitido antes de LV-378
        ReportRun.objects.create(
            period=PERIOD, revision=0, generated_by="test", payload=payload
        )
        user = User.objects.create_user("lector", password="x")
        user.user_permissions.add(
            Permission.objects.get(
                codename="view_reportrun", content_type__app_label="reporting"
            )
        )
        client.force_login(user)
        return client.get(reverse("monthly-report"), {"period": "2026-10"})

    def test_the_sheets_split_requested_from_lapsed(self, paper, layout):
        last = paper.context["permit_sheets"][-1]

        assert [row["cost_centre"] for row in last["awaiting"]] == ["CC903"]
        assert [row["cost_centre"] for row in last["lapsed"]] == ["CC902"]
        assert all(row["status"] == "requested" for row in last["awaiting"])

    def test_the_paper_prints_it_under_its_own_heading(self, paper, layout):
        html = paper.content.decode()

        assert "Vencidos sin cerrar" in html
        # «En proceso» es sólo de la solicitud de CC903 —en la sección 2 y, en el
        # diseño 2, también en su fila del anexo—, nunca del vencido de CC902.
        assert html.count(">En proceso<") == (1 if layout == 1 else 2)

    def test_the_roster_still_lists_every_permit(self, paper, layout):
        listed = sum(len(sheet["rows"]) for sheet in paper.context["roster_sheets"])

        assert listed == 12  # 10 vigentes + 1 en trámite + 1 vencido sin cerrar

    def test_a_report_without_lapsed_permits_prints_no_such_block(
        self, db, client, layout
    ):
        """Los informes ya emitidos no cambian: sin vencidos no hay bloque."""
        frozen = json.loads((SNAPSHOTS / "payload_2026_08.json").read_text("utf-8"))
        ReportRun.objects.create(
            period=date(2026, 8, 1), revision=0, generated_by="t", payload=frozen
        )
        user = User.objects.create_user("lector", password="x")
        user.user_permissions.add(
            Permission.objects.get(
                codename="view_reportrun", content_type__app_label="reporting"
            )
        )
        client.force_login(user)

        html = client.get(reverse("monthly-report"), {"period": "2026-08"}).content

        assert b"Vencidos sin cerrar" not in html


class TestWhatChangedSinceTheLastReport:
    def test_without_a_report_of_the_previous_month_there_is_nothing_to_compare(
        self, payload
    ):
        """`None` y no «sin cambios»: son afirmaciones distintas."""
        assert payload["changes"] is None

    def test_it_is_frozen_against_the_last_revision_of_the_previous_month(self, case):
        before = build(PERIOD, cutoff=CUTOFF)[0]
        before["permits"] = before["permits"][:-1]  # sale el de CC905
        before["permits"].append(
            {
                "folio": "JEJ-OLD-001",
                "status": "approved",
                "in_force": True,
                "cost_centre": "CC901",
            }
        )
        before["cost_centres"][0]["permits_in_force"] = 0  # CC901 sin habilitación
        ReportRun.objects.create(
            period=date(2026, 9, 1), revision=0, generated_by="t", payload=before
        )

        after = build(PERIOD, cutoff=CUTOFF)[0]

        changes = after["changes"]
        assert changes["against"] == {
            "period": "2026-09",
            "revision": 0,
            "cutoff": "2026-10-26",
            "layout": 2,
        }
        assert "JEJ-OLD-001" in changes["in_force"]["removed"]
        assert len(changes["in_force"]["added"]) == 1  # el de CC905
        assert changes["without_permit"] == {"added": [], "removed": ["CC901"]}
        assert changes["kpis"]["permits_in_force"] == {"before": 10, "after": 10}

    def test_a_previous_report_without_layout_is_declared_as_layout_one(self, case):
        old = json.loads((SNAPSHOTS / "payload_2026_08.json").read_text("utf-8"))
        ReportRun.objects.create(
            period=date(2026, 9, 1), revision=0, generated_by="t", payload=old
        )

        after = build(PERIOD, cutoff=CUTOFF)[0]

        assert after["changes"]["against"]["layout"] == 1
        # No se inventa un valor que el informe anterior no traía.
        assert after["changes"]["kpis"]["permits_awaiting"]["before"] == 1

    def test_the_comparison_screen_says_the_format_changed(self, case, client):
        old = json.loads((SNAPSHOTS / "payload_2026_08.json").read_text("utf-8"))
        ReportRun.objects.create(
            period=date(2026, 9, 1), revision=0, generated_by="t", payload=old
        )
        new = ReportRun.objects.create(
            period=PERIOD,
            revision=0,
            generated_by="t",
            payload=build(PERIOD, cutoff=CUTOFF)[0],
        )
        user = User.objects.create_user("lector", password="x")
        user.user_permissions.add(
            Permission.objects.get(
                codename="view_reportrun", content_type__app_label="reporting"
            )
        )
        client.force_login(user)

        html = client.get(reverse("monthly-report-compare", args=[new.pk])).content
        text = html.decode()

        assert "Formato del documento: v1 → v2" in text
        # Las llaves nuevas del informe viejo no existen: «—», no cero.
        assert "Permisos vigentes en faenas con operación" in text


def _run(note="", findings=()):
    return SimpleNamespace(period_note=note, findings=list(findings))


def _figures(**centres):
    """`{código: (vigentes, en trámite)}` como filas de la cobertura."""
    return {
        "cost_centres": [
            {"code": code, "permits_in_force": v, "permits_awaiting": a}
            for code, (v, a) in centres.items()
        ]
    }


class TestTheNarrativeDoesNotContradictTheFigures:
    def test_permits_in_force_of_a_centre_with_none_is_flagged(self):
        """El caso de octubre: «permisos vigentes del CC 706» con CC706 en cero."""
        payload = _figures(CC706=(0, 1))
        run = _run(note="Los permisos vigentes del CC 706 renovaron en octubre.")

        (warning,) = narrative_vs_figures(payload, run)

        assert "CC706" in warning
        assert "0 vigentes" in warning and "1 en trámite" in warning

    def test_without_a_current_permit_does_not_warn(self):
        payload = _figures(CC706=(0, 1))
        run = _run(note="CC706 está sin permiso vigente y espera a la DGAC.")

        assert narrative_vs_figures(payload, run) == []

    def test_a_negation_before_the_word_is_enough(self):
        payload = _figures(CC706=(0, 1))
        run = _run(note="CC706 no tiene permisos vigentes.")

        assert narrative_vs_figures(payload, run) == []

    def test_the_other_way_round_without_permit_for_a_centre_that_has_them(self):
        payload = _figures(CC738=(7, 0))
        run = _run(findings=[{"title": "Cobertura", "text": "CC738 sin permiso."}])

        (warning,) = narrative_vs_figures(payload, run)

        assert "CC738" in warning and "7" in warning

    def test_a_true_statement_does_not_warn(self):
        payload = _figures(CC738=(7, 0))
        run = _run(note="CC738 mantiene sus permisos vigentes hasta noviembre.")

        assert narrative_vs_figures(payload, run) == []

    def test_each_sentence_is_judged_on_its_own(self):
        payload = _figures(CC706=(0, 1), CC738=(7, 0))
        run = _run(note="CC738 tiene permisos vigentes. CC706 no tiene ninguno.")

        assert narrative_vs_figures(payload, run) == []

    def test_a_centre_outside_the_coverage_is_judged_with_its_own_figures(self):
        payload = {
            "cost_centres": [],
            "outside_centres": [
                {"code": "CC716", "permits_in_force": 1, "permits_awaiting": 0}
            ],
        }
        run = _run(note="CC716 no tiene permiso.")

        assert len(narrative_vs_figures(payload, run)) == 1

    def test_unknown_centres_are_left_to_the_other_check(self):
        run = _run(note="Los permisos vigentes de CC999 vencen pronto.")

        assert narrative_vs_figures(_figures(CC706=(0, 0)), run) == []

    def test_there_is_nothing_to_check_without_a_run(self):
        assert narrative_vs_figures(_figures(CC706=(0, 0)), None) == []

    def test_it_reaches_the_screen_warnings(self):
        payload = _figures(CC706=(0, 1))
        run = SimpleNamespace(
            period_note="Los permisos vigentes del CC 706 renovaron.",
            findings=[{"title": "x", "text": "y"}],
            is_editable=True,
        )

        assert any("CC706" in w for w in pre_issue_warnings(payload, run))
