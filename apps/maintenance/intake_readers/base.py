"""Readers for workshop documents: reception and quote (LV-383, PR 2 and 2b of 4).

Each reader turns the text of a reception document into an `IntakeProposal`. They
only propose: whatever a reader does not understand stays `None`, and none of them
ever raises. The person confirms in the form (PR 3).
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol


@dataclass
class IntakeProposal:
    """What a reader found. Every field is optional; `None` means "not understood"."""

    workshop_name: str | None = None
    workshop_order: str | None = None
    received_at: datetime | None = None
    serial_number: str | None = None
    equipment_label: str | None = None
    accessories: str | None = None
    findings: str | None = None
    delivered_by: str | None = None
    # Quote of the workshop (PR 2b); amounts are whole Chilean pesos.
    quote_date: date | None = None
    quote_valid_until: date | None = None
    quote_net: int | None = None
    quote_vat: int | None = None
    quote_total: int | None = None
    quote_lead_time: str | None = None
    quote_warranty: str | None = None
    diagnosis: str | None = None
    reader: str | None = None


class IntakeReader(Protocol):
    """Contract of a reader: recognize a document and read it, never raising."""

    name: str

    def matches(self, text: str) -> bool: ...

    def read(self, text: str) -> IntakeProposal: ...
