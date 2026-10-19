"""LV-336: el interruptor de producción del asistente y su comando de diagnóstico."""

import io

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import reverse

from apps.assistant.client import AssistantUnavailable
from apps.assistant.management.commands import assistant_probar
from apps.assistant.test_lv332_panel import MARKERS
from apps.assistant.tests import SECRET_KEY
from apps.assistant.views import assistant_available
from apps.core.testing import login_as

ASK = "assistant-ask"
PANEL = "assistant-panel-ask"


def _production(settings, enabled=True, allow=False):
    settings.DEBUG = False
    settings.AI_ASSISTANT_ENABLED = enabled
    settings.AI_ASSISTANT_ALLOW_PRODUCTION = allow
    settings.AI_ASSISTANT_MAX_PER_HOUR = 0
    settings.AI_ASSISTANT_DAILY_CAP = 0


class TestTheSwitch:
    def test_production_needs_allow_production_even_if_enabled(self, settings):
        _production(settings, enabled=True, allow=False)

        assert assistant_available() is False

    def test_production_opens_with_both(self, settings):
        _production(settings, enabled=True, allow=True)

        assert assistant_available() is True

    def test_allow_production_alone_does_not_open_it(self, settings):
        _production(settings, enabled=False, allow=True)

        assert assistant_available() is False

    def test_development_needs_only_enabled(self, settings):
        settings.DEBUG = True
        settings.AI_ASSISTANT_ENABLED = True
        settings.AI_ASSISTANT_ALLOW_PRODUCTION = False

        assert assistant_available() is True

    def test_allow_production_is_off_by_default(self, settings):
        from config.settings import base

        assert base.AI_ASSISTANT_ALLOW_PRODUCTION is False


@pytest.mark.django_db
class TestProductionViews:
    def test_enabled_without_allow_is_a_404_with_no_panel(self, settings):
        _production(settings, enabled=True, allow=False)
        client = login_as("view_flightpermission")

        assert client.get(reverse(ASK)).status_code == 404
        assert client.post(reverse(PANEL), {"question": "x"}).status_code == 404
        html = client.get(reverse("permission-list")).content.decode()
        assert not any(marker in html for marker in MARKERS)

    def test_with_both_the_screen_and_panel_exist(self, settings):
        _production(settings, enabled=True, allow=True)
        client = login_as("view_flightpermission")

        assert client.get(reverse(ASK)).status_code == 200
        html = client.get(reverse("permission-list")).content.decode()
        assert 'id="assistant-open"' in html

    def test_emergency_off_closes_it_again(self, settings):
        _production(settings, enabled=False, allow=True)
        client = login_as("view_flightpermission")

        assert client.get(reverse(ASK)).status_code == 404
        html = client.get(reverse("permission-list")).content.decode()
        assert not any(marker in html for marker in MARKERS)

    def test_permission_contract_holds_in_production(self, settings):
        """Abierto en producción, quien no tiene view_flightpermission sigue sin entrar."""
        _production(settings, enabled=True, allow=True)
        client = login_as()

        assert client.get(reverse(ASK)).status_code == 403
        assert client.post(reverse(ASK), {"question": "x"}).status_code == 403
        assert client.post(reverse(PANEL), {"question": "x"}).status_code == 403
        html = login_as("view_operator").get(reverse("operator-list")).content.decode()
        assert not any(marker in html for marker in MARKERS)


class _Probe:
    """Cliente falso para `assistant_probar`: el mismo que usaría el servicio."""

    def __init__(self, configured=True, reply=None, error=None):
        self.configured = configured
        self.api_key = SECRET_KEY if configured else ""
        self.base_url = "https://example.invalid/v1"
        self.model = "test/model"
        self._reply = reply
        self._error = error
        self.calls = 0

    def chat(self, messages, tools=None):
        self.calls += 1
        if self._error:
            raise AssistantUnavailable(self._error)
        return dict(self._reply)


def _run(monkeypatch, probe, *args):
    monkeypatch.setattr(assistant_probar, "NvidiaClient", lambda: probe)
    out = io.StringIO()
    call_command("assistant_probar", *args, stdout=out, stderr=io.StringIO())
    return out.getvalue()


class TestProbeCommand:
    def test_report_without_ping_makes_no_call_and_hides_the_key(
        self, settings, monkeypatch
    ):
        _production(settings, enabled=True, allow=False)
        settings.AI_ASSISTANT_MAX_PER_HOUR = 7
        settings.AI_ASSISTANT_DAILY_CAP = 0
        probe = _Probe()

        text = _run(monkeypatch, probe)

        assert probe.calls == 0
        assert SECRET_KEY not in text
        assert "key: present" in text
        assert "model: test/model" in text
        assert "base_url: https://example.invalid/v1" in text
        assert "switch: CLOSED" in text
        assert "cap_per_hour_per_user: 7" in text
        assert "cap_per_day_global: off (0)" in text

    def test_report_says_open_and_shows_daily_cap(self, settings, monkeypatch):
        _production(settings, enabled=True, allow=True)
        settings.AI_ASSISTANT_DAILY_CAP = 300

        text = _run(monkeypatch, _Probe())

        assert "switch: OPEN" in text
        assert "cap_per_day_global: 300" in text

    def test_missing_key_is_reported(self, settings, monkeypatch):
        _production(settings)

        assert "key: MISSING" in _run(monkeypatch, _Probe(configured=False))

    def test_ping_happy_path_reports_latency_and_tokens_only(
        self, settings, monkeypatch
    ):
        _production(settings, enabled=True, allow=True)
        probe = _Probe(
            reply={
                "role": "assistant",
                "content": "SECRET-MODEL-TEXT",
                "_total_tokens": 42,
            }
        )

        text = _run(monkeypatch, probe, "--ping")

        assert probe.calls == 1
        assert "ping: ok" in text and "tokens: 42" in text and " ms" in text
        assert "SECRET-MODEL-TEXT" not in text
        assert SECRET_KEY not in text

    def test_ping_without_key_fails_without_calling(self, settings, monkeypatch):
        _production(settings)
        probe = _Probe(configured=False)

        with pytest.raises(CommandError, match="not configured"):
            _run(monkeypatch, probe, "--ping")
        assert probe.calls == 0

    def test_ping_error_reports_the_code_not_the_key(self, settings, monkeypatch):
        _production(settings)
        probe = _Probe(error="http-401")

        with pytest.raises(CommandError) as raised:
            _run(monkeypatch, probe, "--ping")
        assert "http-401" in str(raised.value)
        assert SECRET_KEY not in str(raised.value)

    def test_real_client_key_never_in_output(self, settings, monkeypatch):
        """Con el cliente de verdad (sin red: se sustituye `chat`), la llave no sale."""
        _production(settings)
        settings.NVIDIA_API_KEY = SECRET_KEY
        monkeypatch.setattr(
            "apps.assistant.client.NvidiaClient.chat",
            lambda self, messages, tools=None: {"content": "x", "_total_tokens": 3},
        )
        out = io.StringIO()

        call_command("assistant_probar", "--ping", stdout=out)

        assert SECRET_KEY not in out.getvalue()
        assert "key: present" in out.getvalue()
