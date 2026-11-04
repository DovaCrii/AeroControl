"""LV-400: restaurar con la API de respaldo de SQLite, no copiando bytes.

`restore_backup` hacía `shutil.copy2` sobre la base en modo WAL sin tocar
`-wal`/`-shm`: si quedaban los de la base anterior, SQLite los reaplicaba sobre
el archivo restaurado y lo dañaba.
"""

import hashlib
import json
import shutil
import sqlite3

import pytest
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError


def _make_backup(tmp_path, marker):
    path = tmp_path / "backups" / "aero_ops_20260101_000000.sqlite3"
    path.parent.mkdir()
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT)")
    connection.executemany(
        "INSERT INTO t (name) VALUES (?)", [(f"{marker}-{n}",) for n in range(200)]
    )
    connection.commit()
    connection.close()
    path.with_suffix(".json").write_text(
        json.dumps(
            {
                "backup": path.name,
                "size": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        ),
        encoding="utf-8",
    )
    return path


def _wal_database_with_pending_wal(path):
    """Base en WAL cuyas escrituras siguen en `-wal`, como tras un corte."""
    live = sqlite3.connect(path)
    live.execute("PRAGMA journal_mode=WAL")
    live.execute("PRAGMA wal_autocheckpoint=0")
    live.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT)")
    live.executemany(
        "INSERT INTO t (name) VALUES (?)", [(f"old-{n}",) for n in range(500)]
    )
    live.commit()
    # Foto de los tres archivos con el WAL aún sin checkpoint (el estado tras
    # un corte); recién después se cierra la conexión, que sí haría checkpoint.
    snapshot = path.with_name("snapshot.sqlite3")
    for suffix in ("", "-wal", "-shm"):
        shutil.copy2(f"{path}{suffix}", f"{snapshot}{suffix}")
    live.close()
    for suffix in ("", "-wal", "-shm"):
        shutil.copy2(f"{snapshot}{suffix}", f"{path}{suffix}")
    assert path.with_name(path.name + "-wal").stat().st_size > 0


def test_restore_over_a_wal_database_is_not_damaged(tmp_path):
    backup = _make_backup(tmp_path, "restored")
    destination = tmp_path / "dest.sqlite3"
    _wal_database_with_pending_wal(destination)

    call_command("restore_backup", str(backup), str(destination), "--force")

    check = sqlite3.connect(destination)
    try:
        assert check.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        names = [row[0] for row in check.execute("SELECT name FROM t")]
    finally:
        check.close()
    assert "restored-0" in names
    assert len(names) == 200
    assert not any(name.startswith("old-") for name in names)


def test_restoring_over_the_configured_database_requires_force(
    tmp_path, monkeypatch, capsys
):
    backup = _make_backup(tmp_path, "restored")
    live = tmp_path / "live.sqlite3"
    monkeypatch.setitem(settings.DATABASES["default"], "NAME", str(live))

    with pytest.raises(CommandError, match="systemctl stop aerocontrol"):
        call_command("restore_backup", str(backup), str(live))
    assert not live.exists()

    call_command("restore_backup", str(backup), str(live), "--force")
    assert "systemctl stop aerocontrol" in capsys.readouterr().out
    check = sqlite3.connect(live)
    try:
        assert check.execute("SELECT COUNT(*) FROM t").fetchone() == (200,)
    finally:
        check.close()


def test_other_destination_does_not_print_the_service_warning(tmp_path, capsys):
    backup = _make_backup(tmp_path, "restored")
    call_command("restore_backup", str(backup), str(tmp_path / "drill.sqlite3"))
    assert "systemctl" not in capsys.readouterr().out
