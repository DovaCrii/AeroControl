"""B4.4: non-blocking operator-aircraft compatibility check.

Agreed with the user (2026-07-30): a warning, not a validation error, and the
match is Qualification.qualification_type.model_keywords against
Aircraft.model (Aircraft.type is uniformly "RPA" in the real fleet and carries
no signal to compare against).
"""

from datetime import date, timedelta

import pytest
from django.contrib.auth.models import Permission, User
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.registry.models import (
    Aircraft,
    CostCenter,
    Operator,
    Qualification,
    QualificationType,
)
from apps.registry.selectors import operator_aircraft_compatibility_gaps


def _client(*codenames):
    user = User.objects.create_user(f"u-{'-'.join(codenames) or 'none'}", password="pw")
    if codenames:
        user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
    client = Client()
    assert client.login(username=user.username, password="pw")
    return client


def _cc(code="CC1"):
    return CostCenter.objects.create(code=code, name=code)


def _operator(employee_id, cc, full_name=None):
    return Operator.objects.create(
        employee_id=employee_id,
        full_name=full_name or f"Pilot {employee_id}",
        cost_center=cc,
    )


def _aircraft(registration, model, cc):
    return Aircraft.objects.create(
        registration=registration,
        type="RPA",
        model=model,
        manufacturer="DJI",
        cost_center=cc,
    )


class TestCompatibilityGaps:
    @pytest.mark.django_db
    def test_no_gap_when_qualification_keyword_matches_aircraft_model(self, db):
        cc = _cc()
        operator = _operator("E1", cc)
        aircraft = _aircraft("CC-A1", "Mavic 3 Enterprise", cc)
        mavic = QualificationType.objects.create(
            code="mavic", name="Serie Mavic", model_keywords="mavic"
        )
        Qualification.objects.create(
            operator=operator, qualification_type=mavic, issue_date=date(2026, 1, 1)
        )

        gaps = operator_aircraft_compatibility_gaps([operator], [aircraft])

        assert gaps == []

    @pytest.mark.django_db
    def test_gap_when_operator_has_no_matching_qualification(self, db):
        cc = _cc()
        operator = _operator("E1", cc)
        aircraft = _aircraft("CC-A1", "Matrice 300", cc)
        mavic = QualificationType.objects.create(
            code="mavic", name="Serie Mavic", model_keywords="mavic"
        )
        Qualification.objects.create(
            operator=operator, qualification_type=mavic, issue_date=date(2026, 1, 1)
        )

        gaps = operator_aircraft_compatibility_gaps([operator], [aircraft])

        assert gaps == [(operator, aircraft)]

    @pytest.mark.django_db
    def test_expired_qualification_does_not_count(self, db):
        cc = _cc()
        operator = _operator("E1", cc)
        aircraft = _aircraft("CC-A1", "Mavic 3 Enterprise", cc)
        mavic = QualificationType.objects.create(
            code="mavic", name="Serie Mavic", model_keywords="mavic"
        )
        Qualification.objects.create(
            operator=operator,
            qualification_type=mavic,
            issue_date=date(2020, 1, 1),
            expiry_date=timezone.localdate() - timedelta(days=1),
        )

        gaps = operator_aircraft_compatibility_gaps([operator], [aircraft])

        assert gaps == [(operator, aircraft)]

    @pytest.mark.django_db
    def test_empty_rosters_yield_no_gaps(self, db):
        cc = _cc()
        operator = _operator("E1", cc)
        aircraft = _aircraft("CC-A1", "Matrice 300", cc)

        assert operator_aircraft_compatibility_gaps([], [aircraft]) == []
        assert operator_aircraft_compatibility_gaps([operator], []) == []

    @pytest.mark.django_db
    def test_qualification_type_without_keywords_matches_nothing(self, db):
        """Blank model_keywords means the type is not yet configured for
        matching -- it should not silently authorize everything."""
        cc = _cc()
        operator = _operator("E1", cc)
        aircraft = _aircraft("CC-A1", "Matrice 300", cc)
        unset = QualificationType.objects.create(code="unset", name="Sin configurar")
        Qualification.objects.create(
            operator=operator, qualification_type=unset, issue_date=date(2026, 1, 1)
        )

        gaps = operator_aircraft_compatibility_gaps([operator], [aircraft])

        assert gaps == [(operator, aircraft)]


class TestFlightPermissionCreateWarns:
    @pytest.mark.django_db
    def test_creating_a_permission_with_a_gap_warns_but_still_saves(self, db):
        cc = _cc()
        operator = _operator("E1", cc, full_name="Pilot One")
        aircraft = _aircraft("CC-A1", "Matrice 300", cc)
        mavic = QualificationType.objects.create(
            code="mavic", name="Serie Mavic", model_keywords="mavic"
        )
        Qualification.objects.create(
            operator=operator, qualification_type=mavic, issue_date=date(2026, 1, 1)
        )
        client = _client("add_flightpermission", "view_flightpermission")

        response = client.post(
            reverse("permission-create"),
            {
                "status": "requested",
                "permission_number": "P-GAP",
                "operators": [operator.pk],
                "aircraft_fleet": [aircraft.pk],
                "cost_center": cc.pk,
                "purpose": "Survey",
                "valid_from": "2026-07-01",
                "valid_until": "2026-07-10",
                "location": "Site",
            },
            follow=True,
        )

        assert response.status_code == 200
        from apps.operations.models import FlightPermission

        assert FlightPermission.objects.filter(permission_number="P-GAP").exists()
        messages = [str(m) for m in response.context["messages"]]
        assert any("Pilot One" in m and "CC-A1" in m for m in messages)

    @pytest.mark.django_db
    def test_creating_a_permission_with_full_coverage_has_no_warning(self, db):
        cc = _cc()
        operator = _operator("E1", cc, full_name="Pilot One")
        aircraft = _aircraft("CC-A1", "Mavic 3 Enterprise", cc)
        mavic = QualificationType.objects.create(
            code="mavic", name="Serie Mavic", model_keywords="mavic"
        )
        Qualification.objects.create(
            operator=operator, qualification_type=mavic, issue_date=date(2026, 1, 1)
        )
        client = _client("add_flightpermission", "view_flightpermission")

        response = client.post(
            reverse("permission-create"),
            {
                "status": "requested",
                "permission_number": "P-OK",
                "operators": [operator.pk],
                "aircraft_fleet": [aircraft.pk],
                "cost_center": cc.pk,
                "purpose": "Survey",
                "valid_from": "2026-07-01",
                "valid_until": "2026-07-10",
                "location": "Site",
            },
            follow=True,
        )

        assert response.status_code == 200
        messages = [str(m) for m in response.context["messages"]]
        assert not any("qualification" in m.lower() for m in messages)
