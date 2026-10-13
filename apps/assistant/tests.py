"""LV-305: asistente de consulta con IA (prototipo, sólo demo).

Se prueba con un cliente falso: ninguna prueba llama a un servicio real ni necesita una llave.
Lo que fijan estas pruebas es lo que **no** puede aflojarse: apagado por omisión, nunca en
producción, solo lectura, nada personal hacia afuera, tope de vueltas, y que la llave no se filtre.
"""

import io
import json
import logging
import urllib.error
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.assistant import client as client_module
from apps.assistant import service, tools
from apps.assistant.client import AssistantUnavailable, NvidiaClient
from apps.assistant.service import MAX_ROUNDS, Answer, ask
from apps.core.testing import login_as

URL = "assistant-ask"
SECRET_KEY = "nvapi-TEST-NOT-A-REAL-KEY"


def _tool_call(name="permits_summary", arguments="{}", call_id="c1"):
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": call_id,
                "type": "function",
                "function": {"name": name, "arguments": arguments},
            }
        ],
    }


def _final(text):
    return {"role": "assistant", "content": text}


class FakeClient:
    configured = True

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def chat(self, messages, tools=None):
        self.calls.append(json.loads(json.dumps(messages)))
        return self.replies.pop(0)


@pytest.fixture
def enabled(settings):
    settings.AI_ASSISTANT_ENABLED = True
    settings.DEBUG = True
    return settings


@pytest.fixture
def centre(db):
    from apps.registry.models import CostCenter

    return CostCenter.objects.create(code="CC738", name="MLP", operates_flights=True)


@pytest.fixture
def permit(centre):
    from apps.operations.models import FlightPermission

    today = timezone.localdate()
    return FlightPermission.objects.create(
        cost_center=centre,
        purpose="photogrammetry",
        status=FlightPermission.STATUS_APPROVED,
        permission_number="7218",
        location="Calama",
        area_type="unpopulated",
        valid_from=today - timedelta(days=5),
        valid_until=today + timedelta(days=12),
    )


@pytest.mark.django_db
class TestItIsOffUnlessDemo:
    def test_it_is_off_by_default(self, db):
        response = login_as("view_flightpermission").get(reverse(URL))

        assert response.status_code == 404

    def test_enabled_in_production_still_does_not_exist(self, settings):
        """Aunque alguien ponga la variable, sin DEBUG no existe: producción es otra licencia."""
        settings.AI_ASSISTANT_ENABLED = True
        settings.DEBUG = False

        client = login_as("view_flightpermission")

        assert client.get(reverse(URL)).status_code == 404
        assert client.post(reverse(URL), {"question": "x"}).status_code == 404

    def test_anonymous_goes_to_login(self, enabled, client):
        response = client.get(reverse(URL))

        assert response.status_code == 302
        assert "login" in response.url

    def test_without_view_permission_it_is_forbidden(self, enabled):
        client = login_as()  # sin ningún permiso

        assert client.get(reverse(URL)).status_code == 403
        assert client.post(reverse(URL), {"question": "hola"}).status_code == 403

    def test_a_logged_in_user_sees_the_prototype_notice(self, enabled):
        html = login_as("view_flightpermission").get(reverse(URL)).content.decode()

        assert 'id="assistant-question"' in html
        assert 'role="note"' in html


@pytest.mark.django_db
class TestTheAskScreen:
    def test_an_empty_question_is_refused_without_calling_anything(self, enabled):
        response = login_as("view_flightpermission").post(
            reverse(URL), {"question": "  "}
        )

        assert response.status_code == 200
        assert response.context["error"]
        assert "answer" not in response.context

    def test_a_too_long_question_is_refused(self, enabled):
        response = login_as("view_flightpermission").post(
            reverse(URL), {"question": "x" * (service.MAX_QUESTION_CHARS + 1)}
        )

        assert response.context["error"]
        assert "answer" not in response.context

    def test_the_answer_and_the_data_consulted_are_shown(self, enabled, monkeypatch):
        monkeypatch.setattr(
            "apps.assistant.views.ask",
            lambda user, question: Answer(
                "Hay 3 faenas sin permiso.", ["permits_summary"]
            ),
        )

        html = (
            login_as("view_flightpermission")
            .post(reverse(URL), {"question": "¿Qué faenas no tienen permiso?"})
            .content.decode()
        )

        assert "Hay 3 faenas sin permiso." in html
        assert "permits_summary" in html

    def test_without_a_key_it_says_so_and_never_calls_the_network(
        self, enabled, monkeypatch
    ):
        enabled.NVIDIA_API_KEY = ""

        def boom(*args, **kwargs):
            raise AssertionError("no debe llamar a la red sin llave")

        monkeypatch.setattr(client_module.urllib.request, "urlopen", boom)

        html = (
            login_as("view_flightpermission")
            .post(reverse(URL), {"question": "hola"})
            .content.decode()
        )

        assert "assistant-answer" in html


@pytest.mark.django_db
class TestTheToolLoop:
    def test_a_tool_is_run_and_its_data_reaches_the_model(self, permit):
        user = login_as("view_flightpermission").user
        fake = FakeClient([_tool_call(), _final("Hay 1 permiso vigente.")])

        answer = ask(user, "¿Cuántos permisos vigentes hay?", client=fake)

        assert answer.ok is True
        assert answer.text == "Hay 1 permiso vigente."
        assert answer.tools_used == ["permits_summary"]
        second_round = fake.calls[1]
        tool_message = next(m for m in second_round if m["role"] == "tool")
        assert json.loads(tool_message["content"])["in_force"] == 1

    def test_a_user_without_the_permission_gets_an_error_not_the_data(
        self, permit, monkeypatch
    ):
        user = login_as().user  # sin ningún permiso
        monkeypatch.setattr(
            "apps.compliance.kpis.permit_counts",
            lambda *a, **k: (_ for _ in ()).throw(
                AssertionError("no debía ejecutarse")
            ),
        )
        fake = FakeClient([_tool_call(), _final("No tengo ese dato.")])

        ask(user, "¿Cuántos permisos hay?", client=fake)

        tool_message = next(m for m in fake.calls[1] if m["role"] == "tool")
        assert "no permission" in tool_message["content"]

    def test_it_stops_after_the_round_limit(self, permit):
        user = login_as("view_flightpermission").user
        fake = FakeClient([_tool_call(call_id=f"c{i}") for i in range(MAX_ROUNDS + 3)])

        answer = ask(user, "pregunta sin fin", client=fake)

        assert answer.ok is False
        assert len(fake.calls) == MAX_ROUNDS

    def test_an_unavailable_service_gives_a_neutral_message(self):
        class Down:
            configured = True

            def chat(self, messages, tools=None):
                raise AssistantUnavailable("http-500")

        answer = ask(object(), "hola", client=Down())

        assert answer.ok is False
        assert "http-500" not in answer.text

    def test_the_question_text_is_never_logged(self, permit, caplog):
        user = login_as("view_flightpermission").user
        fake = FakeClient([_final("ok")])

        with caplog.at_level(logging.INFO, logger="apps.assistant.service"):
            ask(user, "¿Qué hizo Juan Pérez ayer?", client=fake)

        assert "Juan" not in caplog.text
        assert "assistant_answered" in caplog.text


@pytest.mark.django_db
class TestWhatTheToolsReveal:
    def test_an_unknown_tool_or_bad_arguments_never_raise(self):
        user = login_as("view_flightpermission").user

        assert "unknown tool" in tools.run_tool(user, "drop_everything", "{}")
        # argumentos que no son JSON: se usan los valores por omisión
        assert json.loads(tools.run_tool(user, "expiring_permits", "no-json")) == []

    def test_no_personal_data_leaves_through_any_tool(self, permit, centre):
        """Nombres, RUT y correos de operadores no viajan hacia el servicio externo."""
        from apps.registry.models import Operator

        operator = Operator.objects.create(
            full_name="Piloto Secreto Pérez",
            employee_id="E-777-ID",
            email="piloto.secreto@example.com",
            cost_center=centre,
        )
        permit.operators.add(operator)
        user = login_as(
            "view_flightpermission", "view_operator", "view_costcenter"
        ).user

        outputs = [tools.run_tool(user, name, "{}") for name in tools.TOOLS] + [
            tools.run_tool(user, "expiring_permits", '{"days": 60}')
        ]

        joined = " ".join(outputs)
        assert "Secreto" not in joined
        assert "E-777-ID" not in joined
        assert "example.com" not in joined

    def test_expiring_permits_only_lists_the_agreed_fields(self, permit):
        user = login_as("view_flightpermission").user

        rows = json.loads(tools.run_tool(user, "expiring_permits", '{"days": 30}'))

        assert rows and set(rows[0]) == {
            "permit",
            "cost_centre",
            "valid_until",
            "days_left",
        }

    def test_the_window_is_clamped(self, permit):
        user = login_as("view_flightpermission").user

        # 10 años pedidos: se acota a 365 y no devuelve un error
        assert isinstance(
            json.loads(tools.run_tool(user, "expiring_permits", '{"days": 3650}')), list
        )

    def test_every_tool_declares_a_view_permission_and_none_writes(self):
        for tool in tools.TOOLS.values():
            assert tool.permission.startswith(("operations.view_", "compliance.view_"))


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class TestTheHttpClient:
    def _client(self):
        return NvidiaClient(
            api_key=SECRET_KEY, base_url="https://example.test/v1", model="m", timeout=5
        )

    def test_it_builds_an_openai_style_request(self, monkeypatch):
        captured = {}

        def fake_urlopen(request, timeout):
            captured["url"] = request.full_url
            captured["auth"] = request.get_header("Authorization")
            captured["body"] = json.loads(request.data)
            captured["timeout"] = timeout
            return _Response(
                json.dumps({"choices": [{"message": {"content": "hola"}}]}).encode()
            )

        monkeypatch.setattr(client_module.urllib.request, "urlopen", fake_urlopen)

        message = self._client().chat(
            [{"role": "user", "content": "x"}], tools=tools.tool_definitions()
        )

        assert message["content"] == "hola"
        assert captured["url"] == "https://example.test/v1/chat/completions"
        assert captured["auth"] == f"Bearer {SECRET_KEY}"
        assert captured["body"]["tool_choice"] == "auto"
        assert len(captured["body"]["tools"]) == len(tools.TOOLS)
        assert captured["timeout"] == 5

    @pytest.mark.parametrize(
        "error",
        [
            urllib.error.HTTPError("u", 500, "boom", {}, None),
            urllib.error.URLError("sin red"),
            TimeoutError(),
        ],
    )
    def test_network_failures_become_unavailable_without_leaking_the_key(
        self, monkeypatch, caplog, error
    ):
        def fail(request, timeout):
            raise error

        monkeypatch.setattr(client_module.urllib.request, "urlopen", fail)

        with (
            caplog.at_level(logging.DEBUG),
            pytest.raises(AssistantUnavailable) as raised,
        ):
            self._client().chat([{"role": "user", "content": "x"}])

        assert SECRET_KEY not in caplog.text
        assert SECRET_KEY not in str(raised.value)

    def test_an_unreadable_response_is_unavailable(self, monkeypatch):
        monkeypatch.setattr(
            client_module.urllib.request,
            "urlopen",
            lambda request, timeout: _Response(b"<html>not json</html>"),
        )

        with pytest.raises(AssistantUnavailable):
            self._client().chat([{"role": "user", "content": "x"}])

    def test_it_refuses_without_a_key(self):
        with pytest.raises(AssistantUnavailable):
            NvidiaClient(api_key="").chat([{"role": "user", "content": "x"}])
