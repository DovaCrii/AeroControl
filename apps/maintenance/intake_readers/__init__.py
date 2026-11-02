"""Registry of workshop reception readers and the entry point `read_intake`."""

import logging

from .base import IntakeProposal, IntakeReader
from .geocom import GeocomReader

logger = logging.getLogger(__name__)

READERS: list[IntakeReader] = [GeocomReader()]


def read_intake(text) -> IntakeProposal | None:
    """The proposal of the first reader that recognizes `text`, or `None`.

    Never raises: empty text, non-text or an unknown document all give `None`.
    """
    if not isinstance(text, str) or not text.strip():
        return None
    for reader in READERS:
        try:
            if reader.matches(text):
                return reader.read(text)
        except Exception:  # noqa: BLE001 - a reader must never break the caller
            logger.info("intake_reader_failed", exc_info=True)
    return None


__all__ = ["READERS", "IntakeProposal", "read_intake"]
