"""Corporate letterhead and executive styling for reportlab documents (LV-144).

Before this, the only PDF in the project (the compliance report) was built on a
bare ``getSampleStyleSheet()``: no logo, no footer, no page numbers, and a
navy that was not a brand colour. Nothing said "J.E.J." on a document meant to
be handed to a client or an auditor.

The furniture lives here rather than in the report that needed it first, so the
next report -- LV-145's fleet and personnel roster is already queued -- inherits
the identity instead of growing a second, slightly different one.

reportlab is imported at module scope; callers import *this* module lazily from
inside the view that renders, which is the convention the compliance report
already followed.
"""

from dataclasses import dataclass
from datetime import date
from io import BytesIO

from django.http import HttpResponse
from django.utils import timezone
from django.utils.translation import gettext as _
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, TableStyle

from . import branding

# -- Page geometry ----------------------------------------------------------
#
# Side margins keep the compliance report's existing 0.6in, so its wide tables
# do not have to be re-fitted. The top margin is the one that had to grow: the
# header band (logo plus rule) occupies roughly the first inch of every page,
# and text flowing under a logo is the classic way a letterhead retrofit
# announces itself.
SIDE_MARGIN = 0.6 * inch
TOP_MARGIN = 1.42 * inch
BOTTOM_MARGIN = 1.0 * inch

_HEADER_TOP = 0.5 * inch  # from the top edge to the top of the logo
_LOGO_WIDTH = 1.55 * inch
_RULE_GAP = 12  # between the logo's baseline and the brand rule
_FOOTER_RULE_Y = 0.75 * inch
_FOOTER_TEXT_Y = _FOOTER_RULE_Y - 11

# -- Urgency colours --------------------------------------------------------
#
# Keyed exactly on `apps.compliance.digest.bucket_for`, whose thresholds own
# this scale, and taking their values from the light-theme badge colours in
# `static/css/app.css` -- so a date that is amber on screen is amber on paper.
# `test_lv144_letterhead.py` asserts the key sets match: a new bucket in the
# digest turns the gate red instead of quietly printing in black.
#
# due_7 and due_15 share a colour on purpose, exactly as they do on screen
# (BUCKET_TEXT_CSS separates them by weight, not by hue) -- which is why the
# bold set below is a second table and not a synonym for "has a colour".
BUCKET_COLORS = {
    "overdue": "#A52834",
    "due_7": "#8A5A12",
    "due_15": "#8A5A12",
    "due_30": "#14707F",
    "later": "#384252",
}
BUCKET_BOLD = frozenset({"overdue", "due_7", "due_15"})


def derived_reference(prefix, on=None):
    """A traceable reference for a generated document.

    Explicitly **not** the corporate correlative: paper letters carry a
    ``J.E.J. N° 00x-26`` assigned by a person, and minting numbers into a
    series the company administers elsewhere would put two authorities on the
    same identifier. This is derived from the document kind and the date it was
    produced, and it is labelled as a reference so nobody files it as the
    other thing.
    """
    stamp = on or timezone.localdate()
    return _("Ref. %(prefix)s-%(stamp)s") % {
        "prefix": prefix,
        "stamp": stamp.strftime("%Y%m%d"),
    }


@dataclass(frozen=True)
class Letterhead:
    """What the furniture needs to know about the document it wraps.

    `title` is the running head from page 2 onwards and the PDF's own metadata
    title. It is *not* drawn on page 1: the document body already opens with
    its own heading there, and printing it twice on the first page is how a
    running head reads like a mistake.
    """

    title: str
    reference: str = ""
    generated_on: date | None = None

    @property
    def date_text(self):
        stamp = self.generated_on or timezone.localdate()
        return _("Generated: %(date)s") % {"date": stamp.isoformat()}

    def footer_texts(self, page, total):
        """The two footer strings, left and right.

        Returned rather than drawn straight onto the canvas so a test can
        assert on the exact text -- including that the total is the real page
        count -- without a PDF parser in the dependency list.
        """
        return (
            branding.FOOTER_LINE,
            _("Page %(page)s of %(total)s") % {"page": page, "total": total},
        )


class LetterheadCanvas(canvas.Canvas):
    """Draws the corporate furniture once the page count is known.

    reportlab's ``onFirstPage``/``onLaterPages`` hooks run *while* a page is
    being laid out, when the total page count does not exist yet -- so "Page X
    of **Y**" cannot be written from one. This defers the furniture and only
    the furniture: pages are laid out normally and their canvas state is kept,
    then the header and footer are painted in a second pass from ``save()``,
    which does know how many pages there were. Layout is untouched, so
    flowable splitting and table row repetition behave exactly as before.

    One ``ImageReader`` per document, held on the instance: reportlab keys its
    image cache on the reader it is handed, so a fresh reader per page would
    embed the same PNG once per page.
    """

    letterhead = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._page_states = []
        self._logo = _logo_reader()

    def showPage(self):  # noqa: N802 - reportlab's own casing
        self._page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._page_states)
        for number, state in enumerate(self._page_states, start=1):
            self.__dict__.update(state)
            self._draw_furniture(number, total)
            super().showPage()
        super().save()

    # -- furniture ----------------------------------------------------------

    def _draw_furniture(self, page, total):
        head = self.letterhead
        if head is None:  # a bare LetterheadCanvas: no furniture to draw
            return
        width, height = self._pagesize
        self.saveState()
        self._draw_header(head, page, width, height)
        self._draw_footer(head, page, total, width)
        self.restoreState()

    def _draw_header(self, head, page, width, height):
        top = height - _HEADER_TOP
        bottom = top

        if self._logo is not None:
            logo_width, logo_height = self._logo.getSize()
            drawn_height = _LOGO_WIDTH * logo_height / logo_width
            bottom = top - drawn_height
            self.drawImage(
                self._logo,
                SIDE_MARGIN,
                bottom,
                width=_LOGO_WIDTH,
                height=drawn_height,
                mask="auto",
            )
        else:
            # The asset is missing (someone pruned static/, or a deploy checked
            # out without it). The document keeps its identity in type rather
            # than losing the header altogether.
            self.setFont(branding.FONT_BOLD, 13)
            self.setFillColor(HexColor(branding.BLUE))
            self.drawString(SIDE_MARGIN, top - 13, branding.LEGAL_NAME)
            bottom = top - 13

        right = width - SIDE_MARGIN
        cursor = top - 4
        if head.reference:
            self.setFont(branding.FONT_BOLD, 8)
            self.setFillColor(HexColor(branding.BLUE))
            self.drawRightString(right, cursor, head.reference)
            cursor -= 11
        self.setFont(branding.FONT_REGULAR, 7.5)
        self.setFillColor(HexColor(branding.GRAY_DARK))
        self.drawRightString(right, cursor, head.date_text)
        if page > 1 and head.title:
            cursor -= 10
            self.drawRightString(right, cursor, head.title)

        rule_y = min(bottom, cursor) - _RULE_GAP
        self.setStrokeColor(HexColor(branding.BLUE))
        self.setLineWidth(1.2)
        self.line(SIDE_MARGIN, rule_y, right, rule_y)

    def _draw_footer(self, head, page, total, width):
        left_text, right_text = head.footer_texts(page, total)
        right = width - SIDE_MARGIN
        self.setStrokeColor(HexColor(branding.GRID_TINT))
        self.setLineWidth(0.5)
        self.line(SIDE_MARGIN, _FOOTER_RULE_Y, right, _FOOTER_RULE_Y)
        self.setFillColor(HexColor(branding.GRAY_DARK))
        self.setFont(branding.FONT_REGULAR, 6.5)
        self.drawString(SIDE_MARGIN, _FOOTER_TEXT_Y, left_text)
        self.setFont(branding.FONT_BOLD, 6.5)
        self.drawRightString(right, _FOOTER_TEXT_Y, right_text)


def make_canvasmaker(letterhead):
    """A canvas class bound to `letterhead`, for ``doc.build(canvasmaker=...)``.

    ``build()`` takes a class and instantiates it itself, so the letterhead
    cannot be passed as an argument; it is bound as a class attribute instead.
    """
    return type(
        "BoundLetterheadCanvas", (LetterheadCanvas,), {"letterhead": letterhead}
    )


def _logo_reader():
    path = branding.logo_path()
    if path is None:
        return None
    try:
        return ImageReader(str(path))
    except OSError:
        # A truncated or unreadable PNG is the missing-asset case, not a 500.
        return None


def executive_stylesheet():
    """reportlab's sample stylesheet, restyled to the brand.

    Built on the sample sheet rather than from scratch so that a document
    already written against ``Title`` / ``Normal`` / ``Heading2`` picks up the
    identity without a single content change -- which is what let the
    compliance report keep its wording, its tables and its ordering exactly as
    they were.
    """
    styles = getSampleStyleSheet()
    blue = HexColor(branding.BLUE)
    ink = HexColor(branding.GRAY_DARK)

    styles["Title"].fontName = branding.FONT_BOLD
    styles["Title"].fontSize = 17
    styles["Title"].leading = 21
    styles["Title"].alignment = 0  # left, under the logo, not centred
    styles["Title"].textColor = blue
    styles["Title"].spaceAfter = 4

    for name in ("Heading1", "Heading2", "Heading3"):
        styles[name].fontName = branding.FONT_BOLD
        styles[name].textColor = blue
    styles["Heading2"].fontSize = 11
    styles["Heading2"].leading = 14
    styles["Heading2"].spaceBefore = 12
    styles["Heading2"].spaceAfter = 5
    # LV-164: un encabezado nunca se queda solo al pie de una página. Es el
    # defecto que el usuario vio en el catastro el 2026-08-27 -- "Personal" al
    # final de la hoja y su tabla empezando en la siguiente-- y no se arregla con
    # un salto de página puesto a mano: reaparece en cuanto cambian las filas.
    # `keepWithNext` lo resuelve en el estilo, así que vale para los dos informes
    # y para el que venga.
    styles["Heading2"].keepWithNext = True
    styles["Heading1"].keepWithNext = True
    styles["Heading3"].keepWithNext = True

    for name in ("Normal", "BodyText"):
        styles[name].fontName = branding.FONT_REGULAR
        styles[name].fontSize = 9
        styles[name].leading = 12
        styles[name].textColor = ink

    styles.add(
        ParagraphStyle(
            "Cell",
            fontName=branding.FONT_REGULAR,
            fontSize=7.5,
            leading=9.5,
            textColor=ink,
        )
    )
    styles.add(
        ParagraphStyle(
            "CellHeader",
            parent=styles["Cell"],
            fontName=branding.FONT_BOLD,
            textColor=HexColor(branding.WHITE),
        )
    )
    styles.add(
        ParagraphStyle(
            "Muted",
            parent=styles["Normal"],
            fontSize=8,
            textColor=HexColor(branding.tint(branding.GRAY_DARK, 0.75)),
        )
    )
    return styles


def executive_table_style(extra=()):
    """The shared table look: brand-blue head, hairline grid, banded rows."""
    commands = [
        ("BACKGROUND", (0, 0), (-1, 0), HexColor(branding.BLUE)),
        ("TEXTCOLOR", (0, 0), (-1, 0), HexColor(branding.WHITE)),
        ("FONTNAME", (0, 0), (-1, 0), branding.FONT_BOLD),
        ("FONTNAME", (0, 1), (-1, -1), branding.FONT_REGULAR),
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("LEADING", (0, 0), (-1, -1), 9.5),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.4, HexColor(branding.GRID_TINT)),
        (
            "ROWBACKGROUNDS",
            (0, 1),
            (-1, -1),
            [HexColor(branding.WHITE), HexColor(branding.BAND_TINT)],
        ),
    ]
    commands.extend(extra)
    return TableStyle(commands)


def urgency_commands(ranges):
    """TableStyle commands tinting cell ranges by urgency bucket.

    `ranges` is an iterable of ``(bucket_key, from_cell, to_cell)`` triples in
    reportlab's own ``(column, row)`` coordinates -- the same shape a TableStyle
    command already takes. Range-driven rather than "tint column N of every
    row" on purpose: the compliance report tints four whole *columns*, one per
    bucket, while a listing of expiry dates would tint one date *column* row by
    row with a different bucket each time. Either orientation baked in here
    would have been rewritten by the second caller.

    An unknown or ``None`` key is skipped, so a row with no expiry date simply
    prints in the body colour instead of needing a sentinel entry in the table.
    """
    commands = []
    for key, start, end in ranges:
        color = BUCKET_COLORS.get(key)
        if color is None:
            continue
        commands.append(("TEXTCOLOR", start, end, HexColor(color)))
        if key in BUCKET_BOLD:
            commands.append(("FONTNAME", start, end, branding.FONT_BOLD))
    return commands


def build_pdf(elements, letterhead, pagesize=letter):
    """Render `elements` into PDF bytes wearing the corporate letterhead."""
    output = BytesIO()
    SimpleDocTemplate(
        output,
        pagesize=pagesize,
        leftMargin=SIDE_MARGIN,
        rightMargin=SIDE_MARGIN,
        topMargin=TOP_MARGIN,
        bottomMargin=BOTTOM_MARGIN,
        title=letterhead.title,
        author=branding.LEGAL_NAME,
        subject=letterhead.reference or letterhead.title,
    ).build(elements, canvasmaker=make_canvasmaker(letterhead))
    return output.getvalue()


def pdf_response(elements, letterhead, filename):
    """`build_pdf` as a download response."""
    response = HttpResponse(
        build_pdf(elements, letterhead), content_type="application/pdf"
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
