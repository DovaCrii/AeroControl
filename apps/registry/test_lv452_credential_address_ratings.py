"""LV-452: la dirección (V) y las habilitaciones (XIII) de la credencial DGAC llegan al alta.

Tras LV-448 el alta ya traía número, titular, RUT y fechas, pero dejaba vacías la
dirección y las habilitaciones. Texto **inventado** con la disposición real.
"""

import pytest
from django.urls import reverse

from apps.registry import credential_reader as reader
from apps.registry.operator_intake import initial_from

TEXT = "\n".join(
    [
        "RUT / PASSPORT",
        "11111111-1",
        "III) Nº 12345",
        "IV) OPERADOR DEMO",
        "PRUEBA EJEMPLO",
        "V) CALLE FICTICIA 123 DEPTO 4",
        "COMUNA DEMO",
        "VI) CHILE   01-01-1990",
        "XIV) Validez Certificado / Certificate Validity  15-10-2029",
        "XII) HABILITACIONES (VÁLIDO HASTA) / RATINGS (VALID UNTIL)",
        "OPERADOR RPAS",
        "Encargado del Subdepartamento",
        "XIII) OBSERVACIONES / REMARKS",
        "Modelo A - Modelo B/ Pro 2 - Modelo C",
        "300/ 200.",
        "FECHA OTORGAMIENTO / DATE ISSUED",
        "15-10-2024",
    ]
)


class TestReader:
    def test_the_address_joins_its_two_lines_and_is_doubtful(self):
        prop = reader.credential_from_text(TEXT)[reader.ADDRESS]

        assert prop.value == "CALLE FICTICIA 123 DEPTO 4 COMUNA DEMO"
        assert prop.confidence == reader.DOUBTFUL

    def test_a_one_line_address_is_exact(self):
        prop = reader.credential_from_text(TEXT.replace("COMUNA DEMO\n", ""))[
            reader.ADDRESS
        ]

        assert prop.value == "CALLE FICTICIA 123 DEPTO 4"
        assert prop.confidence == reader.EXACT

    def test_the_ratings_are_the_remarks_copied_as_written(self):
        prop = reader.credential_from_text(TEXT)[reader.RATINGS]

        assert prop.value == "Modelo A - Modelo B/ Pro 2 - Modelo C 300/ 200."
        assert prop.confidence == reader.EXACT

    def test_empty_remarks_never_take_the_issue_date(self):
        text = TEXT.replace("Modelo A - Modelo B/ Pro 2 - Modelo C\n300/ 200.\n", "")

        assert reader.RATINGS not in reader.credential_from_text(text)

    def test_the_signature_lines_of_xii_are_not_ratings(self):
        value = reader.credential_from_text(TEXT)[reader.RATINGS].value

        assert "Encargado" not in value and "OPERADOR RPAS" not in value

    def test_fragments_do_not_carry_the_address(self):
        props = reader.credential_from_text(TEXT)

        assert "FICTICIA" not in " ".join(p.fragment for p in props.values())


def test_the_form_initial_takes_address_and_ratings():
    initial = initial_from(reader.credential_from_text(TEXT))

    assert initial["address"] == "CALLE FICTICIA 123 DEPTO 4 COMUNA DEMO"
    assert (
        initial["authorizations"] == "Modelo A - Modelo B/ Pro 2 - Modelo C 300/ 200."
    )


@pytest.mark.django_db
def test_the_create_form_shows_both(monkeypatch):
    from apps.core.testing import login_as
    from apps.registry import operator_intake

    pending = operator_intake.PendingCredential(
        path="x", sha="y", data=b"", proposals=reader.credential_from_text(TEXT)
    )
    monkeypatch.setattr(operator_intake, "pending_or_none", lambda token, user: pending)
    client = login_as("add_operator", "add_document")

    page = client.get(reverse("operator-create") + "?credential=t").content.decode()
    assert "COMUNA DEMO" in page
    assert "Modelo A - Modelo B" in page
