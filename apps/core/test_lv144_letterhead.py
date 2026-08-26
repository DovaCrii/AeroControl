"""LV-144: the corporate letterhead for generated PDFs.

No PDF parser is used anywhere here, and none is added to the dependency list
for it: reportlab compresses page content streams, so the drawn text is *not*
greppable in the output bytes -- an assertion like `b"Page 1 of 3" in pdf` looks
right and passes vacuously for the wrong reason. What is asserted instead is
the seam (the strings the letterhead hands the canvas, and the page count it is
handed back), the PDF's own metadata, which is not compressed, and the magic
bytes.
"""

import pytest
from django.utils.translation import override
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Table

from . import branding, pdf


@pytest.fixture
def head():
    from datetime import date

    return pdf.Letterhead(
        title="AeroControl — Test report",
        reference="Ref. TST-20260826",
        generated_on=date(2026, 8, 26),
    )


def _three_page_story(styles):
    """Exactly three pages, by explicit page breaks rather than by filling
    them: a story that happens to overflow is a test that changes its own
    page count the day a font metric or a margin moves."""
    return [
        Paragraph("First", styles["Title"]),
        PageBreak(),
        Paragraph("Second", styles["Title"]),
        PageBreak(),
        Paragraph("Third", styles["Title"]),
    ]


# -- the brand's own numbers ------------------------------------------------


def test_the_palette_is_the_brand_manuals():
    """Frozen against section 3.5 of the manual the user supplied. These are
    not preferences to be tidied: #1E418C is PANTONE 661 C, the logo's blue."""
    assert branding.BLUE == "#1E418C"
    assert branding.CYAN == "#60C4F5"
    assert branding.GRAY_DARK == "#4D4D4D"
    assert branding.GRAY_LIGHT == "#B3B3B3"
    assert branding.WHITE == "#FFFFFF"


def test_the_typefaces_are_base14_so_nothing_has_to_be_embedded():
    """The manual specifies Helvetica; the reason it suits a PDF is that all
    three faces used are reportlab base-14, so no font file ships or is
    licensed. A face outside that set would need embedding and would fail on
    the VM, not here."""
    from reportlab.pdfbase.pdfmetrics import getFont

    for face in (branding.FONT_REGULAR, branding.FONT_BOLD, branding.FONT_ITALIC):
        assert getFont(face) is not None


def test_the_off_brand_navy_is_gone_from_the_compliance_report():
    """The report used to paint its table heads #1b2a4a, which is not a brand
    colour and was never in the manual."""
    from pathlib import Path

    from django.conf import settings

    source = (
        Path(settings.BASE_DIR) / "apps" / "compliance" / "report_views.py"
    ).read_text(encoding="utf-8")

    assert "#1b2a4a" not in source
    assert "getSampleStyleSheet" not in source


def test_tint_mixes_a_brand_colour_toward_white():
    assert branding.tint(branding.BLUE, 1.0) == branding.BLUE
    assert branding.tint(branding.BLUE, 0.0) == "#FFFFFF"
    # Halfway between #B3B3B3 and white.
    assert branding.tint(branding.GRAY_LIGHT, 0.5) == "#D9D9D9"
    # The two shades the reports use are derived, not invented beside the five.
    assert branding.GRID_TINT == branding.tint(branding.GRAY_LIGHT, 0.55)
    assert branding.BAND_TINT == branding.tint(branding.GRAY_LIGHT, 0.14)


@pytest.mark.parametrize("strength", [-0.1, 1.1])
def test_tint_refuses_a_strength_outside_the_range(strength):
    with pytest.raises(ValueError):
        branding.tint(branding.BLUE, strength)


# -- the logo asset --------------------------------------------------------


def test_the_logo_is_on_disk_and_is_a_png():
    branding.logo_path.cache_clear()
    path = branding.logo_path()

    assert path is not None, "static/img/jej-logo-blue.png is missing"
    assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_the_logo_is_read_from_disk_and_never_through_a_url():
    """In production STORAGES hashes static names, so the asset does not exist
    in STATIC_ROOT under its source name and a URL would additionally need the
    app to serve its own request while rendering it. This pins the mechanism,
    because the failure only shows up in production."""
    from pathlib import Path

    source = Path(branding.__file__).read_text(encoding="utf-8")
    code = "\n".join(
        line for line in source.splitlines() if not line.strip().startswith("#")
    )

    assert "finders.find" in code
    assert "staticfiles_storage" not in code
    assert "http" not in code.split('"""')[-1]


def test_a_missing_logo_costs_the_letterhead_its_image_and_nothing_else(
    head, monkeypatch
):
    """A pruned static dir, or a deploy checked out without the asset, must not
    turn a compliance report into a 500. The header falls back to the legal
    name set in type."""
    monkeypatch.setattr(branding, "logo_path", lambda: None)

    data = pdf.build_pdf(_three_page_story(pdf.executive_stylesheet()), head)

    assert data[:5] == b"%PDF-"
    assert data.count(b"/Subtype /Image") == 0


# -- the furniture ---------------------------------------------------------


def test_the_page_total_in_the_footer_is_the_real_page_count(head):
    """The whole reason this uses a canvasmaker instead of reportlab's
    onFirstPage/onLaterPages hooks: those run while a page is being laid out,
    when the total does not exist yet, so "of Y" could only ever be a guess.

    The count is cross-checked against the PDF's own page objects rather than
    against len() of what was recorded, which would be circular.

    Asserted in Spanish on purpose. The project's `.mo` is versioned and the
    deploy does not recompile it, so a `.po` entry added without recompiling
    renders in English in production -- and `test_translations` cannot see that,
    because it reads the `.po`. This test does.
    """
    seen = []

    class Recording(pdf.LetterheadCanvas):
        letterhead = head

        def _draw_footer(self, letterhead, page, total, width):
            seen.append(letterhead.footer_texts(page, total)[1])
            super()._draw_footer(letterhead, page, total, width)

    from io import BytesIO

    output = BytesIO()
    SimpleDocTemplate(output, title=head.title).build(
        _three_page_story(pdf.executive_stylesheet()), canvasmaker=Recording
    )
    data = output.getvalue()

    assert data.count(b"/Type /Page\n") == 3
    assert seen == ["Página 1 de 3", "Página 2 de 3", "Página 3 de 3"]

    with override("en"):
        assert head.footer_texts(1, 3)[1] == "Page 1 of 3"


def test_the_logo_is_embedded_once_however_many_pages_there_are(head):
    """One ImageReader per document, not per page. reportlab keys its image
    cache on the reader it is handed, so a reader built inside the per-page
    draw would embed the same PNG on every page -- invisible on screen and a
    file that grows with the report."""
    styles = pdf.executive_stylesheet()
    one_page = pdf.build_pdf([Paragraph("Only", styles["Title"])], head)
    three_pages = pdf.build_pdf(_three_page_story(styles), head)

    assert one_page.count(b"/Type /Page\n") == 1
    assert three_pages.count(b"/Type /Page\n") == 3
    # Two occurrences for one logo: the image plus the soft mask its alpha
    # channel needs. What matters is that the number does not grow with pages.
    assert three_pages.count(b"/Subtype /Image") == one_page.count(b"/Subtype /Image")
    assert one_page.count(b"/Subtype /Image") == 2


def test_the_footer_names_the_company_and_the_page(head):
    left, right = head.footer_texts(2, 5)

    assert branding.LEGAL_NAME in left
    assert branding.ADDRESS in left
    assert branding.WEBSITE in left
    assert right == "Página 2 de 5"


def test_the_running_head_is_absent_from_the_first_page(head):
    """The body opens with its own heading on page 1, so repeating the title in
    the header there reads like a duplication bug. From page 2 it is the only
    thing that says what the sheet in your hand belongs to."""
    drawn = {}

    class Recording(pdf.LetterheadCanvas):
        letterhead = head

        def _draw_header(self, letterhead, page, width, height):
            self._recording_page = page
            super()._draw_header(letterhead, page, width, height)

        def drawRightString(self, x, y, text, **kwargs):  # noqa: N802
            drawn.setdefault(self._recording_page, []).append(text)
            return super().drawRightString(x, y, text, **kwargs)

    from io import BytesIO

    SimpleDocTemplate(BytesIO()).build(
        _three_page_story(pdf.executive_stylesheet()), canvasmaker=Recording
    )

    assert head.title not in drawn[1]
    assert head.title in drawn[2]
    # The reference and the date are on every page: a loose sheet has to carry
    # them, which is the same reason the title appears from page 2.
    for page in (1, 2, 3):
        assert head.reference in drawn[page]
        assert head.date_text in drawn[page]


def test_the_metadata_carries_the_company_and_the_reference(head):
    """Document properties are not compressed, so this is also the one thing a
    test can read straight out of the bytes."""
    data = pdf.build_pdf([Paragraph("x", pdf.executive_stylesheet()["Title"])], head)

    assert b"J.E.J. Ingenier" in data
    assert head.reference.encode() in data


def test_a_canvas_with_no_letterhead_draws_no_furniture():
    """LetterheadCanvas is usable bare (a caller that forgot make_canvasmaker),
    and must not raise on a None letterhead half a document in."""
    from io import BytesIO

    output = BytesIO()
    SimpleDocTemplate(output).build(
        [Paragraph("x", pdf.executive_stylesheet()["Title"])],
        canvasmaker=pdf.LetterheadCanvas,
    )

    assert output.getvalue()[:5] == b"%PDF-"


# -- derived reference -----------------------------------------------------


def test_the_reference_is_labelled_and_is_not_the_corporate_correlative():
    """Paper letters carry a `J.E.J. N° 00x-26` that a person assigns. Minting
    one here would put two authorities on the same identifier, so what the PDF
    prints is derived from the document kind and its date, and says "Ref."."""
    from datetime import date

    reference = pdf.derived_reference("CUM", date(2026, 8, 26))

    assert reference == "Ref. CUM-20260826"
    assert "J.E.J. N" not in reference


# -- urgency palette -------------------------------------------------------


def test_the_urgency_colours_cover_exactly_the_digest_buckets():
    """`bucket_for` owns the thresholds; this table only colours them. If the
    digest gains a tramo, the gate goes red here instead of the new bucket
    printing in body black with nobody noticing."""
    from apps.compliance.digest import BUCKET_BADGE_CSS, BUCKET_TEXT_CSS, BUCKETS

    assert set(pdf.BUCKET_COLORS) == set(BUCKET_BADGE_CSS)
    assert set(pdf.BUCKET_COLORS) == set(BUCKET_TEXT_CSS)
    assert {key for key, _bound in BUCKETS} <= set(pdf.BUCKET_COLORS)
    assert pdf.BUCKET_BOLD <= set(pdf.BUCKET_COLORS)


def test_the_urgency_colours_follow_the_screen_including_the_shared_amber():
    """due_7 and due_15 are the same hue on the dashboard and differ by weight
    (BUCKET_TEXT_CSS: fw-bold vs fw-semibold). Paper does the same, which is
    why the bold set is a second table and not "everything with a colour"."""
    assert pdf.BUCKET_COLORS["due_7"] == pdf.BUCKET_COLORS["due_15"]
    assert pdf.BUCKET_COLORS["overdue"] != pdf.BUCKET_COLORS["due_7"]
    assert "due_30" not in pdf.BUCKET_BOLD
    assert "later" not in pdf.BUCKET_BOLD


def test_urgency_commands_tint_the_ranges_they_are_given():
    commands = pdf.urgency_commands(
        [
            ("overdue", (5, 1), (5, 9)),
            ("due_30", (8, 1), (8, 9)),
            (None, (9, 1), (9, 9)),
            ("not-a-bucket", (10, 1), (10, 9)),
        ]
    )

    kinds = [(name, start, end) for name, start, end, *_ in commands]
    assert ("TEXTCOLOR", (5, 1), (5, 9)) in kinds
    assert ("FONTNAME", (5, 1), (5, 9)) in kinds  # overdue is bold
    assert ("TEXTCOLOR", (8, 1), (8, 9)) in kinds
    assert ("FONTNAME", (8, 1), (8, 9)) not in kinds  # due_30 is not
    # An unknown or missing bucket is skipped, not painted a default colour: a
    # row with no expiry date has no urgency to show.
    assert not [cmd for cmd in kinds if cmd[1][0] in (9, 10)]


# -- shared styling --------------------------------------------------------


def test_the_stylesheet_restyles_the_sample_sheet_rather_than_replacing_it():
    """Built on the sample sheet so a document already written against Title /
    Normal / Heading2 gains the identity with no content change -- which is how
    the compliance report kept every word it had."""
    from reportlab.lib.colors import HexColor

    styles = pdf.executive_stylesheet()

    assert styles["Title"].textColor == HexColor(branding.BLUE)
    assert styles["Title"].fontName == branding.FONT_BOLD
    assert styles["Heading2"].textColor == HexColor(branding.BLUE)
    assert styles["Normal"].fontName == branding.FONT_REGULAR
    assert styles["Cell"].fontSize < styles["Normal"].fontSize


def test_the_table_style_puts_the_brand_blue_behind_the_heading_row():
    from reportlab.lib.colors import HexColor

    style = pdf.executive_table_style()
    table = Table([["a", "b"], ["1", "2"]])
    table.setStyle(style)

    commands = [tuple(command) for command in style.getCommands()]
    assert ("BACKGROUND", (0, 0), (-1, 0), HexColor(branding.BLUE)) in commands
    assert ("GRID", (0, 0), (-1, -1), 0.4, HexColor(branding.GRID_TINT)) in commands


def test_the_table_style_appends_the_extra_commands_after_its_own():
    """Order matters in a TableStyle: the last command on a cell wins, so an
    urgency colour handed in as `extra` has to come after the base FONTNAME and
    TEXTCOLOR or it would be overwritten by them."""
    extra = pdf.urgency_commands([("overdue", (5, 1), (5, 3))])

    commands = pdf.executive_table_style(extra).getCommands()

    assert tuple(commands[-1]) == tuple(extra[-1])
    assert len(commands) == len(pdf.executive_table_style().getCommands()) + len(extra)


def test_pdf_response_is_an_attachment_with_the_given_filename(head):
    response = pdf.pdf_response(
        [Paragraph("x", pdf.executive_stylesheet()["Title"])], head, "roster.pdf"
    )

    assert response["Content-Type"] == "application/pdf"
    assert response["Content-Disposition"] == 'attachment; filename="roster.pdf"'
    assert response.content[:5] == b"%PDF-"
