"""LV-152: la habilitación dice lo que dice la DGAC, y deja de mentir.

La columna "Habilitación" del padrón mostraba una insignia verde "Vigente"
derivada de las habilitaciones estructuradas, contando como vigente toda
habilitación con vencimiento `NULL` — que es como quedaron **todas** las que
entraron por el import. Resultado: casi todo el padrón en verde, con un dato que
nadie ingresó. Es el error que `LV-29` nombró para las vigencias (un nulo es
"nunca se ingresó", no "está bien") y que `LV-74` sigue pagando.

La decisión del usuario fue no estandarizar: *"lo importante de la habilitación
es poner directamente en el recuadro lo que dice la DGAC, no más; no buscar más
allá de estandarizar o algo, ya que es variable el asunto"*. El campo de texto
libre ya existía (`Operator.authorizations`), sólo que enterrado al final del
formulario, después de la dirección.

Las filas se piden como parcial HTMX a propósito: así lo que se afirma es el
contenido de la fila y no una página entera donde "Vigente" también aparece en el
filtro de archivadas.
"""

import pytest
from django.urls import reverse

from apps.core.testing import login_as
from apps.registry.forms import OperatorForm
from apps.registry.models import Operator, Qualification, QualificationType


def _rows(client):
    response = client.get(reverse("operator-list"), HTTP_HX_REQUEST="true")
    assert response.status_code == 200
    return response.content.decode()


@pytest.mark.django_db
class TestTheListShowsWhatTheDgacSays:
    def test_the_row_shows_the_verbatim_text(self):
        Operator.objects.create(
            employee_id="E-1",
            full_name="Ana Rivas",
            authorizations="Multirotor hasta 25 kg · Nocturno",
        )

        assert "Multirotor hasta 25 kg · Nocturno" in _rows(login_as("view_operator"))

    def test_an_operator_without_qualifications_shows_a_dash(self):
        Operator.objects.create(employee_id="E-1", full_name="Ana Rivas")

        rows = _rows(login_as("view_operator"))

        assert "—" in rows

    def test_an_undated_qualification_no_longer_reads_as_current(self):
        # El defecto exacto: una habilitación estructurada sin vencimiento
        # pintaba la fila de verde. Sin el fix, este test encuentra la insignia.
        operator = Operator.objects.create(employee_id="E-1", full_name="Ana Rivas")
        qualification_type = QualificationType.objects.create(
            name="Multirotor", code="MR"
        )
        Qualification.objects.create(
            operator=operator,
            qualification_type=qualification_type,
            expiry_date=None,
        )

        rows = _rows(login_as("view_operator"))

        assert "badge bg-success" not in rows

    def test_the_list_is_403_without_view_operator(self):
        assert login_as().get(reverse("operator-list")).status_code == 403


@pytest.mark.django_db
class TestTheFormAsksForItNextToTheCredential:
    def test_the_qualifications_field_follows_the_credential(self):
        order = list(OperatorForm().fields)

        assert order.index("authorizations") == order.index("credential_expiry") + 1

    def test_it_is_no_longer_buried_after_the_address(self):
        order = list(OperatorForm().fields)

        assert order.index("authorizations") < order.index("address")

    def test_the_field_says_to_copy_it_verbatim(self):
        help_text = str(OperatorForm().fields["authorizations"].help_text)

        assert "DGAC" in help_text
        assert "standardis" in help_text or "estandariz" in help_text
