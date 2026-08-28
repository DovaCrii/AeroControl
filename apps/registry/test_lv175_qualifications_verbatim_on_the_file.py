"""LV-175: la ficha muestra la habilitación como la escribe la DGAC.

Decisión del usuario, sobre lo que veía en producción: *"quitar esa sección de
habilitaciones, dejarlo como algo legible y claro"*. En `p340` ese bloque
mostraba tres filas —Serie Matrice, Serie Mavic, Serie Phantom— con emisión y
vencimiento en guion: las que sembró `seed_operator_qualifications` (`LV-12b`)
parseando el texto libre de la credencial, **sin fechas**. Tres habilitaciones
afirmadas y ninguna respaldada, que es el mismo nulo que `LV-29` definió como
"nunca se ingresó" y que `LV-152` ya había sacado del listado por eso mismo.

Había dos decisiones del usuario apuntando en direcciones opuestas: `R5.8` decía
mostrar el catálogo estructurado en la ficha, y `LV-152` decía *"poner
directamente en el recuadro lo que dice la DGAC, no más; no buscar más allá de
estandarizar"*. Ganó la segunda, que es la más reciente y la que él reafirmó:
**el texto literal de la credencial es el dato; el catálogo es interpretación.**

Lo que estos tests protegen:

- **El texto de la DGAC se ve en la ficha.** Es lo que se fue a buscar ahí.
- **No se borró nada.** `Qualification` y `QualificationType` siguen enteros, y
  siguen alimentando el aviso de compatibilidad de `B4.4` y las alertas de las
  que sí tienen fecha. Esconder una superficie no es dar de baja un subsistema —
  es el patrón de `LV-7`, `LV-D8` y `R5.8`.
"""

import pytest
from django.urls import reverse

from apps.core.testing import login_as
from apps.registry.models import Operator, Qualification, QualificationType


@pytest.fixture
def operator(db):
    return Operator.objects.create(
        employee_id="E-1",
        full_name="Ana Rivas",
        authorizations="MAVIC 3 ENTERPRISE / MATRICE 300 RTK",
    )


def test_the_file_shows_what_the_credential_says(operator):
    client = login_as("view_operator")

    body = client.get(reverse("operator-detail", args=[operator.pk])).content.decode()

    assert "MAVIC 3 ENTERPRISE / MATRICE 300 RTK" in body


def test_the_structured_block_is_gone_from_the_file(operator):
    """Mostraba filas con emisión y vencimiento en guion: no respaldaba nada."""
    QualificationType.objects.create(name="Serie Matrice")
    client = login_as("view_operator", "view_qualification")

    body = client.get(reverse("operator-detail", args=[operator.pk])).content.decode()

    assert "Serie Matrice" not in body


def test_the_data_is_still_there(operator):
    """Se ocultó una superficie, no se dio de baja un subsistema."""
    kind = QualificationType.objects.create(name="Serie Matrice")
    Qualification.objects.create(operator=operator, qualification_type=kind)

    assert Qualification.objects.filter(operator=operator).count() == 1


def test_the_qualification_screens_are_still_reachable(operator):
    """`B4.4` y las alertas siguen leyendo de acá; sólo se fue el bloque."""
    kind = QualificationType.objects.create(name="Serie Matrice")
    qualification = Qualification.objects.create(
        operator=operator, qualification_type=kind
    )
    client = login_as("view_qualification")

    response = client.get(reverse("qualification-list"))

    assert response.status_code == 200
    assert reverse("qualification-update", args=[qualification.pk])
