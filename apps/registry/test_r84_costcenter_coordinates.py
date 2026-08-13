"""R8.4: the site coordinates of a cost center.

Why the pair rule is enforced in `clean()` and not only in the form: a half
entered point does not fail loudly, it fails *silently* -- the dashboard simply
never shows a forecast, and nobody can tell that from "this site has no
coordinates on file yet". The admin, an import and the shell all reach the model
without the form (AGENTS.md: validate in both).
"""

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.registry.forms import CostCenterForm
from apps.registry.models import CostCenter


def _form_data(**overrides):
    data = {
        "code": "742",
        "name": "Tranque Talabre",
        "responsible": "Ricardo Flores",
        "responsible_type": "administrator",
    }
    data.update(overrides)
    return data


@pytest.mark.django_db
class TestPairRule:
    def test_both_together_is_valid(self):
        cc = CostCenter(
            code="CC1", latitude=Decimal("-22.300000"), longitude=Decimal("-68.900000")
        )
        cc.full_clean(exclude=["tenant"])

    def test_neither_is_valid(self):
        """No coordinates is the normal state of an existing cost center, not
        an error to fix."""
        CostCenter(code="CC1").full_clean(exclude=["tenant"])

    @pytest.mark.parametrize(
        ("latitude", "longitude"),
        [(Decimal("-22.300000"), None), (None, Decimal("-68.900000"))],
    )
    def test_a_lone_coordinate_is_refused_on_both_fields(self, latitude, longitude):
        cc = CostCenter(code="CC1", latitude=latitude, longitude=longitude)

        with pytest.raises(ValidationError) as raised:
            cc.full_clean(exclude=["tenant"])

        assert set(raised.value.message_dict) == {"latitude", "longitude"}

    def test_the_form_surfaces_the_same_rule(self):
        form = CostCenterForm(data=_form_data(latitude="-22.3"))

        assert not form.is_valid()
        assert "latitude" in form.errors and "longitude" in form.errors

    def test_the_form_saves_the_pair(self):
        form = CostCenterForm(data=_form_data(latitude="-22.3", longitude="-68.9"))

        assert form.is_valid(), form.errors
        cost_center = form.save()

        assert cost_center.coordinates == (-22.3, -68.9)

    def test_a_cost_center_without_a_site_has_no_coordinates(self):
        assert CostCenter(code="CC1").coordinates is None


@pytest.mark.django_db
class TestRange:
    @pytest.mark.parametrize(
        ("latitude", "longitude"),
        [("-91.000000", "-68.900000"), ("-22.300000", "181.000000")],
    )
    def test_impossible_points_are_refused(self, latitude, longitude):
        cc = CostCenter(
            code="CC1", latitude=Decimal(latitude), longitude=Decimal(longitude)
        )

        with pytest.raises(ValidationError):
            cc.full_clean(exclude=["tenant"])
