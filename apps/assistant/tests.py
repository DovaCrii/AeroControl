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

    @pytest.mark.parametrize(
        ("reason", "expected"),
        [
            ("http-429", "The assistant reached its usage limit. Try again later."),
            (
                "http-401",
                "The assistant's key was not accepted. Ask the administrator to check it.",
            ),
            (
                "http-403",
                "The assistant's key was not accepted. Ask the administrator to check it.",
            ),
            (
                "http-500",
                "The assistant is not available right now. Try again in a moment.",
            ),
        ],
    )
    def test_each_failure_reason_has_its_own_message(self, reason, expected):
        from django.utils.translation import gettext

        expected = gettext(expected)

        class Down:
            configured = True

            def chat(self, messages, tools=None):
                raise AssistantUnavailable(reason)

        answer = ask(object(), "hola", client=Down())

        assert answer.ok is False
        assert expected in answer.text
        assert reason not in answer.text

    def test_the_hourly_cap_stops_the_question_before_calling_the_service(
        self, settings, db
    ):
        settings.AI_ASSISTANT_MAX_PER_HOUR = 2
        user = login_as("view_flightpermission").user
        fake = FakeClient([_final("uno"), _final("dos"), _final("tres")])

        results = [ask(user, "hola", client=fake) for _ in range(3)]

        assert [r.ok for r in results] == [True, True, False]
        assert len(fake.calls) == 2  # la tercera ni salió hacia el servicio

    def test_the_cap_is_per_user(self, settings, db):
        settings.AI_ASSISTANT_MAX_PER_HOUR = 1
        first = login_as("view_flightpermission").user
        second = login_as("view_flightpermission", "view_aircraft").user
        fake = FakeClient([_final("a"), _final("b")])

        assert ask(first, "hola", client=fake).ok is True
        assert ask(second, "hola", client=fake).ok is True

    def test_a_cap_of_zero_means_no_cap(self, settings, db):
        settings.AI_ASSISTANT_MAX_PER_HOUR = 0
        user = login_as("view_flightpermission").user
        fake = FakeClient([_final("x") for _ in range(5)])

        assert all(ask(user, "hola", client=fake).ok for _ in range(5))

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
            "pk",
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


def _world():
    """Dos empresas que no se ven: A con dos permisos vigentes, B con uno."""
    from apps.core.models import OperationalTenant
    from apps.operations.models import FlightPermission
    from apps.registry.models import CostCenter

    today = timezone.localdate()
    tenants = {}
    for key, count in (("a", 2), ("b", 1)):
        tenant = OperationalTenant.objects.create(
            name=f"Empresa {key}", slug=f"empresa-{key}"
        )
        centre = CostCenter.objects.create(
            code=f"CC-{key.upper()}",
            name=f"Faena Secreta {key.upper()}",
            operates_flights=True,
            tenant=tenant,
        )
        for index in range(count):
            FlightPermission.objects.create(
                cost_center=centre,
                purpose="photogrammetry",
                status=FlightPermission.STATUS_APPROVED,
                permission_number=f"{key}{index}",
                location="Calama",
                area_type="unpopulated",
                valid_from=today - timedelta(days=5),
                valid_until=today + timedelta(days=12 + index),
            )
        tenants[key] = tenant
    return tenants


@pytest.mark.django_db
class TestTenantScope:
    """LV-323: con dos empresas, ninguna herramienta ve los datos de la otra."""

    def _user(self, tenant):
        # El nombre de usuario sale de los permisos: uno distinto por empresa.
        extra = "view_aircraft" if tenant.slug.endswith("b") else "view_operator"
        return login_as("view_flightpermission", extra, member_of=tenant).user

    def test_permits_summary_counts_only_the_users_tenant(self):
        tenants = _world()

        a = json.loads(
            tools.run_tool(self._user(tenants["a"]), "permits_summary", "{}")
        )
        b = json.loads(
            tools.run_tool(self._user(tenants["b"]), "permits_summary", "{}")
        )

        assert (a["total"], a["in_force"]) == (2, 2)
        assert (b["total"], b["in_force"]) == (1, 1)

    def test_cost_centres_lists_only_the_users_tenant(self):
        tenants = _world()

        a = json.loads(
            tools.run_tool(self._user(tenants["a"]), "cost_centres_permit_status", "{}")
        )
        b = json.loads(
            tools.run_tool(self._user(tenants["b"]), "cost_centres_permit_status", "{}")
        )

        assert [row["code"] for row in a] == ["CC-A"]
        assert [row["code"] for row in b] == ["CC-B"]

    def test_expiring_permits_lists_only_the_users_tenant(self):
        tenants = _world()

        a = json.loads(
            tools.run_tool(self._user(tenants["a"]), "expiring_permits", "{}")
        )
        b = json.loads(
            tools.run_tool(self._user(tenants["b"]), "expiring_permits", "{}")
        )

        assert {row["cost_centre"] for row in a} == {"CC-A"}
        assert {row["cost_centre"] for row in b} == {"CC-B"}

    def test_a_superuser_still_sees_every_tenant(self):
        _world()
        from django.contrib.auth import get_user_model

        root = get_user_model().objects.create_superuser("root", password="pw")  # nosec B106

        summary = json.loads(tools.run_tool(root, "permits_summary", "{}"))
        centres = json.loads(tools.run_tool(root, "cost_centres_permit_status", "{}"))

        assert summary["total"] == 3
        assert {row["code"] for row in centres} == {"CC-A", "CC-B"}

    def test_the_kpi_functions_without_user_are_unchanged(self):
        """Panel e informes llaman sin `user`: siguen viendo todo."""
        from apps.compliance.kpis import permit_counts, permit_status_by_cost_center

        _world()
        today = timezone.localdate()

        assert permit_counts(today)["total"] == 3
        assert len(permit_status_by_cost_center(today)) == 2

    def test_no_tool_sends_the_cost_centre_name_or_anything_personal(self):
        tenants = _world()
        user = self._user(tenants["a"])

        for name in tools.TOOLS:
            output = tools.run_tool(user, name, "{}")
            assert "Secreta" not in output, name
            assert "Faena" not in output, name

    def test_cost_centres_rows_carry_only_the_agreed_fields(self):
        tenants = _world()

        rows = json.loads(
            tools.run_tool(self._user(tenants["a"]), "cost_centres_permit_status", "{}")
        )

        assert set(rows[0]) == {
            "code",
            "in_force",
            "not_started",
            "awaiting",
            "expiring_in_30_days",
            "next_expiry",
        }


@pytest.mark.django_db
class TestCapAndUsage:
    def test_the_cap_counts_service_calls_not_questions(self, settings, permit):
        settings.AI_ASSISTANT_MAX_PER_HOUR = 2
        user = login_as("view_flightpermission").user
        # Una sola pregunta: llamada 1 pide herramienta, llamada 2 responde.
        fake = FakeClient([_tool_call(), _final("uno"), _final("dos")])

        first = ask(user, "hola", client=fake)
        second = ask(user, "hola otra vez", client=fake)

        assert first.ok is True
        assert second.ok is False  # el tope se gastó en las dos llamadas de la primera
        assert len(fake.calls) == 2

    def test_the_cap_cuts_in_the_middle_of_a_question(self, settings, permit):
        settings.AI_ASSISTANT_MAX_PER_HOUR = 1
        user = login_as("view_flightpermission").user
        fake = FakeClient([_tool_call(), _final("nunca")])

        answer = ask(user, "hola", client=fake)

        assert answer.ok is False
        assert len(fake.calls) == 1

    def test_total_tokens_are_logged_when_the_service_reports_them(
        self, permit, caplog
    ):
        user = login_as("view_flightpermission").user
        first = _tool_call()
        first["_total_tokens"] = 120
        last = _final("ok")
        last["_total_tokens"] = 30
        fake = FakeClient([first, last])

        with caplog.at_level(logging.INFO, logger="apps.assistant.service"):
            ask(user, "hola", client=fake)

        record = next(r for r in caplog.records if r.message == "assistant_answered")
        assert record.total_tokens == 150

    def test_the_token_marker_never_travels_back_to_the_model(self, permit):
        user = login_as("view_flightpermission").user
        first = _tool_call()
        first["_total_tokens"] = 10
        fake = FakeClient([first, _final("ok")])

        ask(user, "hola", client=fake)

        assert "_total_tokens" not in json.dumps(fake.calls[1])

    @pytest.mark.parametrize(
        ("usage", "expected"),
        [
            ({"total_tokens": 42}, 42),
            ({"total_tokens": "42"}, None),
            ({"total_tokens": True}, None),
            ({}, None),
            (None, None),
            ("garbage", None),
        ],
    )
    def test_the_client_reads_usage_tolerantly(self, monkeypatch, usage, expected):
        body = {"choices": [{"message": {"content": "hola"}}]}
        if usage is not None:
            body["usage"] = usage
        monkeypatch.setattr(
            client_module.urllib.request,
            "urlopen",
            lambda request, timeout: _Response(json.dumps(body).encode()),
        )

        message = NvidiaClient(
            api_key=SECRET_KEY, base_url="https://example.test/v1", model="m", timeout=5
        ).chat([{"role": "user", "content": "x"}])

        assert message["content"] == "hola"
        assert message.get("_total_tokens") == expected


@pytest.fixture
def caps(settings):
    settings.AI_ASSISTANT_MAX_PER_HOUR = 0
    settings.AI_ASSISTANT_DAILY_CAP = 0
    return settings


class Down:
    configured = True

    def __init__(self, reason):
        self.reason = reason

    def chat(self, messages, tools=None):
        raise AssistantUnavailable(self.reason)


@pytest.mark.django_db
class TestUsageRegistry:
    def test_neither_question_nor_answer_reaches_the_database_or_the_log(
        self, permit, caplog, caps
    ):
        from django.apps import apps as django_apps
        from django.db import models

        from apps.assistant.models import AssistantUsage

        user = login_as("view_flightpermission").user
        fake = FakeClient([_tool_call(), _final("CENTINELA-RESPUESTA")])

        with caplog.at_level(logging.INFO, logger="apps.assistant.service"):
            ask(user, "CENTINELA-PREGUNTA", client=fake)

        dump = json.dumps(list(AssistantUsage.objects.values()), default=str)
        assert "CENTINELA" not in dump
        assert "CENTINELA" not in caplog.text
        row = AssistantUsage.objects.get()
        assert row.notes == ""
        assert (row.tools, row.rounds, row.outcome) == (
            ["permits_summary"],
            2,
            "ok",
        )
        # Ningún campo de texto libre salvo `notes` (heredado, nunca escrito).
        free_text = [
            f.name
            for f in django_apps.get_model("assistant", "AssistantUsage")._meta.fields
            if isinstance(f, models.TextField)
        ]
        assert free_text == ["notes"]

    def test_the_row_survives_deleting_the_user(self, caps):
        from apps.assistant.models import AssistantUsage

        user = login_as("view_flightpermission").user
        ask(user, "hola", client=FakeClient([_final("x")]))

        user.delete()

        assert AssistantUsage.objects.get().user is None

    def test_the_hourly_cap_is_counted_in_the_database_per_user(self, caps):
        from apps.assistant.models import AssistantUsage

        caps.AI_ASSISTANT_MAX_PER_HOUR = 2
        first = login_as("view_flightpermission").user
        second = login_as("view_flightpermission", "view_aircraft").user
        fake = FakeClient([_final(str(i)) for i in range(6)])

        results = [ask(first, "a", client=fake).ok for _ in range(3)]
        other = ask(second, "b", client=fake)

        assert results == [True, True, False]
        assert other.ok is True
        assert len(fake.calls) == 3
        assert AssistantUsage.objects.filter(outcome="limit").count() == 1

    def test_calls_older_than_an_hour_do_not_count(self, caps):
        from apps.assistant.models import AssistantUsage

        caps.AI_ASSISTANT_MAX_PER_HOUR = 1
        user = login_as("view_flightpermission").user
        ask(user, "a", client=FakeClient([_final("x")]))
        AssistantUsage.objects.update(created_at=timezone.now() - timedelta(hours=2))

        assert ask(user, "b", client=FakeClient([_final("y")])).ok is True

    def test_the_daily_cap_is_global_and_checked_before_every_call(self, permit, caps):
        caps.AI_ASSISTANT_DAILY_CAP = 3
        first = login_as("view_flightpermission").user
        second = login_as("view_flightpermission", "view_aircraft").user
        # La primera pregunta gasta 2 llamadas; la segunda pide herramienta y se corta en
        # su segunda llamada (tope de 3), no sólo en la primera.
        fake = FakeClient([_tool_call(), _final("uno"), _tool_call(), _final("nunca")])

        one = ask(first, "a", client=fake)
        two = ask(second, "b", client=fake)

        assert one.ok is True
        assert two.ok is False
        assert len(fake.calls) == 3
        assert "daily limit" in two.text or "diario" in two.text

    def test_two_requests_in_a_row_respect_the_cap(self, caps):
        caps.AI_ASSISTANT_MAX_PER_HOUR = 1
        user = login_as("view_flightpermission").user
        fake = FakeClient([_final("a"), _final("b")])

        answers = [ask(user, "x", client=fake), ask(user, "y", client=fake)]

        assert [a.ok for a in answers] == [True, False]
        assert len(fake.calls) == 1

    def test_a_network_failure_gives_the_call_back_but_a_429_does_not(self, caps):
        from apps.assistant.models import AssistantUsage

        user = login_as("view_flightpermission").user

        ask(user, "a", client=Down("unreachable"))
        ask(user, "b", client=Down("http-429"))

        rows = {r.outcome: r.rounds for r in AssistantUsage.objects.all()}
        assert rows == {"unreachable": 0, "error-429": 1}

    @pytest.mark.parametrize(
        ("reason", "outcome"),
        [
            ("http-429", "error-429"),
            ("http-401", "auth"),
            ("http-403", "auth"),
            ("unreachable", "unreachable"),
            ("http-500", "error"),
            ("unreadable", "error"),
        ],
    )
    def test_each_failure_has_its_outcome(self, caps, reason, outcome):
        from apps.assistant.models import AssistantUsage

        ask(login_as().user, "hola", client=Down(reason))

        assert AssistantUsage.objects.get().outcome == outcome

    def test_outcome_for_steps_empty_and_ok(self, permit, caps):
        from apps.assistant.models import AssistantUsage

        user = login_as("view_flightpermission").user
        ask(
            user,
            "a",
            client=FakeClient([_tool_call(call_id=f"c{i}") for i in range(MAX_ROUNDS)]),
        )
        ask(user, "b", client=FakeClient([_final("   ")]))
        ask(user, "c", client=FakeClient([_final("listo")]))

        assert sorted(AssistantUsage.objects.values_list("outcome", flat=True)) == [
            "empty",
            "ok",
            "too-many-steps",
        ]

    def test_a_cap_stop_is_recorded_as_limit_and_no_row_stays_pending(self, caps):
        from apps.assistant.models import AssistantUsage

        caps.AI_ASSISTANT_MAX_PER_HOUR = 1
        user = login_as("view_flightpermission").user
        fake = FakeClient([_final("a")])
        ask(user, "x", client=fake)
        ask(user, "y", client=fake)

        assert not AssistantUsage.objects.filter(outcome="pending").exists()
        assert AssistantUsage.objects.filter(outcome="limit", rounds=0).count() == 1

    def test_the_usage_log_is_read_only_in_the_admin(self, client, caps):
        from django.contrib.auth import get_user_model

        from apps.assistant.models import AssistantUsage

        admin_user = get_user_model().objects.create_superuser(
            "boss", "boss@example.test", "pw-for-test-only"
        )
        client.force_login(admin_user)
        row = AssistantUsage.objects.create(user=admin_user, outcome="ok")

        assert (
            client.get(reverse("admin:assistant_assistantusage_changelist")).status_code
            == 200
        )
        assert (
            client.get(reverse("admin:assistant_assistantusage_add")).status_code == 403
        )
        change = reverse("admin:assistant_assistantusage_change", args=[row.pk])
        assert client.post(change, {"outcome": "limit"}).status_code == 403
        delete = reverse("admin:assistant_assistantusage_delete", args=[row.pk])
        assert client.post(delete, {"post": "yes"}).status_code == 403
        row.refresh_from_db()
        assert row.outcome == "ok"

    def test_the_migration_is_complete(self):
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        call_command("makemigrations", "assistant", "--check", "--dry-run", stdout=out)
