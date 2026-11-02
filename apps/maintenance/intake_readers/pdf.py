"""Text of a workshop document for the intake readers (LV-383, PR 2b).

Two extractors read different things right, so the text handed to the readers is
both, one after the other:

- `pypdf` (`apps.core.pdf_text.text_from_pdf`) keeps a label and its value on the
  same line ("Garantia: 30 dias", "NETO $ 511,191"), but it misses the pages whose
  text sits in form-like blocks (the quote's diagnosis and its "Resumen").
- `pdfminer.six` (MIT; used only here) does reach those pages, but it splits a
  label from its value into separate blocks.

The readers take the first match of every field, so the `pypdf` layout comes first
and the `pdfminer` text mainly contributes the diagnosis. If `pdfminer` fails or
returns almost nothing the `pypdf` text alone is used, and the other way round.
Never raises: when nothing can be read the answer is `None`.
"""

import io
import logging

from apps.core.pdf_text import text_from_pdf

logger = logging.getLogger(__name__)

MAX_PAGES = 12
MIN_CHARS = 40  # below this an extractor "returned too little" to be trusted


def _bytes_of(source) -> bytes | None:
    if isinstance(source, bytes | bytearray):
        return bytes(source)
    reader = getattr(source, "read", None)
    if reader is None:
        return None
    seek = getattr(source, "seek", None)
    if seek is not None:
        try:
            seek(0)
        except (OSError, ValueError):
            logger.info("intake_pdf_not_seekable")
    data = reader()
    return data if isinstance(data, bytes) else None


def _pdfminer_text(data: bytes) -> str | None:
    try:
        from pdfminer.high_level import extract_text

        text = extract_text(io.BytesIO(data), maxpages=MAX_PAGES)
    except Exception:  # noqa: BLE001 - an unreadable PDF is "no reading"
        logger.info("intake_pdfminer_unreadable", exc_info=True)
        return None
    return text if text and len(text.strip()) >= MIN_CHARS else None


def _pypdf_text(data: bytes) -> str | None:
    text = text_from_pdf(io.BytesIO(data), pages=MAX_PAGES)
    return text if text and len(text.strip()) >= MIN_CHARS else None


def intake_text(file_or_bytes) -> str | None:
    """The text of a workshop PDF (bytes or file-like), or `None`. Never raises."""
    try:
        data = _bytes_of(file_or_bytes)
    except Exception:  # noqa: BLE001 - reading the upload must not break the caller
        logger.info("intake_pdf_unreadable", exc_info=True)
        return None
    if not data:
        return None
    parts = [t for t in (_pypdf_text(data), _pdfminer_text(data)) if t]
    return "\n".join(parts) if parts else None
