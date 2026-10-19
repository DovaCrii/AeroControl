"""LV-341: observabilidad del uso y voto de utilidad del asistente.

Se fija: 403 sin permiso, 404 apagado, el constraint del voto, la firma (ajena, caducada,
alterada), CSRF, el aviso al 80 % una sola vez, y que ni texto ni argumentos aparecen en la
vista, el admin ni el log (centinelas).
"""

import logging

import pytest
from django.contrib.admin.sites import site
from django.contrib.auth.models import User
from django.core import signing
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.test import Client
from django.urls import reverse

from apps.assistant import usage_views
from apps.assistant.models import AssistantUsage
from apps.assistant.usage_views import VOTE_SALT, sign_usage_id
from apps.core.models import AuditEvent
from apps.core.testing import login_as

USAGE = "assistant-usage"
VOTE = "assistant-vote"
SENTINEL = "SENTINEL-question-text-Juan-Perez"
ARG_SENTINEL = "SENTINEL-tool-argument-9999"


@pytest.fixture
def enabled(settings):
    settings.AI_ASSISTANT_ENABLED = True
    settings.DEBUG = True
    settings.AI_ASSISTANT_DAILY_CAP = 100
    cache.clear()
    return settings


def _usage(user=None, **kwargs):
    return AssistantUsage.objects.create(user=user, **kwargs)


@pytest.mark.django_db
class TestVoteConstraint:
    @pytest.mark.parametrize("value", [None, 1, -1])
    def test_valid_votes_are_stored(self, value):
        usage = _usage(vote=value)
        usage.refresh_from_db()
        assert usage.vote == value

    @pytest.mark.parametrize("value", [0, 2, -2])
    def test_other_values_are_rejected_by_the_database(self, value):
        with pytest.raises(IntegrityError), transaction.atomic():
            _usage(vote=value)


@pytest.mark.django_db
class TestUsageView:
    def test_403_without_the_permission(self, enabled):
        client = login_as("view_flightpermission")
        assert client.get(reverse(USAGE)).status_code == 403

    def test_404_when_off(self, settings):
        settings.AI_ASSISTANT_ENABLED = False
        client = login_as("view_assistantusage")
        assert client.get(reverse(USAGE)).status_code == 404

    def test_it_shows_numbers_by_day_user_and_outcome(self, enabled):
        client = login_as("view_assistantusage")
        _usage(client.user, rounds=2, total_tokens=1234, outcome="ok")
        _usage(client.user, rounds=1, outcome="limit")

        html = client.get(reverse(USAGE)).content.decode()

        assert "1234" in html
        assert client.user.username in html
        assert str(AssistantUsage.OUTCOME_CHOICES[1][1]) in html

    def test_no_text_or_arguments_appear_in_view_admin_or_log(self, enabled, caplog):
        enabled.AI_ASSISTANT_DAILY_CAP = 2
        client = login_as("view_assistantusage")
        _usage(client.user, rounds=2, tools=[ARG_SENTINEL], outcome="ok")

        with caplog.at_level(logging.WARNING):
            html = client.get(reverse(USAGE)).content.decode()

        admin = site._registry[AssistantUsage]
        fields = set(admin.list_display) | set(admin.readonly_fields)
        assert "assistant_daily_cap_80" in caplog.text
        for haystack in (html, caplog.text):
            assert SENTINEL not in haystack and ARG_SENTINEL not in haystack
        # el modelo no tiene dónde guardar la pregunta ni la respuesta
        assert not {"question", "answer", "text", "prompt"} & fields

    def test_warning_strip_and_log_only_above_80_percent(self, enabled, caplog):
        client = login_as("view_assistantusage")
        _usage(client.user, rounds=79)
        with caplog.at_level(logging.WARNING):
            html = client.get(reverse(USAGE)).content.decode()
        assert "usage-cap-warning" not in html
        assert "assistant_daily_cap_80" not in caplog.text

        _usage(client.user, rounds=1)
        with caplog.at_level(logging.WARNING):
            html = client.get(reverse(USAGE)).content.decode()
        assert "usage-cap-warning" in html
        assert "80%" in html

    def test_the_log_warning_is_emitted_once_per_day(self, enabled, caplog):
        client = login_as("view_assistantusage")
        _usage(client.user, rounds=90)
        with caplog.at_level(logging.WARNING):
            for _ in range(3):
                client.get(reverse(USAGE))
        assert caplog.text.count("assistant_daily_cap_80") == 1

    def test_no_cap_means_no_warning(self, enabled):
        enabled.AI_ASSISTANT_DAILY_CAP = 0
        client = login_as("view_assistantusage")
        _usage(client.user, rounds=500)
        assert b"usage-cap-warning" not in client.get(reverse(USAGE)).content


@pytest.mark.django_db
class TestVote:
    def _post(self, client, token, vote):
        return client.post(reverse(VOTE), {"usage_id": token, "vote": vote})

    def test_403_without_the_permission(self, enabled):
        client = login_as()
        usage = _usage(client.user)
        assert self._post(client, sign_usage_id(usage), 1).status_code == 403

    def test_404_when_off(self, settings):
        settings.AI_ASSISTANT_ENABLED = False
        client = login_as("view_flightpermission")
        usage = _usage(client.user)
        assert self._post(client, sign_usage_id(usage), 1).status_code == 404

    def test_a_tool_permission_other_than_flights_can_vote_its_own_row(self, enabled):
        """LV-348: quien ve el panel con otra herramienta (p. ej. `view_aircraft`) puede votar."""
        client = login_as("view_aircraft")
        usage = _usage(client.user)
        owner = User.objects.create_user("owner2", password="pw")  # nosec B106
        other = _usage(owner)

        assert self._post(client, sign_usage_id(usage), 1).status_code == 204
        usage.refresh_from_db()
        assert usage.vote == 1
        assert self._post(client, sign_usage_id(other), 1).status_code == 404
        other.refresh_from_db()
        assert other.vote is None

    def test_get_is_not_allowed(self, enabled):
        client = login_as("view_flightpermission")
        assert client.get(reverse(VOTE)).status_code == 405

    def test_a_vote_is_stored_and_audited(self, enabled):
        client = login_as("view_flightpermission")
        usage = _usage(client.user)

        response = self._post(client, sign_usage_id(usage), -1)

        assert response.status_code == 204
        usage.refresh_from_db()
        assert usage.vote == -1
        event = AuditEvent.objects.filter(object_id=str(usage.pk)).latest("created_at")
        assert event.model_label == "assistant.AssistantUsage"

    def test_the_vote_can_be_changed(self, enabled):
        client = login_as("view_flightpermission")
        usage = _usage(client.user)
        self._post(client, sign_usage_id(usage), -1)
        self._post(client, sign_usage_id(usage), 1)
        usage.refresh_from_db()
        assert usage.vote == 1

    def test_someone_elses_row_is_rejected(self, enabled):
        client = login_as("view_flightpermission")
        owner = User.objects.create_user("owner", password="pw")  # nosec B106
        usage = _usage(owner)

        assert self._post(client, sign_usage_id(usage), 1).status_code == 404
        usage.refresh_from_db()
        assert usage.vote is None

    def test_a_token_signed_for_another_person_is_rejected(self, enabled):
        client = login_as("view_flightpermission")
        usage = _usage(client.user)
        stolen = signing.dumps({"u": str(usage.pk), "p": 0}, salt=VOTE_SALT)
        assert self._post(client, stolen, 1).status_code == 404

    def test_a_tampered_signature_is_rejected(self, enabled):
        client = login_as("view_flightpermission")
        usage = _usage(client.user)
        token = sign_usage_id(usage)[:-2] + "xx"
        assert self._post(client, token, 1).status_code == 400
        assert self._post(client, str(usage.pk), 1).status_code == 400

    def test_an_expired_signature_is_rejected(self, enabled, monkeypatch):
        client = login_as("view_flightpermission")
        usage = _usage(client.user)
        monkeypatch.setattr(usage_views, "VOTE_MAX_AGE", -1)
        assert self._post(client, sign_usage_id(usage), 1).status_code == 400
        usage.refresh_from_db()
        assert usage.vote is None

    @pytest.mark.parametrize("value", ["0", "2", "-2", "x", ""])
    def test_a_vote_outside_plus_minus_one_is_rejected(self, enabled, value):
        client = login_as("view_flightpermission")
        usage = _usage(client.user)
        assert self._post(client, sign_usage_id(usage), value).status_code == 400
        usage.refresh_from_db()
        assert usage.vote is None

    def test_csrf_is_enforced(self, enabled):
        login = login_as("view_flightpermission")
        usage = _usage(login.user)
        strict = Client(enforce_csrf_checks=True)
        strict.cookies = login.cookies
        response = strict.post(
            reverse(VOTE), {"usage_id": sign_usage_id(usage), "vote": 1}
        )
        assert response.status_code == 403
        usage.refresh_from_db()
        assert usage.vote is None


def test_both_new_views_are_protected_by_a_model_permission():
    from apps.core.test_lv268_permission_contract import _has_model_permission

    assert _has_model_permission(usage_views.AssistantUsageView)
    assert _has_model_permission(usage_views.AssistantVote)
