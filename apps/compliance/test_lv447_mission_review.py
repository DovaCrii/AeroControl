"""LV-447: la revisión de cada REG-016 en 24 h (Manual Act. 19), con alerta.

El REG-016 se carga por misión en el centro de costo; lo revisa el Gerente de
Operaciones o quien designe por escrito, a más tardar el día siguiente a la misión.
Lo que se fija: que cada registro abra **una** revisión (y sólo uno vigente), que el
plazo sea el que dice el Manual (23:59 del día de plazo en plazo, 00:01 siguiente
fuera), que la alerta nazca y se cierre sola, que el permiso de revisar no lo tenga
ningún rol salvo Administrator, y el alcance por empresa. Fechas fijas y datos ficticios.
"""

from datetime import date, datetime, timedelta
from importlib import import_module

import pytest
from django.contrib.auth.models import Group, User
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, transaction
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.compliance.management.commands.seed_alert_rules import (
    ESSENTIAL_RULES,
    OPTIONAL_RULES,
)
from apps.compliance.models import (
    Alert,
    AlertRule,
    Document,
    DocumentType,
    MissionReview,
)
from apps.core.management.commands.bootstrap_roles import ROLE_PERMISSIONS
from apps.core.models import OperationalTenant
from apps.core.testing import login_as, pin_now
from apps.registry.models import Aircraft, CostCenter

migration = import_module("apps.compliance.migrations.0031_lv447_mission_review")

MISSION = date(2026, 11, 11)
DUE = date(2026, 11, 12)
RULE_NAME = "Revisión REG-016 en 24 h"


def local(day, hour, minute=0):
    return timezone.make_aware(datetime(day.year, day.month, day.day, hour, minute))


@pytest.fixture
def kind(db):
    return DocumentType.objects.get_or_create(
        code="flight-log",
        defaults={"name": "Registro único de misión", "requires_expiry": False},
    )[0]


@pytest.fixture
def site(db):
    return CostCenter.objects.create(code="CC9", name="Faena ficticia")


def _log(site, kind, day=MISSION, **extra):
    return Document.objects.create(
        title=f"REG-016 {day}",
        doc_type=kind,
        content_type=ContentType.objects.get_for_model(CostCenter),
        object_id=site.pk,
        file_path=f"flight-log/{site.code}-{day}.pdf",
        issue_date=day,
        **extra,
    )


def _review(site, kind, day=MISSION):
    return MissionReview.objects.get(document=_log(site, kind, day))


class TestItIsBornOncePerRecord:
    def test_loading_a_reg_016_opens_its_review_for_the_next_day(self, site, kind):
        document = _log(site, kind)

        review = MissionReview.objects.get(document=document)

        assert (review.cost_center, review.mission_date, review.due_on) == (
            site,
            MISSION,
            DUE,
        )
        assert review.status == "pending"

    def test_saving_again_does_not_open_a_second_one(self, site, kind):
        document = _log(site, kind)

        document.title = "Corregido"
        document.save()

        assert MissionReview.objects.filter(document=document).count() == 1

    def test_correcting_the_mission_date_moves_a_pending_deadline(self, site, kind):
        document = _log(site, kind)

        document.issue_date = date(2026, 11, 14)
        document.save()

        review = MissionReview.objects.get(document=document)
        assert (review.mission_date, review.due_on) == (
            date(2026, 11, 14),
            date(2026, 11, 15),
        )

    def test_a_reviewed_one_keeps_its_dates_when_the_document_is_edited(
        self, site, kind
    ):
        document = _log(site, kind)
        MissionReview.objects.get(document=document).mark(
            "reviewed", None, when=local(DUE, 10)
        )

        document.issue_date = date(2026, 11, 14)
        document.save()

        assert MissionReview.objects.get(document=document).due_on == DUE

    @pytest.mark.parametrize(
        "extra",
        [
            {"source_reference": "Z:/lote/x.pdf"},  # importado en lote
            {"issue_date": None},  # sin fecha de misión no hay plazo
            {"is_current_version": False},
        ],
    )
    def test_what_cannot_be_measured_opens_nothing(self, site, kind, extra):
        fields = {"issue_date": MISSION, **extra}
        Document.objects.create(
            title="x",
            doc_type=kind,
            content_type=ContentType.objects.get_for_model(CostCenter),
            object_id=site.pk,
            file_path="x.pdf",
            **fields,
        )

        assert MissionReview.objects.count() == 0

    def test_only_the_mission_record_on_a_cost_center_opens_one(self, site, kind):
        other = DocumentType.objects.create(code="otro", name="Otro")
        _log(site, other)
        aircraft = Aircraft.objects.create(
            registration="RPA-9",
            type="RPA",
            model="M",
            manufacturer="F",
            cost_center=site,
        )
        Document.objects.create(
            title="x",
            doc_type=kind,
            content_type=ContentType.objects.get_for_model(Aircraft),
            object_id=aircraft.pk,
            file_path="x.pdf",
            issue_date=MISSION,
        )

        assert MissionReview.objects.count() == 0

    def test_a_new_version_takes_over_the_review_instead_of_opening_another(
        self, site, kind, settings, tmp_path
    ):
        """Por la vista real: el reemplazo conserva **una** revisión, y es de la nueva."""
        settings.DOCUMENTS_ROOT = str(tmp_path)
        old = _log(site, kind)
        User.objects.create_superuser("admin447", "a447@test.com", "password")
        client = Client()
        assert client.login(username="admin447", password="password")

        response = client.post(
            reverse("document-replace", args=[old.pk]),
            {
                "title": old.title,
                "doc_type": kind.pk,
                "entity_type": ContentType.objects.get_for_model(CostCenter).pk,
                "object_id": str(site.pk),
                "issue_date": MISSION,
                "file": SimpleUploadedFile(
                    "new.pdf", b"%PDF-1.4\n%%EOF\n", content_type="application/pdf"
                ),
            },
        )

        assert response.status_code == 302, response.context["form"].errors
        new = Document.objects.get(is_current_version=True)
        assert new.pk != old.pk
        assert MissionReview.objects.count() == 1
        assert MissionReview.objects.get().document == new


class TestTheOriginIsExactlyOne:
    def test_a_review_without_an_origin_is_rejected(self, site):
        with pytest.raises(IntegrityError), transaction.atomic():
            MissionReview.objects.create(
                cost_center=site, mission_date=MISSION, due_on=DUE
            )

    def test_clean_rejects_none_and_both(self, site, kind):
        with pytest.raises(ValidationError):
            MissionReview(cost_center=site, mission_date=MISSION, due_on=DUE).clean()
        both = MissionReview(
            cost_center=site,
            document=_log(site, kind),
            flight_record_id="00000000-0000-0000-0000-000000000001",
            mission_date=MISSION,
            due_on=DUE,
        )
        with pytest.raises(ValidationError):
            both.clean()


class TestTheDeadlineIsTwentyFourHours:
    def test_the_last_minute_of_the_due_day_is_on_time(self, site, kind):
        review = _review(site, kind)

        review.mark("reviewed", None, when=local(DUE, 23, 59))

        assert review.reviewed_on_time is True
        assert MissionReview.objects.on_time().count() == 1

    def test_one_minute_into_the_next_day_is_late(self, site, kind):
        review = _review(site, kind)

        review.mark("reviewed", None, when=local(DUE + timedelta(days=1), 0, 1))

        assert review.reviewed_on_time is False
        assert MissionReview.objects.on_time().count() == 0

    def test_a_pending_review_is_neither(self, site, kind):
        review = _review(site, kind)

        assert review.reviewed_on_time is None
        assert review.is_overdue(DUE) is False  # el día de plazo aún es plazo
        assert review.is_overdue(DUE + timedelta(days=1)) is True

    def test_observed_counts_as_reviewed(self, site, kind):
        review = _review(site, kind)

        review.mark("observed", None, "Falta firma", when=local(MISSION, 18))

        assert review.reviewed_on_time is True
        assert review.notes == "Falta firma"

    def test_marking_pending_is_not_an_outcome(self, site, kind):
        with pytest.raises(ValueError):
            _review(site, kind).mark("pending", None)


def _rule(**extra):
    return AlertRule.objects.create(
        name=RULE_NAME,
        entity_type="compliance.missionreview",
        field_to_watch="due_on",
        days_before_expiry=0,
        **extra,
    )


class TestTheAlert:
    def test_it_is_born_on_the_due_day_and_not_before(self, site, kind, monkeypatch):
        _rule()
        review = _review(site, kind)

        pin_now(monkeypatch, local(MISSION, 12))
        call_command("generate_alerts")
        assert Alert.objects.count() == 0

        pin_now(monkeypatch, local(DUE, 7))
        call_command("generate_alerts")
        alert = Alert.objects.get()
        assert alert.object_id == review.pk

    def test_a_reviewed_record_never_alerts(self, site, kind, monkeypatch):
        _rule()
        _review(site, kind).mark("reviewed", None, when=local(MISSION, 20))

        pin_now(monkeypatch, local(DUE + timedelta(days=3), 7))
        call_command("generate_alerts")

        assert Alert.objects.count() == 0

    def test_reviewing_closes_the_open_alert(self, site, kind, monkeypatch):
        _rule()
        review = _review(site, kind)
        pin_now(monkeypatch, local(DUE, 7))
        call_command("generate_alerts")
        assert Alert.objects.filter(is_resolved=False).count() == 1

        review.mark("reviewed", None, when=local(DUE, 9))

        assert Alert.objects.filter(is_resolved=False).count() == 0
        assert Alert.objects.get().is_resolved is True


class TestTheRuleIsSeeded:
    def test_the_migration_and_the_seed_agree(self):
        assert migration.RULE in OPTIONAL_RULES
        assert migration.RULE[0] not in [row[0] for row in ESSENTIAL_RULES]

    def test_the_migration_adds_it_once_to_tenants_that_use_rules(self, db):
        from django.apps import apps

        _rule()
        migration.add_review_rule(apps, None)
        migration.add_review_rule(apps, None)

        assert AlertRule.objects.filter(name=RULE_NAME).count() == 1

    def test_a_tenant_with_no_rules_gets_none(self, db):
        from django.apps import apps

        migration.add_review_rule(apps, None)

        assert AlertRule.objects.filter(name=RULE_NAME).count() == 0

    def test_reversing_keeps_a_rule_that_already_alerted(self, site, kind, monkeypatch):
        from django.apps import apps

        _rule()
        _review(site, kind)
        pin_now(monkeypatch, local(DUE, 7))
        call_command("generate_alerts")

        migration.remove_review_rule(apps, None)

        assert AlertRule.objects.filter(name=RULE_NAME).count() == 1


class TestThePermissionIsAssignedByHand:
    def test_no_role_but_administrator_carries_it(self, db):
        assert all(
            "review_missionreview" not in codenames
            for codenames in ROLE_PERMISSIONS.values()
        )

        call_command("bootstrap_roles")

        admin = Group.objects.get(name="Administrator")
        assert admin.permissions.filter(codename="review_missionreview").exists()
        for group in Group.objects.exclude(name="Administrator"):
            assert not group.permissions.filter(
                codename="review_missionreview"
            ).exists(), group.name


def _two_tenants(kind):
    mine = OperationalTenant.objects.create(name="Mía", slug="mia-447")
    theirs = OperationalTenant.objects.create(name="Ajena", slug="ajena-447")
    own = CostCenter.objects.create(code="CC-MIA", name="Mía", tenant=mine)
    foreign = CostCenter.objects.create(code="CC-AJENA", name="Ajena", tenant=theirs)
    return mine, own, foreign, _review(own, kind), _review(foreign, kind)


class TestTheTray:
    def test_without_view_permission_the_list_is_403(self, site, kind):
        assert login_as().get(reverse("mission-review-list")).status_code == 403

    def test_the_list_shows_only_my_tenants_reviews(self, kind):
        mine, _own, _foreign, _mine_review, _theirs = _two_tenants(kind)

        body = (
            login_as("view_missionreview", member_of=mine)
            .get(reverse("mission-review-list"))
            .content.decode()
        )

        assert "CC-MIA" in body
        assert "CC-AJENA" not in body

    def test_filters_by_status_and_overdue(self, site, kind, monkeypatch):
        pending = _review(site, kind)
        done = _review(site, kind, date(2026, 11, 13))
        done.mark("reviewed", None, when=local(date(2026, 11, 13), 9))
        pin_now(monkeypatch, local(date(2026, 11, 20), 9))
        client = login_as("view_missionreview")

        overdue = client.get(reverse("mission-review-list"), {"overdue": "1"})
        reviewed = client.get(reverse("mission-review-list"), {"status": "reviewed"})

        assert [r.pk for r in overdue.context["objects"]] == [pending.pk]
        assert [r.pk for r in reviewed.context["objects"]] == [done.pk]

    def test_the_month_sample_counts_on_time_over_total(self, site, kind, monkeypatch):
        pin_now(monkeypatch, local(date(2026, 11, 20), 9))
        _review(site, kind, date(2026, 11, 11)).mark(
            "reviewed", None, when=local(date(2026, 11, 12), 23, 59)
        )
        _review(site, kind, date(2026, 11, 12)).mark(
            "reviewed", None, when=local(date(2026, 11, 14), 0, 1)
        )
        _review(site, kind, date(2026, 11, 15))
        _review(site, kind, date(2026, 10, 30))  # otro mes: no cuenta

        context = (
            login_as("view_missionreview").get(reverse("mission-review-list")).context
        )

        assert (context["month_on_time"], context["month_total"]) == (1, 3)

    def test_the_row_offers_marking_only_with_the_review_permission(self, site, kind):
        mark_url = reverse("mission-review-mark", args=[_review(site, kind).pk])

        plain = login_as("view_missionreview").get(reverse("mission-review-list"))
        reviewer = login_as("view_missionreview", "review_missionreview").get(
            reverse("mission-review-list")
        )

        assert mark_url not in plain.content.decode()
        assert mark_url in reviewer.content.decode()


class TestMarking:
    def _post(self, client, review, status="reviewed", **extra):
        return client.post(
            reverse("mission-review-mark", args=[review.pk]),
            {"status": status, **extra},
        )

    def test_marking_needs_the_review_permission(self, site, kind):
        review = _review(site, kind)

        for codenames in (
            (),
            ("view_missionreview",),
            ("view_missionreview", "change_missionreview", "add_missionreview"),
        ):
            assert self._post(login_as(*codenames), review).status_code == 403
        review.refresh_from_db()
        assert review.status == "pending"

    def test_a_reviewer_marks_it_and_it_is_attributed(self, site, kind):
        review = _review(site, kind)
        client = login_as("review_missionreview")

        response = self._post(client, review, "observed", notes="Sin firma del piloto")

        assert response.status_code == 302
        review.refresh_from_db()
        assert review.status == "observed"
        assert review.reviewed_by == client.user
        assert review.reviewed_at is not None
        assert review.notes == "Sin firma del piloto"

    def test_an_invalid_outcome_is_a_400(self, site, kind):
        review = _review(site, kind)
        client = login_as("review_missionreview")

        assert self._post(client, review, "pending").status_code == 400
        assert self._post(client, review, "bogus").status_code == 400

    def test_get_is_not_allowed(self, site, kind):
        review = _review(site, kind)
        response = login_as("review_missionreview").get(
            reverse("mission-review-mark", args=[review.pk])
        )
        assert response.status_code == 405

    def test_another_tenants_review_is_a_404(self, kind):
        mine, _own, _foreign, _mine_review, theirs = _two_tenants(kind)

        response = self._post(login_as("review_missionreview", member_of=mine), theirs)

        assert response.status_code == 404
        theirs.refresh_from_db()
        assert theirs.status == "pending"


@pytest.mark.django_db
class TestBackfill:
    def _old_logs(self, site, kind):
        """Registros anteriores a la función: sin revisión (se borra la que nació)."""
        logs = [
            _log(site, kind, date(2026, 11, 11)),
            _log(site, kind, date(2026, 11, 3)),
        ]
        MissionReview.objects.all().delete()
        return logs

    def test_it_opens_the_missing_ones_since_the_date(self, site, kind):
        self._old_logs(site, kind)

        call_command("backfill_mission_reviews", "--since", "2026-11-10")

        assert MissionReview.objects.count() == 1
        assert MissionReview.objects.get().mission_date == MISSION

    def test_dry_run_changes_nothing_and_a_rerun_adds_nothing(self, site, kind):
        self._old_logs(site, kind)

        call_command("backfill_mission_reviews", "--since", "2026-11-10", "--dry-run")
        assert MissionReview.objects.count() == 0

        call_command("backfill_mission_reviews", "--since", "2026-11-10")
        call_command("backfill_mission_reviews", "--since", "2026-11-10")
        assert MissionReview.objects.count() == 1

    def test_a_bad_date_is_an_error(self, db):
        with pytest.raises(CommandError):
            call_command("backfill_mission_reviews", "--since", "10-11-2026")


class TestItIsReachable:
    """Sin entrada propia en el menú (agregar una obliga a su ícono y su módulo): se
    abre desde el cierre mensual y desde el documento."""

    def test_the_document_links_to_its_review_only_with_permission(self, site, kind):
        document = _log(site, kind)
        url = reverse("document-detail", args=[document.pk])

        seen = login_as("view_document", "view_missionreview").get(url)
        blind = login_as("view_document").get(url)

        assert reverse("mission-review-list") in seen.content.decode()
        assert reverse("mission-review-list") not in blind.content.decode()

    def test_the_monthly_close_links_to_the_tray(self, site, kind):
        url = reverse("monthly-review")

        seen = login_as("view_monthlycompliancereview", "view_missionreview").get(url)
        blind = login_as("view_monthlycompliancereview").get(url)

        assert reverse("mission-review-list") in seen.content.decode()
        assert reverse("mission-review-list") not in blind.content.decode()


class TestReplacingMovesThePendingDeadline:
    def _replace(self, site, kind, old, day, settings, tmp_path):
        settings.DOCUMENTS_ROOT = str(tmp_path)
        User.objects.create_superuser("admin447b", "b447@test.com", "password")
        client = Client()
        assert client.login(username="admin447b", password="password")
        response = client.post(
            reverse("document-replace", args=[old.pk]),
            {
                "title": old.title,
                "doc_type": kind.pk,
                "entity_type": ContentType.objects.get_for_model(CostCenter).pk,
                "object_id": str(site.pk),
                "issue_date": day,
                "file": SimpleUploadedFile(
                    "new.pdf", b"%PDF-1.4\n%%EOF\n", content_type="application/pdf"
                ),
            },
        )
        assert response.status_code == 302

    def test_a_pending_review_follows_the_new_mission_date(
        self, site, kind, settings, tmp_path
    ):
        old = _log(site, kind)

        self._replace(site, kind, old, date(2026, 11, 14), settings, tmp_path)

        review = MissionReview.objects.get()
        assert (review.mission_date, review.due_on) == (
            date(2026, 11, 14),
            date(2026, 11, 15),
        )

    def test_a_reviewed_one_keeps_its_deadline(self, site, kind, settings, tmp_path):
        old = _log(site, kind)
        MissionReview.objects.get().mark("reviewed", None, when=local(DUE, 9))

        self._replace(site, kind, old, date(2026, 11, 14), settings, tmp_path)

        review = MissionReview.objects.get()
        assert (review.mission_date, review.due_on) == (MISSION, DUE)


class TestTheCsvExport:
    def test_it_exports_exactly_the_declared_columns(self, site, kind):
        _review(site, kind)

        response = login_as("view_missionreview").get(
            reverse("mission-review-list"), {"export": "csv"}
        )
        body = b"".join(response.streaming_content).decode("utf-8-sig")
        header = body.splitlines()[0].split(",")

        names = ("cost_center", "mission_date", "due_on", "status", "reviewed_at")
        assert header == [
            MissionReview._meta.get_field(n).verbose_name.title() for n in names
        ]
        assert len(header) == 5
        assert "reviewed_by" not in body.lower()


class TestTheSignalAloneOnAReplacement:
    """La vista guarda dos veces (la segunda sólo el archivo), y esa segunda pasada
    escondía una rama rota: acá la nueva versión se guarda **una** vez."""

    def _version(self, old, day):
        new = Document(
            title=old.title,
            doc_type=old.doc_type,
            content_type=old.content_type,
            object_id=old.object_id,
            file_path="nuevo.pdf",
            issue_date=day,
        )
        new._supersedes = old
        new.save()
        return new

    def test_a_pending_review_moves_with_a_single_save(self, site, kind):
        old = _log(site, kind)

        new = self._version(old, date(2026, 11, 14))

        review = MissionReview.objects.get()
        assert review.document == new
        assert (review.mission_date, review.due_on) == (
            date(2026, 11, 14),
            date(2026, 11, 15),
        )

    def test_a_reviewed_one_does_not_move(self, site, kind):
        old = _log(site, kind)
        MissionReview.objects.get().mark("reviewed", None, when=local(DUE, 9))

        self._version(old, date(2026, 11, 14))

        assert MissionReview.objects.get().due_on == DUE
