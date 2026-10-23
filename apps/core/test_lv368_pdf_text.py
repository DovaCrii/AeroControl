"""LV-368 fase 2: `text_from_pdf` es la única puerta de lectura de PDF."""

import io
import logging

from apps.core.pdf_text import text_from_pdf


def _pdf(pages):
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    page = canvas.Canvas(buffer)
    for lines in pages:
        for index, line in enumerate(lines):
            page.drawString(70, 750 - index * 20, line)
        page.showPage()
    page.save()
    return io.BytesIO(buffer.getvalue())


def test_reads_only_the_requested_number_of_pages():
    stream = _pdf([["first page"], ["second page"], ["third page"]])
    text = text_from_pdf(stream, pages=2)
    assert "first page" in text and "second page" in text
    assert "third page" not in text


def test_default_is_two_pages():
    text = text_from_pdf(_pdf([["one"], ["two"], ["three"]]))
    assert "two" in text and "three" not in text


def test_not_a_pdf_is_none_and_never_raises(caplog):
    with caplog.at_level(logging.INFO):
        assert text_from_pdf(io.BytesIO(b"not a pdf")) is None
    assert "pdf_unreadable" in caplog.text


def test_a_pdf_without_text_is_none():
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    page = canvas.Canvas(buffer)
    page.rect(10, 10, 50, 50)
    page.save()
    assert text_from_pdf(io.BytesIO(buffer.getvalue())) is None
