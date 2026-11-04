"""LV-401: los PDF de `DOCUMENTS_ROOT` tienen respaldo, y la carpeta de
respaldos no crece sin fin.

`backup` sólo copiaba la base: en la VM los documentos firmados no se
respaldaban y nada borraba respaldos viejos.
"""

import hashlib
import json
import tarfile

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.core.backups import (
    DB_PATTERN,
    DOCS_PATTERN,
    apply_retention,
    docs_manifest_path,
    latest_backup,
)
from apps.core.models import JobRun


@pytest.fixture
def folders(tmp_path, settings, monkeypatch):
    docs = tmp_path / "docs"
    (docs / "permits").mkdir(parents=True)
    (docs / "permits" / "a.pdf").write_bytes(b"%PDF-a")
    (docs / "b.pdf").write_bytes(b"%PDF-bb")
    (docs / "workshop-intake-pending").mkdir()
    (docs / "workshop-intake-pending" / "pending.pdf").write_bytes(b"%PDF-pending")
    backups = tmp_path / "backups"
    settings.DOCUMENTS_ROOT = docs
    monkeypatch.setenv("BACKUPS_DIR", str(backups))
    return docs, backups


def _fake(directory, stem, suffix, manifest=True, extra=None):
    """Un respaldo falso con nombre de fecha `stem`."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{stem}{suffix}"
    path.write_bytes(b"x")
    if manifest:
        meta = {"backup": path.name, "sha256": "0" * 64, **(extra or {})}
        target = (
            docs_manifest_path(path)
            if suffix == ".tar.gz"
            else path.with_suffix(".json")
        )
        target.write_text(json.dumps(meta), encoding="utf-8")
    return path


@pytest.mark.django_db
def test_tar_has_the_pdfs_but_not_the_pending_intake(folders):
    docs, backups = folders
    call_command("backup_documents")

    (archive,) = backups.glob(DOCS_PATTERN)
    with tarfile.open(archive) as tar:
        names = tar.getnames()
    assert "permits/a.pdf" in names
    assert "b.pdf" in names
    assert not any("workshop-intake-pending" in name for name in names)


@pytest.mark.django_db
def test_manifest_matches_the_tar(folders):
    docs, backups = folders
    call_command("backup_documents")

    (archive,) = backups.glob(DOCS_PATTERN)
    manifest = json.loads(docs_manifest_path(archive).read_text(encoding="utf-8"))
    assert manifest["backup"] == archive.name
    assert manifest["files"] == 2
    assert manifest["bytes"] == len(b"%PDF-a") + len(b"%PDF-bb")
    assert manifest["size"] == archive.stat().st_size
    assert manifest["sha256"] == hashlib.sha256(archive.read_bytes()).hexdigest()
    assert manifest["created_at"]
    run = JobRun.objects.get(command="backup_documents")
    assert run.result == JobRun.RESULT_OK


@pytest.mark.django_db
def test_missing_documents_folder_is_a_clear_error(folders, settings, tmp_path):
    settings.DOCUMENTS_ROOT = tmp_path / "nope"

    with pytest.raises(CommandError, match="Documents folder not found"):
        call_command("backup_documents")

    assert JobRun.objects.get(command="backup_documents").result == (
        JobRun.RESULT_ERROR
    )


@pytest.mark.django_db
def test_keep_must_be_positive(folders):
    with pytest.raises(CommandError, match="at least 1"):
        call_command("backup_documents", keep=0)


@pytest.mark.django_db
def test_keep_3_leaves_the_last_three_with_their_manifests(folders):
    _, backups = folders
    for day in range(1, 6):
        _fake(backups, f"aero_docs_2020010{day}_020000", ".tar.gz")

    call_command("backup_documents", keep=3)

    # 5 viejos + 1 nuevo, quedan los 3 más recientes (el nuevo y dos viejos).
    kept = sorted(p.name for p in backups.glob(DOCS_PATTERN))
    assert kept[:2] == [
        "aero_docs_20200104_020000.tar.gz",
        "aero_docs_20200105_020000.tar.gz",
    ]
    assert len(kept) == 3
    assert len(list(backups.glob("aero_docs_*.json"))) == 3


def test_retention_leaves_exactly_the_last_n_pairs(tmp_path):
    for day in range(1, 6):
        _fake(tmp_path, f"aero_docs_2026110{day}_020000", ".tar.gz")

    removed = apply_retention(tmp_path, DOCS_PATTERN, 3)

    assert len(removed) == 2
    assert sorted(p.name for p in tmp_path.glob("*.tar.gz")) == [
        f"aero_docs_2026110{day}_020000.tar.gz" for day in (3, 4, 5)
    ]
    assert sorted(p.name for p in tmp_path.glob("*.json")) == [
        f"aero_docs_2026110{day}_020000.json" for day in (3, 4, 5)
    ]


def test_a_backup_without_manifest_is_not_deleted(tmp_path):
    old = _fake(tmp_path, "aero_docs_20261101_020000", ".tar.gz", manifest=False)
    _fake(tmp_path, "aero_docs_20261102_020000", ".tar.gz")
    _fake(tmp_path, "aero_docs_20261103_020000", ".tar.gz")

    removed = apply_retention(tmp_path, DOCS_PATTERN, 1)

    assert old.exists()
    assert removed == ["aero_docs_20261102_020000.tar.gz"]


def test_a_manifest_naming_another_file_does_not_count(tmp_path):
    old = _fake(tmp_path, "aero_docs_20261101_020000", ".tar.gz")
    docs_manifest_path(old).write_text(
        json.dumps({"backup": "otro.tar.gz", "sha256": "0"}), encoding="utf-8"
    )
    _fake(tmp_path, "aero_docs_20261102_020000", ".tar.gz")

    assert apply_retention(tmp_path, DOCS_PATTERN, 1) == []
    assert old.exists()


def test_the_newest_is_never_deleted_even_with_keep_zero(tmp_path):
    _fake(tmp_path, "aero_docs_20261101_020000", ".tar.gz")
    newest = _fake(tmp_path, "aero_docs_20261102_020000", ".tar.gz")

    apply_retention(tmp_path, DOCS_PATTERN, 0)

    assert newest.exists()
    assert docs_manifest_path(newest).exists()


def test_retention_only_touches_its_own_pattern(tmp_path):
    stranger = tmp_path / "notes.sqlite3"
    stranger.write_bytes(b"x")
    db = _fake(tmp_path, "aero_ops_20261101_020000", ".sqlite3")
    _fake(tmp_path, "aero_docs_20261101_020000", ".tar.gz")
    _fake(tmp_path, "aero_docs_20261102_020000", ".tar.gz")

    apply_retention(tmp_path, DOCS_PATTERN, 1)

    assert stranger.exists()
    assert db.exists()


def test_database_backups_are_pruned_by_count(tmp_path):
    for day in range(1, 5):
        _fake(tmp_path, f"aero_ops_2026110{day}_020000", ".sqlite3")

    removed = apply_retention(tmp_path, DB_PATTERN, 2)

    assert len(removed) == 2
    assert len(list(tmp_path.glob("*.sqlite3"))) == 2
    assert len(list(tmp_path.glob("*.json"))) == 2


@pytest.mark.django_db
def test_verify_does_not_pick_up_the_documents_manifest(folders):
    _, backups = folders
    _fake(backups, "aero_ops_20261101_020000", ".sqlite3")
    call_command("backup_documents")  # el manifiesto de documentos es más nuevo

    assert latest_backup()["name"] == "aero_ops_20261101_020000.sqlite3"
