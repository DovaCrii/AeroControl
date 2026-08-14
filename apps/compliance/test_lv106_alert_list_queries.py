"""LV-106: the alerts inbox cost one query per row.

Measured on the demo before the fix: **62 queries for 21 alerts**, against 6-16
for every other list in the app. `AlertList` does `select_related` on the two
plain FKs, but the row also renders `content_object` -- a GenericForeignKey,
which no `select_related` can follow -- and reads it three times per row (the
record's name, `watched_date`, `is_overdue`).

It matters more than the number suggests: it is the screen the user described as
the one they work from, so it grows with exactly the thing that makes it useful.
Third appearance of the shape V.18/V.19 already cost this project twice, so the
test is written the way those were: **the count must not grow with the rows**,
which is the property, rather than a magic number that drifts.
"""

from datetime import date, timedelta

import pytest
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.compliance.models import Alert, AlertRule
from apps.registry.models import (
    Aircraft,
    CostCenter,
    Operator,
    Qualification,
    QualificationType,
)


@pytest.fixture
def rule(db):
    return AlertRule.objects.create(
        name="Vencimiento de habilitaciones",
        entity_type="qualification",
        field_to_watch="expiry_date",
    )


def _qualifications(count, prefix="A"):
    """`count` qualifications, callable twice in one test (hence the prefix:
    operator ids and cost-center codes are unique)."""
    cost_center, _created = CostCenter.objects.get_or_create(
        code="OPS", defaults={"name": "Operations"}
    )
    qualification_type, _made = QualificationType.objects.get_or_create(
        code="dgac-credential", defaults={"name": "Credencial DGAC"}
    )
    made = []
    for index in range(count):
        operator = Operator.objects.create(
            employee_id=f"{prefix}{index}",
            full_name=f"Pilot {prefix}{index}",
            cost_center=cost_center,
        )
        made.append(
            Qualification.objects.create(
                operator=operator,
                qualification_type=qualification_type,
                issue_date=date(2026, 1, 1),
                expiry_date=timezone.localdate() + timedelta(days=index + 1),
            )
        )
    return made


def _alerts_for(rule, records):
    content_type = ContentType.objects.get_for_model(Qualification)
    for record in records:
        Alert.objects.create(
            alert_rule=rule,
            content_type=content_type,
            object_id=record.pk,
            message="Expiring soon",
        )


def _admin_client():
    User.objects.create_superuser("admin", "a@test.com", "password")
    client = Client()
    assert client.login(username="admin", password="password")
    return client


def _queries_for_the_list(client):
    with CaptureQueriesContext(connection) as captured:
        response = client.get(reverse("alert-list"))
    assert response.status_code == 200
    return len(captured.captured_queries)


@pytest.mark.django_db
def test_the_query_count_does_not_grow_with_the_number_of_alerts(rule):
    client = _admin_client()
    _alerts_for(rule, _qualifications(5))
    # Warm-up, discarded: the first request of a process also fills the
    # ContentType and permission caches, which made the *second* measurement
    # look cheaper than the first no matter what the page did.
    _queries_for_the_list(client)
    few = _queries_for_the_list(client)

    _alerts_for(rule, _qualifications(20, prefix="B"))
    many = _queries_for_the_list(client)

    # Five times the rows must not mean more queries at all. Verified failing
    # without the prefetch: 24 queries for 5 alerts, 84 for 25.
    assert many == few, f"{few} queries for 5 alerts, {many} for 25"


@pytest.mark.django_db
def test_the_rows_still_say_what_they_are_about(rule):
    """A prefetch that quietly returned nothing would also be constant-time."""
    client = _admin_client()
    _alerts_for(rule, _qualifications(3))

    content = client.get(reverse("alert-list")).content.decode()

    assert "Credencial DGAC" in content
    assert "Record unavailable" not in content


@pytest.mark.django_db
def test_alerts_over_several_entity_types_still_resolve(rule):
    """The prefetch groups by content type; more than one is the real case."""
    client = _admin_client()
    _alerts_for(rule, _qualifications(2))
    aircraft = Aircraft.objects.create(
        registration="RPA-106", type="RPA", model="M3", manufacturer="DJI"
    )
    aircraft_rule = AlertRule.objects.create(
        name="Seguro por vencer",
        entity_type="aircraft",
        field_to_watch="insurance_expiry",
    )
    Alert.objects.create(
        alert_rule=aircraft_rule,
        content_type=ContentType.objects.get_for_model(Aircraft),
        object_id=aircraft.pk,
        message="Insurance expiring",
    )

    content = client.get(reverse("alert-list")).content.decode()

    assert "RPA-106" in content
    assert "Credencial DGAC" in content
