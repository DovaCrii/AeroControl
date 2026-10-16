"""LV-322: `deploy_status` es de sólo lectura y no filtra nada."""

import io
import json

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import get_resolver
from django.utils import timezone

from apps.core.management.commands import deploy_status
from apps.core.models import JobRun

pytestmark = pytest.mark.django_db


def run(*args):
    out = io.StringIO()
    call_command("deploy_status", *args, stdout=out)
    return out.getvalue()


def test_json_has_the_expected_keys():
    data = json.loads(run("--json"))
    assert {
        "head",
        "head_short",
        "branch_ok",
        "settings_module",
        "db_path_ok",
        "pending_migrations",
        "jobs",
    } <= set(data)
    assert "timers" not in data and "health" not in data
    assert isinstance(data["pending_migrations"], list)


def test_human_output_is_the_default():
    text = run()
    assert "pending migrations:" in text and "db_path_ok" in text
    with pytest.raises(ValueError):
        json.loads(text)


def test_simulated_pending_migration(monkeypatch):
    class M:
        app_label = "registry"
        name = "9999_x"

    class Fake:
        def __init__(self, conn):
            self.loader = type(
                "L", (), {"graph": type("G", (), {"leaf_nodes": lambda s: []})()}
            )()

        def migration_plan(self, targets):
            return [(M(), False)]

    monkeypatch.setattr(deploy_status, "MigrationExecutor", Fake)
    data = json.loads(run("--json"))
    assert data["pending_migrations"] == [{"app": "registry", "name": "9999_x"}]


def test_db_path_ok_false_with_another_path(monkeypatch):
    monkeypatch.setenv("DEPLOY_EXPECTED_DB", "/otra/ruta/distinta.sqlite3")
    assert json.loads(run("--json"))["db_path_ok"] is False


def test_db_path_ok_true_when_it_matches(monkeypatch, settings):
    monkeypatch.setenv("DEPLOY_EXPECTED_DB", str(settings.DATABASES["default"]["NAME"]))
    assert json.loads(run("--json"))["db_path_ok"] is True


def test_no_secrets_and_no_paths(monkeypatch, settings):
    monkeypatch.setenv("SECRET_SENTINEL", "SECRET_SENTINEL_VALUE_123")
    settings.SECRET_KEY = "SECRET_SENTINEL_VALUE_123"
    for args in (("--json",), ()):
        text = run(*args)
        assert "SECRET_SENTINEL" not in text
        assert str(settings.DATABASES["default"]["NAME"]) not in text
        assert deploy_status.DEFAULT_EXPECTED_DB not in text
        assert "/srv/" not in text


def test_writes_nothing_to_the_database():
    before = JobRun.objects.count()
    run("--json")
    run()
    assert JobRun.objects.count() == before


def test_the_mutation_check_catches_a_write(monkeypatch):
    """Control: el conteo de arriba sí detecta una escritura."""
    original = deploy_status.job_health

    def writing():
        JobRun.objects.create(command="deploy_status", started_at=timezone.now())
        return original()

    monkeypatch.setattr(deploy_status, "job_health", writing)
    before = JobRun.objects.count()
    run("--json")
    assert JobRun.objects.count() == before + 1


def test_not_exposed_through_urls():
    patterns = repr(get_resolver().url_patterns)
    assert "deploy_status" not in patterns and "deploy-status" not in patterns


def test_optional_probes_fail_soft(monkeypatch):
    monkeypatch.setattr(deploy_status, "collect_timers", lambda: None)
    monkeypatch.setattr(deploy_status, "probe_health", lambda port: None)
    data = json.loads(run("--json", "--with-systemd", "--probe-health"))
    assert data["timers"] is None and data["health"] is None


def test_health_port_is_forwarded(monkeypatch):
    seen = []
    monkeypatch.setattr(
        deploy_status, "probe_health", lambda port: seen.append(port) or 200
    )
    data = json.loads(run("--json", "--probe-health", "--health-port", "9123"))
    assert seen == [9123] and data["health"] == 200


def test_unknown_option_is_an_error():
    with pytest.raises(CommandError):
        call_command("deploy_status", "--nope")


def test_git_missing_degrades_to_none(monkeypatch):
    monkeypatch.setattr(deploy_status, "_git", lambda *a: None)
    data = json.loads(run("--json"))
    assert data["head"] is None and data["branch_ok"] is False
