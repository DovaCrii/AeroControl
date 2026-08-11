"""LV-71: renewing a watched date closes its own alert, with a traceable reason.

Before this, four paths closed an alert automatically (document superseded,
maintenance completed, monthly review signed, Kanban card completed) but
renewing the thing the alert was *about* did not -- so a JAC policy or a DGAC
credential needed the renewal **and** a manual resolve, and those are most of
the real alerts. The user chose to close automatically but with a machine-written
reason, so ISO 10.2's root-cause-on-record survives without anyone typing it.
"""

from datetime import date, timedelta

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.utils import timezone

from apps.registry.models import Aircraft, CostCenter, Operator
from .models import Alert, AlertRule

TODAY = timezone.localdate()


def _rule(**kwargs):
    defaults = {
        "name": "Seguros JAC por vencer",
        "entity_type": "registry.aircraft",
        "field_to_watch": "insurance_expiry",
        "days_before_expiry": 30,
    }
    defaults.update(kwargs)
    return AlertRule.objects.create(**defaults)


def _alert_for(rule, obj):
    return Alert.objects.create(
        alert_rule=rule,
        content_type=ContentType.objects.get_for_model(obj),
        object_id=obj.pk,
        message="Expiring soon",
    )


@pytest.fixture
def aircraft(db):
    cost_center = CostCenter.objects.create(code="CC1", name="One")
    return Aircraft.objects.create(
        registration="RPA-5534",
        type="RPAS",
        model="M300",
        manufacturer="DJI",
        cost_center=cost_center,
        insurance_expiry=TODAY - timedelta(days=3),  # overdue
    )


@pytest.mark.django_db
def test_renewing_the_date_closes_the_alert_with_an_automatic_reason(aircraft):
    alert = _alert_for(_rule(), aircraft)
    renewed = TODAY + timedelta(days=365)

    aircraft.insurance_expiry = renewed
    aircraft.save()

    alert.refresh_from_db()
    assert alert.is_resolved is True
    # The reason has to say *why* and *to when*, or it is no better than a
    # silent close for an auditor.
    assert renewed.isoformat() in alert.resolution_reason
    assert alert.resolution_reason  # never blank


@pytest.mark.django_db
def test_a_date_still_inside_the_window_does_not_close(aircraft):
    """Renewing by a week when the rule watches 30 days is not a fix -- and
    closing it would only make the alert flap, since the next generate_alerts
    run would recreate it."""
    alert = _alert_for(_rule(days_before_expiry=30), aircraft)

    aircraft.insurance_expiry = TODAY + timedelta(days=10)
    aircraft.save()

    alert.refresh_from_db()
    assert alert.is_resolved is False


@pytest.mark.django_db
def test_clearing_the_date_does_not_close(aircraft):
    """A missing vigencia is a worse state than an expiring one, so the alert
    must stay open."""
    alert = _alert_for(_rule(), aircraft)

    aircraft.insurance_expiry = None
    aircraft.save()

    alert.refresh_from_db()
    assert alert.is_resolved is False


@pytest.mark.django_db
def test_a_status_rule_is_left_alone(aircraft):
    """Rules watching `status` already close through resolve_open_alerts_for;
    this signal must not reach into that path."""
    alert = _alert_for(_rule(field_to_watch="status"), aircraft)

    aircraft.status = "active"
    aircraft.save()

    alert.refresh_from_db()
    assert alert.is_resolved is False


@pytest.mark.django_db
def test_an_already_resolved_alert_is_not_touched_again(aircraft):
    alert = _alert_for(_rule(), aircraft)
    alert.resolve(reason="Cerrada a mano por Ana")

    aircraft.insurance_expiry = TODAY + timedelta(days=365)
    aircraft.save()

    alert.refresh_from_db()
    # The human's reason survives; the signal only looks at open alerts.
    assert alert.resolution_reason == "Cerrada a mano por Ana"


@pytest.mark.django_db
def test_generate_alerts_does_not_recreate_what_the_signal_closed(aircraft):
    """The point of sharing `days_before_expiry` with generate_alerts: the
    alert must stay closed, not come back the next morning."""
    rule = _rule()
    _alert_for(rule, aircraft)

    aircraft.insurance_expiry = TODAY + timedelta(days=365)
    aircraft.save()
    call_command("generate_alerts")

    assert Alert.objects.filter(is_resolved=False, alert_rule=rule).count() == 0


@pytest.mark.django_db
def test_reopening_after_an_automatic_close_still_works(aircraft):
    alert = _alert_for(_rule(), aircraft)
    aircraft.insurance_expiry = TODAY + timedelta(days=365)
    aircraft.save()
    alert.refresh_from_db()
    assert alert.is_resolved is True

    alert.reopen()

    alert.refresh_from_db()
    assert alert.is_resolved is False
    assert alert.resolution_reason == ""  # reopen clears it (R6.2)


@pytest.mark.django_db
def test_only_this_objects_alerts_close(aircraft):
    """Two aircraft under the same rule: renewing one must not touch the other
    -- the LV-68 lesson, now in the automatic path."""
    other = Aircraft.objects.create(
        registration="RPA-5532",
        type="RPAS",
        model="M300",
        manufacturer="DJI",
        cost_center=aircraft.cost_center,
        insurance_expiry=TODAY - timedelta(days=3),
    )
    rule = _rule()
    mine = _alert_for(rule, aircraft)
    theirs = _alert_for(rule, other)

    aircraft.insurance_expiry = TODAY + timedelta(days=365)
    aircraft.save()

    mine.refresh_from_db()
    theirs.refresh_from_db()
    assert mine.is_resolved is True
    assert theirs.is_resolved is False


@pytest.mark.django_db
def test_it_also_covers_operator_credentials(db):
    """Not aircraft-specific: the signal is wired to every watchable model with
    a date rule."""
    operator = Operator.objects.create(
        employee_id="OP-1",
        full_name="Carlos Peñailillo",
        credential_expiry=TODAY - timedelta(days=100),
    )
    rule = _rule(
        name="Credenciales DGAC por vencer",
        entity_type="registry.operator",
        field_to_watch="credential_expiry",
    )
    alert = _alert_for(rule, operator)

    operator.credential_expiry = date(2029, 5, 2)
    operator.save()

    alert.refresh_from_db()
    assert alert.is_resolved is True
    assert "2029-05-02" in alert.resolution_reason
