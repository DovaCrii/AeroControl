"""LV-138: el plan geoespacial gana su folio correlativo anual.

Pedido del usuario mirando el listado: *"el id que se ve o cómo se están sumando
deben ser estandarizados, generar un id de título inicial con seguimiento de
crecimiento del 1 al infinito"*, y después: *"sumar una nueva columna así como los
permisos tienen ese estándar, así dejamos solamente el título de comentario con CC
y el nombre del KMZ"*.

El título hacía de identificador y venía en **dos formas distintas** según cómo se
hubiera importado el plan — "JEJ-2026-002 · CC861_area_permiso" con permiso, y
"CC738 - MLP · Juan Quiroz · CG-01_circunferencia_grande" sin él —, así que no se
podía citar ni ordenar. Ahora el identificador es `PG-2026-001`, correlativo anual
como el del permiso, y el título vuelve a ser el comentario.
"""

import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.geo.forms import GeoPlanImportForm
from apps.geo.models import GeoPlan
from apps.registry.models import CostCenter

YEAR = timezone.now().year


@pytest.fixture
def cost_center(db):
    return CostCenter.objects.create(code="CC738", name="MLP")


@pytest.fixture
def owner(db):
    return User.objects.create_user("owner-138", "o138@test.com", "pw")  # nosec B106


def _plan(cost_center, owner, title="Un plan"):
    return GeoPlan.objects.create(
        title=title, cost_center=cost_center, created_by=owner
    )


@pytest.mark.django_db
class TestTheFolio:
    def test_the_first_plan_of_the_year_is_001(self, cost_center, owner):
        plan = _plan(cost_center, owner)

        assert plan.folio == f"PG-{YEAR}-001"

    def test_it_grows_one_by_one(self, cost_center, owner):
        folios = [_plan(cost_center, owner, f"Plan {n}").folio for n in range(1, 4)]

        assert folios == [
            f"PG-{YEAR}-001",
            f"PG-{YEAR}-002",
            f"PG-{YEAR}-003",
        ]

    def test_it_does_not_change_when_the_plan_is_saved_again(self, cost_center, owner):
        """Un identificador que se mueve al editar deja de identificar."""
        plan = _plan(cost_center, owner)
        original = plan.folio

        plan.title = "Otro título"
        plan.save()
        plan.refresh_from_db()

        assert plan.folio == original

    def test_an_archived_plan_keeps_its_number_and_it_is_not_reused(
        self, cost_center, owner
    ):
        """Reutilizarlo haría que dos planes distintos hayan sido el mismo folio
        en momentos distintos, que es lo único que un identificador no puede
        permitirse."""
        first = _plan(cost_center, owner, "Se archiva")
        first.is_active = False
        first.save(update_fields=["is_active"])

        second = _plan(cost_center, owner, "El siguiente")

        assert first.folio == f"PG-{YEAR}-001"
        assert second.folio == f"PG-{YEAR}-002"

    def test_it_leads_the_string_representation(self, cost_center, owner):
        plan = _plan(cost_center, owner, "CC738 · CG-01_circunferencia_grande")

        assert str(plan).startswith(f"PG-{YEAR}-001 · ")


@pytest.mark.django_db
class TestTheTitleIsNowJustAComment:
    def _form(self, cost_center, file_name):
        # Un KML mínimo y válido: lo que importa acá es el título que se deriva,
        # pero el formulario valida el archivo antes de llegar a eso.
        kml = (
            b'<?xml version="1.0" encoding="UTF-8"?>'
            b'<kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
            b"<name>x</name><Placemark><name>p</name>"
            b"<Point><coordinates>-70.7,-31.9,0</coordinates></Point>"
            b"</Placemark></Document></kml>"
        )
        return GeoPlanImportForm(
            data={"cost_center": str(cost_center.pk), "title": ""},
            files={"file": SimpleUploadedFile(file_name, kml)},
        )

    def test_it_is_the_cost_center_code_and_the_file_name(self, cost_center):
        """Sin el nombre de la faena ni el responsable: los dos ya están en su
        propia columna, repetidos en cada fila."""
        form = self._form(cost_center, "CG-01_circunferencia_grande.kml")

        assert form.is_valid(), form.errors
        assert form.cleaned_data["title"] == "CC738 · CG-01_circunferencia_grande"
