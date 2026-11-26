"""Readers of the documents that CLOSE a maintenance: certificate and report (LV-460).

The intake readers (`READERS`, `read_intake`) read what a workshop hands over when
it **receives** an aircraft; these read what it hands over when it **returns** it:
the maintenance certificate and the technical report. A separate registry because
the two answer different questions (an intake opens a record, a closure completes
it) and a document must never be read as the other kind.

Same contract as the intake readers: a reader only proposes, whatever it does not
understand stays `None`, and nothing here ever raises. To support another
workshop, add a reader with `matches`/`read` to `CLOSURE_READERS`.

Privacy: the documents carry the client's contact, phone, e-mail and RUT and the
technician's name. No reader keeps any of them: a proposal holds only the
workshop, the order, the aircraft and the dates, hours and verdict.
"""

import logging
from dataclasses import fields

from .base import CERTIFICATE, REPORT, ClosureProposal
from .heliboss import HelibossCertificateReader, HelibossReportReader

logger = logging.getLogger(__name__)

__all__ = [
    "CERTIFICATE",
    "CLOSURE_READERS",
    "REPORT",
    "ClosureProposal",
    "merge_closures",
    "read_closure",
]


def merge_closures(proposals):
    """One proposal from several documents of the same job, or `None`.

    The certificate goes first: it is the document that certifies, so its date of
    issue and its hours win over the report's. A field the first one lacks is
    taken from the next. `document_kind` and `reader` describe the first one.
    """
    ordered = sorted(
        (p for p in proposals if p is not None),
        key=lambda p: 0 if p.document_kind == CERTIFICATE else 1,
    )
    if not ordered:
        return None
    merged = ClosureProposal()
    for field in fields(ClosureProposal):
        for proposal in ordered:
            value = getattr(proposal, field.name)
            if value not in (None, ""):
                setattr(merged, field.name, value)
                break
    return merged


CLOSURE_READERS = [HelibossCertificateReader(), HelibossReportReader()]


def read_closure(text) -> ClosureProposal | None:
    """The proposal of the first closure reader that recognizes `text`, or `None`.

    Never raises: empty text, non-text or an unknown document all give `None`.
    """
    if not isinstance(text, str) or not text.strip():
        return None
    for reader in CLOSURE_READERS:
        try:
            if reader.matches(text):
                return reader.read(text)
        except Exception:  # noqa: BLE001 - a reader must never break the caller
            logger.info("closure_reader_failed", exc_info=True)
    return None
