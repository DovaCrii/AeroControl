"""LV-445: la sección 5 dibujada, congelada y editable.

Lo que protege, por orden de gravedad:

1. **Los informes congelados no cambian**: sin `manual` en el payload no hay hoja, ni
   líneas de portada, ni cambia la numeración de páginas.
2. **«Pendiente», no 0**: un `None` se dibuja ámbar punteado.
3. La numeración «Página N de M» sigue cuadrando con la hoja nueva en medio.
4. La observación escrita viaja a la revisión siguiente, tiene tope y exige permiso.
5. Las invariantes I9 e I10 detectan un payload alterado a mano.
6. La migración de datos no pisa lo que alguien editó.

Datos ficticios (`CC90x`, `RPA-90xx`) y fechas fijas.
"""

import importlib
import json
import os
import re
from datetime import date, datetime, timezone as dt_timezone
from pathlib import Path

import pytest
from django.apps import apps as django_apps
from django.contrib.auth.models import Permission, User
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.core.testing import pin_now
from apps.reporting import invariants
from django.utils.translation import ngettext

from apps.reporting.builder import build, find_missing
from apps.reporting.checks import manual_warnings, pre_issue_warnings
from apps.reporting.forms import PeriodNoteForm
from apps.reporting.manual_case import CUTOFF, PERIOD, make_manual_case
from apps.reporting.models import ReportRun, ReportTemplate
from apps.reporting.test_snapshot_monthly import _check
from apps.reporting.views import MonthlyReportView

SNAPSHOTS = Path(__file__).parent / "snapshots"
NOW = datetime(2026, 12, 2, 15, 0, tzinfo=dt_timezone.utc)
NOTE = "Nota ficticia sobre el cumplimiento del Manual para la prueba."


def _user(name, *codenames):
    user = User.objects.create_user(name, password="x")
    for codename in codenames:
        user.user_permissions.add(
            Permission.objects.get(
                codename=codename, content_type__app_label="reporting"
            )
        )
    return user


@pytest.fixture
def case_payload(db):
    make_manual_case()
    return build(PERIOD, cutoff=CUTOFF)[0]


def _page(client, payload, period=PERIOD, **extra):
    ReportRun.objects.create(
        period=period, revision=0, generated_by="t", payload=payload, **extra
    )
    return client.get(reverse("monthly-report"), {"period": f"{period:%Y-%m}"})


@pytest.fixture
def reader(client, db):
    client.force_login(_user("reader", "view_reportrun"))
    return client


def _foots(html):
    return re.findall(r"Página (\d+) de (\d+)", " ".join(html.split()))


class TestTheSheetIsDrawnOnlyWhenThePayloadCarriesIt:
    def test_a_report_with_manual_draws_section_five_between_the_plan_and_the_annex(
        self, reader, db
    ):
        from apps.reporting.v2_case import _permit

        sites = make_manual_case()
        _permit(sites[0], start=date(2026, 11, 1), end=date(2027, 3, 1))
        payload = build(PERIOD, cutoff=CUTOFF)[0]

        html = _page(reader, payload).content.decode()

        assert "Cumplimiento del Manual de Operaciones (Act. 19)" in html
        assert "5.1 REG-016 por Centro de Costo" in html
        assert "5.3 Qué cambió con la Act. 19" in html
        assert html.index("Cumplimiento del Manual") > html.index(
            "Plan de normalización"
        )
        assert html.index("Cumplimiento del Manual") < html.index("Anexo · Registro")

    def test_the_page_numbers_add_up_with_the_new_sheet(self, reader, case_payload):
        html = _page(reader, case_payload).content.decode()
        foots = _foots(html)
        total = MonthlyReportView._sheets(case_payload)["total_pages"]

        assert [int(page) for page, _of in foots] == list(range(1, total + 1))
        assert {int(of) for _page_number, of in foots} == {total}

    def test_a_frozen_report_without_the_key_is_drawn_exactly_as_before(
        self, reader, db
    ):
        frozen = json.loads((SNAPSHOTS / "payload_2026_10_v2.json").read_text("utf-8"))
        assert "manual" not in frozen
        before = MonthlyReportView._sheets(frozen)

        html = _page(reader, frozen, date(2026, 10, 1)).content.decode()

        assert before["manual_sheets"] == []
        assert "Cumplimiento del Manual" not in html
        assert "rpt2-man" not in html
        assert "Marco regulatorio" not in html
        assert {int(of) for _page_number, of in _foots(html)} == {before["total_pages"]}

    def test_the_cover_lines_appear_only_if_the_payload_has_them(
        self, reader, case_payload
    ):
        fresh = _page(reader, case_payload).content.decode()

        assert "Marco regulatorio: Manual de Operaciones AOC" in fresh
        assert "control interno (INS-096)" in fresh
        ReportRun.objects.all().delete()
        old = json.loads((SNAPSHOTS / "payload_2026_08.json").read_text("utf-8"))
        assert "manual_reference" not in old["meta"]
        html = _page(reader, old, date(2026, 8, 1)).content.decode()
        assert "Marco regulatorio" not in html


class TestNoDataIsDrawnPendingNeverZero:
    def test_a_none_is_pending_and_a_zero_is_zero(self, reader, case_payload):
        payload = json.loads(json.dumps(case_payload))
        kpis = payload["manual"]["missions"]["kpis"]
        kpis["records_late"]["value"] = None
        kpis["records_on_time"]["value"] = 0

        body = _page(reader, payload).content.decode()
        strip = body.split("REG-016 en plazo")[0].split("rpt2-kpis")[-1]

        assert 'class="rpt-pending"' in body
        # El «en plazo» en cero se dibuja como 0 en su tarjeta.
        assert re.search(r"rpt2-kpi-value\">0<span", body)
        assert strip

    def test_the_cases_pending_indicators_are_listed_as_missing(self, case_payload):
        _payload, missing = build(PERIOD, cutoff=CUTOFF)

        assert "manual.missions.kpis.missions_flown" in missing
        assert "manual.maintenance.kpis.due_by_level" in missing


class TestTheNarrativeNote:
    @pytest.fixture
    def draft(self, case_payload):
        return ReportRun.objects.create(
            period=PERIOD, generated_by="t", payload=case_payload
        )

    @staticmethod
    def _post(**overrides):
        data = {
            "findings-TOTAL_FORMS": "0",
            "findings-INITIAL_FORMS": "0",
            "findings-MIN_NUM_FORMS": "0",
            "findings-MAX_NUM_FORMS": "8",
            "actions-TOTAL_FORMS": "0",
            "actions-INITIAL_FORMS": "0",
            "actions-MIN_NUM_FORMS": "0",
            "actions-MAX_NUM_FORMS": "6",
            "period_note": "",
            "manual_note": NOTE,
        }
        data.update(overrides)
        return data

    def test_the_note_is_saved_and_printed_on_the_last_sheet(self, client, db, draft):
        client.force_login(_user("writer", "view_reportrun", "change_reportrun"))

        response = client.post(
            reverse("monthly-report-narrative", args=[draft.pk]), self._post()
        )
        draft.refresh_from_db()
        html = client.get(
            reverse("monthly-report"), {"period": "2026-11"}
        ).content.decode()

        assert response.status_code == 302 and draft.manual_note == NOTE
        assert NOTE in html

    def test_the_form_draws_the_field(self, client, db, draft):
        client.force_login(_user("writer", "view_reportrun", "change_reportrun"))

        html = client.get(
            reverse("monthly-report-narrative", args=[draft.pk])
        ).content.decode()

        assert 'name="manual_note"' in html

    def test_without_the_change_permission_the_post_is_a_403(self, client, db, draft):
        client.force_login(_user("reader", "view_reportrun"))

        response = client.post(
            reverse("monthly-report-narrative", args=[draft.pk]), self._post()
        )
        draft.refresh_from_db()

        assert response.status_code == 403 and draft.manual_note == ""

    def test_it_travels_to_the_next_revision(self, case_payload, monkeypatch):
        from django.utils import timezone

        # La fecha es andamio: diciembre, con noviembre ya cerrado (lección LV-223).
        real = timezone.localdate
        monkeypatch.setattr(
            "django.utils.timezone.localdate",
            lambda value=None, tz=None: (
                date(2026, 12, 2) if value is None else real(value)
            ),
        )
        first = ReportRun.objects.create(
            period=PERIOD, generated_by="t", payload=case_payload, manual_note=NOTE
        )

        second, created = ReportRun.freeze(PERIOD, "t", force=True)

        assert created and second.revision == first.revision + 1
        assert second.manual_note == NOTE

    def test_more_than_1200_characters_fail_in_the_model_and_in_the_form(self, draft):
        too_long = "x" * (ReportRun.MANUAL_NOTE_MAX + 1)
        draft.manual_note = too_long

        with pytest.raises(ValidationError) as error:
            draft.full_clean()
        form = PeriodNoteForm(
            {"period_note": "", "manual_note": too_long}, instance=draft
        )

        assert "manual_note" in error.value.message_dict
        assert not form.is_valid() and "manual_note" in form.errors
        draft.manual_note = "x" * ReportRun.MANUAL_NOTE_MAX
        draft.full_clean()

    def test_a_centre_named_in_the_note_that_does_not_exist_is_warned(self, draft):
        from apps.reporting.checks import unknown_codes_in_text

        draft.manual_note = "Falta cargar el REG-016 de CC777."

        assert unknown_codes_in_text(draft.payload, draft) == ["CC777"]


class TestTheInvariantsCatchAHandEditedPayload:
    def test_a_consistent_payload_breaks_nothing(self, case_payload):
        assert invariants.violations(case_payload) == []

    def test_i9_catches_a_total_that_does_not_match_the_rows(self, case_payload):
        case_payload["manual"]["missions"]["kpis"]["records_total"]["value"] += 1

        assert "I9" in [code for code, _data in invariants.violations(case_payload)]

    def test_i9_catches_a_row_that_does_not_match_the_total(self, case_payload):
        case_payload["manual"]["missions"]["rows"][0]["records"] += 1

        assert "I9" in [code for code, _data in invariants.violations(case_payload)]

    def test_i10_catches_the_states_that_do_not_cover_the_fleet(self, case_payload):
        case_payload["manual"]["inspections"]["kpis"]["missing"]["value"] += 1

        assert "I10" in [code for code, _data in invariants.violations(case_payload)]

    def test_i10_catches_a_gap_list_that_is_not_the_non_current_aircraft(
        self, case_payload
    ):
        case_payload["manual"]["inspections"]["gaps"].pop()

        assert "I10" in [code for code, _data in invariants.violations(case_payload)]

    def test_a_pending_figure_is_not_evaluated(self, case_payload):
        case_payload["manual"]["missions"]["kpis"]["records_total"]["value"] = None

        assert "I9" not in [code for code, _data in invariants.violations(case_payload)]

    def test_the_messages_are_readable_and_reach_the_screen_warnings(
        self, case_payload
    ):
        case_payload["manual"]["inspections"]["kpis"]["missing"]["value"] += 1

        warnings = pre_issue_warnings(case_payload, None)

        assert any("LVE-002" in warning for warning in warnings)


class TestTheWarningsBeforeIssuing:
    def test_late_records_and_pending_indicators_are_warned(self, case_payload):
        warnings = manual_warnings(case_payload)
        pending = len(find_missing(case_payload["manual"]))

        # Contra el catálogo (`ngettext` con el mismo msgid), no contra un texto
        # tecleado: el idioma de la corrida no cambia el resultado.
        assert warnings[0] == ngettext(
            "%(count)d REG-016 was filed after the deadline (the day after the "
            "mission).",
            "%(count)d REG-016 were filed after the deadline (the day after the "
            "mission).",
            1,
        ) % {"count": 1}
        assert str(pending) in warnings[1] and pending > 0
        assert len(warnings) == 2

    def test_without_the_section_there_are_no_warnings(self):
        assert manual_warnings({"meta": {}}) == []


class TestTheMigrationDoesNotOverwriteWhatWasEdited:
    @staticmethod
    def _migration():
        return importlib.import_module(
            "apps.reporting.migrations.0008_lv445_manual_act19_cover_texts"
        )

    def test_a_factory_scope_is_updated_and_an_edited_one_is_kept(self, db):
        migration = self._migration()
        template = ReportTemplate.current()

        ReportTemplate.objects.filter(pk=template.pk).update(
            scope=migration.OLD_SCOPE, manual_reference="", internal_control_note=""
        )
        migration.apply_cover_texts(django_apps, None)
        template.refresh_from_db()
        assert template.scope == migration.NEW_SCOPE
        assert template.manual_reference == migration.REFERENCE

        ReportTemplate.objects.filter(pk=template.pk).update(
            scope="Alcance redactado a mano", manual_reference="Marco propio"
        )
        migration.apply_cover_texts(django_apps, None)
        template.refresh_from_db()
        assert template.scope == "Alcance redactado a mano"
        assert template.manual_reference == "Marco propio"

    def test_the_reverse_only_undoes_the_seeded_values(self, db):
        migration = self._migration()
        template = ReportTemplate.current()
        ReportTemplate.objects.filter(pk=template.pk).update(
            scope=migration.NEW_SCOPE,
            manual_reference="Marco propio",
            internal_control_note=migration.NOTE,
        )

        migration.revert_cover_texts(django_apps, None)
        template.refresh_from_db()

        assert template.scope == migration.OLD_SCOPE
        assert template.manual_reference == "Marco propio"
        assert template.internal_control_note == ""


class TestTheCoverTextsAreEditable:
    def test_the_template_form_draws_the_two_new_fields(self, client, db):
        client.force_login(_user("writer", "view_reportrun", "change_reportrun"))

        html = client.get(reverse("monthly-report-template")).content.decode()

        assert 'name="cover-manual_reference"' in html
        assert 'name="cover-internal_control_note"' in html

    def test_they_reach_the_next_payload(self, db):
        ReportTemplate.objects.filter(pk=ReportTemplate.current().pk).update(
            manual_reference="Marco ficticio de la prueba"
        )

        payload, _missing = build(PERIOD, cutoff=CUTOFF)

        assert payload["meta"]["manual_reference"] == "Marco ficticio de la prueba"


class TestTheSnapshot:
    """El HTML normalizado de un informe de noviembre con datos ficticios. Se
    regenera a propósito con `UPDATE_SNAPSHOTS=1` (el payload también)."""

    def test_the_november_report_with_the_manual_section(self, client, db, monkeypatch):
        pin_now(monkeypatch, NOW)
        path = SNAPSHOTS / "payload_2026_11_manual.json"
        if os.environ.get("UPDATE_SNAPSHOTS") == "1":
            make_manual_case()
            payload = build(PERIOD, cutoff=CUTOFF)[0]
            path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
                newline="\n",
            )
        payload = json.loads(path.read_text("utf-8"))
        client.force_login(_user("reader", "view_reportrun"))
        ReportRun.objects.create(
            period=PERIOD,
            revision=0,
            generated_by="test",
            payload=payload,
            findings=[],
            period_note="Nota ficticia del periodo para la prueba.",
            manual_note=NOTE,
        )

        html = client.get(
            reverse("monthly-report"), {"period": "2026-11"}
        ).content.decode()

        _check("monthly_2026_11_manual", html)
