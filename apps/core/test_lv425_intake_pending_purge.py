"""LV-425: los PDF provisionales abandonados del ingreso se borran.

Todo en `tmp_path`; `DOCUMENTS_ROOT` apunta ahí. Los PDF son sintéticos.
"""

import os
import time
from io import StringIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import reverse

from apps.compliance.models import DocumentType
from apps.core import intake_pending
from apps.core.intake_pending import purge_stale_pending
from apps.core.models import JobRun
from apps.core.testing import login_as
from apps.maintenance.test_intake_views import reception_pdf
from apps.registry.test_lv405_operator_with_credential import LINES
from apps.registry.test_lv405_operator_with_credential import _pdf as credential_pdf

HOUR = 3600


@pytest.fixture
def root(settings, tmp_path):
    settings.DOCUMENTS_ROOT = str(tmp_path)
    return tmp_path


def _make(root, relative, age_hours):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"%PDF-1.4 sintetico")
    stamp = time.time() - age_hours * HOUR
    os.utime(path, (stamp, stamp))
    return path


def test_old_file_is_deleted_and_recent_one_stays(root):
    old = _make(root, "workshop-intake-pending/old.pdf", 30)
    recent = _make(root, "workshop-intake-pending/recent.pdf", 1)
    assert purge_stale_pending() == 1
    assert not old.exists()
    assert recent.exists()


def test_operator_credential_subfolder_is_covered(root):
    old = _make(root, "workshop-intake-pending/operator-credential/old.pdf", 48)
    fresh = _make(root, "workshop-intake-pending/operator-credential/new.pdf", 0.5)
    assert purge_stale_pending() == 1
    assert not old.exists() and fresh.exists()


def test_nothing_outside_the_prefix_is_touched(root):
    pending = _make(root, "workshop-intake-pending/old.pdf", 100)
    sibling = _make(root, "workshop-intake-pending-other/old.pdf", 100)
    definitive = _make(root, "documents/2026/old.pdf", 100)
    assert purge_stale_pending() == 1
    assert not pending.exists()
    assert sibling.exists() and definitive.exists()


def test_a_symlink_pointing_outside_is_not_followed(root, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside") / "secret.pdf"
    outside.write_bytes(b"x")
    os.utime(outside, (1, 1))
    link = root / "workshop-intake-pending" / "link.pdf"
    link.parent.mkdir(parents=True)
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not available")
    assert purge_stale_pending() == 0
    assert outside.exists()


def test_missing_folder_is_not_an_error(root):
    assert purge_stale_pending() == 0


def test_max_age_and_now_are_respected(root):
    path = _make(root, "workshop-intake-pending/a.pdf", 10)
    assert purge_stale_pending(max_age_hours=12) == 0
    assert purge_stale_pending(max_age_hours=12, now=time.time() + 5 * HOUR) == 1
    assert not path.exists()


@pytest.mark.django_db
def test_command_dry_run_reports_without_deleting(root):
    old = _make(root, "workshop-intake-pending/old.pdf", 30)
    out = StringIO()
    call_command("purge_intake_pending", "--dry-run", stdout=out)
    assert old.exists()
    assert "workshop-intake-pending/old.pdf" in out.getvalue()
    assert "1 file(s) would be deleted" in out.getvalue()
    assert not JobRun.objects.filter(command="purge_intake_pending").exists()


@pytest.mark.django_db
def test_command_deletes_records_a_job_run_and_honors_hours(root):
    path = _make(root, "workshop-intake-pending/a.pdf", 10)
    call_command("purge_intake_pending", "--hours", "12", stdout=StringIO())
    assert path.exists()
    call_command("purge_intake_pending", "--hours", "6", stdout=StringIO())
    assert not path.exists()
    run = JobRun.objects.filter(command="purge_intake_pending").first()
    assert run.result == JobRun.RESULT_OK
    assert "1 file(s) removed" in run.summary


@pytest.mark.django_db
def test_command_rejects_a_non_positive_threshold(root):
    with pytest.raises(CommandError):
        call_command("purge_intake_pending", "--hours", "0", stdout=StringIO())


def test_purge_failure_never_propagates(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("disk gone")

    monkeypatch.setattr(intake_pending, "purge_stale_pending", boom)
    intake_pending.purge_stale_pending_safely()  # no lanza


# --- las dos vistas de subida ---------------------------------------------


@pytest.fixture
def workshop_upload(root):
    client = login_as("add_maintenancerecord", "add_document")

    def go():
        return client.post(
            reverse("maintenance-intake-new"),
            {
                "file": SimpleUploadedFile(
                    "t.pdf", reception_pdf(), content_type="application/pdf"
                )
            },
        )

    return go


@pytest.fixture
def operator_upload(root, db):
    DocumentType.objects.get_or_create(
        code="dgac-credential",
        defaults={"name": "Credencial DGAC", "requires_expiry": True},
    )
    client = login_as("add_operator", "add_document", "view_operator")

    def go():
        return client.post(
            reverse("operator-credential-intake"),
            {
                "file": SimpleUploadedFile(
                    "c.pdf", credential_pdf(LINES), content_type="application/pdf"
                )
            },
        )

    return go


@pytest.mark.django_db
@pytest.mark.parametrize("fixture_name", ["workshop_upload", "operator_upload"])
def test_an_upload_triggers_the_purge_and_sweeps_old_files(request, root, fixture_name):
    go = request.getfixturevalue(fixture_name)
    old = _make(root, "workshop-intake-pending/abandoned.pdf", 40)
    response = go()
    assert response.status_code in (200, 302)
    assert not old.exists()
    # el PDF recién subido sí queda
    assert list((root / "workshop-intake-pending").rglob("*.pdf"))


@pytest.mark.django_db
@pytest.mark.parametrize("fixture_name", ["workshop_upload", "operator_upload"])
def test_a_failing_purge_does_not_break_the_upload(request, monkeypatch, fixture_name):
    go = request.getfixturevalue(fixture_name)

    def boom(*args, **kwargs):
        raise RuntimeError("purge exploded")

    monkeypatch.setattr(intake_pending, "purge_stale_pending", boom)
    response = go()
    assert response.status_code in (200, 302)
    root = request.getfixturevalue("root")
    assert list(root.rglob("*.pdf"))


@pytest.mark.django_db
@pytest.mark.parametrize("fixture_name", ["workshop_upload", "operator_upload"])
def test_an_upload_calls_the_purge_once(request, monkeypatch, fixture_name):
    go = request.getfixturevalue(fixture_name)
    calls = []
    monkeypatch.setattr(
        intake_pending, "purge_stale_pending", lambda *a, **k: calls.append(1)
    )
    go()
    assert calls == [1]
