"""LV-144: the compliance report PDF, retrofitted with the corporate letterhead.

Asserted at the seam -- the letterhead, the flowables and the table commands the
view hands `apps.core.pdf` -- rather than on the output bytes, because reportlab
compresses page streams and a byte assertion on drawn text passes for the wrong
reason. What the bytes *can* prove is the document metadata, which is not
compressed, and that is checked too.
"""

from datetime import date, timedelta

import pytest
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.core import pdf as corepdf
from apps.registry.models import Aircraft, CostCenter
from .digest import BUCKETS
from .models import Document, DocumentType
from .reports import COST_CENTER_HEADERS

TODAY = timezone.localdate()


@pytest.fixture
def world(db):
    cost_center = CostCenter.objects.create(code="FAENA-01", name="Faena Norte")
    aircraft = Aircraft.objects.create(
        registration="CC-AAA",
        type="Multirotor",
        model="M300",
        manufacturer="DJI",
        cost_center=cost_center,
    )
    doc_type = DocumentType.objects.create(code="SEG", name="Seguro")
    aircraft_ct = ContentType.objects.get_for_model(Aircraft)
    for title, offset in (("expired", -5), ("due-soon", 3), ("due-late", 25)):
        Document.objects.create(
            title=title,
            doc_type=doc_type,
            content_type=aircraft_ct,
            object_id=aircraft.pk,
            file_path=f"seg/{title}.pdf",
            issue_date=date(2026, 1, 1),
            expiry_date=TODAY + timedelta(days=offset),
        )
    return {"cost_center": cost_center}


@pytest.fixture
def capture(monkeypatch):
    """Record what the view hands the shared PDF helper, and let it render.

    Patching the helper on `apps.core.pdf` (not on the view) is what makes this
    work: the view imports the module inside `get()`, so the attribute lookup
    happens per request.
    """
    recorded = {}
    real_response = corepdf.pdf_response
    real_urgency = corepdf.urgency_commands
    real_table_style = corepdf.executive_table_style

    def pdf_response(elements, letterhead, filename):
        recorded["elements"] = list(elements)
        recorded["letterhead"] = letterhead
        recorded["filename"] = filename
        return real_response(elements, letterhead, filename)

    def urgency_commands(ranges):
        ranges = list(ranges)
        recorded.setdefault("urgency", []).extend(ranges)
        return real_urgency(ranges)

    def executive_table_style(extra=()):
        # `Table.setStyle` applies the commands and keeps no TableStyle to read
        # back, so the style is captured on its way in.
        style = real_table_style(extra)
        recorded.setdefault("table_styles", []).append(style)
        return style

    monkeypatch.setattr(corepdf, "pdf_response", pdf_response)
    monkeypatch.setattr(corepdf, "urgency_commands", urgency_commands)
    monkeypatch.setattr(corepdf, "executive_table_style", executive_table_style)
    return recorded


@pytest.fixture
def response(world, capture):
    User.objects.create_superuser("admin", "a@test.com", "password")
    client = Client()
    assert client.login(username="admin", password="password")
    return client.get(reverse("compliance-report-pdf"))


def _paragraph_texts(elements):
    return [
        element.getPlainText()
        for element in elements
        if hasattr(element, "getPlainText")
    ]


def _tables(elements):
    return [element for element in elements if hasattr(element, "_cellvalues")]


def test_the_report_pdf_wears_the_letterhead(response, capture):
    assert response.status_code == 200
    assert response.content[:5] == b"%PDF-"
    assert capture["filename"] == "aerocontrol-cumplimiento.pdf"

    letterhead = capture["letterhead"]
    assert isinstance(letterhead, corepdf.Letterhead)
    assert letterhead.reference.startswith("Ref. CUM-")
    # Metadata is the one part of the output that is not compressed.
    assert b"J.E.J. Ingenier" in response.content
    assert letterhead.reference.encode() in response.content


def test_the_generated_date_moved_into_the_letterhead(response, capture):
    """It used to be a line in the body. The letterhead prints it on every
    page now, and printing it twice on page one reads like a bug -- so the body
    line went, and this pins that it went for that reason and not by accident.
    """
    texts = _paragraph_texts(capture["elements"])

    assert not [text for text in texts if text.startswith("Generado:")]
    assert capture["letterhead"].date_text.startswith("Generado:")


def test_the_content_survived_the_restyling(response, capture):
    """The furniture changed and the report did not. Every section the R6.4
    report had is still there, in order, with its tables."""
    from django.utils.translation import gettext

    texts = _paragraph_texts(capture["elements"])

    assert texts[0].startswith("AeroControl")
    # Compared against the same catalog lookups the view makes, rather than
    # against Spanish spelled out here: this stays true in either language.
    for heading in (
        gettext("Compared with the previous period"),
        gettext("By cost center"),
        gettext("Alert resolution in the period"),
        gettext("Open alerts"),
    ):
        assert heading in texts

    tables = _tables(capture["elements"])
    # Comparison and by-cost-center. The fixture has no open alerts, so that
    # section is still a sentence and not an empty grid -- the behaviour the
    # R6.4 report already had, and one this restyling had to preserve.
    assert len(tables) == 2
    assert gettext("No open alerts.") in texts
    by_cost_center = tables[1]
    assert by_cost_center._cellvalues[0] == [str(h) for h in COST_CENTER_HEADERS]
    assert len(by_cost_center._cellvalues) == 2  # header plus the one faena


def test_the_bucket_columns_are_the_last_four_of_the_header_row():
    """The view derives which columns to tint as "the last len(BUCKETS) of
    COST_CENTER_HEADERS" instead of writing 5..8. That derivation is only safe
    while the header row really does end with the buckets, in the digest's
    order -- so it is pinned here rather than left as a comment.
    """
    tail = COST_CENTER_HEADERS[-len(BUCKETS) :]

    assert len(tail) == 4
    assert tail[0] == "Vencidos"  # the "overdue" bucket has no day bound
    for header, (_key, bound) in zip(tail[1:], BUCKETS[1:], strict=True):
        assert str(bound) in header, f"{header!r} is not the {bound}-day column"


def test_the_cost_center_bucket_columns_are_tinted_by_urgency(response, capture):
    """A "3" under Vencidos prints in the same red the dashboard uses."""
    ranges = capture["urgency"]
    first_column = len(COST_CENTER_HEADERS) - len(BUCKETS)

    assert [key for key, _start, _end in ranges] == [key for key, _bound in BUCKETS]
    for offset, (_key, start, end) in enumerate(ranges):
        assert start == (first_column + offset, 1)
        # One data row in the fixture, so the range ends on row 1; what matters
        # is that it spans the data rows and never touches the heading row.
        assert end == (first_column + offset, 1)
        assert start[1] >= 1


def test_the_tint_reaches_the_style_the_table_was_given(response, capture):
    """The commands are not merely computed: they arrive inside the shared
    table style, and only in the by-cost-center table -- the comparison table's
    columns carry no urgency, so tinting them would be colour without meaning.
    """
    from reportlab.lib.colors import HexColor

    comparison, by_cost_center = capture["table_styles"]
    first_column = len(COST_CENTER_HEADERS) - len(BUCKETS)
    overdue = ("TEXTCOLOR", (first_column, 1), (first_column, 1))

    matching = [
        command
        for command in by_cost_center.getCommands()
        if tuple(command[:3]) == overdue
    ]
    assert matching, f"no urgency tint on {overdue}"
    assert matching[-1][3] == HexColor(corepdf.BUCKET_COLORS["overdue"])

    # One TEXTCOLOR per bucket column, plus a FONTNAME on the urgent ones.
    expected = len(BUCKETS) + sum(
        1 for key, _bound in BUCKETS if key in corepdf.BUCKET_BOLD
    )
    plain = len(comparison.getCommands())
    assert len(by_cost_center.getCommands()) == plain + expected
