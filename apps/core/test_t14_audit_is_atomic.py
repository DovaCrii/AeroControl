"""T1.4 paso 2: la auditoría atómica con la mutación (`AUDIT_FAIL_CLOSED`).

Antes el middleware escribía el `AuditEvent` después de la respuesta y fuera de toda
transacción: si la escritura fallaba, el cambio ya estaba confirmado y sólo quedaba una
línea de log. Con `AUDIT_FAIL_CLOSED` encendido, las peticiones que mutan corren dentro
de una transacción y la auditoría se escribe **antes de confirmarla**: si no se puede,
se deshace el cambio entero y la persona ve un 503.

Decisión del usuario (2026-10-07): fail-closed. **Apagado por omisión**, porque es lo que
intercepta todas las mutaciones y la lección del service worker es que algo así no se
despliega encendido.
"""

import logging

import pytest
from django.conf import settings as django_settings
from django.contrib.auth.models import AnonymousUser, User
from django.db import transaction
from django.test import RequestFactory
from django.urls import reverse

from apps.core import audit_health
from apps.core.middleware import RequestMetricsMiddleware
from apps.core.models import AuditEvent
from apps.workboard.models import KanbanBoard


@pytest.fixture
def admin(client, db):
    user = User.objects.create_superuser("a14", "a14@test.com", "pw")  # nosec B106
    client.force_login(user)
    return client


@pytest.fixture
def log_dir(settings, tmp_path):
    settings.LOG_DIR = tmp_path
    return tmp_path


@pytest.fixture
def strict(settings, log_dir):
    settings.AUDIT_FAIL_CLOSED = True


@pytest.fixture
def audit_down(monkeypatch):
    def fail_create(**kwargs):
        raise RuntimeError("audit database unavailable")

    monkeypatch.setattr(AuditEvent.objects, "create", fail_create)


def _create_board(client, name="Tablero"):
    return client.post(reverse("board-create"), {"name": name})


class TestItShipsSwitchedOff:
    def test_the_default_is_fail_open(self):
        """Algo que intercepta toda mutación no se despliega encendido."""
        assert django_settings.AUDIT_FAIL_CLOSED is False

    @pytest.mark.django_db
    def test_switched_off_a_failed_audit_still_saves_the_change(
        self, admin, log_dir, audit_down
    ):
        response = _create_board(admin)

        assert response.status_code == 302
        assert KanbanBoard.objects.filter(name="Tablero").exists()


@pytest.mark.django_db
class TestFailClosed:
    def test_a_failed_audit_undoes_the_change_and_says_so(
        self, admin, strict, audit_down
    ):
        response = _create_board(admin)

        assert response.status_code == 503
        assert not KanbanBoard.objects.filter(name="Tablero").exists()
        assert response["Retry-After"] == "30"
        body = response.content.decode()
        assert "Cambio no guardado" in body
        assert "No se modificó nada" in body

    def test_the_failure_is_still_recorded_for_the_administration_centre(
        self, admin, strict, audit_down, caplog
    ):
        with caplog.at_level(logging.ERROR):
            _create_board(admin)

        assert "audit_write_failed" in caplog.text
        assert audit_health.last_failure()["count"] == 1

    def test_a_successful_audit_commits_change_and_entry_together(self, admin, strict):
        response = _create_board(admin, "Atómico")

        assert response.status_code == 302
        board = KanbanBoard.objects.get(name="Atómico")
        event = AuditEvent.objects.latest("created_at")
        assert event.action == "post_success"
        assert event.object_id == str(board.pk)

    def test_the_503_page_keeps_the_security_headers_and_the_request_id(
        self, admin, strict, audit_down
    ):
        response = _create_board(admin)

        assert response["X-Request-ID"]
        assert (
            "Content-Security-Policy" in response
            or "Content-Security-Policy-Report-Only" in response
        )

    def test_a_read_is_never_wrapped_or_refused(self, admin, strict, audit_down):
        """El modo estricto es sólo para mutaciones: leer no se audita ni se frena."""
        response = admin.get(reverse("dashboard"))

        assert response.status_code == 200

    def test_an_anonymous_post_is_not_audited_and_not_refused(
        self, client, strict, audit_down
    ):
        """Sin sesión no hay actor al que atribuir nada: se redirige a entrar, como
        siempre, aunque la auditoría esté caída."""
        response = client.post(reverse("board-create"), {"name": "x"})

        assert response.status_code == 302
        assert "login" in response.url

    def test_the_login_path_is_excluded_like_before(self, client, strict, audit_down):
        response = client.post(
            reverse("login"), {"username": "nobody", "password": "wrong"}
        )

        assert response.status_code in (200, 302)  # nunca 503: /accounts/ no se audita

    def test_a_denied_attempt_is_audited_too_and_fails_closed_if_it_cannot_be(
        self, client, strict, audit_down
    ):
        """Un 403 también es un hecho que debe quedar escrito."""
        user = User.objects.create_user("noperm", password="pw")  # nosec B106
        client.force_login(user)

        response = client.post(reverse("board-create"), {"name": "x"})

        assert response.status_code == 503


@pytest.mark.django_db
class TestAllOrNothing:
    """Una petición puede dejar varias entradas (LV-176): o todas, o ninguna."""

    def _request(self, user):
        request = RequestFactory().post("/workboard/boards/new/")
        request.user = user
        request._audit_siblings = [
            {"model_label": "workboard.KanbanBoard", "object_id": "2", "action": None}
        ]
        return request

    def test_a_failure_on_the_second_entry_undoes_the_view_and_the_first_entry(
        self, settings, log_dir, monkeypatch
    ):
        settings.AUDIT_FAIL_CLOSED = True
        user = User.objects.create_user("sib", password="pw")  # nosec B106
        real_create = AuditEvent.objects.create
        calls = {"n": 0}

        def second_fails(**kwargs):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("disk full")
            return real_create(**kwargs)

        monkeypatch.setattr(AuditEvent.objects, "create", second_fails)

        def view(request):
            from django.http import HttpResponse

            KanbanBoard.objects.create(name="Medio hecho")
            return HttpResponse("ok")

        response = RequestMetricsMiddleware(view)(self._request(user))

        assert response.status_code == 503
        assert calls["n"] == 2
        assert not KanbanBoard.objects.filter(name="Medio hecho").exists()
        assert AuditEvent.objects.count() == 0  # tampoco quedó la primera entrada

    def test_the_views_own_nested_transaction_is_undone_with_it(
        self, settings, log_dir, audit_down
    ):
        """Una vista que abre su propio `atomic()` sólo crea un punto de guardado:
        la transacción de afuera la arrastra al deshacer."""
        settings.AUDIT_FAIL_CLOSED = True
        user = User.objects.create_user("nest", password="pw")  # nosec B106

        def view(request):
            from django.http import HttpResponse

            with transaction.atomic():
                KanbanBoard.objects.create(name="Anidado")
            return HttpResponse("ok")

        response = RequestMetricsMiddleware(view)(self._request(user))

        assert response.status_code == 503
        assert not KanbanBoard.objects.filter(name="Anidado").exists()

    def test_with_every_entry_written_the_view_is_committed(self, settings, log_dir):
        settings.AUDIT_FAIL_CLOSED = True
        user = User.objects.create_user("ok14", password="pw")  # nosec B106

        def view(request):
            from django.http import HttpResponse

            KanbanBoard.objects.create(name="Completo")
            return HttpResponse("ok")

        response = RequestMetricsMiddleware(view)(self._request(user))

        assert response.status_code == 200
        assert KanbanBoard.objects.filter(name="Completo").exists()
        assert AuditEvent.objects.count() == 2  # la principal y la hermana

    def test_an_unauthenticated_request_writes_nothing_and_commits(
        self, settings, log_dir
    ):
        settings.AUDIT_FAIL_CLOSED = True
        request = RequestFactory().post("/csp-report/")
        request.user = AnonymousUser()

        def view(request):
            from django.http import HttpResponse

            return HttpResponse(status=204)

        response = RequestMetricsMiddleware(view)(request)

        assert response.status_code == 204
        assert AuditEvent.objects.count() == 0
