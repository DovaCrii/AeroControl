"""LV-322: estado de un despliegue, sólo lectura, para comprobar que *llegó*.

Condensa en una salida las señales que `AGENTS.md` pide mirar a mano tras un
despliegue (rama, hash, migraciones sin aplicar, trabajos programados). No escribe
en la base, no crea `JobRun`, no tiene URL ni vista: es sólo consola.

Sin secretos: de la configuración sólo imprime el **nombre** del módulo de settings;
la ruta de la base se compara en Python y sale un booleano, nunca el valor.
"""

import json
import os
import subprocess  # nosec B404 - sólo `git` y `systemctl`, sin shell ni entrada de usuario
import urllib.request

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from apps.core.jobs import job_health

# Ruta de datos de producción ya publicada en `docs/dev/ubuntu-vm-deploy.md`.
DEFAULT_EXPECTED_DB = "/srv/aerocontrol-data/db/aero_ops.sqlite3"


def _git(*args):
    try:
        out = subprocess.run(  # nosec B603 B607 - argumentos fijos, sin shell
            ["git", *args],
            cwd=settings.BASE_DIR,
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None


def _same_path(a, b):
    return os.path.normcase(os.path.normpath(str(a))) == os.path.normcase(
        os.path.normpath(str(b))
    )


def pending_migrations():
    executor = MigrationExecutor(connection)
    plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
    return [{"app": m.app_label, "name": m.name} for m, _backwards in plan]


def collect_timers():
    try:
        out = subprocess.run(  # nosec B603 B607 - argumentos fijos, sin shell
            ["systemctl", "list-timers", "aerocontrol-*", "--output=json"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        rows = json.loads(out.stdout or "[]")
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    return [
        {"unit": r.get("unit"), "next": r.get("next"), "last": r.get("last")}
        for r in rows
    ]


def probe_health(port):
    url = f"http://127.0.0.1:{int(port)}/health"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:  # nosec B310 - esquema http fijo, 127.0.0.1
            return resp.status
    except Exception:  # noqa: BLE001 - cualquier fallo es "no responde"
        return None


class Command(BaseCommand):
    help = "Read-only deployment status (head, pending migrations, jobs)."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", dest="as_json")
        parser.add_argument("--with-systemd", action="store_true")
        parser.add_argument("--probe-health", action="store_true")
        parser.add_argument("--health-port", type=int, default=8000)

    def handle(self, *args, **options):
        head = _git("rev-parse", "HEAD")
        branch = _git("rev-parse", "--abbrev-ref", "HEAD")
        expected_db = os.environ.get("DEPLOY_EXPECTED_DB", DEFAULT_EXPECTED_DB)
        real_db = settings.DATABASES["default"].get("NAME")
        data = {
            "head": head,
            "head_short": head[:7] if head else None,
            "branch_ok": branch == "main",
            "settings_module": os.environ.get("DJANGO_SETTINGS_MODULE"),
            "db_path_ok": _same_path(real_db, expected_db),
            "pending_migrations": pending_migrations(),
            "jobs": job_health(),
        }
        if options["with_systemd"]:
            data["timers"] = collect_timers()
        if options["probe_health"]:
            data["health"] = probe_health(options["health_port"])

        if options["as_json"]:
            self.stdout.write(json.dumps(data, default=str, indent=2))
            return
        self.stdout.write(f"head: {data['head_short']}  branch_ok: {data['branch_ok']}")
        self.stdout.write(
            f"settings: {data['settings_module']}  db_path_ok: {data['db_path_ok']}"
        )
        pend = data["pending_migrations"]
        self.stdout.write(f"pending migrations: {len(pend)}")
        for m in pend:
            self.stdout.write(f"  {m['app']}.{m['name']}")
        for j in data["jobs"]:
            flag = (
                "NEVER RAN"
                if j.get("never_ran")
                else ("STALE" if j.get("stale") else "ok")
            )
            self.stdout.write(f"job {j['command']}: {flag} ({j.get('when')})")
        for key in ("timers", "health"):
            if key in data:
                self.stdout.write(f"{key}: {data[key]}")
