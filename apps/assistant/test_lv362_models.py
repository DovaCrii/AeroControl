"""LV-362: cadena de modelos de respaldo, `enable_thinking`, razonamiento filtrado, 429 y cupo.

Sin red (`conftest.py` la bloquea): `urlopen` se reemplaza por un guion por modelo. Cada prueba
fija un comportamiento que no puede aflojarse; ver `docs/dev/asistente-ia.md`.
"""

import io
import json
import logging
import urllib.error

import pytest
from django.core.management import call_command

from apps.assistant import client as client_module
from apps.assistant import service
from apps.assistant.client import AssistantUnavailable, NvidiaClient, strip_reasoning
from apps.assistant.management.commands import assistant_probar
from apps.assistant.models import AssistantUsage
from apps.assistant.service import ask
from apps.core.testing import login_as

pytestmark = pytest.mark.django_db

SECRET_KEY = "nvapi-TEST-NOT-A-REAL-KEY"
TOOLS = [{"type": "function", "function": {"name": "t", "parameters": {}}}]
MESSAGES = [{"role": "user", "content": "SECRET-QUESTION-TEXT"}]


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def ok(content="hola", tokens=7, tool_calls=None, **extra):
    message = {"role": "assistant", "content": content, **extra}
    if tool_calls:
        message["tool_calls"] = tool_calls
    return _Response(
        json.dumps(
            {"choices": [{"message": message}], "usage": {"total_tokens": tokens}}
        ).encode()
    )


def http(status, body=b""):
    return urllib.error.HTTPError("u", status, "x", {}, io.BytesIO(body))


class Service:
    """`urlopen` falso: por modelo, una lista de respuestas o errores que se van consumiendo."""

    def __init__(self, script):
        self.script = {model: list(items) for model, items in script.items()}
        self.calls = []

    def __call__(self, request, timeout):
        body = json.loads(request.data) if request.data else {}
        self.calls.append((request.full_url, body))
        model = body.get("model")
        item = self.script[model].pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    @property
    def models_called(self):
        return [body.get("model") for _url, body in self.calls]


@pytest.fixture(autouse=True)
def _clean(settings, monkeypatch):
    client_module._THINKING_UNSUPPORTED.clear()
    client_module._TOOLS_UNSUPPORTED.clear()
    settings.AI_ASSISTANT_RETRIES_429 = 2
    settings.AI_ASSISTANT_RETRY_BACKOFF = 1.0
    settings.AI_ASSISTANT_MAX_PER_HOUR = 0
    settings.AI_ASSISTANT_DAILY_CAP = 0
    sleeps = []
    monkeypatch.setattr(client_module, "_sleep", sleeps.append)
    yield sleeps
    client_module._THINKING_UNSUPPORTED.clear()
    client_module._TOOLS_UNSUPPORTED.clear()


@pytest.fixture
def sleeps(_clean):
    return _clean


def chain(*models):
    return NvidiaClient(
        api_key=SECRET_KEY,
        base_url="https://example.test/v1",
        model=models[0],
        fallbacks=list(models[1:]),
        timeout=5,
    )


def install(monkeypatch, script):
    fake = Service(script)
    monkeypatch.setattr(client_module.urllib.request, "urlopen", fake)
    return fake


class TestStripReasoning:
    def test_removes_think_blocks_and_keeps_the_answer(self):
        assert strip_reasoning("<think>pienso\nmucho</think>\nHola.") == "Hola."

    def test_a_closing_tag_without_opening_keeps_what_follows(self):
        assert strip_reasoning("razonamiento largo</think>Respuesta") == "Respuesta"

    def test_an_unclosed_think_is_all_reasoning(self):
        assert strip_reasoning("<think>nunca termina") == ""

    @pytest.mark.parametrize(
        "text",
        [
            "Here's a thinking process:\n1. The user asks...",
            "Here is a thinking process to answer this question",
            "Thinking Process:\n- step one",
        ],
    )
    def test_leaked_reasoning_without_tags_is_dropped(self, text):
        assert strip_reasoning(text) == ""

    def test_plain_text_and_none_pass_through(self):
        assert strip_reasoning("  Hay 3 permisos vigentes.  ") == (
            "Hay 3 permisos vigentes."
        )
        assert strip_reasoning(None) == ""
        # Una frase que sólo menciona «thinking» en medio no es razonamiento filtrado.
        assert strip_reasoning("I was thinking process-wise") != ""


class TestTheChain:
    def test_defaults_come_from_settings_in_one_place(self, settings):
        settings.NVIDIA_MODEL = "a/one"
        settings.NVIDIA_MODEL_FALLBACKS = " b/two, c/three ,,a/one"

        assert NvidiaClient(api_key="k").models == ["a/one", "b/two", "c/three"]

    def test_404_goes_to_the_next_model(self, monkeypatch):
        fake = install(monkeypatch, {"a": [http(404)], "b": [ok("de b")]})

        message = chain("a", "b").chat(MESSAGES)

        assert message["content"] == "de b" and message["_model"] == "b"
        assert fake.models_called == ["a", "b"]

    def test_410_goes_to_the_next_model(self, monkeypatch):
        install(monkeypatch, {"a": [http(410)], "b": [ok("de b")]})

        assert chain("a", "b").chat(MESSAGES)["_model"] == "b"

    def test_an_empty_answer_goes_to_the_next_model(self, monkeypatch):
        install(monkeypatch, {"a": [ok("   ")], "b": [ok("de b")]})

        assert chain("a", "b").chat(MESSAGES)["content"] == "de b"

    def test_reasoning_only_goes_to_the_next_model(self, monkeypatch):
        install(
            monkeypatch,
            {
                "a": [ok("<think>solo pienso</think>")],
                "b": [ok("Here's a thinking process: ...")],
                "c": [ok("listo")],
            },
        )

        message = chain("a", "b", "c").chat(MESSAGES)

        assert message["content"] == "listo" and message["_model"] == "c"

    def test_reasoning_is_stripped_from_a_good_answer(self, monkeypatch):
        install(monkeypatch, {"a": [ok("<think>x</think>Respuesta")]})

        assert chain("a").chat(MESSAGES)["content"] == "Respuesta"

    def test_all_empty_returns_an_empty_message_not_an_error(self, monkeypatch):
        install(monkeypatch, {"a": [ok("")], "b": [ok(None)]})

        message = chain("a", "b").chat(MESSAGES)

        assert not message.get("content") and not message.get("tool_calls")

    def test_all_gone_is_a_typed_http_error(self, monkeypatch):
        install(monkeypatch, {"a": [http(404)], "b": [http(410)]})

        with pytest.raises(AssistantUnavailable) as raised:
            chain("a", "b").chat(MESSAGES)

        assert raised.value.kind == "http"

    def test_a_server_error_does_not_burn_the_chain(self, monkeypatch):
        fake = install(monkeypatch, {"a": [http(500)], "b": [ok()]})

        with pytest.raises(AssistantUnavailable, match="http-500"):
            chain("a", "b").chat(MESSAGES)

        assert fake.models_called == ["a"]

    def test_the_answering_model_is_recorded_in_the_usage_row(self, monkeypatch):
        install(monkeypatch, {"a": [http(404)], "b": [ok("listo")]})
        user = login_as("view_flightpermission").user

        answer = ask(user, "hola", client=chain("a", "b"))

        assert answer.ok
        assert AssistantUsage.objects.get().model == "b"


class TestThinkingOption:
    def test_every_request_turns_thinking_off(self, monkeypatch):
        fake = install(monkeypatch, {"a": [ok()]})

        chain("a").chat(MESSAGES)

        assert fake.calls[0][1]["chat_template_kwargs"] == {"enable_thinking": False}

    def test_a_400_retries_without_the_option_and_remembers_it(self, monkeypatch):
        fake = install(monkeypatch, {"a": [http(400), ok("uno"), ok("dos")]})

        assert chain("a").chat(MESSAGES)["content"] == "uno"
        assert chain("a").chat(MESSAGES)["content"] == "dos"

        bodies = [body for _url, body in fake.calls]
        assert "chat_template_kwargs" in bodies[0]
        assert "chat_template_kwargs" not in bodies[1]
        assert "chat_template_kwargs" not in bodies[2]  # recordado: ni se intenta

    def test_a_422_is_treated_the_same(self, monkeypatch):
        install(monkeypatch, {"a": [http(422), ok("uno")]})

        assert chain("a").chat(MESSAGES)["content"] == "uno"
        assert "a" in client_module._THINKING_UNSUPPORTED

    def test_a_400_for_another_reason_is_not_remembered_as_thinking(self, monkeypatch):
        install(monkeypatch, {"a": [http(400), http(400)]})

        with pytest.raises(AssistantUnavailable, match="http-400"):
            chain("a").chat(MESSAGES)

        assert "a" not in client_module._THINKING_UNSUPPORTED


class TestTools:
    CALL = [
        {
            "id": "c1",
            "type": "function",
            "function": {"name": "permits_summary", "arguments": "{}"},
        }
    ]

    def test_a_tool_call_without_text_is_a_valid_answer(self, monkeypatch):
        fake = install(monkeypatch, {"a": [ok(None, tool_calls=self.CALL)]})

        message = chain("a", "b").chat(MESSAGES, tools=TOOLS)

        assert message["tool_calls"] and fake.models_called == ["a"]

    def test_the_fallback_still_gets_the_tools(self, monkeypatch):
        fake = install(
            monkeypatch,
            {"a": [http(404)], "b": [ok(None, tool_calls=self.CALL)]},
        )

        message = chain("a", "b").chat(MESSAGES, tools=TOOLS)

        assert message["tool_calls"]
        assert fake.calls[1][1]["tools"] == TOOLS
        assert fake.calls[1][1]["tool_choice"] == "auto"

    def test_a_model_that_rejects_tools_is_skipped_and_remembered(self, monkeypatch):
        fake = install(
            monkeypatch,
            {
                "a": [http(400), http(400, b"tools are not supported"), ok("sin")],
                "b": [ok("con herramientas"), ok("otra vez")],
            },
        )

        first = chain("a", "b").chat(MESSAGES, tools=TOOLS)
        second = chain("a", "b").chat(MESSAGES, tools=TOOLS)

        assert first["_model"] == second["_model"] == "b"
        # A: la petición, su reintento sin «pensar»; después, ni se toca. B responde las dos.
        assert fake.models_called == ["a", "a", "b", "b"]
        # Sin herramientas, A sigue sirviendo.
        assert chain("a", "b").chat(MESSAGES)["_model"] == "a"

    def test_without_any_tool_capable_model_the_error_is_clear(self, monkeypatch):
        install(
            monkeypatch,
            {
                "a": [http(400, b"no tool support") for _ in range(2)],
                "b": [http(422, b"tool_choice invalid") for _ in range(2)],
            },
        )

        with pytest.raises(AssistantUnavailable) as raised:
            chain("a", "b").chat(MESSAGES, tools=TOOLS)

        assert str(raised.value) == "no-tools"
        assert raised.value.kind == "http"

    def test_a_400_that_does_not_mention_tools_does_not_mark_the_model(
        self, monkeypatch
    ):
        install(monkeypatch, {"a": [http(400, b"too long") for _ in range(2)]})

        with pytest.raises(AssistantUnavailable, match="http-400"):
            chain("a").chat(MESSAGES, tools=TOOLS)

        assert client_module._TOOLS_UNSUPPORTED == set()

    def test_the_service_says_so_plainly_and_does_not_charge_for_it(self, monkeypatch):
        install(
            monkeypatch,
            {"a": [http(400, b"tools?") for _ in range(2)]},
        )
        user = login_as("view_flightpermission").user

        answer = ask(user, "hola", client=chain("a"))

        assert answer.ok is False and answer.state == "error"
        assert "tools" in answer.text.lower() or "herramientas" in answer.text
        assert "no-tools" not in answer.text
        assert AssistantUsage.objects.get().outcome == "error"


class TestRateLimitRetry:
    def test_a_429_is_retried_with_short_growing_waits(self, monkeypatch, sleeps):
        fake = install(monkeypatch, {"a": [http(429), http(429), ok("al fin")]})

        assert chain("a").chat(MESSAGES)["content"] == "al fin"

        assert sleeps == [1.0, 2.0]
        assert fake.models_called == ["a", "a", "a"]

    def test_it_gives_up_after_two_retries(self, monkeypatch, sleeps):
        fake = install(monkeypatch, {"a": [http(429)] * 5})

        with pytest.raises(AssistantUnavailable) as raised:
            chain("a").chat(MESSAGES)

        assert str(raised.value) == "http-429" and raised.value.kind == "rate"
        assert len(fake.calls) == 3 and len(sleeps) == 2

    def test_the_cap_is_two_even_if_configured_higher(
        self, monkeypatch, sleeps, settings
    ):
        settings.AI_ASSISTANT_RETRIES_429 = 9
        fake = install(monkeypatch, {"a": [http(429)] * 9})

        with pytest.raises(AssistantUnavailable):
            chain("a").chat(MESSAGES)

        assert len(fake.calls) == 3

    def test_zero_disables_the_retry(self, monkeypatch, sleeps, settings):
        settings.AI_ASSISTANT_RETRIES_429 = 0
        fake = install(monkeypatch, {"a": [http(429)] * 3})

        with pytest.raises(AssistantUnavailable):
            chain("a").chat(MESSAGES)

        assert len(fake.calls) == 1 and sleeps == []

    def test_a_single_wait_never_exceeds_the_ceiling(
        self, monkeypatch, sleeps, settings
    ):
        settings.AI_ASSISTANT_RETRY_BACKOFF = 100
        install(monkeypatch, {"a": [http(429)] * 3})

        with pytest.raises(AssistantUnavailable):
            chain("a").chat(MESSAGES)

        assert max(sleeps) == client_module.MAX_BACKOFF_SECONDS

    def test_the_friendly_message_is_fixed_and_hides_the_code(self, monkeypatch):
        install(monkeypatch, {"a": [http(429)] * 3})
        user = login_as("view_flightpermission").user

        answer = ask(user, "hola", client=chain("a"))

        assert answer.state == "limit"
        assert "429" not in answer.text
        assert answer.text == service._unavailable_text("http-429")


class TestTypedErrors:
    @pytest.mark.parametrize(
        ("error", "reason", "kind"),
        [
            (TimeoutError(), "timeout", "timeout"),
            (
                urllib.error.URLError(TimeoutError()),
                "timeout",
                "timeout",
            ),
            (urllib.error.URLError("sin red"), "unreachable", "network"),
            (http(401), "http-401", "auth"),
            (http(403), "http-403", "auth"),
            (http(500), "http-500", "http"),
        ],
    )
    def test_each_failure_has_its_kind(self, monkeypatch, error, reason, kind):
        install(monkeypatch, {"a": [error]})

        with pytest.raises(AssistantUnavailable) as raised:
            chain("a").chat(MESSAGES)

        assert str(raised.value) == reason and raised.value.kind == kind

    def test_a_bad_body_is_bad_response(self, monkeypatch):
        install(monkeypatch, {"a": [_Response(b"<html>")]})

        with pytest.raises(AssistantUnavailable) as raised:
            chain("a").chat(MESSAGES)

        assert raised.value.kind == "bad_response"

    def test_no_key_is_not_configured(self):
        with pytest.raises(AssistantUnavailable) as raised:
            NvidiaClient(api_key="").chat(MESSAGES)

        assert raised.value.kind == "not_configured"

    @pytest.mark.parametrize("status", [400, 401, 404, 429, 500])
    def test_the_key_and_the_question_never_reach_logs_or_messages(
        self, monkeypatch, caplog, status
    ):
        body = f"echo {SECRET_KEY} SECRET-QUESTION-TEXT".encode()
        install(monkeypatch, {"a": [http(status, body) for _ in range(4)]})

        with caplog.at_level(logging.DEBUG), pytest.raises(AssistantUnavailable) as e:
            chain("a").chat(MESSAGES)

        assert SECRET_KEY not in caplog.text and SECRET_KEY not in str(e.value)
        assert "SECRET-QUESTION-TEXT" not in caplog.text
        assert "SECRET-QUESTION-TEXT" not in str(e.value)


class TestQuotaAndPrivacy:
    @pytest.mark.parametrize(
        ("error", "rounds"),
        [
            (TimeoutError(), 0),
            (urllib.error.URLError("sin red"), 0),
            (http(429), 0),
            (http(500), 1),
            (http(401), 1),
        ],
    )
    def test_quota_is_given_back_only_when_the_call_never_answered(
        self, monkeypatch, error, rounds
    ):
        install(monkeypatch, {"a": [error] * 4})
        user = login_as("view_flightpermission").user

        ask(user, "SECRET-QUESTION-TEXT", client=chain("a"))

        assert AssistantUsage.objects.get().rounds == rounds

    def test_a_given_back_call_leaves_room_under_the_hourly_cap(
        self, monkeypatch, settings
    ):
        settings.AI_ASSISTANT_MAX_PER_HOUR = 1
        install(monkeypatch, {"a": [TimeoutError(), ok("listo")]})
        user = login_as("view_flightpermission").user

        first = ask(user, "a", client=chain("a"))
        second = ask(user, "b", client=chain("a"))

        assert first.ok is False and second.ok is True

    def test_no_question_or_answer_text_is_stored(self, monkeypatch):
        install(monkeypatch, {"a": [ok("SECRET-ANSWER-TEXT")]})
        user = login_as("view_flightpermission").user

        ask(user, "SECRET-QUESTION-TEXT", client=chain("a"))

        row = AssistantUsage.objects.get()
        stored = json.dumps(
            {
                f.name: str(getattr(row, f.name))
                for f in AssistantUsage._meta.concrete_fields
            }
        )
        assert "SECRET-QUESTION-TEXT" not in stored
        assert "SECRET-ANSWER-TEXT" not in stored

    def test_tokens_still_come_from_the_answering_model(self, monkeypatch):
        install(monkeypatch, {"a": [http(404)], "b": [ok("listo", tokens=33)]})
        user = login_as("view_flightpermission").user

        ask(user, "hola", client=chain("a", "b"))

        assert AssistantUsage.objects.get().total_tokens == 33


def _models_payload(*ids):
    return _Response(json.dumps({"data": [{"id": i} for i in ids]}).encode())


class TestListModels:
    def test_it_lists_ids_sorted_and_deduplicated(self, monkeypatch):
        seen = {}

        def fake(request, timeout):
            seen["url"] = request.full_url
            seen["method"] = request.get_method()
            return _models_payload("z/b", "a/a", "z/b")

        monkeypatch.setattr(client_module.urllib.request, "urlopen", fake)

        assert chain("a").list_models() == ["a/a", "z/b"]
        assert seen == {"url": "https://example.test/v1/models", "method": "GET"}

    def test_bad_payload_and_http_errors_are_typed(self, monkeypatch):
        monkeypatch.setattr(
            client_module.urllib.request,
            "urlopen",
            lambda request, timeout: _Response(b'{"data": 3}'),
        )
        with pytest.raises(AssistantUnavailable, match="unreadable"):
            chain("a").list_models()

        def gone(request, timeout):
            raise http(404)

        monkeypatch.setattr(client_module.urllib.request, "urlopen", gone)
        with pytest.raises(AssistantUnavailable, match="http-404"):
            chain("a").list_models()


class _ProbeClient:
    """Reemplaza a `NvidiaClient` en el comando: lista modelos y responde por modelo."""

    def __init__(self, behaviour, listed):
        self.behaviour = behaviour
        self.listed = listed
        self.configured = True
        self.api_key = SECRET_KEY
        self.base_url = "https://example.invalid/v1"
        self.model = "a"
        self.models = ["a", "b"]
        self.calls = []

    def list_models(self):
        return self.listed

    def factory(self, model=None, fallbacks=None, **kwargs):
        owner = self

        class Single:
            def chat(self_inner, messages, tools=None):
                owner.calls.append((model, bool(tools), messages))
                outcome = owner.behaviour[(model, bool(tools))]
                if isinstance(outcome, BaseException):
                    raise outcome
                return outcome

        return Single()


class TestProbeModels:
    def _run(self, monkeypatch, probe, *args):
        monkeypatch.setattr(
            assistant_probar,
            "NvidiaClient",
            lambda **kw: probe.factory(**kw) if kw else probe,
        )
        out = io.StringIO()
        call_command("assistant_probar", *args, stdout=out, stderr=io.StringIO())
        return out.getvalue()

    def test_it_reports_which_models_answer_with_and_without_tools(self, monkeypatch):
        reply = {"role": "assistant", "content": "SECRET-MODEL-TEXT"}
        probe = _ProbeClient(
            {
                ("a", False): reply,
                ("a", True): AssistantUnavailable("no-tools"),
                ("b", False): AssistantUnavailable("http-404"),
                ("b", True): AssistantUnavailable("http-404"),
            },
            ["a", "x/other"],
        )

        text = self._run(monkeypatch, probe, "--models")

        assert "service models: 2" in text and "x/other" in text
        assert "a: listed; chat ok" in text and "tools FAIL (no-tools)" in text
        assert "b: NOT LISTED; chat FAIL (http-404)" in text
        assert "models: 1/2 of the chain answer" in text
        assert "SECRET-MODEL-TEXT" not in text and SECRET_KEY not in text
        # Lo enviado es un «ping» fijo: nunca nada de la persona.
        assert all(m == [{"role": "user", "content": "ping"}] for *_x, m in probe.calls)

    def test_listing_failure_is_a_clean_command_error(self, monkeypatch):
        probe = _ProbeClient({}, [])
        probe.list_models = lambda: (_ for _ in ()).throw(
            AssistantUnavailable("http-401")
        )

        with pytest.raises(Exception, match=r"listing failed \(http-401\)") as raised:
            self._run(monkeypatch, probe, "--models")

        assert SECRET_KEY not in str(raised.value)

    def test_without_a_key_it_fails_without_calling(self, monkeypatch):
        probe = _ProbeClient({}, [])
        probe.configured = False

        with pytest.raises(Exception, match="not configured"):
            self._run(monkeypatch, probe, "--models")

        assert probe.calls == []

    def test_the_plain_report_shows_the_fallbacks_and_still_hides_the_key(
        self, monkeypatch
    ):
        text = self._run(monkeypatch, _ProbeClient({}, []))

        assert "fallbacks: b" in text and SECRET_KEY not in text
