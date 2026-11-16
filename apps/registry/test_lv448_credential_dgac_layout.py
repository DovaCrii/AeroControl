"""LV-448: el formato real de la credencial DGAC (campos numerados en romanos).

Con una credencial real, el alta decía «se leyó y se completó el formulario» y dejaba
todo vacío: el lector se había escrito sin ver ninguna, y ninguna etiqueta del formato
OACI coincidía. Este texto es **inventado**: imita la disposición (romanos, español e
inglés, el RUT debajo de «RUT / PASSPORT», la emisión en la línea siguiente) sin un solo
dato real. El RUT es de ejemplo.
"""

from datetime import date

import pytest
from django.urls import reverse

from apps.registry import credential_reader as reader

DGAC_TEXT = "\n".join(
    [
        "RUT / PASSPORT",
        "IX) La persona individualizada en este documento esta autorizada para ejercer",
        "las atribuciones que otorga la credencial",
        "11111111-1",
        "I)  REPÚBLICA DE CHILE",
        "REPUBLIC OF CHILE",
        "II) OPERADOR RPA",
        "RPA OPERATOR",
        "CREDENCIAL",
        "III) Nº 12345",
        "IV) OPERADOR DEMO",
        "PRUEBA EJEMPLO",
        "V) CALLE FICTICIA 123",
        "VI) CHILE   01-01-1990",
        "VIII) DIRECCIÓN GENERAL DE AERONÁUTICA CIVIL",
        "XIV) Validez Certificado / Certificate Validity  15-10-2029",
        "XII) HABILITACIONES (VÁLIDO HASTA) / RATINGS (VALID UNTIL)",
        "OPERADOR RPAS 15-10-2029",
        "XIII) OBSERVACIONES / REMARKS",
        "FECHA OTORGAMIENTO / DATE ISSUED",
        "15-10-2024",
    ]
)


class TestDgacLayout:
    def test_every_field_is_read(self):
        props = reader.credential_from_text(DGAC_TEXT)

        assert props[reader.NUMBER].value == "12345"
        assert props[reader.EXPIRY_DATE].value == date(2029, 10, 15)
        assert props[reader.ISSUE_DATE].value == date(2024, 10, 15)
        assert props[reader.RUT].value == "11111111-1"
        assert props[reader.HOLDER].value == "OPERADOR DEMO PRUEBA EJEMPLO"

    def test_confidence(self):
        props = reader.credential_from_text(DGAC_TEXT)

        for field in (reader.NUMBER, reader.EXPIRY_DATE, reader.ISSUE_DATE, reader.RUT):
            assert props[field].confidence == reader.EXACT, field
        # El nombre armado con dos líneas es una suposición: se revisa.
        assert props[reader.HOLDER].confidence == reader.DOUBTFUL

    def test_the_ratings_date_is_not_taken_as_the_expiry(self):
        text = DGAC_TEXT.replace(
            "XIV) Validez Certificado / Certificate Validity  15-10-2029", ""
        )

        props = reader.credential_from_text(text)
        assert reader.EXPIRY_DATE not in props

    def test_two_ruts_give_no_rut(self):
        props = reader.credential_from_text(DGAC_TEXT + "\n22222222-2")

        assert reader.RUT not in props

    def test_fragments_never_carry_the_rut_or_the_holder(self):
        props = reader.credential_from_text(DGAC_TEXT)

        fragments = " ".join(p.fragment for p in props.values())
        assert "11111111" not in fragments and "OPERADOR DEMO" not in fragments

    def test_a_text_without_the_numbered_layout_is_untouched(self):
        assert reader._dgac_layout(["Nº 1234", "Vencimiento: 01-01-2030"], "") == {}


@pytest.mark.django_db
def test_nothing_recognized_does_not_claim_the_form_was_filled(client, monkeypatch):
    """Leído pero sin datos: el aviso ya no dice «se completó el formulario»."""
    from apps.core.testing import login_as
    from apps.registry import operator_intake

    pending = operator_intake.PendingCredential(
        path="x", sha="y", data=b"", proposals={}
    )
    monkeypatch.setattr(operator_intake, "pending_or_none", lambda token, user: pending)
    client = login_as("add_operator", "add_document")

    page = client.get(reverse("operator-create") + "?credential=t").content.decode()
    assert "data-credential-nothing" in page
    assert "data-credential-read" not in page
