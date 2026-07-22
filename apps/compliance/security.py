import shutil
import subprocess
import tempfile
from pathlib import Path

from django.conf import settings


def scan_uploaded_file(uploaded):
    """Optionally scan an upload with a configured ClamAV-compatible command."""
    command = getattr(settings, "DOCUMENTS_ANTIVIRUS_COMMAND", "")
    if not command:
        return
    executable = shutil.which(command)
    if not executable:
        raise RuntimeError("Configured antivirus command is not available")
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
        result = subprocess.run(
            [executable, "--no-summary", temporary_path],
            capture_output=True,
            check=False,
        )
    finally:
        if temporary_path:
            Path(temporary_path).unlink(missing_ok=True)
        uploaded.seek(current_position)
    if result.returncode != 0:
        raise RuntimeError("Antivirus scan rejected the uploaded file")
