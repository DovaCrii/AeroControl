"""Antivirus gate for uploaded files.

**Fails closed on purpose**: when a scanner is configured but cannot give a
verdict, the upload is refused rather than stored unscanned. See
docs/dev/pendientes-usuario-2026-08-13.md.

What LV-96 changed is *what the person is told*. Every non-zero exit used to
produce one message -- "Antivirus scan rejected the uploaded file" -- so a
scanner that could not run at all (missing signature database, unreadable
temporary file, out of memory) accused the **document** of being infected. Those
are opposite problems: one is fixed by not uploading that file, the other only by
an administrator, and the person retrying with a different PDF has no way to tell
which they are in. The two exits are now two exceptions with two messages, and
the scanner failure is logged with its return code so the answer is in
`aero_ops.log` instead of in somebody's memory.
"""

import logging
import shutil

# Used only for the shell-free antivirus call in scan_uploaded_file below.
import subprocess  # nosec B404
import tempfile
from pathlib import Path

from django.conf import settings
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)

# ClamAV's contract (clamscan and clamdscan share it): 0 clean, 1 a signature
# matched, anything else means the scan itself failed.
SCANNER_CLEAN = 0
SCANNER_INFECTED = 1


class UploadRejected(RuntimeError):
    """A signature matched: the file is the problem."""


class ScannerUnavailable(RuntimeError):
    """No verdict could be obtained: the scanner is the problem.

    Still refuses the upload -- the guarantee is "nothing is stored unscanned",
    not "nothing infected is stored" -- but says so in those words, because the
    person holding the file cannot fix this one.
    """


def scan_uploaded_file(uploaded):
    """Scan an upload with the configured ClamAV-compatible command.

    Returns None when it is clean or when no scanner is configured. Raises
    `UploadRejected` or `ScannerUnavailable`, both `RuntimeError`, so the three
    call sites that already catch `RuntimeError` keep working unchanged.
    """
    command = getattr(settings, "DOCUMENTS_ANTIVIRUS_COMMAND", "")
    if not command:
        return
    executable = shutil.which(command)
    if not executable:
        logger.error("antivirus_command_missing", extra={"command": command})
        raise ScannerUnavailable(
            _(
                "This file could not be checked for viruses because the "
                "antivirus is unavailable, so it was not saved. This is a server "
                "problem, not a problem with your file: tell an administrator."
            )
        )
    current_position = uploaded.tell()
    uploaded.seek(0)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            suffix=Path(uploaded.name).suffix, delete=False
        ) as temporary:
            temporary_path = temporary.name
            for chunk in uploaded.chunks():
                temporary.write(chunk)
        # executable is resolved by shutil.which() from the trusted
        # DOCUMENTS_ANTIVIRUS_COMMAND setting; args are a fixed list and there is
        # no shell, so there is no untrusted-input execution path.
        #
        # The timeout is not optional: `clamscan` reloads the whole signature
        # database on every call, and a scanner that hangs would hold this
        # worker until the proxy gives up -- which the person sees as a page
        # that never answers, the least diagnosable failure of all.
        result = subprocess.run(  # nosec B603
            [executable, "--no-summary", temporary_path],
            capture_output=True,
            check=False,
            timeout=getattr(settings, "DOCUMENTS_ANTIVIRUS_TIMEOUT", 120),
        )
    except subprocess.TimeoutExpired:
        logger.error("antivirus_scan_timeout", extra={"command": command})
        raise ScannerUnavailable(
            _(
                "The virus check took too long, so this file was not saved. This "
                "is a server problem, not a problem with your file: tell an "
                "administrator."
            )
        ) from None
    finally:
        if temporary_path:
            Path(temporary_path).unlink(missing_ok=True)
        uploaded.seek(current_position)

    if result.returncode == SCANNER_CLEAN:
        return
    if result.returncode == SCANNER_INFECTED:
        raise UploadRejected(
            _("The antivirus found a threat in this file, so it was not saved.")
        )
    # Everything else is the scanner failing. The return code and the tail of
    # stderr go to the log -- without them "the antivirus said no" is
    # unfalsifiable, and this is exactly the state a fresh ClamAV install sits
    # in until `freshclam` has finished downloading its database.
    logger.error(
        "antivirus_scan_failed",
        extra={
            "command": command,
            "returncode": result.returncode,
            "stderr": result.stderr.decode("utf-8", "replace")[-500:].strip(),
        },
    )
    raise ScannerUnavailable(
        _(
            "This file could not be checked for viruses, so it was not saved. "
            "This is a server problem, not a problem with your file: tell an "
            "administrator."
        )
    )
