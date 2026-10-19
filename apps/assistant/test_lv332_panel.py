"""LV-332: panel lateral del asistente (botón flotante + fragmento `ask/panel/`).

Cliente falso en todo: nada llama a un servicio real ni necesita llave. Lo que se fija: sin el
candado no sale HTML del panel; el fragmento exige POST, CSRF, sesión y `view_flightpermission`;
las citas las arma el servidor y sólo con permisos de la empresa de quien pregunta; el texto del
modelo sale escapado; y nada del texto se guarda.
"""

import json
import uuid

import pytest
from django.test import Client
from django.urls import reverse
from django.utils.translation import gettext

from apps.assistant import service, tools
from apps.assistant.models import AssistantUsage
from apps.assistant.tests import FakeClient, _final, _tool_call, _world
from apps.core.testing import login_as

PANEL = "assistant-panel-ask"
MARKERS = ("assistant-panel", "assistant-open", "assistant-panel.js")


@pytest.fixture
def enabled(settings):
    settings.AI_ASSISTANT_ENABLED = True
    settings.DEBUG = True
    settings.AI_ASSISTANT_MAX_PER_HOUR = 0
    settings.AI_ASSISTANT_DAILY_CAP = 0
    return settings


@pytest.fixture
def fake(monkeypatch):
    def install(*replies):
        client = FakeClient(replies)
        monkeypatch.setattr(service, "NvidiaClient", lambda: client)
        return client

    return install


def _page(client, name="permission-list"):
    return client.get(reverse(name))


@pytest.mark.django_db
class TestThePanelIsAbsentUnlessAvailable:
    def test_nothing_is_drawn_while_the_assistant_is_off(self, db):
        html = _page(login_as("view_flightpermission")).content.decode()

        assert not any(marker in html for marker in MARKERS)

    def test_enabled_in_production_still_draws_nothing(self, settings):
        settings.AI_ASSISTANT_ENABLED = True
        settings.DEBUG = False

        html = _page(login_as("view_flightpermission")).content.decode()

        assert not any(marker in html for marker in MARKERS)

    def test_it_is_drawn_for_a_user_who_can_view_permits(self, enabled):
        html = _page(login_as("view_flightpermission")).content.decode()

        assert 'id="assistant-open"' in html
        assert 'role="dialog"' in html
        assert "js/assistant-panel.js" in html

    def test_a_user_with_no_tool_permission_gets_no_panel(self, enabled):
        html = login_as("view_operator").get(reverse("operator-list")).content.decode()

        assert not any(marker in html for marker in MARKERS)

    def test_the_login_page_has_no_panel(self, enabled, client):
        html = client.get(reverse("login")).content.decode()

        assert not any(marker in html for marker in MARKERS)


@pytest.mark.django_db
class TestSuggestionsFollowTheScreen:
    def test_permits_screen_offers_the_two_permit_questions(self, enabled):
        response = _page(login_as("view_flightpermission"))

        shown = [str(s) for s in response.context["assistant_suggestions"]]
        assert gettext("Which permits expire in the next 30 days?") in shown
        assert gettext("Which sites have no current permit?") in shown
        assert "data-assistant-suggest" in response.content.decode()

    def test_another_module_falls_back_to_what_the_user_can_ask(self, enabled):
        response = _page(login_as("view_flightpermission", "view_alert"), "alert-list")

        shown = [str(s) for s in response.context["assistant_suggestions"]]
        assert gettext("Open alerts by urgency") in shown


@pytest.mark.django_db
class TestThePanelFragmentGate:
    def test_off_it_does_not_exist(self, db):
        client = login_as("view_flightpermission")

        assert client.post(reverse(PANEL), {"question": "x"}).status_code == 404

    def test_enabled_in_production_it_does_not_exist(self, settings):
        settings.AI_ASSISTANT_ENABLED = True
        settings.DEBUG = False

        client = login_as("view_flightpermission")

        assert client.post(reverse(PANEL), {"question": "x"}).status_code == 404

    def test_a_get_is_refused(self, enabled):
        assert login_as("view_flightpermission").get(reverse(PANEL)).status_code == 405

    def test_anonymous_goes_to_login(self, enabled, client):
        response = client.post(reverse(PANEL), {"question": "x"})

        assert response.status_code == 302 and "login" in response.url

    def test_without_view_permission_it_is_forbidden(self, enabled):
        response = login_as().post(reverse(PANEL), {"question": "hola"})

        assert response.status_code == 403

    def test_a_post_without_csrf_is_rejected(self, enabled, fake):
        fake(_final("no debe llegar"))
        user = login_as("view_flightpermission").user
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(user)

        assert strict.post(reverse(PANEL), {"question": "x"}).status_code == 403
        assert not AssistantUsage.objects.exists()

    def test_an_empty_question_is_refused_without_calling_the_service(
        self, enabled, fake
    ):
        double = fake()

        response = login_as("view_flightpermission").post(
            reverse(PANEL), {"question": "  "}
        )

        assert response.status_code == 200
        assert 'role="alert"' in response.content.decode()
        assert double.calls == []


@pytest.mark.django_db
class TestCitations:
    def _ask(self, user, fake):
        fake(_tool_call("expiring_permits", '{"days": 60}'), _final("Vencen pronto."))
        http = Client()
        http.force_login(user)
        return http.post(reverse(PANEL), {"question": "¿Qué vence?"})

    def _pks(self, tenant):
        from apps.operations.models import FlightPermission

        return list(
            FlightPermission.objects.filter(cost_center__tenant=tenant).values_list(
                "pk", flat=True
            )
        )

    def test_citations_are_only_the_askers_tenant(self, enabled, fake):
        tenants = _world()
        user = login_as(
            "view_flightpermission", "view_operator", member_of=tenants["a"]
        ).user

        html = self._ask(user, fake).content.decode()

        assert gettext("Cited records") in html
        own = self._pks(tenants["a"])
        assert len(own) == 2
        for pk in own:
            assert reverse("permission-detail", args=[pk]) in html
        for pk in self._pks(tenants["b"]):
            assert str(pk) not in html

    def test_the_other_tenant_sees_only_its_own(self, enabled, fake):
        tenants = _world()
        user = login_as(
            "view_flightpermission", "view_aircraft", member_of=tenants["b"]
        ).user

        html = self._ask(user, fake).content.decode()

        (own,) = self._pks(tenants["b"])
        assert reverse("permission-detail", args=[own]) in html
        assert not any(str(pk) in html for pk in self._pks(tenants["a"]))

    def test_a_link_written_by_the_model_is_never_drawn(self, enabled, fake):
        fake(
            _final(
                'Abra <a href="https://evil.example/x">aquí</a> o '
                "[ver](https://evil.example/y) <script>alert(1)</script>"
            )
        )

        html = (
            login_as("view_flightpermission")
            .post(reverse(PANEL), {"question": "hola"})
            .content.decode()
        )

        assert "<script>alert" not in html
        assert '<a href="https://evil' not in html
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
        assert gettext("Cited records") not in html

    def test_only_uuid_pks_make_a_citation(self):
        rows = [
            {"pk": "javascript:alert(1)", "permit": "X"},
            {"pk": str(uuid.uuid4()), "permit": "OK-1"},
            {"permit": "sin pk"},
        ]

        cites = tools.citations_for("expiring_permits", rows)

        assert [c["label"] for c in cites] == ["OK-1"]
        assert cites[0]["url"].startswith("/")
        assert tools.citations_for("permits_summary", rows) == []

    def test_an_empty_answer_carries_no_citations(self, enabled, fake):
        _world()
        fake(_tool_call("expiring_permits", "{}"), _final(""))
        user = login_as("view_flightpermission", "view_operator").user

        answer = service.ask(user, "x")

        assert answer.citations == []


@pytest.mark.django_db
class TestStatesAndPrivacy:
    def test_the_cap_reached_state_is_marked(self, enabled, fake):
        enabled.AI_ASSISTANT_MAX_PER_HOUR = 1
        fake(_tool_call(), _final("no llega"))
        user = login_as("view_flightpermission").user
        answer = service.ask(user, "hola")

        assert answer.state == "limit" and not answer.ok
        http = Client()
        http.force_login(user)
        html = http.post(reverse(PANEL), {"question": "otra"}).content.decode()
        assert "ai-msg--limit" in html

    def test_a_service_failure_is_neutral(self, enabled, monkeypatch):
        class Down:
            configured = True

            def chat(self, messages, tools=None):
                raise service.AssistantUnavailable("boom-secret-detail")

        monkeypatch.setattr(service, "NvidiaClient", lambda: Down())

        html = (
            login_as("view_flightpermission")
            .post(reverse(PANEL), {"question": "hola"})
            .content.decode()
        )

        assert "ai-msg--error" in html
        assert "boom-secret-detail" not in html

    def test_neither_question_nor_answer_is_stored(self, enabled, fake):
        fake(_tool_call(), _final("CENTINELA-RESPUESTA"))

        login_as("view_flightpermission").post(
            reverse(PANEL), {"question": "CENTINELA-PREGUNTA"}
        )

        dump = json.dumps(list(AssistantUsage.objects.values()), default=str)
        assert AssistantUsage.objects.count() == 1
        assert "CENTINELA" not in dump

    def test_the_pk_does_not_break_the_personal_data_guard(self, enabled):
        from apps.operations.models import FlightPermission
        from apps.registry.models import Operator

        tenants = _world()
        permit = FlightPermission.objects.filter(cost_center__tenant=tenants["a"])[0]
        permit.operators.add(
            Operator.objects.create(
                full_name="Piloto Secreto Pérez",
                employee_id="E-777-ID",
                email="piloto.secreto@example.com",
                cost_center=permit.cost_center,
            )
        )
        user = login_as(
            "view_flightpermission", "view_operator", member_of=tenants["a"]
        ).user

        out = tools.run_tool(user, "expiring_permits", '{"days": 60}')

        assert "Secreto" not in out
        assert "E-777-ID" not in out
        assert "example.com" not in out
        for row in json.loads(out)["data"]:
            uuid.UUID(row["pk"])
