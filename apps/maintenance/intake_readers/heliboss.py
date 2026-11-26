r"""Readers for the Heliboss (DJI Authorized Service Center) closure documents (LV-460).

Two documents close a Heliboss job:

* the **certificate** ("C E R T I F I C A D O"): label/value pairs (Fecha, NUI,
  Tipo, Modelo, "S/N AE"), the flight-hours block ("0 h 0 min 1 h 22 min ...":
  last record, current record, hours) and a paragraph that names the serial and
  the interval ("... 150 horas de vuelo o 6 meses ...");
* the **technical report** ("INFORME TECNICO DE MANTENCION"): "N° INFORME", "EQUIPO
  INSPECCIONADO DJI <model> / <serial>", the dates spelled out ("13 de noviembre de
  2026"), "Horas de vuelo" and "Veredicto".

The headings come letter-spaced ("D A T O S  D E  A E R O N A V E"), so every
heading is matched with `_spaced`, which allows whitespace between letters; the
labels the readers take values from are ordinary words. The text arrives as the
`pypdf` layout followed by the `pdfminer` one (`intake_text`), and the first match
wins; values are taken from the **same line** as their label (`[ \t]`, never a
newline), because in the `pdfminer` layout the next line after a label is often
another label's value.

Privacy: Contacto, Técnico, RUT, Teléfono and Correo are never read.
"""

import logging
import re
import unicodedata
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from apps.registry.models import normalize_serial

from .base import CERTIFICATE, REPORT, ClosureProposal

logger = logging.getLogger(__name__)

WORKSHOP = "Heliboss"

MONTHS = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}

_SAME_LINE = r"[ \t]*:?[ \t]*"
_NUMERIC_DATE = r"(\d{1,2})/(\d{1,2})/(\d{4})"
_WORDS_DATE = r"(\d{1,2})\s+de\s+([a-záéíóú]+)\s+(?:de|del)\s+(\d{4})"
_DURATION = re.compile(r"(\d{1,5})\s*h\s*(\d{1,2})\s*min", re.IGNORECASE)
_SERIAL = r"([A-Z0-9]{6,30})\b"


def _fold(text):
    plain = unicodedata.normalize("NFKD", text)
    return "".join(c for c in plain if not unicodedata.combining(c))


def _compact(text):
    """Lower-case, no accents, no whitespace: "C E R T I F I C A D O" -> "certificado"."""
    return re.sub(r"\s+", "", _fold(text)).casefold()


def _spaced(phrase):
    """A regex for `phrase` that also matches it letter-spaced and without accents."""
    words = []
    for word in _fold(phrase).split():
        words.append(r"\s*".join(re.escape(letter) for letter in word))
    return r"\s+".join(words)


def _search(pattern, text, flags=re.IGNORECASE):
    return re.search(pattern, text, flags)


def _day(day, month, year):
    try:
        return date(int(year), int(month), int(day))
    except (TypeError, ValueError):
        return None


def _date_after(label, text):
    """The date printed after `label` on the same line: dd/mm/yyyy or in words."""
    match = _search(label + _SAME_LINE + _NUMERIC_DATE, text)
    if match:
        return _day(*match.groups())
    match = _search(label + _SAME_LINE + _WORDS_DATE, text)
    if match:
        day, month_name, year = match.groups()
        month = MONTHS.get(_fold(month_name).casefold())
        return _day(day, month, year) if month else None
    return None


def _hours(hours, minutes):
    """'1 h 22 min' -> Decimal('1.4'): hours with one decimal, like `hours_at`."""
    total = Decimal(int(hours)) + Decimal(int(minutes)) / Decimal(60)
    return total.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def _line_value(label, text):
    match = _search(r"(?m)^[ \t]*" + label + r"[ \t]+(\S[^\n]*?)[ \t]*$", text)
    return match.group(1).strip() if match else None


def _kind_value(label, text):
    """The maintenance type after `label`, cut where a "Técnico ..." label begins:
    a layout that puts both on one line must not drag the technician's name along."""
    value = _line_value(label, text)
    if not value:
        return None
    value = re.split(r"\s+T\S{1,2}cnico\b", value, maxsplit=1, flags=re.IGNORECASE)[0]
    return value.strip()[:120] or None


def _interval(text):
    match = _search(r"(\d{1,4})\s+horas\s+de\s+vuelo\s+o\s+(\d{1,3})\s+meses", text)
    if not match:
        return None, None
    return int(match.group(1)), int(match.group(2))


def _serial(value):
    return normalize_serial(value) or None


class _HelibossReader:
    name = ""
    kind = ""

    def read(self, text):
        proposal = ClosureProposal(
            document_kind=self.kind, workshop_name=WORKSHOP, reader=self.name
        )
        for step in self.steps():
            try:
                step(text, proposal)
            except Exception:  # noqa: BLE001 - a field we cannot read stays None
                logger.info("heliboss_field_unreadable", exc_info=True)
        return proposal

    @staticmethod
    def _interval(text, proposal):
        proposal.interval_hours, proposal.interval_months = _interval(text)


class HelibossCertificateReader(_HelibossReader):
    """The one-page maintenance certificate."""

    name = "heliboss_certificate"
    kind = CERTIFICATE

    def matches(self, text):
        compact = _compact(text)
        return (
            "heliboss" in compact
            and "certificado" in compact
            and "informetecnicodemantencion" not in compact
        )

    def steps(self):
        return (
            self._order,
            self._issued,
            self._aircraft,
            self._hours,
            self._kind,
            self._interval,
        )

    @staticmethod
    def _order(text, proposal):
        # "NUI 1234" on the label line, or "NUI: 1234" in the quality stamp; never a
        # date that follows on the next line ("NUI\n\n24/11/2026").
        match = _search(r"\bNUI" + _SAME_LINE + r"(\d{2,})\b(?!/)", text)
        if match:
            proposal.workshop_order = match.group(1)

    @staticmethod
    def _issued(text, proposal):
        proposal.issued_on = _date_after(r"\bFecha", text)

    @staticmethod
    def _aircraft(text, proposal):
        serial = _search(r"S\s*/\s*N\s*AE" + _SAME_LINE + _SERIAL, text, 0)
        paragraph = _search(
            r"la\s+aeronave\s+(.+?),\s*con\s+n\S{0,2}mero\s+de\s+serie\s+" + _SERIAL,
            text,
        )
        if serial:
            proposal.serial_number = _serial(serial.group(1))
        elif paragraph:
            proposal.serial_number = _serial(paragraph.group(2))
        model = _line_value(r"Modelo", text)
        if not model and paragraph:
            model = re.sub(r"\s+", " ", paragraph.group(1)).strip()
        brand = _line_value(r"Marca", text)
        if model:
            label = f"{brand} {model}" if brand and brand not in model else model
            proposal.equipment_label = label[:150]

    @staticmethod
    def _hours(text, proposal):
        # The block prints three durations: last record, current record, hours. The
        # aircraft's hours are the current record (the second one).
        header = _search(_spaced("registro de horas de vuelo"), _fold(text))
        if not header:
            return
        window = _fold(text)[header.end() : header.end() + 400]
        durations = _DURATION.findall(window)
        if len(durations) >= 2:
            proposal.hours = _hours(*durations[1])
        elif durations:
            proposal.hours = _hours(*durations[0])

    @staticmethod
    def _kind(text, proposal):
        proposal.maintenance_kind = _kind_value(r"Tipo", text)


class HelibossReportReader(_HelibossReader):
    """The several-page technical report ("INFORME TECNICO DE MANTENCION")."""

    name = "heliboss_report"
    kind = REPORT

    def matches(self, text):
        compact = _compact(text)
        return "heliboss" in compact and "informetecnicodemantencion" in compact

    def steps(self):
        return (
            self._order,
            self._equipment,
            self._dates,
            self._hours,
            self._kind,
            self._verdict,
            self._interval,
        )

    @staticmethod
    def _order(text, proposal):
        match = _search(r"\bN\S{0,2}\s*INFORME" + _SAME_LINE + r"(\d{2,})\b", text)
        match = match or _search(r"\bNUI" + _SAME_LINE + r"(\d{2,})\b(?!/)", text)
        if match:
            proposal.workshop_order = match.group(1)

    @staticmethod
    def _equipment(text, proposal):
        match = _search(
            r"EQUIPO\s+INSPECCIONADO" + _SAME_LINE + r"([^\n/]+?)\s*/\s*" + _SERIAL,
            text,
        )
        if match:
            proposal.equipment_label = match.group(1).strip()[:150]
            proposal.serial_number = _serial(match.group(2))
            return
        serial = _search(r"N\S{0,2}\s*de\s+serie" + _SAME_LINE + _SERIAL, text)
        if serial:
            proposal.serial_number = _serial(serial.group(1))

    @staticmethod
    def _dates(text, proposal):
        proposal.issued_on = _date_after(r"FECHA\s+DEL\s+INFORME", text)
        proposal.received_on = _date_after(r"FECHA\s+DE\s+INGRESO", text)

    @staticmethod
    def _hours(text, proposal):
        match = _search(r"Horas\s+de\s+vuelo" + _SAME_LINE + _DURATION.pattern, text)
        if match:
            proposal.hours = _hours(*match.groups())

    @staticmethod
    def _kind(text, proposal):
        proposal.maintenance_kind = _kind_value(r"TIPO\s+DE\s+MANTENCI\S{1,2}N", text)

    @staticmethod
    def _verdict(text, proposal):
        # Upper-case words after "Veredicto"; "Estado del informe" stops it.
        match = re.search(r"Veredicto\s*:?\s*((?:[A-ZÁÉÍÓÚÑ]{2,}[ \t]?)+)", text)
        if match:
            proposal.verdict = match.group(1).strip()[:120]
