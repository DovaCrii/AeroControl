"""LV-450: la ficha del operador, por tarjetas agrupadas.

Las afirmaciones se acotan a la región de la hoja (`class="tk-sheet"` hasta el
`<details>` final): el armazón de la página comparte vocabulario con ella.
"""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext

from apps.core.testing import login_as
from apps.core.templatetags.aero_tags import fields_detail, fields_grouped
from apps.registry.models import CostCenter, Operator

EXCLUDE = "left_company_on,departure_reason,departure_note"
NOTE = "SENTINEL-SALIDA-LV450"


@pytest.fixture
def operator(db):
    center = CostCenter.objects.create(code="CC-000", name="Faena Demo")
    return Operator.objects.create(
        employee_id="DEMO-0000",
        full_name="Operador Demo",
        email="demo@example.com",
        cost_center=center,
    )


def _sheet(operator, perm="view_operator"):
    html = (
        login_as(perm)
        .get(reverse("operator-detail", args=[operator.pk]))
        .content.decode()
    )
    start = html.index('class="tk-sheet"')
    return html[start : html.index("</details>", start) + len("</details>")]


@pytest.mark.django_db
class TestTheOperatorSheet:
    def test_every_field_appears_exactly_once(self, operator):
        sheet = _sheet(operator)
        details = sheet.split('class="tk-empty-fields"', 1)[1]
        listed = details.split('<p class="mb-0">', 1)[1].split("</p>")[0].split(", ")
        cards = sheet.split('class="tk-empty-fields"', 1)[0]
        labels = [f["label"] for f in fields_detail(operator, EXCLUDE)]

        assert labels
        for label in labels:
            in_cards = cards.count(f"<dt>{label}</dt>")
            assert in_cards + listed.count(label) == 1, label

    def test_the_departure_fields_stay_off_the_sheet(self, operator):
        operator.register_departure(
            left_on=timezone.localdate() - timedelta(days=2),
            reason="resignation",
            note=NOTE,
        )
        client = login_as("view_operator")

        html = client.get(
            reverse("operator-detail", args=[operator.pk])
        ).content.decode()

        assert NOTE not in html
        assert not any(
            name
            in {
                g_f["name"]
                for g in fields_grouped(operator, EXCLUDE)["groups"]
                for g_f in g["fields"]
            }
            for name in ("left_company_on", "departure_reason", "departure_note")
        )
        for label in ("Left the company on", "Departure reason", "Departure note"):
            assert f"<dt>{gettext(label)}</dt>" not in html

    def test_empty_notes_go_to_the_closing_details(self, operator):
        sheet = _sheet(operator)
        cards, details = sheet.split('class="tk-empty-fields"', 1)

        assert gettext("Notes") in details
        assert f"<dt>{gettext('Notes')}</dt>" not in cards
        assert 'id="sheet-notes"' not in sheet
        assert cards.index('id="sheet-identification"') >= 0

    def test_a_note_with_content_gets_its_card_after_identification(self, operator):
        operator.notes = "Nota demo"
        operator.save()

        sheet = _sheet(operator)

        assert sheet.index('id="sheet-identification"') < sheet.index(
            'id="sheet-notes"'
        )

    def test_an_empty_credential_shows_in_its_card_as_not_registered(self, operator):
        sheet = _sheet(operator)
        card = sheet.split('id="sheet-credential"', 1)[1].split("</section>")[0]

        assert f"<dt>{gettext('DGAC credential')}</dt>" in card
        assert card.count("tk-empty") == 2
        assert gettext("Not registered") in card

    def test_a_model_without_a_layout_keeps_the_table(self, db):
        center = CostCenter.objects.create(code="CC-001", name="Faena Demo")

        assert fields_grouped(center, "") == {"groups": [], "empty": []}
        html = (
            login_as("view_costcenter")
            .get(reverse("costcenter-detail", args=[center.pk]))
            .content.decode()
        )
        assert "<table" in html and "tk-sheet" not in html
