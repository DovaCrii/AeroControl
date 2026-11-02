"""Registry of workshop document readers (reception and quote) and the entry point `read_intake`."""

import logging

from .base import IntakeProposal, IntakeReader
from .geocom import GeocomReader
from .geocom_quote import GeocomQuoteReader

logger = logging.getLogger(__name__)

READERS: list[IntakeReader] = [GeocomReader(), GeocomQuoteReader()]


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
