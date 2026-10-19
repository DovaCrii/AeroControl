"""LV-286 -> LV-344: el expediente ya no ofrece ni menciona la revisión meteorológica.

LV-286 la volvió informativa (2026-10-07); el 2026-10-19 la persona dijo «ya no se
ocupa la revisión meteorológica» y `LV-344` paso 1 retiró el renglón del expediente.
La revisión, su modelo y su registro en el plan geoespacial siguen intactos
(paso 2, con su condición de cierre en `MASTER_PLAN.md`).
"""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import translation

from apps.geo.models import GeoPlan
from apps.operations.dossier import MISSING, UNKNOWN, operational_dossier
from apps.operations.test_lv107_dossier import cost_center, permission  # noqa: F401


@pytest.fixture
def plan(permission, cost_center):  # noqa: F811
    owner = User.objects.create_user("w286", "w286@test.com", "pw")  # nosec B106
    return GeoPlan.objects.create(
        title="Plan",
        cost_center=cost_center,
        created_by=owner,
        flight_permission=permission,
    )


@pytest.mark.django_db
class TestTheDossierNoLongerOffersTheWeatherReview:
    def test_there_is_no_weather_row(self, permission, plan):  # noqa: F811
        keys = [i.key for i in operational_dossier(permission)["items"]]

        assert "weather" not in keys
        assert "geo_plan" in keys

    def test_no_row_points_at_the_plan_to_record_a_review(self, permission, plan):  # noqa: F811
        urls = [i.action_url for i in operational_dossier(permission)["items"]]

        assert reverse("geo-plan-detail", args=[plan.pk]) not in urls

    def test_the_gap_counts_are_those_of_the_other_items(self, permission, plan):  # noqa: F811
        """Era opcional: quitarlo no mueve «por confirmar» ni «faltan»."""
        dossier = operational_dossier(permission)
        items = dossier["items"]

        assert dossier["unknown_count"] == sum(1 for i in items if i.status == UNKNOWN)
        assert dossier["missing_count"] == sum(1 for i in items if i.status == MISSING)
        assert dossier["info_count"] == 0

    def test_a_recorded_review_does_not_reappear_in_the_dossier(self, permission, plan):  # noqa: F811
        plan.weather_reviews.create(
            flight_permission=permission,
            target_date=permission.valid_from,
            latitude="-22.300000",
            longitude="-68.900000",
        )

        keys = [i.key for i in operational_dossier(permission)["items"]]

        assert "weather" not in keys
        assert plan.weather_reviews.count() == 1  # la evidencia guardada no se toca


@pytest.mark.django_db
class TestThePermitPage:
    def test_the_page_does_not_mention_the_weather_review(
        self,
        client,
        permission,  # noqa: F811
        plan,
    ):
        admin = User.objects.create_superuser("w286a", "w286a@test.com", "pw")  # nosec B106
        client.force_login(admin)
        for language in ("es", "en"):
            with translation.override(language):
                body = client.get(
                    reverse("permission-detail", args=[permission.pk])
                ).content.decode()
            section = body.split("<h2", 1)[1] if "<h2" in body else body
            assert "Revisión meteorológica" not in section
            assert "Weather reviewed" not in section
