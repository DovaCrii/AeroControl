"""R7.6: effectiveness verification of corrective actions (ISO 10.2).

R6.2 made resolving record a root cause, but resolving was terminal -- nobody
ever went back to ask whether the action worked, so a reason on record could
describe a fix that never held. These cover the second look: the due date, the
human confirmation, and the daily job that escalates what nobody signed off.
"""

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.core import mail
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from apps.core.testing import login_as
from apps.core.groups import REPORT_RECIPIENTS
from apps.registry.models import (
    CostCenter,
    Operator,
    Qualification,
    QualificationType,
)

from .models import Alert, AlertRule


@pytest.fixture
def alert(db):
    cost_center = CostCenter.objects.create(code="OPS", name="Operations")
    operator = Operator.objects.create(
        employee_id="P1", full_name="Pilot One", cost_center=cost_center
    )
    qualification_type = QualificationType.objects.create(
        code="dgac-credential", name="Credencial DGAC"
    )
    qualification = Qualification.objects.create(
        operator=operator,
        qualification_type=qualification_type,
        issue_date=timezone.localdate() - timedelta(days=400),
        expiry_date=timezone.localdate() + timedelta(days=3),
    )
    rule = AlertRule.objects.create(
        name="Credenciales DGAC por vencer",
        entity_type="qualification",
        field_to_watch="expiry_date",
    )
    return Alert.objects.create(
        alert_rule=rule,
        content_type=ContentType.objects.get_for_model(Qualification),
        object_id=qualification.pk,
        message="Expiring soon",
    )


class TestTheDueDate:
    @pytest.mark.django_db
    def test_resolving_starts_the_clock(self, alert):
        alert.resolve(reason="Credencial renovada")

        alert.refresh_from_db()
        assert alert.effectiveness_due_date == timezone.localdate() + timedelta(
            days=Alert.EFFECTIVENESS_DAYS
        )
        assert alert.effectiveness_verified_at is None

    @pytest.mark.django_db
    def test_an_automatic_resolution_also_starts_it(self, alert):
        """An automatic close (LV-71's renewed expiry date, a completed
        maintenance) is still a corrective action whose effect 10.2 expects
        someone to confirm -- it is not exempt for having had no human."""
        alert.resolve()  # no reason: the automatic callers' path

        alert.refresh_from_db()
        assert alert.effectiveness_due_date is not None

    @pytest.mark.django_db
    def test_not_due_before_the_window_elapses(self, alert):
        alert.resolve(reason="Credencial renovada")

        assert alert.effectiveness_is_due is False

    @pytest.mark.django_db
    def test_due_once_the_window_has_passed(self, alert):
        alert.resolve(reason="Credencial renovada")
        alert.effectiveness_due_date = timezone.localdate() - timedelta(days=1)
        alert.save(update_fields=["effectiveness_due_date"])

        assert alert.effectiveness_is_due is True

    @pytest.mark.django_db
    def test_an_alert_resolved_before_this_existed_is_never_overdue(self, alert):
        """Nullable on purpose: there is no honest due date to invent for the
        alerts already resolved when the field was added, and defaulting them
        to "due now" would open the feature with a backlog nobody caused."""
        alert.resolve(reason="Credencial renovada")
        alert.effectiveness_due_date = None
        alert.save(update_fields=["effectiveness_due_date"])

        assert alert.effectiveness_is_due is False


class TestVerifying:
    @pytest.mark.django_db
    def test_verifying_leaves_the_alert_resolved(self, alert):
        """Not the inverse of reopening: it adds a second statement, it does
        not undo the first."""
        alert.resolve(reason="Credencial renovada")
        user = User.objects.create_user("verifier", password="pw")

        assert alert.verify_effectiveness(user=user, note="Sigue vigente") is True

        alert.refresh_from_db()
        assert alert.is_resolved is True
        assert alert.resolution_reason == "Credencial renovada"
        assert alert.effectiveness_verified_by == user
        assert alert.effectiveness_note == "Sigue vigente"
        assert alert.effectiveness_is_due is False

    @pytest.mark.django_db
    def test_an_open_alert_cannot_be_verified(self, alert):
        """It would attest to the effectiveness of an action nobody took."""
        user = User.objects.create_user("verifier", password="pw")

        assert alert.verify_effectiveness(user=user) is False

        alert.refresh_from_db()
        assert alert.effectiveness_verified_at is None

    @pytest.mark.django_db
    def test_reopening_clears_the_verification(self, alert):
        """Reopening *is* the answer to "did it work?" -- no. A verification
        left behind would attest to a resolution that no longer stands."""
        alert.resolve(reason="Credencial renovada")
        alert.verify_effectiveness(user=None, note="Sigue vigente")

        alert.reopen()

        alert.refresh_from_db()
        assert alert.effectiveness_verified_at is None
        assert alert.effectiveness_note == ""
        assert alert.effectiveness_due_date is None


class TestTheView:
    @pytest.mark.django_db
    def test_the_button_appears_only_once_verification_is_due(self, alert):
        alert.resolve(reason="Credencial renovada")
        client = login_as("view_alert", "change_alert")
        url = reverse("alert-verify-effectiveness", args=[alert.pk])

        not_due_yet = client.get(reverse("alert-list")).content.decode()
        assert url not in not_due_yet

        alert.effectiveness_due_date = timezone.localdate() - timedelta(days=1)
        alert.save(update_fields=["effectiveness_due_date"])

        assert url in client.get(reverse("alert-list")).content.decode()

    @pytest.mark.django_db
    def test_posting_records_the_verification(self, alert):
        alert.resolve(reason="Credencial renovada")
        alert.effectiveness_due_date = timezone.localdate() - timedelta(days=1)
        alert.save(update_fields=["effectiveness_due_date"])
        client = login_as("view_alert", "change_alert")

        response = client.post(
            reverse("alert-verify-effectiveness", args=[alert.pk]),
            {"note": "Verificado contra el padrón DGAC"},
        )

        assert response.status_code == 302
        alert.refresh_from_db()
        assert alert.effectiveness_verified_at is not None
        assert alert.effectiveness_note == "Verificado contra el padrón DGAC"

    @pytest.mark.django_db
    def test_requires_the_change_permission(self, alert):
        alert.resolve(reason="Credencial renovada")
        client = login_as("view_alert")

        response = client.post(reverse("alert-verify-effectiveness", args=[alert.pk]))

        assert response.status_code == 403
        alert.refresh_from_db()
        assert alert.effectiveness_verified_at is None

    @pytest.mark.django_db
    def test_records_its_own_audit_event(self, alert):
        from apps.core.models import AuditEvent

        alert.resolve(reason="Credencial renovada")
        client = login_as("view_alert", "change_alert")

        client.post(reverse("alert-verify-effectiveness", args=[alert.pk]))

        assert AuditEvent.objects.filter(
            action="alert_effectiveness_verified", object_id=str(alert.pk)
        ).exists()


class TestTheScheduledJob:
    @pytest.mark.django_db
    def test_escalates_what_nobody_verified(self, alert):
        from django.contrib.auth.models import Group

        recipient = User.objects.create_user(
            "director", email="dir@test.com", password="pw"
        )
        Group.objects.create(name=REPORT_RECIPIENTS).user_set.add(recipient)
        alert.resolve(reason="Credencial renovada")
        alert.effectiveness_due_date = timezone.localdate() - timedelta(days=1)
        alert.save(update_fields=["effectiveness_due_date"])

        call_command("check_alert_effectiveness")

        assert len(mail.outbox) == 1
        body = mail.outbox[0].body
        # The reason travels with it: the reader has to judge whether *that*
        # action can be expected to have held.
        assert "Credencial renovada" in body
        assert "Pilot One" in body

    @pytest.mark.django_db
    def test_says_nothing_when_everything_is_verified(self, alert):
        from django.contrib.auth.models import Group

        recipient = User.objects.create_user(
            "director", email="dir@test.com", password="pw"
        )
        Group.objects.create(name=REPORT_RECIPIENTS).user_set.add(recipient)
        alert.resolve(reason="Credencial renovada")
        alert.effectiveness_due_date = timezone.localdate() - timedelta(days=1)
        alert.save(update_fields=["effectiveness_due_date"])
        alert.verify_effectiveness(user=recipient)

        call_command("check_alert_effectiveness")

        assert mail.outbox == []

    @pytest.mark.django_db
    def test_never_verifies_anything_by_itself(self, alert):
        """A machine confirming that a corrective action was effective is the
        opposite of the evidence 10.2 asks for."""
        alert.resolve(reason="Credencial renovada")
        alert.effectiveness_due_date = timezone.localdate() - timedelta(days=1)
        alert.save(update_fields=["effectiveness_due_date"])

        call_command("check_alert_effectiveness")

        alert.refresh_from_db()
        assert alert.effectiveness_verified_at is None
        assert alert.is_resolved is True

    @pytest.mark.django_db
    def test_dry_run_sends_nothing(self, alert):
        from django.contrib.auth.models import Group

        recipient = User.objects.create_user(
            "director", email="dir@test.com", password="pw"
        )
        Group.objects.create(name=REPORT_RECIPIENTS).user_set.add(recipient)
        alert.resolve(reason="Credencial renovada")
        alert.effectiveness_due_date = timezone.localdate() - timedelta(days=1)
        alert.save(update_fields=["effectiveness_due_date"])

        call_command("check_alert_effectiveness", "--dry-run")

        assert mail.outbox == []

    @pytest.mark.django_db
    def test_missing_recipients_group_does_not_crash_the_timer(self, alert):
        """Same choice as R6.5: a configuration gap must not take down a daily
        job and hide everything else it reports."""
        alert.resolve(reason="Credencial renovada")
        alert.effectiveness_due_date = timezone.localdate() - timedelta(days=1)
        alert.save(update_fields=["effectiveness_due_date"])

        call_command("check_alert_effectiveness")

        assert mail.outbox == []
