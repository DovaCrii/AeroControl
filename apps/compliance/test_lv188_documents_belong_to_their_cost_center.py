"""LV-188: un documento pertenece a la faena del registro del que cuelga.

Encontrado el 2026-08-31 al verificar `LV-187`, que a su vez salió del pendiente
anotado en el test de `LV-186`.

`documents_for_cost_center` resolvía la faena de un documento mirando **sólo
`Aircraft` y `Operator`**, mientras `ALERT_COST_CENTER_PATHS` —la tabla que el
docstring de `cost_centers_for_refs` predica como única— declara **siete**
modelos. Las dos mitades discrepaban, y se veía en el panel: la Carta Permiso
salía con el chip `CC738` y **desaparecía al filtrar por `CC738`**. La fila
afirmaba una faena y el filtro de esa misma faena la negaba.

Lo que sube esto de "una pantalla" a cumplimiento: la misma función alimenta
`alerts_for_cost_center`, el resumen diario por correo y `_cost_center_row` —el
informe por faena, que produce los KPI, el informe ejecutivo y
`ComplianceSnapshot`—, y **ahí no hay filtro de usuario de por medio**: los
documentos colgados de un permiso, de un mantenimiento, de una habilitación o de
una revisión mensual no contaban en el cumplimiento de ninguna faena, nunca.

El test que sostiene el diseño es `test_every_declared_model_survives_the_filter`:
recorre la tabla y **falla con `KeyError` si alguien agrega un modelo y no su
caso acá**, que es la forma de que un modelo faltante se vea — igual que
`test_it_agrees_with_alerts_for_cost_center` sostiene a `LV-146`.
"""

from datetime import timedelta
from itertools import count

import pytest
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from apps.compliance.models import Document, DocumentType, MonthlyComplianceReview
from apps.compliance.reports import (
    ALERT_COST_CENTER_PATHS,
    build_compliance_report,
    documents_for_cost_center,
)
from apps.maintenance.models import MaintenanceRecord
from apps.operations.models import FlightPermission
from apps.registry.models import (
    Aircraft,
    CostCenter,
    KnowledgeAssessment,
    Operator,
    Qualification,
    QualificationType,
)

TODAY = timezone.localdate()
CUTOFF = TODAY + timedelta(days=30)


@pytest.fixture
def mine(db):
    return CostCenter.objects.create(code="CC738", name="MLP")


@pytest.fixture
def other(db):
    return CostCenter.objects.create(code="CC861", name="Talabre")


def _permit(cost_center, folio="JEJ-2026-004"):
    return FlightPermission.objects.create(
        internal_folio=folio,
        cost_center=cost_center,
        purpose="survey",
        valid_from=TODAY,
        valid_until=TODAY + timedelta(days=90),
        location="Quebrada km 13",
        area_type="dan_91",
    )


def _document(subject, title="Carta Permiso", days=10):
    return Document.objects.create(
        title=title,
        doc_type=DocumentType.objects.get_or_create(
            code="permit-letter", defaults={"name": "Carta Permiso"}
        )[0],
        content_type=ContentType.objects.get_for_model(type(subject)),
        object_id=subject.pk,
        issue_date=TODAY - timedelta(days=1),
        expiry_date=TODAY + timedelta(days=days),
        is_current_version=True,
    )


def _current_documents():
    return Document.objects.filter(is_active=True, is_current_version=True)


# Un sujeto de cada modelo con faena declarada. Es un mapa y no una cadena de
# `if`s por la misma razón que `ALERT_COST_CENTER_PATHS` lo es: el día que la
# tabla crezca, este diccionario es lo que hay que completar, y el test de abajo
# **falla** si falta una entrada en vez de pasar cubriendo seis de siete.
def _subject_factories():
    # `employee_id` y `registration` son únicos por tenant, y tres de los siete
    # modelos cuelgan de un operador o de una aeronave: sin el contador, el
    # segundo sujeto choca contra el primero.
    serial = count(1)

    def operator_of(cost_center):
        return Operator.objects.create(
            employee_id=f"E-{next(serial)}",
            full_name="Ana Rivas",
            cost_center=cost_center,
        )

    def aircraft_of(cost_center):
        index = next(serial)
        return Aircraft.objects.create(
            registration=f"RPA-{index}",
            serial_number=f"SN-{index}",
            cost_center=cost_center,
        )

    return {
        "registry.aircraft": aircraft_of,
        "registry.operator": operator_of,
        "registry.qualification": lambda cc: Qualification.objects.create(
            operator=operator_of(cc),
            qualification_type=QualificationType.objects.get_or_create(
                code="MR", defaults={"name": "Multirotor"}
            )[0],
            expiry_date=TODAY + timedelta(days=60),
        ),
        "registry.knowledgeassessment": lambda cc: KnowledgeAssessment.objects.create(
            operator=operator_of(cc),
            question_count=10,
            correct_count=9,
            score_percent=90,
            passed=True,
            expires_on=TODAY + timedelta(days=300),
        ),
        "operations.flightpermission": _permit,
        "maintenance.maintenancerecord": lambda cc: MaintenanceRecord.objects.create(
            aircraft=aircraft_of(cc),
            maintenance_type="preventive",
            description="Revisión de hélices",
            scheduled_date=TODAY,
        ),
        "compliance.monthlycompliancereview": (
            lambda cc: MonthlyComplianceReview.objects.create(
                cost_center=cc, period=TODAY.replace(day=1)
            )
        ),
    }


@pytest.mark.django_db
class TestWhatWasBroken:
    def test_a_permit_letter_survives_the_filter_of_its_own_cost_center(self, mine):
        """El caso exacto reproducido: la fila decía `CC738` y al filtrar por
        `CC738` la lista quedaba vacía."""
        _document(_permit(mine))

        assert documents_for_cost_center(mine, _current_documents()).count() == 1

    def test_the_panel_row_and_the_panel_filter_agree(self, mine):
        """El invariante en la pantalla donde el usuario lo vio: lo que la fila
        afirma —el chip de faena, que pone `cost_centers_for_refs`— es lo que el
        filtro de esa faena devuelve. Antes el chip decía `CC738` y el filtro la
        borraba."""
        from apps.dashboard.views import upcoming_expirations

        _document(_permit(mine))
        Aircraft.objects.create(registration="RPA-1", serial_number="S1")

        sin_filtro = upcoming_expirations(TODAY, CUTOFF)
        con_filtro = upcoming_expirations(TODAY, CUTOFF, mine)

        atribuidas = {
            item["label"] for item in sin_filtro if item["cost_center_code"] == "CC738"
        }
        assert atribuidas == {"Carta Permiso"}
        assert atribuidas == {item["label"] for item in con_filtro}

    def test_the_compliance_report_counts_it(self, mine):
        """La mitad grave: acá no hay filtro de usuario de por medio. Una carta
        de permiso vencida no contaba como vencida en ninguna faena."""
        _document(_permit(mine), days=-5)

        row = build_compliance_report(cost_center=mine)["by_cost_center"][0]

        assert row["total"] == 1
        assert row["expired"] == 1

    def test_every_declared_model_survives_the_filter(self, mine):
        """**El test que sostiene el diseño.** Un documento colgado de cada
        modelo con faena declarada sobrevive al filtro de su faena.

        `_subject_factories()[label]` levanta `KeyError` si la tabla crece y este
        archivo no: un modelo que falte se ve, que es la misma promesa que el
        comentario de `ALERT_COST_CENTER_PATHS` hace.
        """
        factories = _subject_factories()

        for label in ALERT_COST_CENTER_PATHS:
            subject = factories[label](mine)
            document = _document(subject, title=f"Doc de {label}")

            found = documents_for_cost_center(mine, _current_documents())

            assert document.pk in set(found.values_list("pk", flat=True)), label


@pytest.mark.django_db
class TestWhatStillHasToStayOut:
    def test_another_cost_centers_document_stays_out(self, mine, other):
        """El contrapeso: extender la tabla no puede abrir la puerta a todo."""
        _document(_permit(other, folio="JEJ-2026-009"))

        assert documents_for_cost_center(mine, _current_documents()).count() == 0

    def test_a_company_document_belongs_to_no_cost_center(self, mine):
        """Cuelga del tenant, no de un registro. Sin faena no es de ninguna, y
        el filtro es lo que lo deja fuera — no un caso especial escrito aparte."""
        Document.objects.create(
            title="Manual de operaciones",
            doc_type=DocumentType.objects.create(code="manual", name="Manual"),
            content_type=ContentType.objects.get_for_model(CostCenter),
            object_id="00000000-0000-0000-0000-000000000000",
            issue_date=TODAY - timedelta(days=1),
            expiry_date=TODAY + timedelta(days=10),
        )

        assert documents_for_cost_center(mine, _current_documents()).count() == 0

    def test_an_archived_subject_drops_out(self, mine):
        """El criterio que la lista corta ya tenía y que esta fila **no**
        cambia: un documento se cuenta como trabajo de cumplimiento, y el de un
        registro archivado no lo es. Es lo único que distingue este recorrido del
        de las alertas, donde el archivado sí entra porque ahí se atribuye en vez
        de contar."""
        permit = _permit(mine)
        _document(permit)
        permit.is_active = False
        permit.save(update_fields=["is_active"])

        assert documents_for_cost_center(mine, _current_documents()).count() == 0

    def test_no_subjects_at_all_means_no_documents_not_all_of_them(self, mine, other):
        """`Q(pk__in=[])` es el neutro del `|`. Con la faena sin un solo
        registro, el resultado tiene que ser vacío y no la tabla entera — el modo
        de fallar que un `Q()` vacío habría producido en silencio."""
        _document(_permit(other, folio="JEJ-2026-009"))

        assert documents_for_cost_center(mine, _current_documents()).count() == 0


@pytest.mark.django_db
class TestWhatItCosts:
    def test_it_is_one_query_and_does_not_grow_with_the_table(
        self, mine, django_assert_num_queries
    ):
        """El informe llama a esto **una vez por faena**, así que resolver siete
        modelos con siete consultas habría multiplicado por tres el costo de una
        pantalla que ya existía. Van como subconsulta: una sola consulta, y los
        ids no viajan a Python para volver a la base."""
        for index in range(5):
            _document(_permit(mine, folio=f"JEJ-2026-{index:03d}"), title=f"C{index}")

        with django_assert_num_queries(1):
            assert documents_for_cost_center(mine, _current_documents()).count() == 5
