"""R5.8: "Habilitaciones" was redundant with the operator's own ficha --
Operator.authorizations (free text) said the same thing the Qualification
list showed structured, usually with no date. Moved: the ficha now shows the
operator's real qualifications, replacing the free-text field; the sidebar
link is hidden (Qualification/qualification-list are untouched -- they still
back the expiry alerts and the operator-aircraft compatibility check)."""

from datetime import date, timedelta

import pytest
from django.contrib.auth.models import Permission, User
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.registry.models import CostCenter, Operator, Qualification, QualificationType

TODAY = timezone.localdate()


def _client(*codenames):
    user = User.objects.create_user(f"u-{'-'.join(codenames) or 'none'}", password="pw")
    if codenames:
        user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
    client = Client()
    assert client.login(username=user.username, password="pw")
    return client


@pytest.mark.django_db
def test_ficha_shows_qualifications_instead_of_free_text_authorizations():
    cc = CostCenter.objects.create(code="CC1", name="One")
    operator = Operator.objects.create(
        employee_id="E1",
        full_name="Pilot One",
        cost_center=cc,
        authorizations="Matrice 300 Rtk - Mavic 3",
    )
    mavic = QualificationType.objects.create(code="mavic", name="Serie Mavic")
    Qualification.objects.create(
        operator=operator,
        qualification_type=mavic,
        issue_date=date(2026, 1, 1),
        expiry_date=TODAY + timedelta(days=30),
    )

    response = _client("view_operator", "view_qualification").get(
        reverse("operator-detail", args=[operator.pk])
    )
    content = response.content.decode()

    assert "Serie Mavic" in content
    assert "Matrice 300 Rtk - Mavic 3" not in content


@pytest.mark.django_db
def test_ficha_shows_empty_state_with_no_qualifications():
    operator = Operator.objects.create(employee_id="E1", full_name="Pilot One")

    response = _client("view_operator").get(
        reverse("operator-detail", args=[operator.pk])
    )

    assert list(response.context["qualifications"]) == []


@pytest.mark.django_db
def test_ficha_marks_an_expired_qualification():
    operator = Operator.objects.create(employee_id="E1", full_name="Pilot One")
    phantom = QualificationType.objects.create(code="phantom", name="Serie Phantom")
    Qualification.objects.create(
        operator=operator,
        qualification_type=phantom,
        expiry_date=date(2000, 1, 1),
    )

    response = _client("view_operator").get(
        reverse("operator-detail", args=[operator.pk])
    )

    assert "bg-danger" in response.content.decode()


@pytest.mark.django_db
def test_ficha_edit_link_requires_change_qualification_permission():
    operator = Operator.objects.create(employee_id="E1", full_name="Pilot One")
    mavic = QualificationType.objects.create(code="mavic", name="Serie Mavic")
    qualification = Qualification.objects.create(
        operator=operator, qualification_type=mavic
    )

    without_perm = _client("view_operator").get(
        reverse("operator-detail", args=[operator.pk])
    )
    assert reverse("qualification-update", args=[qualification.pk]) not in (
        without_perm.content.decode()
    )

    with_perm = _client("view_operator", "change_qualification").get(
        reverse("operator-detail", args=[operator.pk])
    )
    assert reverse("qualification-update", args=[qualification.pk]) in (
        with_perm.content.decode()
    )


@pytest.mark.django_db
def test_sidebar_does_not_link_to_qualification_list_but_the_url_still_works():
    client = _client("view_operator", "view_qualification")

    response = client.get(reverse("operator-list"))

    assert reverse("qualification-list") not in response.content.decode()
    # LV-7/LV-D8 pattern: hidden from the menu, not deleted -- the page is
    # still reachable directly (audit-all-at-once).
    assert client.get(reverse("qualification-list")).status_code == 200
