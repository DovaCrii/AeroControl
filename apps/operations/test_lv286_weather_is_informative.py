"""LV-286: la revisión meteorológica del expediente es informativa, no «por confirmar».

Pedido del usuario (2026-10-07, mirando la ficha de un permiso con la insignia
«1 por confirmar» por la revisión meteorológica): *«lo quitamos para la revisión,
como punto es opcional o informativo»*.

Un renglón que nace ámbar y que nadie está obligado a cerrar deja un contador que no
llega a cero, y eso enseña a ignorar el contador — la misma razón por la que
`LV-194` retiró los dos últimos renglones.
"""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone

from apps.geo.models import GeoPlan
from apps.operations.dossier import INFO, OK, UNKNOWN, operational_dossier
from apps.operations.test_lv107_dossier import cost_center, permission  # noqa: F401

TODAY = timezone.localdate()


@pytest.fixture
def plan(permission, cost_center):  # noqa: F811
    owner = User.objects.create_user("w286", "w286@test.com", "pw")  # nosec B106
    return GeoPlan.objects.create(
        title="Plan",
        cost_center=cost_center,
        created_by=owner,
        flight_permission=permission,
    )


def _weather(permission):  # noqa: F811
    return next(
        i for i in operational_dossier(permission)["items"] if i.key == "weather"
    )


@pytest.mark.django_db
class TestWithoutAReview:
    def test_the_row_is_informative_not_to_confirm(self, permission, plan):  # noqa: F811
        item = _weather(permission)

        assert item.status == INFO
        assert item.status != UNKNOWN

    def test_it_adds_nothing_to_the_to_confirm_counter(self, permission, plan):  # noqa: F811
        dossier = operational_dossier(permission)

        # Lo que cuenta como «por confirmar» son los demás renglones; el
        # meteorológico se cuenta aparte, como informativo.
        others = sum(
            1 for i in dossier["items"] if i.status == UNKNOWN and i.key != "weather"
        )
        assert dossier["unknown_count"] == others
        assert dossier["info_count"] == 1

    def test_it_does_not_stop_the_dossier_from_reading_complete_on_its_own(
        self,
        permission,  # noqa: F811
        plan,
    ):
        """Lo único opcional que queda sin registrar no puede impedir «Completo»."""
        dossier = operational_dossier(permission)
        pending = [i.key for i in dossier["items"] if not i.counts_toward_complete]

        assert "weather" not in pending

    def test_the_shortcut_to_record_it_is_kept(self, permission, plan):  # noqa: F811
        """Es opcional, no inalcanzable: sigue llevando al plan donde se registra."""
        item = _weather(permission)

        assert item.action_url == reverse("geo-plan-detail", args=[plan.pk])

    def test_the_detail_says_it_is_optional(self, permission, plan):  # noqa: F811
        assert str(_weather(permission).detail).startswith("Opcional")


@pytest.mark.django_db
class TestWithAReview:
    def test_a_recorded_review_still_reads_as_in_order(self, permission, plan):  # noqa: F811
        plan.weather_reviews.create(
            flight_permission=permission,
            target_date=TODAY,
            latitude="-22.300000",
            longitude="-68.900000",
        )

        item = _weather(permission)

        assert item.status == OK
        assert operational_dossier(permission)["info_count"] == 0


@pytest.mark.django_db
class TestThePermitPage:
    def _body(self, client, permission, plan):  # noqa: F811
        admin = User.objects.create_superuser("w286a", "w286a@test.com", "pw")  # nosec B106
        client.force_login(admin)
        return client.get(
            reverse("permission-detail", args=[permission.pk])
        ).content.decode()

    def test_no_amber_to_confirm_badge_for_the_weather_review(
        self,
        client,
        permission,  # noqa: F811
        plan,
    ):
        body = self._body(client, permission, plan)

        assert "Revisión meteorológica registrada" in body  # el renglón sigue ahí
        assert (
            "por confirmar"
            not in body.split("Expediente operativo")[1].split("</h2>")[0]
        )

    def test_the_row_is_drawn_as_optional_not_as_a_warning_dot(
        self,
        client,
        permission,  # noqa: F811
        plan,
    ):
        body = self._body(client, permission, plan)
        section = body.split("Revisión meteorológica registrada")[0].rsplit("<tr>", 1)[
            1
        ]

        assert "text-warning" not in section
        assert "Opcional" in section

    def test_the_detail_is_written_in_spanish(self, client, permission, plan):  # noqa: F811
        body = self._body(client, permission, plan)

        assert "Opcional: sin revisión registrada" in body
