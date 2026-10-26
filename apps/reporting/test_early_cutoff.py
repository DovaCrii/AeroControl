"""LV-375: el informe de corte anticipado, y su cierre el día 1.

La persona que emite el informe de octubre lo necesita **antes** de que termine
el mes. `build` ya aceptaba un corte y el papel ya imprimía «período en curso»;
lo único que lo impedía era la guarda de `LV-233` de `ReportRun.freeze`, que
sigue intacta para todo lo que no pida el corte anticipado.

Lo que estos tests protegen, por orden de gravedad:

1. **Que el cierre no se pierda.** Un anticipado ya congelado hacía que el
   trabajo del día 1 dijera «ya existe» y no emitiera nada: octubre se habría
   quedado con datos al 26.
2. **Que la vía anticipada no abra la puerta de atrás**: mes cerrado, mes
   futuro, corte en el futuro o antes del día 1 se rechazan en el **modelo**.
3. **Que el permiso sea propio**: `add`/`change` redactan, no emiten con el mes
   abierto.
4. **Que el papel lo diga** —y que los informes cerrados no cambien ni un byte
   (lo vigilan los snapshots de `test_snapshot_monthly.py`)— y que el motivo no
   se imprima.

Fechas fijadas con `pin_now`: «hoy» es el 26 de octubre de 2026 salvo que el test
diga otra cosa. Datos ficticios.
"""

from datetime import date, datetime, timezone as dt_timezone
from io import StringIO

import pytest
from django.contrib.auth.models import Permission, User
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.urls import reverse

from apps.core.models import AuditEvent
from apps.core.testing import pin_now
from apps.registry.models import CostCenter
from apps.reporting.models import ReportRun

PERIOD = date(2026, 10, 1)
TODAY = datetime(2026, 10, 26, 15, 0, tzinfo=dt_timezone.utc)
CLOSING_DAY = datetime(2026, 11, 1, 15, 0, tzinfo=dt_timezone.utc)
CUTOFF = date(2026, 10, 26)
REASON = "Reunión con la DGAC el 27 de octubre."


def _user(name, *codenames):
    user = User.objects.create_user(name, password="x", email=f"{name}@test.com")
    for codename in codenames:
        user.user_permissions.add(
            Permission.objects.get(
                codename=codename, content_type__app_label="reporting"
            )
        )
    return user


@pytest.fixture
def today(db, monkeypatch):
    pin_now(monkeypatch, TODAY)
    CostCenter.objects.create(code="CC738", name="MLP", operates_flights=True)
    return CUTOFF


@pytest.fixture
def issuer_client(client, today):
    client.force_login(_user("emisor", "view_reportrun", "issue_early_reportrun"))
    return client


def _early(by="emisor", cutoff=CUTOFF, reason=REASON):
    return ReportRun.freeze(PERIOD, by, early_cutoff=cutoff, reason=reason)


def _command(**kwargs):
    out = StringIO()
    call_command("generate_monthly_report", stdout=out, **kwargs)
    return out.getvalue()


class TestThePermissionIsItsOwn:
    def test_add_and_change_are_not_enough(self, client, today):
        """Quien redacta la narrativa no decide emitir con el mes abierto."""
        client.force_login(
            _user("redactor", "view_reportrun", "add_reportrun", "change_reportrun")
        )

        assert client.get(reverse("monthly-report-early")).status_code == 403
        assert (
            client.post(reverse("monthly-report-early"), {"reason": REASON}).status_code
            == 403
        )
        assert not ReportRun.objects.exists()

    def test_only_the_administrator_role_has_the_permission(self, db):
        """Sólo el administrador emite: lo recibe porque `bootstrap_roles` le da
        todos los permisos; ningún otro rol lo trae."""
        from django.contrib.auth.models import Group

        call_command("bootstrap_roles", stdout=StringIO())

        def holders():
            return set(
                Group.objects.filter(
                    permissions__codename="issue_early_reportrun"
                ).values_list("name", flat=True)
            )

        assert holders() == {"Administrator"}

    def test_the_button_only_shows_with_the_permission(self, client, today):
        client.force_login(_user("redactor", "view_reportrun", "add_reportrun"))

        html = client.get(reverse("monthly-report"), {"period": "2026-10"}).content
        assert b"monthly/early/" not in html

    def test_the_button_shows_for_the_open_month_and_the_permission(
        self, issuer_client
    ):
        response = issuer_client.get(reverse("monthly-report"), {"period": "2026-10"})

        assert response.context["can_issue_early"] is True
        assert b"monthly/early/" in response.content

    def test_no_button_for_a_closed_month(self, issuer_client):
        response = issuer_client.get(reverse("monthly-report"), {"period": "2026-09"})

        assert response.context["can_issue_early"] is False


class TestTheHappyPath:
    def test_it_freezes_revision_zero_as_a_draft_marked_early(self, today):
        run, created = _early()

        assert created is True
        assert run.revision == 0
        assert run.status == ReportRun.STATUS_DRAFT  # nunca aprueba
        assert run.approved_by == ""
        assert run.is_early_cutoff is True
        meta = run.payload["meta"]
        assert meta["cutoff"] == "2026-10-26"
        assert meta["in_progress"] is True
        assert meta["days_remaining"] == 5
        assert meta["early_cutoff"] is True
        assert meta["early_reason"] == REASON
        assert run.code == "JEJ-GTE-CT-INF-RPA-2026-10"

    def test_the_view_flow_audits_the_reason(self, issuer_client):
        response = issuer_client.post(
            reverse("monthly-report-early"), {"period": "2026-10", "reason": REASON}
        )

        assert response.status_code == 302
        run = ReportRun.objects.get()
        assert run.generated_by == "emisor"
        event = AuditEvent.objects.filter(object_id=str(run.pk)).latest("created_at")
        assert event.action == "create"
        meta = event.metadata
        assert meta["reason"] == REASON
        assert meta["early_cutoff"] == "2026-10-26"
        assert meta["days_remaining"] == 5
        assert meta["replaced_revision"] is None

    def test_the_confirmation_text_is_translated_in_the_view(self, issuer_client):
        response = issuer_client.get(reverse("monthly-report-early"))
        text = response.context["confirm_text"]

        assert "26-10-2026" in text
        assert "5" in text
        assert "%(" not in text
        assert 'data-confirm="' in response.content.decode()

    def test_a_short_reason_is_not_accepted_by_the_form(self, issuer_client):
        response = issuer_client.post(
            reverse("monthly-report-early"), {"period": "2026-10", "reason": "corto"}
        )

        assert response.status_code == 200
        assert not ReportRun.objects.exists()


class TestTheModelValidatesTheEarlyPath:
    def test_the_cutoff_equal_to_today_is_accepted(self, today):
        assert _early(cutoff=CUTOFF)[1] is True

    def test_tomorrow_is_rejected(self, today):
        with pytest.raises(ValidationError):
            _early(cutoff=date(2026, 10, 27))
        assert not ReportRun.objects.exists()

    def test_before_the_first_day_is_rejected(self, today):
        with pytest.raises(ValidationError):
            _early(cutoff=date(2026, 9, 30))

    def test_a_past_day_of_the_month_is_accepted_by_the_model(self, today):
        run, _created = _early(cutoff=date(2026, 10, 20))

        assert run.payload["meta"]["days_remaining"] == 11

    def test_a_future_month_is_rejected(self, today):
        with pytest.raises(ValidationError):
            ReportRun.freeze(
                date(2026, 12, 1), "x", early_cutoff=date(2026, 12, 1), reason=REASON
            )

    def test_a_closed_month_is_rejected_by_the_early_path(self, today):
        with pytest.raises(ValidationError):
            ReportRun.freeze(
                date(2026, 9, 1), "x", early_cutoff=date(2026, 9, 20), reason=REASON
            )

    def test_the_last_day_of_the_month_is_not_an_early_cutoff(self, monkeypatch, db):
        pin_now(monkeypatch, datetime(2026, 10, 31, 15, 0, tzinfo=dt_timezone.utc))

        with pytest.raises(ValidationError):
            _early(cutoff=date(2026, 10, 31))

    @pytest.mark.parametrize("reason", ["", "   ", "corto", "x" * 301])
    def test_the_reason_is_required_and_bounded(self, today, reason):
        with pytest.raises(ValidationError):
            _early(reason=reason)
        assert not ReportRun.objects.exists()

    def test_the_normal_freeze_still_rejects_the_open_month(self, today):
        """LV-233 intacta: sin `early_cutoff`, un mes abierto no se congela."""
        with pytest.raises(ValidationError):
            ReportRun.freeze(PERIOD, "x")

    def test_the_command_still_rejects_the_open_month(self, today):
        from django.core.management.base import CommandError

        with pytest.raises(CommandError):
            _command(period="2026-10")
        assert not ReportRun.objects.exists()


class TestIdempotenceAndRevisions:
    def test_the_same_day_does_not_create_two(self, today):
        first, _created = _early()
        again, created = _early()

        assert created is False
        assert again.pk == first.pk
        assert ReportRun.objects.count() == 1

    def test_another_cutoff_replaces_the_draft_with_a_new_revision(self, today):
        first, _created = _early(cutoff=date(2026, 10, 20))
        second, created = _early(cutoff=CUTOFF)

        first.refresh_from_db()
        assert created is True
        assert second.revision == 1
        assert first.status == ReportRun.STATUS_SUPERSEDED

    def test_an_approved_early_cutoff_is_not_replaced_by_another_early(self, today):
        first, _created = _early(cutoff=date(2026, 10, 20))
        first.approve("firmante")

        with pytest.raises(ValidationError):
            _early(cutoff=CUTOFF)

        assert ReportRun.objects.count() == 1

    def test_the_same_cutoff_after_approval_returns_the_existing_one(self, today):
        first, _created = _early()
        first.approve("firmante")

        again, created = _early()

        assert (again.pk, created) == (first.pk, False)

    def test_a_normal_report_in_the_period_blocks_the_early_path(self, today):
        ReportRun.objects.create(period=PERIOD, revision=0, generated_by="x")

        with pytest.raises(ValidationError):
            _early()

    def test_the_narrative_travels_to_the_new_early_revision(self, today):
        first, _created = _early(cutoff=date(2026, 10, 20))
        first.period_note = "Nota ficticia."
        first.findings = [{"severity": "warning", "title": "T", "text": "Texto."}]
        first.save()

        second, _created = _early(cutoff=CUTOFF)

        assert second.period_note == "Nota ficticia."
        assert second.findings == first.findings


class TestTheClosingRevisionOnTheFirst:
    """**El riesgo grave**: sin esto octubre se queda con datos al 26."""

    def _closing_day(self, monkeypatch):
        pin_now(monkeypatch, CLOSING_DAY)

    def test_the_command_issues_revision_one_without_force(self, today, monkeypatch):
        early, _created = _early()
        early.approve("firmante")
        early.actions = [{"action": "Renovar", "owner": "ADC", "due": ""}]
        early.period_note = "Nota ficticia."
        early.save()
        self._closing_day(monkeypatch)

        output = _command(period="2026-10")

        runs = list(ReportRun.objects.filter(period=PERIOD).order_by("revision"))
        assert [r.revision for r in runs] == [0, 1]
        zero, one = runs
        assert zero.status == ReportRun.STATUS_SUPERSEDED
        assert zero.approved_by == "firmante"  # la evidencia sobrevive
        assert zero.approved_at is not None
        assert one.status == ReportRun.STATUS_DRAFT
        assert one.is_early_cutoff is False
        assert one.payload["meta"]["in_progress"] is False
        assert one.payload["meta"]["cutoff"] == "2026-10-31"
        assert one.payload["meta"]["replaces_early_cutoff"] == "2026-10-26"
        assert "Reemplaza a la de corte anticipado" in output
        # La narrativa y las acciones viajan.
        assert one.period_note == "Nota ficticia."
        assert one.actions == early.actions

    def test_the_default_period_of_the_command_is_the_closed_month(
        self, today, monkeypatch
    ):
        _early()
        self._closing_day(monkeypatch)

        _command()  # sin --period: el mes recién cerrado

        assert ReportRun.objects.filter(period=PERIOD).count() == 2

    def test_running_the_closing_twice_does_not_create_a_third(
        self, today, monkeypatch
    ):
        _early()
        self._closing_day(monkeypatch)
        _command()

        output = _command()

        assert ReportRun.objects.filter(period=PERIOD).count() == 2
        assert "ya existe" in output

    def test_dry_run_says_the_closing_would_be_issued(self, today, monkeypatch):
        _early()
        self._closing_day(monkeypatch)

        output = _command(period="2026-10", dry_run=True)

        assert "se emitiría la revisión de cierre" in output.lower()
        assert ReportRun.objects.filter(period=PERIOD).count() == 1

    def test_freeze_itself_issues_the_closing(self, today, monkeypatch):
        _early()
        self._closing_day(monkeypatch)

        run, created = ReportRun.freeze(PERIOD, "cron")

        assert created is True
        assert run.revision == 1

    def test_while_the_month_is_open_the_command_says_nothing_changes(self, today):
        _early()

        output = _command(period="2026-10")

        assert "ya existe" in output
        assert ReportRun.objects.count() == 1

    def test_the_closing_warns_that_it_replaces_the_early_one(
        self, today, monkeypatch, client
    ):
        _early()
        self._closing_day(monkeypatch)
        _command(period="2026-10")
        client.force_login(_user("lector", "view_reportrun"))

        response = client.get(reverse("monthly-report"), {"period": "2026-10"})

        assert any(
            "reemplaza a la de corte anticipado (26-10)" in w
            for w in response.context["warnings"]
        )


class TestThePaperSaysIt:
    def _page(self, client, name="monthly-report"):
        return client.get(reverse(name), {"period": "2026-10"}).content.decode()

    def test_the_cover_the_foot_and_the_brief_say_early_cutoff(self, issuer_client):
        _early()

        html = self._page(issuer_client)
        brief = self._page(issuer_client, "monthly-report-brief")

        # La portada queda como estaba (decisión de la persona): ya dice el corte
        # y que el período sigue en curso, sin marca nueva.
        assert "26-10-2026 <span" in html
        assert "· período en curso, 5 días por transcurrir" in html
        assert "Período 01–31 de octubre de 2026" in html
        assert "Revisión 0 · Corte anticipado 26-10-2026 · Página 1 de" in html
        flat = " ".join(html.split())
        assert "estado al corte anticipado del 26-10" in flat
        assert "al cierre del período" not in flat
        assert "corte anticipado" in brief
        assert "(corte 26-10)" in html

    def test_the_document_code_does_not_change(self, issuer_client):
        run, _created = _early()

        assert "JEJ-GTE-CT-INF-RPA-2026-10" in self._page(issuer_client)
        assert run.revision == 0

    def test_the_reason_is_on_screen_but_not_in_the_printed_paper(self, issuer_client):
        _early()

        html = self._page(issuer_client)
        screen, _sep, paper = html.partition('<div class="rpt-doc">')

        assert REASON in screen
        assert REASON not in paper
        # En pantalla está dentro de un bloque que no se imprime.
        at = screen.index("Informe con corte anticipado")
        opening = screen[screen.rindex("<div", 0, at) : at]
        assert "d-print-none" in opening

    def test_the_screen_warning_names_the_missing_days(self, issuer_client):
        _early()

        response = issuer_client.get(reverse("monthly-report"), {"period": "2026-10"})

        assert any("5" in w and "26-10" in w for w in response.context["warnings"])

    def test_a_closed_month_shows_no_mark(self, client, db, monkeypatch):
        pin_now(monkeypatch, CLOSING_DAY)
        CostCenter.objects.create(code="CC738", name="MLP", operates_flights=True)
        ReportRun.freeze(PERIOD, "x")
        client.force_login(_user("lector", "view_reportrun"))

        html = client.get(reverse("monthly-report"), {"period": "2026-10"}).content
        text = html.decode()

        assert "corte anticipado" not in text.lower()
        assert "Corte anticipado" not in text
        assert "al cierre del período" in " ".join(text.split())

    def test_the_comparison_shows_both_cutoffs(self, today, monkeypatch, client):
        early, _created = _early()
        pin_now(monkeypatch, CLOSING_DAY)
        closing, _created = ReportRun.freeze(PERIOD, "cron")
        client.force_login(_user("lector", "view_reportrun"))

        html = client.get(
            reverse("monthly-report-compare", args=[closing.pk])
        ).content.decode()

        assert "31-10-2026" in html
        assert "26-10-2026" in html
        assert early.is_early_cutoff
