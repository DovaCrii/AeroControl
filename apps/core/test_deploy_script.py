"""LV-327: pruebas de `scripts/deploy.sh` sin VM.

Un repo bare + un clon que hace de `/opt/aerocontrol` (`DEPLOY_ROOT`), y un `PATH` falso con
stubs de `sudo`, `systemctl`, `systemd-run`, `curl` y `uv` que **registran** cada llamada en un
archivo y responden lo que cada prueba fija. Lo que NO prueba esto: systemd, sudo y gunicorn
reales, `uv sync` y `manage.py` verdaderos, ni la red (ver MASTER_PLAN, LV-327).

En Windows el script corre con el `bash` de WSL: las rutas se convierten con `wslpath`.
"""

import os
import shlex
import shutil
import subprocess  # nosec B404 - pruebas: sólo bash/git con argumentos propios
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "deploy.sh"
SENTINEL = "SECRET_SENTINEL_9f3a"


def _bash_works():
    if not shutil.which("bash") or not shutil.which("git"):
        return False
    try:
        r = subprocess.run(  # nosec B603 B607
            ["bash", "-c", "command -v git python3 >/dev/null && echo ok"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return r.stdout.strip() == "ok"


pytestmark = pytest.mark.skipif(
    not _bash_works(), reason="needs bash (WSL on Windows), git and python3"
)


def posix(path):
    if os.name != "nt":
        return str(path)
    out = subprocess.run(  # nosec B603 B607
        ["bash", "-c", f"wslpath -u {shlex.quote(str(path))}"],
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.strip()


def sh(cmd, env=None):
    exports = "".join(f"export {k}={shlex.quote(v)}; " for k, v in (env or {}).items())
    return subprocess.run(  # nosec B603 B607
        ["bash", "-c", exports + cmd],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )


STUBS = {
    "sudo": r"""#!/usr/bin/env bash
echo "sudo $*" >> "$STUB_LOG"
case "$1" in -v|-n) exit 0;; esac
exec "$@"
""",
    "systemctl": r"""#!/usr/bin/env bash
echo "systemctl $*" >> "$STUB_LOG"
case "$1" in
  is-active) cat "$STUB_DIR/active" 2>/dev/null || echo active ;;
  list-timers) echo "aerocontrol-a.timer"; echo "aerocontrol-b.timer" ;;
esac
exit 0
""",
    "curl": r"""#!/usr/bin/env bash
echo "curl $*" >> "$STUB_LOG"
printf '%s' "$(cat "$STUB_DIR/health" 2>/dev/null || echo 200)"
""",
    "uv": r"""#!/usr/bin/env bash
echo "uv $*" >> "$STUB_LOG"
if [ "$1" = sync ]; then cat "$STUB_DIR/sync" 2>/dev/null || echo "Installed 2 packages"; fi
exit 0
""",
    # Hace de systemd: lee el EnvironmentFile (el centinela vive ahí) y corre el "manage.py".
    "systemd-run": r"""#!/usr/bin/env bash
envfile=""
for a in "$@"; do case "$a" in EnvironmentFile=*) envfile="${a#EnvironmentFile=}";; esac; done
[ -n "$envfile" ] && set -a && . "$envfile" && set +a
args=("$@"); sub=""
for i in "${!args[@]}"; do
  if [ "${args[$i]}" = "manage.py" ]; then sub="${args[$((i+1))]}"; fi
done
echo "manage $sub ${args[*]: -1}" >> "$STUB_LOG"
case "$sub" in
  deploy_status)
    n=$(( $(cat "$STUB_DIR/ds.count" 2>/dev/null || echo 0) + 1 )); echo $n > "$STUB_DIR/ds.count"
    if [ -f "$STUB_DIR/ds.$n" ]; then cat "$STUB_DIR/ds.$n"; else cat "$STUB_DIR/ds.default"; fi ;;
  backup) echo "Backup created" ;;
  verify_backup) cat "$STUB_DIR/verify" 2>/dev/null || echo "backup: restorable." ;;
  migrate) echo "  Applying x.0001... OK" ;;
  collectstatic) cat "$STUB_DIR/cs" 2>/dev/null || echo "5 static files copied to 'x', 0 unmodified." ;;
  showmigrations) echo "[ ] 0001_x" ;;
esac
exit 0
""",
}

DS_OK = (
    '{"settings_module": "config.settings.prod", "db_path_ok": true, '
    '"pending_migrations": []}'
)


def ds_pending(n):
    items = ", ".join('{"app": "registry", "name": "00%02d_x"}' % i for i in range(n))
    return (
        '{"settings_module": "config.settings.prod", "db_path_ok": true, '
        f'"pending_migrations": [{items}]}}'
    )


class World:
    def __init__(self, tmp_path, proot):
        self.root = tmp_path
        self.proot = proot  # la misma carpeta, vista desde bash
        self.bare = self.root / "origin.git"
        self.dev = self.root / "dev"
        self.vm = self.root / "opt" / "aerocontrol"
        self.stub = self.root / "stub"
        self.log = self.stub / "calls.log"
        self.envfile = self.root / "aerocontrol.env"
        self.stub.mkdir()
        bindir = self.stub / "bin"
        bindir.mkdir()
        for name, body in STUBS.items():
            (bindir / name).write_text(body, newline="\n")
        sh(f"chmod +x {self.q(bindir)}/*")
        (self.stub / "ds.default").write_text(DS_OK)
        self.envfile.write_text(f"SECRET={SENTINEL}\n", newline="\n")
        (self.vm.parent).mkdir()
        self.git(
            f"git init -q --bare -b main {self.q(self.bare)} && "
            f"git clone -q {self.q(self.bare)} {self.q(self.dev)} && cd {self.q(self.dev)}"
            " && git checkout -q -B main && echo a > a.txt && git add -A && git commit -qm init"
            " && git push -q origin main"
        )
        self.git(f"git clone -q {self.q(self.bare)} {self.q(self.vm)}")

    def q(self, p):
        rel = Path(p).relative_to(self.root).as_posix()
        return shlex.quote(self.proot if rel == "." else f"{self.proot}/{rel}")

    def git(self, cmd):
        full = (
            "export GIT_CONFIG_COUNT=3 GIT_CONFIG_KEY_0=safe.directory GIT_CONFIG_VALUE_0='*' "
            "GIT_CONFIG_KEY_1=user.name GIT_CONFIG_VALUE_1=t GIT_CONFIG_KEY_2=user.email "
            "GIT_CONFIG_VALUE_2=t@t; " + cmd
        )
        r = sh(full)
        assert r.returncode == 0, r.stderr
        return r.stdout.strip()

    def push(self, files):
        """Un commit nuevo en origin con `files` {ruta: contenido}."""
        writes = " && ".join(
            f"mkdir -p $(dirname {shlex.quote(p)}) && printf %s {shlex.quote(c)} > {shlex.quote(p)}"
            for p, c in files.items()
        )
        self.git(
            f"cd {self.q(self.dev)} && {writes} && git add -A && git commit -qm change"
            " && git push -q origin main"
        )

    def vm_git(self, args):
        return self.git(f"cd {self.q(self.vm)} && git {args}")

    def run(self, *args):
        cmd = (
            f'export PATH={self.q(self.stub / "bin")}":$PATH" '
            f"STUB_DIR={self.q(self.stub)} STUB_LOG={self.q(self.log)} "
            f"DEPLOY_ROOT={self.q(self.vm)} DEPLOY_ENV_FILE={self.q(self.envfile)} DEPLOY_FAKE=1 "
            "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=safe.directory GIT_CONFIG_VALUE_0='*'; "
            f"touch {self.q(self.log)}; "
            f"bash {shlex.quote(posix(SCRIPT))} {' '.join(args)}"
        )
        r = sh(cmd)
        out = r.stdout + r.stderr
        self.stdout = r.stdout
        assert SENTINEL not in out, "el script imprimio un valor del entorno"
        return r.returncode, out

    def calls(self):
        return self.log.read_text() if self.log.exists() else ""


@pytest.fixture
def world(tmp_path):
    """En Windows el mundo vive dentro de WSL (`/tmp`): git sobre /mnt/c tarda minutos."""
    if os.name != "nt":
        yield World(tmp_path, str(tmp_path))
        return
    probe = sh("echo $WSL_DISTRO_NAME; mktemp -d /tmp/acdeploy.XXXXXX")
    distro, proot = probe.stdout.split()
    root = Path(rf"\\wsl.localhost\{distro}") / proot.lstrip("/")
    try:
        yield World(root, proot)
    finally:
        sh(f"rm -rf {shlex.quote(proot)}")


def summary(out):
    return out.split("=== RESUMEN", 1)[1].strip().splitlines()


def test_detached_head_aborts(world):
    world.push({"b.txt": "b"})
    world.vm_git("checkout -q --detach")
    rc, out = world.run()
    assert rc != 0
    assert "FALLÓ en paso 1" in out and "HEAD desprendido" in out
    assert "restart" not in world.calls()


def test_dirty_tree_aborts(world):
    world.push({"b.txt": "b"})
    (world.vm / "a.txt").write_text("changed")
    rc, out = world.run()
    assert rc != 0
    assert "FALLÓ en paso 2" in out and "no esta limpio" in out
    assert "restart" not in world.calls()


def test_untracked_file_that_pull_would_overwrite_aborts(world):
    world.push({"new.txt": "n"})
    (world.vm / "new.txt").write_text("local")
    rc, out = world.run()
    assert rc != 0
    assert "FALLÓ en paso 2" in out and "mv new.txt" in out


def test_uv_sync_that_installs_nothing_aborts_and_rollback_is_only_printed(world):
    old = world.vm_git("rev-parse HEAD")
    world.push({"uv.lock": "lock"})
    (world.stub / "sync").write_text("Audited 64 packages")
    rc, out = world.run()
    assert rc != 0
    assert "FALLÓ en paso 8" in out
    assert f"git checkout {old} && sudo systemctl restart aerocontrol" in out
    assert "restart" not in world.calls()  # imprimido, nunca ejecutado
    assert "vuelta" not in out


def test_allow_noop_sync_lets_it_continue(world):
    world.push({"uv.lock": "lock"})
    (world.stub / "sync").write_text("Audited 64 packages")
    rc, out = world.run("--allow-noop-sync")
    assert rc == 0 and "DEPLOY OK" in out


def test_static_with_zero_copied_aborts(world):
    world.push({"static/a.css": "x"})
    (world.stub / "cs").write_text("0 static files copied to 'x', 9 unmodified.")
    rc, out = world.run()
    assert rc != 0
    assert "FALLÓ en paso 10" in out
    assert "systemctl restart" not in world.calls()


def test_health_503_aborts_without_running_the_rollback(world):
    world.push({"b.txt": "b"})
    (world.stub / "health").write_text("503")
    rc, out = world.run()
    assert rc != 0
    assert "FALLÓ en paso 12" in out and "503" in out
    assert "git checkout" in out and "NO se ejecuta" in out
    # el HEAD sigue en el commit nuevo: el rollback sólo se imprimió
    assert world.vm_git("rev-parse HEAD") == world.vm_git("rev-parse origin/main")
    assert "systemctl checkout" not in world.calls()


def test_wrong_settings_module_aborts_before_anything_is_written(world):
    world.push({"b.txt": "b"})
    (world.stub / "ds.default").write_text(
        '{"settings_module": "config.settings.dev", "db_path_ok": true, '
        '"pending_migrations": []}'
    )
    rc, out = world.run()
    assert rc != 0 and "FALLÓ en paso 5" in out
    assert "restart" not in world.calls() and "backup" not in world.calls()


def test_happy_path_with_migrations_static_and_deps(world):
    world.push(
        {
            "apps/registry/migrations/0099_x.py": "m",
            "static/a.css": "x",
            "pyproject.toml": "p",
            "docs/scheduled-operations.md": "t",
        }
    )
    (world.stub / "ds.1").write_text(DS_OK)
    (world.stub / "ds.2").write_text(ds_pending(1))
    (world.stub / "ds.3").write_text(DS_OK)
    rc, out = world.run()
    assert rc == 0, out
    lines = summary(world.stdout)
    assert len(lines) <= 10, lines
    assert lines[0].startswith("DEPLOY OK")
    assert "HEAD == origin/main: sí" in lines
    assert "timers" in " ".join(lines) and "mkjob" in " ".join(lines)
    assert world.vm_git("rev-parse HEAD") == world.vm_git("rev-parse origin/main")
    calls = [c.split()[1] for c in world.calls().splitlines() if c.startswith("manage")]
    order = [c for c in calls if c != "deploy_status"]
    assert order == ["backup", "verify_backup", "migrate", "collectstatic"]
    assert "systemctl restart aerocontrol" in world.calls()
    # el respaldo va ANTES del pull: con el código viejo
    assert "uv sync --no-dev --locked" in world.calls()


def test_leftover_pending_migration_is_applied_even_if_diff_has_none(world):
    world.push({"b.txt": "b"})
    (world.stub / "ds.1").write_text(ds_pending(1))
    (world.stub / "ds.2").write_text(ds_pending(1))
    (world.stub / "ds.3").write_text(DS_OK)
    rc, out = world.run()
    assert rc == 0, out
    assert "manage migrate" in world.calls() and "manage backup" in world.calls()


def test_migrations_still_pending_after_migrate_abort(world):
    world.push({"apps/registry/migrations/0099_x.py": "m"})
    (world.stub / "ds.default").write_text(ds_pending(1))
    rc, out = world.run()
    assert rc != 0 and "FALLÓ en paso 9" in out
    assert "restore_backup" in out
    assert "manage showmigrations" in world.calls()


def test_dry_run_reads_but_never_writes(world):
    world.push({"apps/registry/migrations/0099_x.py": "m", "static/a.css": "x"})
    before = world.vm_git("rev-parse HEAD")
    rc, out = world.run("--dry-run")
    assert rc == 0, out
    assert "DRY-RUN" in out
    calls = world.calls()
    for forbidden in ("restart", "migrate", "backup", "collectstatic", "uv sync"):
        assert forbidden not in calls
    assert "deploy_status" in calls
    assert world.vm_git("rev-parse HEAD") == before


def test_nothing_to_deploy_exits_zero_and_checks_health(world):
    rc, out = world.run()
    assert rc == 0 and "nada que subir" in out
    assert "restart" not in world.calls() and "curl" in world.calls()


def test_status_flag_only_wraps_deploy_status(world):
    rc, out = world.run("--status")
    assert rc == 0
    cmds = [c.split()[1] for c in world.calls().splitlines() if c.startswith("manage")]
    assert cmds == ["deploy_status"]
