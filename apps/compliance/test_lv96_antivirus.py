"""LV-96: an antivirus that cannot run says so, instead of blaming the file.

Every non-zero exit used to raise the same "Antivirus scan rejected the uploaded
file", so a broken scanner and an infected document were indistinguishable on
screen. They are opposite problems: one is fixed by not uploading that file, the
other only by an administrator. The tests here pin the two apart, and pin that
the refusal itself does not change -- nothing is stored unscanned.

Text is asserted under `translation.override("en")` so these keep passing in the
Spanish interface (the source strings are the English msgids).
"""

import logging
import subprocess

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import translation

from apps.compliance import security
from apps.compliance.security import (
    ScannerUnavailable,
    UploadRejected,
    scan_uploaded_file,
)

PDF_BYTES = b"%PDF-1.4\nfor tests\n"


class _Result:
    def __init__(self, returncode, stderr=b""):
        self.returncode = returncode
        self.stderr = stderr
        self.stdout = b""


@pytest.fixture
def upload():
    return SimpleUploadedFile("policy.pdf", PDF_BYTES, content_type="application/pdf")


@pytest.fixture
def scanner(settings, monkeypatch):
    """A configured scanner whose exit code each test decides."""
    settings.DOCUMENTS_ANTIVIRUS_COMMAND = "clamscan"
    monkeypatch.setattr(security.shutil, "which", lambda _c: "/usr/bin/clamscan")

    def configure(returncode, stderr=b""):
        monkeypatch.setattr(
            security.subprocess,
            "run",
            lambda *a, **kw: _Result(returncode, stderr),
        )

    return configure


def test_no_scanner_configured_is_not_an_error(settings, upload):
    """Unchanged behaviour: without a command there is nothing to enforce."""
    settings.DOCUMENTS_ANTIVIRUS_COMMAND = ""

    assert scan_uploaded_file(upload) is None


def test_a_clean_file_passes(scanner, upload):
    scanner(security.SCANNER_CLEAN)

    assert scan_uploaded_file(upload) is None


def test_a_signature_match_blames_the_file(scanner, upload):
    scanner(security.SCANNER_INFECTED)

    with pytest.raises(UploadRejected) as caught:
        scan_uploaded_file(upload)

    with translation.override("en"):
        assert "threat" in str(caught.value)


def test_a_scanner_error_blames_the_server_not_the_file(scanner, upload):
    """Exit 2 is where a fresh ClamAV sits until `freshclam` has finished."""
    scanner(2, stderr=b"ERROR: Can't open file or directory")

    with pytest.raises(ScannerUnavailable) as caught:
        scan_uploaded_file(upload)

    with translation.override("en"):
        message = str(caught.value)
    assert "not a problem with your file" in message
    assert "threat" not in message


def test_the_two_verdicts_do_not_share_a_message(scanner, upload):
    """The point of the change, stated once as a single assertion."""
    with translation.override("en"):
        scanner(security.SCANNER_INFECTED)
        with pytest.raises(RuntimeError) as infected:
            scan_uploaded_file(upload)
        scanner(2)
        with pytest.raises(RuntimeError) as broken:
            scan_uploaded_file(upload)

        assert str(infected.value) != str(broken.value)


def test_a_scanner_error_is_logged_with_its_return_code(scanner, upload, caplog):
    """Without this, "the antivirus said no" is unfalsifiable after the fact."""
    scanner(2, stderr=b"ERROR: Can't open file or directory")

    with caplog.at_level(logging.ERROR), pytest.raises(ScannerUnavailable):
        scan_uploaded_file(upload)

    record = next(r for r in caplog.records if r.message == "antivirus_scan_failed")
    assert record.returncode == 2
    assert "Can't open file" in record.stderr


def test_a_missing_command_fails_closed_and_is_logged(
    settings, monkeypatch, upload, caplog
):
    settings.DOCUMENTS_ANTIVIRUS_COMMAND = "clamscan"
    monkeypatch.setattr(security.shutil, "which", lambda _c: None)

    with caplog.at_level(logging.ERROR), pytest.raises(ScannerUnavailable):
        scan_uploaded_file(upload)

    assert any(r.message == "antivirus_command_missing" for r in caplog.records)


def test_a_hung_scanner_does_not_hold_the_worker(settings, monkeypatch, upload):
    """No timeout means a page that never answers -- the least diagnosable
    failure this path can produce."""
    settings.DOCUMENTS_ANTIVIRUS_COMMAND = "clamscan"
    monkeypatch.setattr(security.shutil, "which", lambda _c: "/usr/bin/clamscan")

    def hang(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="clamscan", timeout=kwargs.get("timeout"))

    monkeypatch.setattr(security.subprocess, "run", hang)

    with pytest.raises(ScannerUnavailable):
        scan_uploaded_file(upload)


def test_the_timeout_is_actually_passed_to_the_scanner(settings, monkeypatch, upload):
    settings.DOCUMENTS_ANTIVIRUS_COMMAND = "clamscan"
    settings.DOCUMENTS_ANTIVIRUS_TIMEOUT = 7
    monkeypatch.setattr(security.shutil, "which", lambda _c: "/usr/bin/clamscan")
    seen = {}

    def record(*args, **kwargs):
        seen.update(kwargs)
        return _Result(security.SCANNER_CLEAN)

    monkeypatch.setattr(security.subprocess, "run", record)
    scan_uploaded_file(upload)

    assert seen["timeout"] == 7


def test_the_command_may_carry_arguments(settings, monkeypatch, upload):
    """LV-97: "clamdscan --fdpass" is one setting, not a name.

    `--fdpass` is what lets the daemon scan a 0600 temporary file it cannot
    open itself; without argument support the clamdscan decision cannot be
    configured at all. Only the first token goes through `shutil.which`.
    """
    settings.DOCUMENTS_ANTIVIRUS_COMMAND = "clamdscan --fdpass"
    resolved = {}
    monkeypatch.setattr(
        security.shutil,
        "which",
        lambda name: resolved.setdefault("name", name) and "/usr/bin/clamdscan",
    )
    seen = {}

    def record(argv, **kwargs):
        seen["argv"] = argv
        return _Result(security.SCANNER_CLEAN)

    monkeypatch.setattr(security.subprocess, "run", record)
    scan_uploaded_file(upload)

    assert resolved["name"] == "clamdscan"
    assert seen["argv"][:2] == ["/usr/bin/clamdscan", "--fdpass"]
    assert seen["argv"][2] == "--no-summary"


def test_the_file_can_still_be_read_after_a_scan(scanner, upload):
    """`upload_errors` reads the file after scanning it, so the position the
    scan consumed has to come back."""
    scanner(security.SCANNER_CLEAN)
    scan_uploaded_file(upload)

    upload.seek(0)
    assert upload.read() == PDF_BYTES


@pytest.mark.django_db
def test_the_upload_form_shows_the_server_message_not_the_infected_one(scanner, upload):
    """The whole point, seen from where the person actually reads it."""
    from apps.compliance.forms import upload_errors

    scanner(2)

    with translation.override("en"):
        errors = [str(error) for error in upload_errors(upload)]

    assert any("not a problem with your file" in error for error in errors)
