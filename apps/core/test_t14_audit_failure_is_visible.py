"""T1.4 (paso 1): un fallo al escribir la auditoría deja de ser sólo una línea de log.

El middleware escribe el `AuditEvent` después de la respuesta, fuera de toda
transacción, y si falla sigue (fail-open). Esa decisión **no cambia** acá —hacerlo
fail-closed es el paso 2, detrás de `AUDIT_FAIL_CLOSED` y apagado por defecto—; lo
que cambia es que el fallo se **vea**: una marca en disco y una línea en el panel
de situación del centro de administración.
"""

import json
import logging

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.urls import reverse

from apps.core import audit_health
from apps.core.models import AuditEvent
from apps.workboard.models import KanbanBoard


@pytest.fixture
def log_dir(settings, tmp_path):
    """Un `LOG_DIR` propio: la marca vive en disco y no puede ensuciar el real."""
    settings.LOG_DIR = tmp_path
    return tmp_path


@pytest.fixture
def staff_client(client, db):
    admin = User.objects.create_superuser("t14", "t14@test.com", "pw")  # nosec B106
    client.force_login(admin)
    return client


@pytest.fixture
def audit_down(monkeypatch):
    def fail_create(**kwargs):
        raise RuntimeError("audit database unavailable")

    monkeypatch.setattr(AuditEvent.objects, "create", fail_create)


def _mutate(client, name="Board"):
    return client.post(reverse("board-create"), {"name": name})


@pytest.mark.django_db
class TestTheFailureLeavesAMark:
    def test_a_failed_audit_write_is_recorded(
        self, staff_client, log_dir, audit_down, caplog
    ):
        with caplog.at_level(logging.ERROR):
            response = _mutate(staff_client)

        # Fail-open: la mutación se confirma igual (decisión vigente).
        assert response.status_code == 302
        assert KanbanBoard.objects.filter(name="Board").exists()
        # La línea de log de siempre sigue ahí...
        assert "audit_write_failed" in caplog.text
        # ...y ahora hay además una marca que alguien puede leer.
        failure = audit_health.last_failure()
        assert failure["count"] == 1
        assert failure["method"] == "POST"
        assert failure["path"] == reverse("board-create")
        assert failure["error"] == "RuntimeError"
        assert failure["request_id"]

    def test_the_mark_counts_repeats_and_keeps_the_first_date(
        self, staff_client, log_dir, audit_down
    ):
        _mutate(staff_client, "Uno")
        first = audit_health.last_failure()["first_at"]
        _mutate(staff_client, "Dos")

        failure = audit_health.last_failure()

        assert failure["count"] == 2
        assert failure["first_at"] == first

    def test_the_error_message_is_not_stored_only_its_type(
        self, staff_client, log_dir, audit_down
    ):
        """El mensaje de un error de base puede traer datos de la fila, y esto se
        muestra en una pantalla."""
        _mutate(staff_client)

        raw = (log_dir / audit_health.MARKER_NAME).read_text(encoding="utf-8")

        assert "audit database unavailable" not in raw

    def test_a_successful_write_leaves_no_mark(self, staff_client, log_dir):
        response = _mutate(staff_client)

        assert response.status_code == 302
        assert audit_health.last_failure() is None
        assert not (log_dir / audit_health.MARKER_NAME).exists()

    def test_an_unwritable_mark_never_breaks_the_request(
        self, staff_client, settings, tmp_path, audit_down
    ):
        """La marca es una ayuda: si no se puede escribir, la petición sigue."""
        blocker = tmp_path / "not-a-directory"
        blocker.write_text("x", encoding="utf-8")
        settings.LOG_DIR = blocker  # un archivo donde debería ir el directorio

        response = _mutate(staff_client)

        assert response.status_code == 302
        assert KanbanBoard.objects.filter(name="Board").exists()

    def test_a_corrupt_mark_reads_as_none_not_as_an_error(self, log_dir):
        (log_dir / audit_health.MARKER_NAME).write_text("{not json", encoding="utf-8")

        assert audit_health.last_failure() is None


@pytest.mark.django_db
class TestTheAdministrationCenterShowsIt:
    def test_it_is_green_when_nothing_failed(self, staff_client, log_dir):
        body = staff_client.get(reverse("administration")).content.decode()

        assert "Escrituras del registro de auditoría" in body
        assert "se guardaron" not in body.lower()

    def test_it_turns_red_and_says_how_many_and_when(
        self, staff_client, log_dir, audit_down
    ):
        _mutate(staff_client, "Uno")
        _mutate(staff_client, "Dos")

        response = staff_client.get(reverse("administration"))
        body = response.content.decode()

        assert response.context["situation"]["health"]["audit"] is False
        assert "Se guardaron 2 cambio(s) sin su entrada de auditoría" in body
        assert audit_health.last_failure()["last_at"] in body

    def test_it_never_shows_the_mark_to_someone_without_the_job_permission(
        self, client, log_dir
    ):
        """El bloque de salud ya va detrás de `core.view_jobrun`: sin ese permiso
        no hay panel, y la marca no se filtra por otra puerta."""
        nobody = User.objects.create_user("t14b", "t14b@test.com", "pw")  # nosec B106
        client.force_login(nobody)
        audit_health.record_failure(
            request_id="r", method="POST", path="/x/", error=RuntimeError()
        )

        body = client.get(reverse("administration")).content.decode()

        assert "sin su entrada de auditoría" not in body


@pytest.mark.django_db
class TestClearingTheMark:
    def test_it_clears_a_recorded_failure(self, log_dir, capsys):
        audit_health.record_failure(
            request_id="r", method="POST", path="/x/", error=RuntimeError()
        )
        audit_health.record_failure(
            request_id="r2", method="POST", path="/y/", error=RuntimeError()
        )

        call_command("clear_audit_failure")

        assert audit_health.last_failure() is None
        assert "2 failure(s)" in capsys.readouterr().out

    def test_with_nothing_recorded_it_says_so_and_does_not_fail(self, log_dir, capsys):
        call_command("clear_audit_failure")

        assert "No audit write failure on record." in capsys.readouterr().out

    def test_the_mark_is_valid_json_with_the_documented_keys(self, log_dir):
        audit_health.record_failure(
            request_id="r", method="PUT", path="/z/", error=ValueError()
        )

        raw = json.loads((log_dir / audit_health.MARKER_NAME).read_text("utf-8"))

        assert set(raw) == {
            "count",
            "first_at",
            "last_at",
            "request_id",
            "method",
            "path",
            "error",
        }
