r"""Reader for the Geocom "DOCUMENTO DE RECEPCION DE EQUIPOS" (LV-383, PR 2).

The extracted text of the real document has broken accented characters and line
breaks between words, so every label is matched tolerantly (`\S{0,3}` stands for a
possibly mangled accented letter) and nothing depends on accents.

Privacy: the RUT printed next to "ENTREGADOS POR" is never kept, only the name.
Serial numbers are returned exactly as read, upper-cased and without spaces
(ADR-0002: exact match, no O/0 normalization).
"""

import logging
import re
import unicodedata
from datetime import datetime
from zoneinfo import ZoneInfo

from .base import IntakeProposal

logger = logging.getLogger(__name__)
SANTIAGO = ZoneInfo("America/Santiago")

_FLAGS = re.IGNORECASE | re.DOTALL
_TITLE = re.compile(r"DOCUMENTO\s+DE\s+RECEPCI\S{0,3}N\s+DE\s+EQUIPOS", _FLAGS)
_RUT = re.compile(r"\b\d{1,2}(?:\.\d{3}){2}\s*-\s*[\dkK]\b|\b\d{7,8}\s*-\s*[\dkK]\b")
_ROW = re.compile(
    r"EQUIPOS\s+RECEPCI\S{0,3}NADOS.*?\b\d+\s+([A-Z]{2,8}-\d+)\s+(.+?)\s+([A-Z0-9]{8,})\b",
    _FLAGS,
)
_RECEIVED = re.compile(
    r"Fecha\s*:\s*(\d{1,2})/(\d{1,2})/(\d{4})\s+(\d{1,2}):(\d{2}):(\d{2})", _FLAGS
)
_INSTRUMENT = re.compile(r"INFORMACI\S{0,3}N\s+DEL\s+INSTRUMENTO\s*:?(.*)", _FLAGS)
_SERIAL_LABEL = r"N\S{0,3}\s*DE\s+SERIE"
_FIELD_SERIAL = re.compile(_SERIAL_LABEL + r"\s*:?\s*([A-Z0-9]+)", _FLAGS)
_FIELD_EQUIPMENT = re.compile(r"\bEQUIPO\s*:?\s*(.+?)\s+" + _SERIAL_LABEL, _FLAGS)
_ACCESSORIES = re.compile(
    r"ACCESORIOS\s*:?\s*(.*?)\s*(?:\d\s*\.\s*)?OBSERVACIONES\s*:", _FLAGS
)
# Findings end where the boilerplate of the page begins (CONSIDERACIONES, the page
# counter or the footer e-mail); otherwise they would drag the next section along.
_FINDINGS = re.compile(
    r"OBSERVACIONES\s*:\s*(.*?)"
    r"(?=\s*(?:\d\s*\.\s*)?CONSIDERACIONES\b|\s*PAG\s+\d+\s*/\s*\d+|\s+\S+@\S+|\s+DOCUMENTO\s+DE\s+RECEPCI|\Z)",
    _FLAGS,
)
_ORDER_LABELED = re.compile(r"\bOT\s*:?\s*([A-Z]{2,8})\s*-\s*(\d+)\b", re.DOTALL)
_DELIVERED = re.compile(r"ENTREGADOS\s+POR\s*:\s*(.+)", _FLAGS)


def _fold(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text)
    return "".join(c for c in plain if not unicodedata.combining(c)).casefold()


def _squash(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("�", "?")).strip()


def _or_none(value):
    return value or None


def _delivered_by(text: str) -> str | None:
    match = _DELIVERED.search(text)
    if not match:
        return None
    rest = match.group(1)
    rut = _RUT.search(rest[:300])
    chunk = rest[: rut.start()] if rut else rest.split("\n")[0]
    name = _squash(re.sub(r"\bRUT\s*:?\s*$", "", _squash(chunk), flags=re.IGNORECASE))
    if not name or any(c.isdigit() for c in name) or len(name.split()) > 6:
        return None
    return name[:150]


def _received_at(text: str) -> datetime | None:
    match = _RECEIVED.search(text)
    if not match:
        return None
    day, month, year, hour, minute, second = (int(p) for p in match.groups())
    try:
        return datetime(year, month, day, hour, minute, second, tzinfo=SANTIAGO)
    except ValueError:
        return None


class GeocomReader:
    name = "geocom"

    def matches(self, text: str) -> bool:
        folded = _fold(text)
        return bool(_TITLE.search(folded)) and "geocom" in folded

    def read(self, text: str) -> IntakeProposal:
        proposal = IntakeProposal(workshop_name="Geocom", reader=self.name)
        flat = _squash(text)
        steps = (
            lambda: setattr(proposal, "delivered_by", _delivered_by(text)),
            lambda: setattr(proposal, "received_at", _received_at(flat)),
            lambda: self._equipment(flat, proposal),
            lambda: self._instrument(flat, proposal),
        )
        for step in steps:
            try:
                step()
            except Exception:  # noqa: BLE001 - a field we cannot read stays None
                logger.info("geocom_field_unreadable", exc_info=True)
        return proposal

    @staticmethod
    def _equipment(flat: str, proposal: IntakeProposal) -> None:
        row = _ROW.search(flat)
        if row:
            proposal.workshop_order = row.group(1).upper()
            proposal.equipment_label = _or_none(_squash(row.group(2)))
            proposal.serial_number = row.group(3).upper()
        elif (labeled := _ORDER_LABELED.search(flat)) is not None:
            # Another extractor gives the equipment before the OT, so no row matches.
            proposal.workshop_order = f"{labeled.group(1).upper()}-{labeled.group(2)}"

    @staticmethod
    def _instrument(flat: str, proposal: IntakeProposal) -> None:
        section = _INSTRUMENT.search(flat)
        if not section:
            return
        body = section.group(1)
        serial = _FIELD_SERIAL.search(body)
        if serial:
            proposal.serial_number = serial.group(1).upper()
        equipment = _FIELD_EQUIPMENT.search(body)
        if equipment:
            proposal.equipment_label = _or_none(_squash(equipment.group(1)))
        accessories = _ACCESSORIES.search(body)
        if accessories:
            proposal.accessories = _or_none(_squash(accessories.group(1)))
        findings = _FINDINGS.search(body)
        if findings:
            proposal.findings = _or_none(_squash(findings.group(1)))
