"""LV-192 y LV-193: dos pedidos del usuario sobre los permisos, con captura.

**LV-192 — la faena, visible.** El listado mostraba Número, Operadores,
Aeronaves, Vigencia y Estado. La faena **iba en el CSV desde `LV-53`** y no en la
tabla: el dato con el que se agrupa el trabajo estaba en el archivo exportado y
no en la pantalla donde se decide qué permiso abrir.

**LV-193 — "Completado" seguía ofreciéndose.** Textual: *"en los permisos aún
sale completado y no está dentro del enfoque; ahora sólo solicitado, aprobado y
caducado"*. `LV-155` ya había retirado ese estado del flujo y del stepper con la
línea del usuario —*"completado no debe salir luego de aprobado; es caducado y
final se archiva"*— y **el selector de "Corregir el estado" quedó fuera**: seguía
listando `STATUS_CHOICES` completo. Lo irónico es dónde: la pantalla que existe
para arreglar un estado equivocado era la única que podía volver a escribir el
estado retirado, y el defecto que `LV-101` encontró en producción era
precisamente alguien deshaciendo un "completado" puesto por error.

Sigue siendo retiro **de pantalla y no de base**: el valor queda en
`STATUS_CHOICES` para que el filtro del listado encuentre las filas que lo tienen
(`JEJ-2026-003` en producción), y corregir un permiso *desde* completado hacia
otro estado sigue siendo posible — es lo único que se puede hacer con ellas.
"""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.core.testing import login_as
from apps.operations.forms import StatusCorrectionForm
from apps.operations.models import FlightPermission
from apps.registry.models import CostCenter

TODAY = timezone.localdate()


@pytest.fixture
def center(db):
    return CostCenter.objects.create(code="CC738", name="MLP")


def _permit(center, folio="JEJ-2026-003", status=FlightPermission.STATUS_APPROVED):
    return FlightPermission.objects.create(
        internal_folio=folio,
        cost_center=center,
        purpose="survey",
        valid_from=TODAY,
        valid_until=TODAY + timedelta(days=60),
        location="Minera Los Pelambres",
        area_type="dan_91",
        status=status,
    )


@pytest.mark.django_db
class TestTheListShowsTheCostCenter:
    def test_the_code_is_in_the_table(self, center):
        _permit(center)

        content = (
            login_as("view_flightpermission").get(reverse("permission-list"))
        ).content.decode()

        assert "CC738" in content
        assert "cc-chip" in content

    def test_it_comes_before_the_operators_column(self, center):
        """La razón de `LV-146`: los códigos son de ancho casi uniforme y los
        nombres no, así que el chip cae en la misma x en todas las filas."""
        _permit(center)
        content = (
            login_as("view_flightpermission").get(reverse("permission-list"))
        ).content.decode()

        # Los encabezados entre sí, y anclados a `scope="col"`: el chip vive en
        # el cuerpo —compararlo contra el `<th>` mediría el orden de la tabla y
        # no el de las columnas— y "Operadores" a secas está también en el menú
        # lateral, que va antes que la tabla entera.
        assert content.index('scope="col">Centro de costo') < content.index(
            'scope="col">Operadores'
        )

    def test_the_folio_stays_the_first_column(self, center):
        """La faena va segunda: el folio es el valor primario y el enlace de la
        fila, y moverlo del borde rompería la lectura de las otras listas."""
        _permit(center)
        content = (
            login_as("view_flightpermission").get(reverse("permission-list"))
        ).content.decode()

        assert content.index("JEJ-2026-003") < content.index("cc-chip")

    def test_it_does_not_cost_a_query_per_row(self, center):
        """25 filas por página en el listado que se abre para elegir un permiso.
        Sin `select_related`, leer el código costaba una consulta por fila.

        Se afirma **la propiedad y no un número**: triplicar las filas no cambia
        el conteo. Un tope fijo hay que reajustarlo cada vez que la página gana
        una consulta por cualquier otro motivo, y entonces deja de decir nada
        sobre las filas — que es lo único que este test vigila.
        """
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        client = login_as("view_flightpermission")
        client.get(reverse("permission-list"))  # calentamiento: sesión, permisos

        def consultas():
            with CaptureQueriesContext(connection) as captured:
                client.get(reverse("permission-list"))
            return len(captured)

        for index in range(3):
            _permit(center, folio=f"JEJ-2026-{index:03d}")
        con_tres = consultas()

        for index in range(3, 9):
            _permit(center, folio=f"JEJ-2026-{index:03d}")

        assert consultas() == con_tres


@pytest.mark.django_db
class TestCompletedIsNoLongerOffered:
    def test_the_correction_form_does_not_offer_it(self, center):
        values = dict(
            StatusCorrectionForm(current_status=FlightPermission.STATUS_APPROVED)
            .fields["status"]
            .choices
        )

        assert FlightPermission.STATUS_COMPLETED not in values

    def test_the_three_statuses_of_the_current_focus_are_there(self, center):
        """Lo que el usuario nombró: solicitado, aprobado y caducado. Se
        comprueba que **están**, no sólo que falta el retirado: un filtro de más
        habría dejado el selector inservible."""
        values = dict(
            StatusCorrectionForm(current_status=FlightPermission.STATUS_DENIED)
            .fields["status"]
            .choices
        )

        assert FlightPermission.STATUS_REQUESTED in values
        assert FlightPermission.STATUS_APPROVED in values
        assert FlightPermission.STATUS_EXPIRED in values

    def test_the_screen_does_not_render_it(self, center):
        permit = _permit(center)

        content = (
            login_as("view_flightpermission", "change_flightpermission")
            .get(reverse("permission-correct-status", args=[permit.pk]))
            .content.decode()
        )

        assert "Completado" not in content

    def test_a_legacy_completed_permit_can_still_be_corrected_away(self, center):
        """La mitad que no se puede romper: `JEJ-2026-003` está completado en
        producción, y corregirlo hacia otro estado es lo único que se puede hacer
        con esa fila. Si el retiro le quitara también la salida, el estado
        retirado sería permanente justo donde hay que sacarlo."""
        permit = _permit(center, status=FlightPermission.STATUS_COMPLETED)

        values = dict(
            StatusCorrectionForm(current_status=permit.status).fields["status"].choices
        )

        assert FlightPermission.STATUS_APPROVED in values
        assert FlightPermission.STATUS_COMPLETED not in values

    def test_the_list_filter_can_still_find_them(self, center):
        """Retiro de pantalla y no de base: el valor sigue en `STATUS_CHOICES`
        para que las filas que lo tienen se puedan encontrar."""
        _permit(center, status=FlightPermission.STATUS_COMPLETED)

        response = login_as("view_flightpermission").get(
            reverse("permission-list"), {"status": FlightPermission.STATUS_COMPLETED}
        )

        assert len(response.context["objects"]) == 1
