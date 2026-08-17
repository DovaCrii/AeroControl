"""R7.6: non-conformities (ISO 10.2).

A reflight or a rejected survey is **not** an expiry alert, so it does not go
through the AlertRule engine -- that branch watches "expires in N days" and
forcing anything else into it repeats the mistake R5.1 already avoided. What
the two do share is the effectiveness follow-up, which is why that lives in a
mixin rather than duplicated.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import Group, User
from django.core import mail
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from apps.core.testing import login_as
from apps.core.groups import REPORT_RECIPIENTS
from apps.registry.models import CostCenter

from .models import Deliverable, NonConformity


def _finding(**kwargs):
    kwargs.setdefault("title", "Re-vuelo sector 3")
    kwargs.setdefault("source", NonConformity.SOURCE_REFLIGHT)
    kwargs.setdefault("description", "Cobertura insuficiente en el borde norte.")
    return NonConformity.objects.create(**kwargs)


class TestClosingRequiresTheAnalysis:
    @pytest.mark.django_db
    def test_cannot_close_without_a_root_cause(self, db):
        """ISO 10.2 wants the cause on record. Filing a finding as handled
        while recording neither the cause nor the action is the exact gap R6.2
        closed for alerts."""
        finding = _finding()

        assert finding.can_close is False
        assert finding.close() is False

        finding.refresh_from_db()
        assert finding.status == NonConformity.STATUS_OPEN

    @pytest.mark.django_db
    def test_cannot_close_with_a_cause_but_no_action(self, db):
        finding = _finding(root_cause="Plan de vuelo mal trazado")

        assert finding.can_close is False

    @pytest.mark.django_db
    def test_whitespace_does_not_count_as_analysis(self, db):
        finding = _finding(root_cause="   ", corrective_action="  ")

        assert finding.can_close is False

    @pytest.mark.django_db
    def test_closing_with_both_records_who_and_starts_the_clock(self, db):
        finding = _finding(
            root_cause="Plan de vuelo mal trazado",
            corrective_action="Se rehizo el plan y se voló de nuevo el 2026-08-15",
        )
        user = User.objects.create_user("closer", password="pw")

        assert finding.close(user=user) is True

        finding.refresh_from_db()
        assert finding.status == NonConformity.STATUS_CLOSED
        assert finding.closed_by == user
        assert finding.closed_at is not None
        assert finding.effectiveness_due_date == timezone.localdate() + timedelta(
            days=NonConformity.EFFECTIVENESS_DAYS
        )


class TestTheSharedEffectivenessPattern:
    @pytest.mark.django_db
    def test_an_open_finding_cannot_be_verified(self, db):
        finding = _finding()

        assert finding.verify_effectiveness() is False

    @pytest.mark.django_db
    def test_verifying_leaves_it_closed(self, db):
        finding = _finding(root_cause="Causa", corrective_action="Accion")
        finding.close()

        assert finding.verify_effectiveness(note="Se mantuvo") is True

        finding.refresh_from_db()
        assert finding.status == NonConformity.STATUS_CLOSED
        assert finding.effectiveness_note == "Se mantuvo"
        assert finding.effectiveness_is_due is False

    @pytest.mark.django_db
    def test_reopening_clears_the_verification(self, db):
        finding = _finding(root_cause="Causa", corrective_action="Accion")
        finding.close()
        finding.verify_effectiveness(note="Se mantuvo")

        finding.reopen()

        finding.refresh_from_db()
        assert finding.status == NonConformity.STATUS_OPEN
        assert finding.effectiveness_verified_at is None
        assert finding.effectiveness_due_date is None
        assert finding.closed_at is None

    @pytest.mark.django_db
    def test_the_alert_pattern_still_works_after_the_extraction(self, db):
        """The mixin was extracted from Alert; this guards that the move did
        not change Alert's behaviour."""
        from django.contrib.contenttypes.models import ContentType

        from apps.registry.models import Operator, Qualification, QualificationType

        from .models import Alert, AlertRule

        cost_center = CostCenter.objects.create(code="OPS", name="Ops")
        operator = Operator.objects.create(
            employee_id="P1", full_name="Pilot One", cost_center=cost_center
        )
        qualification = Qualification.objects.create(
            operator=operator,
            qualification_type=QualificationType.objects.create(
                code="dgac", name="Credencial"
            ),
            issue_date=timezone.localdate() - timedelta(days=400),
            expiry_date=timezone.localdate() + timedelta(days=3),
        )
        alert = Alert.objects.create(
            alert_rule=AlertRule.objects.create(
                name="Regla", entity_type="qualification", field_to_watch="expiry_date"
            ),
            content_type=ContentType.objects.get_for_model(Qualification),
            object_id=qualification.pk,
            message="x",
        )

        alert.resolve(reason="Renovada")

        alert.refresh_from_db()
        assert alert.effectiveness_due_date is not None
        assert alert.verify_effectiveness() is True


class TestTheRejectedDeliverableTrigger:
    @pytest.mark.django_db
    def test_rejecting_a_deliverable_opens_a_finding(self, db):
        """The clause's most important trigger: leaving it to someone to
        remember to file one is how the record ends up incomplete."""
        contract = CostCenter.objects.create(code="CC1", name="Uno")
        deliverable = Deliverable.objects.create(
            title="Levantamiento Mina Norte",
            cost_center=contract,
            rmse_xy_cm=Decimal("22.0"),
        )
        client = login_as("view_deliverable", "change_deliverable")

        client.post(reverse("deliverable-reject", args=[deliverable.pk]))

        finding = NonConformity.objects.get()
        assert finding.source == NonConformity.SOURCE_REJECTED_DELIVERABLE
        assert finding.cost_center == contract
        assert finding.content_object == deliverable
        assert finding.status == NonConformity.STATUS_OPEN
        # Opened without analysis on purpose: prompting for a root cause at
        # rejection time gets "pending" typed in, which looks answered.
        assert finding.root_cause == ""
        assert finding.can_close is False

    @pytest.mark.django_db
    def test_a_released_deliverable_opens_nothing(self, db):
        contract = CostCenter.objects.create(code="CC1", name="Uno")
        deliverable = Deliverable.objects.create(
            title="Levantamiento", cost_center=contract
        )
        deliverable.status = Deliverable.STATUS_RELEASED
        deliverable.save(update_fields=["status"])
        client = login_as("view_deliverable", "change_deliverable")

        client.post(reverse("deliverable-reject", args=[deliverable.pk]))

        assert NonConformity.objects.count() == 0


class TestTheViews:
    @pytest.mark.django_db
    def test_closing_without_analysis_is_refused_by_the_view(self, db):
        finding = _finding()
        client = login_as("view_nonconformity", "change_nonconformity")

        client.post(reverse("nonconformity-close", args=[finding.pk]))

        finding.refresh_from_db()
        assert finding.status == NonConformity.STATUS_OPEN

    @pytest.mark.django_db
    def test_closing_with_analysis_works(self, db):
        finding = _finding(root_cause="Causa", corrective_action="Accion")
        client = login_as("view_nonconformity", "change_nonconformity")

        client.post(reverse("nonconformity-close", args=[finding.pk]))

        finding.refresh_from_db()
        assert finding.status == NonConformity.STATUS_CLOSED

    @pytest.mark.django_db
    def test_the_detail_page_says_what_is_missing(self, db):
        finding = _finding()
        client = login_as("view_nonconformity", "change_nonconformity")

        content = client.get(
            reverse("nonconformity-detail", args=[finding.pk])
        ).content.decode()

        assert "Sin investigar aún" in content

    @pytest.mark.django_db
    def test_the_list_requires_view_permission(self, db):
        assert login_as().get(reverse("nonconformity-list")).status_code == 403

    @pytest.mark.django_db
    def test_verifying_requires_the_change_permission(self, db):
        finding = _finding(root_cause="Causa", corrective_action="Accion")
        finding.close()
        client = login_as("view_nonconformity")

        response = client.post(
            reverse("nonconformity-verify-effectiveness", args=[finding.pk])
        )

        assert response.status_code == 403
        finding.refresh_from_db()
        assert finding.effectiveness_verified_at is None

    @pytest.mark.django_db
    def test_records_an_audit_event_on_close(self, db):
        from apps.core.models import AuditEvent

        finding = _finding(root_cause="Causa", corrective_action="Accion")
        client = login_as("view_nonconformity", "change_nonconformity")

        client.post(reverse("nonconformity-close", args=[finding.pk]))

        assert AuditEvent.objects.filter(
            action="non_conformity_closed", object_id=str(finding.pk)
        ).exists()


class TestTheScheduledJobCoversBoth:
    @pytest.mark.django_db
    def test_a_closed_finding_awaiting_verification_is_escalated(self, db):
        """One job, one mail: a second timer over the same question would mean
        two mails a manager has to reconcile."""
        recipient = User.objects.create_user(
            "director", email="dir@test.com", password="pw"
        )
        Group.objects.create(name=REPORT_RECIPIENTS).user_set.add(recipient)
        finding = _finding(
            root_cause="Plan mal trazado", corrective_action="Se rehizo el plan"
        )
        finding.close()
        finding.effectiveness_due_date = timezone.localdate() - timedelta(days=1)
        finding.save(update_fields=["effectiveness_due_date"])

        call_command("check_alert_effectiveness")

        assert len(mail.outbox) == 1
        body = mail.outbox[0].body
        assert "Re-vuelo sector 3" in body
        assert "Se rehizo el plan" in body

    @pytest.mark.django_db
    def test_a_verified_finding_is_not_escalated(self, db):
        recipient = User.objects.create_user(
            "director", email="dir@test.com", password="pw"
        )
        Group.objects.create(name=REPORT_RECIPIENTS).user_set.add(recipient)
        finding = _finding(root_cause="Causa", corrective_action="Accion")
        finding.close()
        finding.effectiveness_due_date = timezone.localdate() - timedelta(days=1)
        finding.save(update_fields=["effectiveness_due_date"])
        finding.verify_effectiveness(user=recipient)

        call_command("check_alert_effectiveness")

        assert mail.outbox == []

    @pytest.mark.django_db
    def test_an_open_finding_is_never_escalated(self, db):
        """Nothing has been done yet, so there is nothing whose effectiveness
        could be in question."""
        recipient = User.objects.create_user(
            "director", email="dir@test.com", password="pw"
        )
        Group.objects.create(name=REPORT_RECIPIENTS).user_set.add(recipient)
        finding = _finding()
        finding.effectiveness_due_date = timezone.localdate() - timedelta(days=1)
        finding.save(update_fields=["effectiveness_due_date"])

        call_command("check_alert_effectiveness")

        assert mail.outbox == []
