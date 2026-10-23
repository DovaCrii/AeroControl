"""PDF layer of the ENR 5.1 import (LV-361, phase 2).

The only module that touches the PDF. `pdfplumber` is imported lazily and is
not a required dependency: without it `read_pages` raises `PdfSupportMissing`.
The parser itself (`aip_parser`) never sees the file, only words with a
bounding box.
"""

import hashlib


class PdfSupportMissing(RuntimeError):
    """pdfplumber is not installed."""


def sha256_of(path):
    """Hex SHA-256 of a file, streamed (idempotence key of the import)."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_pages(source):
    """Pages of words ({text, x0, x1, top, bottom}) from a PDF path or file object."""
    try:
        import pdfplumber
    except ImportError as exc:
        raise PdfSupportMissing("pdfplumber is required to read the AIP PDF") from exc
    pages = []
    with pdfplumber.open(source) as pdf:
        for page in pdf.pages:
            pages.append(
                [
                    {key: word[key] for key in ("text", "x0", "x1", "top", "bottom")}
                    for word in page.extract_words()
                ]
            )
    return pages
