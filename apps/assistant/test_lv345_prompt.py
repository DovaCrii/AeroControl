# ruff: noqa: F811
"""LV-345: prompt versionado, modo demo guionizado y golden set.

Fija lo que importa: el prompt trae sus reglas, el servidor (no el modelo) garantiza que no
salgan URL ni respuestas largas, el cliente guionizado sólo existe con DEBUG, y el texto de la
pregunta y de la respuesta no llega nunca al log ni a la base.
"""

import io
import json
import logging
import uuid

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import translation

from apps.assistant import fake_client, prompts, service
from apps.assistant.client import NvidiaClient
from apps.assistant.evals.golden import GOLDEN, SENTINELS, evaluate
from apps.assistant.fake_client import ScriptedClient
from apps.assistant.management.commands import assistant_probar
from apps.assistant.models import AssistantUsage
from apps.assistant.tests import FakeClient, _final, _tool_call, caps  # noqa: F401
from apps.assistant.test_lv340_tools import PERMS, _user, world  # noqa: F401
from apps.core.testing import login_as


class TestTheFakeClientNeedsDebug:
    def test_it_is_ignored_without_debug_and_check_warns(self, settings):
        settings.AI_ASSISTANT_FAKE = True
        settings.DEBUG = False

        assert isinstance(service.default_client(), NvidiaClient)
        warnings = fake_client.check_fake_client_only_in_debug(None)
        assert [w.id for w in warnings] == ["assistant.W001"]

    def test_with_debug_it_is_used_and_check_is_quiet(self, settings):
        settings.AI_ASSISTANT_FAKE = True
        settings.DEBUG = True

        assert isinstance(service.default_client(), ScriptedClient)
        assert fake_client.check_fake_client_only_in_debug(None) == []

    def test_off_by_default(self, settings):
        settings.AI_ASSISTANT_FAKE = False
        settings.DEBUG = True

        assert isinstance(service.default_client(), NvidiaClient)
        assert fake_client.check_fake_client_only_in_debug(None) == []


class TestThePrompt:
    def test_it_carries_its_rules(self):
        text = prompts.SYSTEM_PROMPT

        assert prompts.PROMPT_VERSION
        assert prompts.OUT_OF_SCOPE in text
        for topic in prompts.TOPICS:
            assert topic in text
        assert str(prompts.MAX_BULLETS) in text and str(prompts.MAX_WORDS) in text
        assert prompts.NOTHING_PREVENTS in text
        assert "dd-mm-aaaa" in text
        assert '{"data"' in text  # el contenido de las herramientas es DATO
        assert "NUNCA escribas URL" in text

    @pytest.mark.django_db
    def test_the_service_sends_that_prompt_and_logs_its_version(self, caps, caplog):  # noqa: F811
        user = login_as("view_flightpermission").user
        fake = FakeClient([_final("ok")])

        with caplog.at_level(logging.INFO, logger="apps.assistant.service"):
            service.ask(user, "hola", client=fake)

        assert fake.calls[0][0] == {"role": "system", "content": prompts.SYSTEM_PROMPT}
        record = next(r for r in caplog.records if r.message == "assistant_answered")
        assert record.prompt_version == prompts.PROMPT_VERSION


@pytest.mark.django_db
class TestTheServerCleansTheModelText:
    def _ask(self, caps, text):  # noqa: F811
        user = login_as("view_flightpermission").user
        return service.ask(user, "hola", client=FakeClient([_final(text)]))

    def test_urls_are_removed(self, caps):  # noqa: F811
        answer = self._ask(
            caps,
            "Vea https://evil.example/x y HTTP://a.b/c y www.evil.com/z fin.",
        )

        for fragment in ("http", "www.", "evil"):
            assert fragment not in answer.text.lower()
        assert "fin." in answer.text

    def test_the_text_is_cut_to_the_limit(self, caps):  # noqa: F811
        answer = self._ask(caps, "a" * 5000)

        assert len(answer.text) == service.MAX_ANSWER_CHARS
        assert answer.text.endswith("…")

    def test_a_short_text_is_untouched(self, caps):  # noqa: F811
        assert self._ask(caps, "  Hola.  ").text == "Hola."

    def test_html_is_still_escaped_by_the_panel(self, caps):  # noqa: F811
        # El servidor no escapa: lo hace la plantilla (LV-332 lo verifica); aquí sólo se
        # comprueba que el recorte no deja el texto a medio escapar.
        answer = self._ask(caps, "<b>x</b> " * 400)

        assert len(answer.text) <= service.MAX_ANSWER_CHARS


@pytest.mark.django_db
class TestNothingTextualIsKept:
    def test_scripted_question_and_answer_never_reach_log_or_database(
        self,
        world,
        caps,
        caplog,  # noqa: F811
    ):
        user = _user(world["a"])

        with caplog.at_level(logging.DEBUG):
            answer = service.ask(
                user,
                "CENTINELA-PREGUNTA ¿qué mantenciones vienen?",
                client=ScriptedClient(),
            )

        assert answer.ok and answer.tools_used == ["upcoming_maintenance"]
        dump = json.dumps(list(AssistantUsage.objects.values()), default=str)
        assert "CENTINELA" not in dump
        assert "CENTINELA" not in caplog.text
        assert answer.text not in dump and answer.text not in caplog.text
        assert AssistantUsage.objects.get().model == "scripted"


class _Recording(ScriptedClient):
    def __init__(self):
        self.tool_calls = []

    def chat(self, messages, tools=None):
        reply = super().chat(messages, tools)
        self.tool_calls += reply.get("tool_calls") or []
        return reply


@pytest.mark.django_db
class TestGoldenSet:
    @pytest.fixture(autouse=True)
    def _english(self):
        # Las frases esperadas son fragmentos de las plantillas fuente (inglés).
        with translation.override("en"):
            yield

    def test_there_are_at_least_fifteen_cases_and_names_are_unique(self):
        assert len(GOLDEN) >= 15
        assert len({case.name for case in GOLDEN}) == len(GOLDEN)

    @pytest.mark.parametrize("case", GOLDEN, ids=lambda case: case.name)
    def test_case(self, world, caps, case):  # noqa: F811
        from django.urls import reverse

        from apps.registry.models import Operator

        # El RUT del operador sembrado es un centinela más (sin pasar por `save`).
        Operator.objects.update(rut="12.345.678-5")
        if case.permissions == ():
            user = login_as().user
        else:
            user = _user(world["a"], *(case.permissions or PERMS))
        client = _Recording()

        result = evaluate(user, case, client=client)
        text = result["text"]

        assert result["state"] == "ok", text
        assert result["ok_tools"], (
            case.name,
            [c["function"]["name"] for c in client.tool_calls],
        )
        if case.args:
            arguments = json.loads(client.tool_calls[0]["function"]["arguments"])
            assert case.args.items() <= arguments.items()
        for phrase in case.must_include:
            assert phrase in text, (case.name, phrase)
        for banned in case.must_not:
            assert banned not in text, (case.name, banned)
        for sentinel in SENTINELS:
            assert sentinel not in text
        cited = [cite["url"] for cite in result["answer"].citations]
        for url_name in case.citations:
            if url_name == "alert-list":
                prefix = reverse(url_name)
            else:
                zero = str(uuid.UUID(int=0))
                prefix = reverse(url_name, args=[zero]).split(zero)[0]
            assert any(url.startswith(prefix) for url in cited), (case.name, url_name)
        if not case.citations:
            assert cited == []


class _EvalProbe:
    """Cliente falso para `--eval`: responde con texto reconocible que NUNCA debe imprimirse."""

    def __init__(self, configured=True):
        self.configured = configured
        self.model = "test/model"
        self.calls = 0

    def chat(self, messages, tools=None):
        self.calls += 1
        if messages[-1]["role"] == "tool":
            return {"role": "assistant", "content": "CENTINELA-TEXTO-DEL-MODELO"}
        return _tool_call("permits_summary")


def _run_eval(monkeypatch, probe, *args):
    monkeypatch.setattr(assistant_probar, "NvidiaClient", lambda: probe)
    out = io.StringIO()
    call_command("assistant_probar", *args, stdout=out, stderr=io.StringIO())
    return out.getvalue()


@pytest.mark.django_db
class TestEvalCommand:
    def test_without_a_key_it_fails_without_calling(self, monkeypatch):
        user = login_as("view_flightpermission").user
        probe = _EvalProbe(configured=False)

        with pytest.raises(CommandError, match="not configured"):
            _run_eval(monkeypatch, probe, "--eval", "--user", str(user.pk))

        assert probe.calls == 0

    def test_it_needs_a_user(self, monkeypatch):
        probe = _EvalProbe()

        with pytest.raises(CommandError, match="--user"):
            _run_eval(monkeypatch, probe, "--eval")

        assert probe.calls == 0

    def test_it_prints_only_figures_never_the_text(self, monkeypatch, caps):  # noqa: F811
        user = login_as("view_flightpermission").user
        probe = _EvalProbe()

        text = _run_eval(
            monkeypatch, probe, "--eval", "--user", str(user.pk), "--max", "3"
        )

        assert "CENTINELA" not in text
        assert "Flight permits" not in text
        lines = text.strip().splitlines()
        assert len(lines) == 4  # tres preguntas + el resumen
        assert lines[0].startswith("permits_summary: tools OK, citations 0, length ")
        assert "ms, tokens unknown" in lines[0]
        assert probe.calls > 0

    def test_it_counts_in_the_usage_table_and_respects_the_caps(
        self, monkeypatch, settings
    ):
        settings.AI_ASSISTANT_DAILY_CAP = 0
        settings.AI_ASSISTANT_MAX_PER_HOUR = 2
        user = login_as("view_flightpermission").user

        text = _run_eval(
            monkeypatch, _EvalProbe(), "--eval", "--user", str(user.pk), "--max", "3"
        )

        # 2 llamadas por pregunta y tope de 2 por hora: sólo la primera llega a contestar.
        assert AssistantUsage.objects.filter(user=user).count() == 3
        assert AssistantUsage.objects.filter(user=user, outcome="limit").count() == 2
        assert "tools KO" in text

    def test_it_runs_with_the_permissions_of_that_user(self, monkeypatch, caps):  # noqa: F811
        user = login_as().user  # sin permisos
        text = _run_eval(
            monkeypatch, _EvalProbe(), "--eval", "--user", str(user.pk), "--max", "1"
        )

        # La herramienta devuelve un error de permiso, no datos: la fila lo registra igual.
        assert "permits_summary: tools OK" in text
        assert "citations 0" in text
