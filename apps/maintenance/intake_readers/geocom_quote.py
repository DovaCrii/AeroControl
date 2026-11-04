r"""Reader for the Geocom quote ("COTIZACION" / "PROPUESTA COMERCIAL") (LV-383, PR 2b).

A team may go straight to the workshop, so the first document that arrives can be
the quote, which carries the diagnosis. As with the reception reader, the extracted
text has broken accented characters and line breaks between words: labels are
matched tolerantly (`\S{0,3}` stands for a possibly mangled accented letter).

Privacy: the quote also prints bank details, the workshop's RUT, e-mails and
contact names. None of them is read or kept: they are not fields of the proposal.
The serial is returned as read, upper-cased (ADR-0002: no O/0 normalization).
"""

import logging
import re
from datetime import date, timedelta

from .base import IntakeProposal
from .geocom import _TITLE as _RECEPTION_TITLE
from .geocom import _fold, _or_none, _squash

logger = logging.getLogger(__name__)

_FLAGS = re.IGNORECASE | re.DOTALL
_TITLE = re.compile(r"COTIZACI\S{0,3}N|PROPUESTA\s+COMERCIAL", _FLAGS)
# Workshop order: not preceded/followed by word characters or "@" (e-mails).
_ORDER = re.compile(r"(?<![\w@.])([A-Z]{2,8})\s*-\s*(\d+)(?![\w@])")
_ORDER_LABELED = re.compile(
    r"(?:\bOT\b|ORDEN\s+DE\s+TRABAJO)\s*(?:N\S{0,3})?\s*:?\s*"
    r"([A-Z]{2,8})\s*-\s*(\d+)(?![\w@])",
    re.IGNORECASE,
)
_SERIAL = re.compile(
    r"(?:N\S{0,3}\s*DE\s+)?SERIE\s*:?\s*((?=[A-Z0-9]*\d)[A-Z0-9]{6,})", _FLAGS
)
_SERIAL_TOKEN = r"((?=[A-Z0-9]*\d)[A-Z0-9]{8,})"
# Table row, which text extractors give on one line or as three blocks:
# "O.T EQUIPO SERIE <OT> <equipment> <serial>".
_TABLE_ROW = re.compile(
    r"\bO\s*\.?\s*T\s+EQUIPO\s+SERIE\s+([A-Z]{2,8})\s*-\s*(\d+)\s+(.{1,150}?)\s+"
    + _SERIAL_TOKEN,
    _FLAGS,
)
# "<equipment> SN <serial>" under "PROPUESTA COMERCIAL".
_SN_LINE = re.compile(
    r"PROPUESTA\s+COMERCIAL\s+(.{1,150}?)\s+SN\s+" + _SERIAL_TOKEN, _FLAGS
)
_EQUIPMENT = re.compile(
    r"\bEQUIPO\s*:\s*(.{1,150}?)\s+(?:N\S{0,3}\s*DE\s+)?SERIE\b", _FLAGS
)
_QUOTE_DATE = re.compile(r"Santiago\s*,\s*(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})", _FLAGS)
_VALIDITY = re.compile(
    r"Validez\s+de\s+la\s+Cotizaci\S{0,3}n\s*:?\s*(\d{1,4})\s*d\S{0,3}as", _FLAGS
)
# Thousands separated by ".", "," or a space; cents are not kept.
_AMOUNT = r"(\d+(?:[.,]\d{3})*(?:\s\d{3}(?!\d|[.,]\d))*)"
_MONEY_GAP = r"\s*:?\s*(?:CLP)?\s*\$?\s*"
_NET = re.compile(r"\bNeto\b" + _MONEY_GAP + _AMOUNT, _FLAGS)
_VAT = re.compile(r"\bIVA\b\s*(?:\(\s*\d+\s*%\s*\))?" + _MONEY_GAP + _AMOUNT, _FLAGS)
_TOTAL = re.compile(r"\bTotal\b" + _MONEY_GAP + _AMOUNT, _FLAGS)
_SUB_BEFORE = re.compile(r"Sub[\s.\-]*$", re.IGNORECASE)
_LEAD_TIME = re.compile(
    r"Plazo\s+de\s+entrega\s*:?\s*(?:de\s+)?(\d{1,3})\s*(d\S{0,3}as|semanas)"
    r"(?:\s+(h\S{0,3}biles|corridos|calendario))?",
    _FLAGS,
)
_WARRANTY = re.compile(
    r"Garant\S{0,3}a\s*:?\s*(?:de\s+)?(\d{1,3})\s*(d\S{0,3}as|meses)", _FLAGS
)
_SUMMARY_START = re.compile(
    r"^[ \t]*(?:4\s*\.\s*0\s*\.?\s*)?Resumen[ \t]*:?[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)
_SUMMARY_END = re.compile(
    r"\n\s*\d{1,2}\s*\.\s*\d\s+\S"  # next numbered section
    r"|\n[ \t]*\S+@\S+[ \t]*\|"  # page footer (e-mail | phone)
    r"|\n\s*(?:Neto|Sub\s*total|Validez|Condiciones|Forma\s+de\s+pago)\b",
    re.IGNORECASE,
)
# An item starts at a bullet glyph or after a blank line (wrapped lines stay together).
_PRIVATE_USE = re.compile(r"[\ue000-\uf8ff]")  # symbol-font bullets (U+F0B7)
_BULLET = re.compile(r"^[ \t]*[•·▪◦●■–*�\ue000-\uf8ff-][ \t]*", re.MULTILINE)
_BLANK_LINE = re.compile(r"\n[ \t\xa0]*\n")
SUMMARY_LIMIT = 1500


def _amount(match) -> int | None:
    if not match:
        return None
    digits = re.sub(r"\D", "", match.group(1))
    return int(digits) if digits else None


def _total(flat: str):
    """First "Total" that is not the tail of "Sub total" (LV-417)."""
    for match in _TOTAL.finditer(flat):
        if not _SUB_BEFORE.search(flat[: match.start()]):
            return match
    return None


def _days_label(number: str, unit: str) -> str:
    return f"{int(number)} " + ("semanas" if unit.lower() == "semanas" else "días")


def _quote_date(flat: str) -> date | None:
    match = _QUOTE_DATE.search(flat)
    if not match:
        return None
    day, month, year = (int(p) for p in match.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _summary(text: str) -> str | None:
    start = _SUMMARY_START.search(text)
    if not start:
        return None
    body = text[start.end() :]
    end = _SUMMARY_END.search(body)
    if end:
        body = body[: end.start()]
    items = []
    marked = _BLANK_LINE.sub("\n\x00", _BULLET.sub("\x00", "\n" + body))
    for chunk in marked.split("\x00"):
        item = _squash(_PRIVATE_USE.sub("", chunk))
        if item:
            items.append(item if item[-1] in ".:;!?" else item + ".")
    summary = " ".join(items)
    if len(summary) > SUMMARY_LIMIT:
        summary = summary[:SUMMARY_LIMIT].rsplit(" ", 1)[0].rstrip(",;:") + "…"
    return _or_none(summary)


class GeocomQuoteReader:
    name = "geocom_quote"

    def matches(self, text: str) -> bool:
        folded = _fold(text)
        return (
            bool(_TITLE.search(folded))
            and "geocom" in folded
            and not _RECEPTION_TITLE.search(folded)
        )

    def read(self, text: str) -> IntakeProposal:
        proposal = IntakeProposal(workshop_name="Geocom", reader=self.name)
        flat = _squash(text)
        steps = (
            lambda: self._equipment(flat, proposal),
            lambda: self._order(flat, proposal),
            lambda: self._dates(flat, proposal),
            lambda: self._amounts(flat, proposal),
            lambda: self._terms(flat, proposal),
            lambda: setattr(proposal, "diagnosis", _summary(text)),
        )
        for step in steps:
            try:
                step()
            except Exception:  # noqa: BLE001 - a field we cannot read stays None
                logger.info("geocom_quote_field_unreadable", exc_info=True)
        return proposal

    @staticmethod
    def _order(flat: str, proposal: IntakeProposal) -> None:
        match = _ORDER_LABELED.search(flat) or _ORDER.search(flat)
        if match and proposal.workshop_order is None:
            proposal.workshop_order = f"{match.group(1).upper()}-{match.group(2)}"

    @staticmethod
    def _equipment(flat: str, proposal: IntakeProposal) -> None:
        row = _TABLE_ROW.search(flat)
        if row:
            proposal.workshop_order = f"{row.group(1).upper()}-{row.group(2)}"
            proposal.equipment_label = _or_none(_squash(row.group(3)))
            proposal.serial_number = row.group(4).upper()
        sn_line = _SN_LINE.search(flat)
        if sn_line:
            if proposal.equipment_label is None:
                proposal.equipment_label = _or_none(_squash(sn_line.group(1)))
            if proposal.serial_number is None:
                proposal.serial_number = sn_line.group(2).upper()
        if proposal.serial_number is None:
            serial = _SERIAL.search(flat)
            if serial:
                proposal.serial_number = serial.group(1).upper()
        if proposal.equipment_label is None:
            equipment = _EQUIPMENT.search(flat)
            if equipment:
                proposal.equipment_label = _or_none(_squash(equipment.group(1)))

    @staticmethod
    def _dates(flat: str, proposal: IntakeProposal) -> None:
        proposal.quote_date = _quote_date(flat)
        validity = _VALIDITY.search(flat)
        if validity and proposal.quote_date:
            proposal.quote_valid_until = proposal.quote_date + timedelta(
                days=int(validity.group(1))
            )

    @staticmethod
    def _amounts(flat: str, proposal: IntakeProposal) -> None:
        proposal.quote_net = _amount(_NET.search(flat))
        proposal.quote_vat = _amount(_VAT.search(flat))
        total = _amount(_total(flat))
        # net + VAT that do not add up to the total (±1 peso): a wrong reading
        # is worse than an empty field, so the person types it.
        if (
            total is not None
            and proposal.quote_net is not None
            and proposal.quote_vat is not None
            and abs(proposal.quote_net + proposal.quote_vat - total) > 1
        ):
            total = None
        proposal.quote_total = total

    @staticmethod
    def _terms(flat: str, proposal: IntakeProposal) -> None:
        lead = _LEAD_TIME.search(flat)
        if lead:
            label = _days_label(lead.group(1), lead.group(2))
            suffix = (lead.group(3) or "").lower()
            if suffix.startswith("h"):
                label += " hábiles"
            elif suffix:
                label += " " + suffix
            proposal.quote_lead_time = label
        warranty = _WARRANTY.search(flat)
        if warranty:
            unit = "meses" if warranty.group(2).lower() == "meses" else "días"
            proposal.quote_warranty = f"{int(warranty.group(1))} {unit}"
