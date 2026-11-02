"""LV-386: el selector de tipo de documento con ayuda (PR 3 de 4). Datos ficticios."""

import re
from pathlib import Path

import pytest
from django.urls import reverse
from django.utils.translation import gettext, override

from apps.compliance.models import DocumentType
from apps.core.testing import login_as, without_template_comments

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / "templates" / "compliance"
HINT_TEMPLATE = TEMPLATES / "_doc_type_hint.html"
SCRIPT = ROOT / "static" / "js" / "doc-type-hint.js"


@pytest.fixture
def types(db):
    with_ref = DocumentType.objects.create(
        code="T386A",
        name="Bitácora de vuelo",
        reference_code="REG-015",
        description="Registro de cada vuelo.",
        requires_expiry=False,
    )
    bare = DocumentType.objects.create(
        code="T386B", name="Documento suelto", requires_expiry=True
    )
    return with_ref, bare


def _form_html(client, **params):
    response = client.get(reverse("document-create"), params)
    assert response.status_code == 200
    return response.content.decode()


def _option(html, doc_type):
    return re.search(rf'<option value="{doc_type.pk}"[^>]*>[^<]*</option>', html)


@pytest.mark.django_db
class TestTheOptions:
    def test_the_label_carries_the_form_code_and_the_data_attributes(self, types):
        with_ref, _bare = types
        html = _form_html(login_as("add_document", "view_document"))

        option = _option(html, with_ref).group(0)

        assert "Bitácora de vuelo · REG-015" in option
        assert 'data-description="Registro de cada vuelo."' in option
        assert 'data-expiry="no"' in option

    def test_a_type_without_a_code_keeps_its_plain_name(self, types):
        _with_ref, bare = types
        html = _form_html(login_as("add_document", "view_document"))

        option = _option(html, bare).group(0)

        assert ">Documento suelto<" in option
        assert "·" not in option
        assert 'data-expiry="yes"' in option


@pytest.mark.django_db
class TestTheServerDrawnHint:
    def test_the_initial_value_is_described_without_js(self, types):
        with_ref, _bare = types
        with override("es"):
            html = _form_html(
                login_as("add_document", "view_document"), doc_type=str(with_ref.pk)
            )
            expected = gettext("Asks for an expiry date: no")

        hint = re.search(r'<p id="doc-type-hint".*?</p>', html, re.S).group(0)
        assert "Registro de cada vuelo." in hint
        assert "Pide fecha de vencimiento: no" in hint
        assert expected in hint
        assert " hidden" not in hint.split(">")[0]

    def test_a_type_without_description_shows_only_the_expiry_line(self, types):
        _with_ref, bare = types
        html = _form_html(
            login_as("add_document", "view_document"), doc_type=str(bare.pk)
        )

        hint = re.search(r'<p id="doc-type-hint".*?</p>', html, re.S).group(0)
        assert "data-doc-type-description" not in hint
        assert "data-doc-type-expiry" in hint

    def test_without_a_selection_the_hint_is_hidden_and_empty(self, types):
        html = _form_html(login_as("add_document", "view_document"))

        hint = re.search(r'<p id="doc-type-hint".*?</p>', html, re.S).group(0)
        assert " hidden" in hint.split(">")[0]
        assert re.sub(r"<[^>]+>", "", hint).strip() == ""

    def test_aria_describedby_points_at_an_existing_id(self, types):
        html = _form_html(login_as("add_document", "view_document"))

        select = re.search(r"<select[^>]*data-doc-type-select[^>]*>", html).group(0)
        target = re.search(r'aria-describedby="([^"]+)"', select).group(1)
        assert f'id="{target}"' in html

    def test_the_bulk_form_has_the_hint_too(self, types):
        response = login_as("add_document", "view_document").get(
            reverse("document-bulk-upload")
        )
        html = response.content.decode()

        assert 'id="doc-type-hint"' in html
        assert "data-doc-type-select" in html


class TestNoInlineScript:
    def test_the_hint_template_has_no_inline_script_or_handlers(self):
        text = without_template_comments(HINT_TEMPLATE.read_text(encoding="utf-8"))

        for tag in re.findall(r"<script\b[^>]*>", text):
            assert " src=" in tag, tag
        assert not re.search(r"\son[a-z]+\s*=", text)

    def test_the_script_has_one_change_listener_and_no_eval(self):
        js = SCRIPT.read_text(encoding="utf-8")

        assert js.count('addEventListener("change"') == 1
        assert "eval(" not in js and "innerHTML" not in js


def test_the_new_strings_are_translated():
    with override("es"):
        assert gettext("Asks for an expiry date: yes") == (
            "Pide fecha de vencimiento: sí"
        )
        assert gettext("Asks for an expiry date: no") == (
            "Pide fecha de vencimiento: no"
        )
