"""LV-240: el correo diario avisaba de dos de seis fuentes.

Encontrado en la revisión de brechas del 2026-09-21. `build_digest` tenía su propia
recolección —habilitaciones y documentos— mientras el panel recorría seis, así que
**el seguro JAC, la credencial DGAC, la prueba de conocimientos y la vigencia del
permiso salían en pantalla y no en el correo**.

⚠️ **Y la que faltaba era la única que va a buscar a la persona.** El panel exige
que alguien lo abra; el correo llega. Quien no entra a la aplicación —que es
justamente a quien el digest existe para alcanzar— no se enteraba de que caduca una
póliza. Hoy no se nota en producción porque `EMAIL_HOST` está vacío y no ha salido
un solo correo: se habría notado el día de encender el SMTP, que es el peor momento
para descubrir que el aviso es parcial.

La causa era una dependencia al revés: `digest` no podía importar de
`dashboard.views`, que a su vez lo importa a él. La recolección se mudó a
`compliance.expirations` y ahora las dos superficies leen la misma.
"""

from datetime import timedelta

import pytest
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from apps.compliance.digest import build_digest
from apps.compliance.models import Alert, AlertRule, Document, DocumentType
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
SOON = TODAY + timedelta(days=10)


@pytest.fixture
def centre(db):
    return CostCenter.objects.create(code="CC738", name="Faena", operates_flights=True)


def _labels(buckets):
    return {item["label"] for items in buckets.values() for item in items}


def _details(buckets):
    return {item["detail"] for items in buckets.values() for item in items}


class TestTheFourSourcesThatNeverReachedTheInbox:
    @pytest.mark.django_db
    def test_a_lapsing_jac_insurance_is_in_the_digest(self, centre):
        Aircraft.objects.create(
            registration="RPA-9001",
            type="RPA",
            model="M3",
            manufacturer="DJI",
            cost_center=centre,
            status="active",
            insurance_expiry=SOON,
        )

        assert "RPA-9001" in _labels(build_digest(centre, today=TODAY))

    @pytest.mark.django_db
    def test_a_lapsing_dgac_credential_is_in_the_digest(self, centre):
        Operator.objects.create(
            employee_id="E1",
            full_name="Ana Pérez",
            cost_center=centre,
            credential_expiry=SOON,
        )

        assert "Ana Pérez" in _labels(build_digest(centre, today=TODAY))

    @pytest.mark.django_db
    def test_a_lapsing_knowledge_assessment_is_in_the_digest(self, centre):
        operator = Operator.objects.create(
            employee_id="E1", full_name="Ana Pérez", cost_center=centre
        )
        KnowledgeAssessment.objects.create(
            operator=operator,
            taken_at=TODAY - timedelta(days=355),
            expires_on=SOON,
            question_count=25,
            correct_count=23,
            score_percent=92,
            passed=True,
        )

        buckets = build_digest(centre, today=TODAY)

        assert any(
            "Ana Pérez" in item["label"] for items in buckets.values() for item in items
        )

    @pytest.mark.django_db
    def test_a_lapsing_permit_is_in_the_digest(self, centre):
        permit = FlightPermission.objects.create(
            cost_center=centre,
            purpose="photogrammetry",
            status=FlightPermission.STATUS_APPROVED,
            location="Sector",
            area_type="unpopulated",
            valid_from=TODAY - timedelta(days=60),
            valid_until=SOON,
        )

        assert permit.internal_folio in _labels(build_digest(centre, today=TODAY))

    @pytest.mark.django_db
    def test_every_line_says_what_kind_of_expiry_it_is(self, centre):
        """Con seis orígenes conviviendo en una lista, saber qué es cada línea
        manda sobre el resto — y el sujeto ya viene en la etiqueta."""
        Aircraft.objects.create(
            registration="RPA-9001",
            type="RPA",
            model="M3",
            manufacturer="DJI",
            cost_center=centre,
            status="active",
            insurance_expiry=SOON,
        )
        Operator.objects.create(
            employee_id="E1",
            full_name="Ana Pérez",
            cost_center=centre,
            credential_expiry=SOON,
        )

        details = _details(build_digest(centre, today=TODAY))

        assert len(details) == 2
        assert all(detail for detail in details)


class TestTheRulesThatCameWithTheSharedCollection:
    @pytest.mark.django_db
    def test_a_resolved_expiry_stops_arriving_every_morning(self, centre):
        """⚠️ **La regla que más importa en un correo diario.**

        `LV-122` la trajo al panel: un vencimiento resuelto y no renovado tiene una
        fecha que no va a cambiar nunca, así que sin esto se queda para siempre. En
        una pantalla eso llena la lista; en un correo **que sale cada mañana** es lo
        que enseña a no abrirlo, la lección de `LV-118`.
        """
        operator = Operator.objects.create(
            employee_id="E1",
            full_name="Ana Pérez",
            cost_center=centre,
            credential_expiry=TODAY - timedelta(days=200),
        )
        rule = AlertRule.objects.create(
            name="Credencial",
            entity_type="registry.operator",
            field_to_watch="credential_expiry",
            days_before_expiry=30,
        )
        Alert.objects.create(
            alert_rule=rule,
            content_type=ContentType.objects.get_for_model(Operator),
            object_id=operator.pk,
            watched_value=operator.credential_expiry.isoformat(),
            is_resolved=True,
        )

        assert "Ana Pérez" not in _labels(build_digest(centre, today=TODAY))

    @pytest.mark.django_db
    def test_a_retired_aircraft_does_not_generate_mail(self, centre):
        """`LV-90`/`LV-113`: el estado terminal se lee del propio modelo. Una
        aeronave dada de baja con el seguro vencido no es trabajo de nadie."""
        Aircraft.objects.create(
            registration="RPA-9002",
            type="RPA",
            model="M3",
            manufacturer="DJI",
            cost_center=centre,
            status="retired",
            insurance_expiry=TODAY - timedelta(days=30),
        )

        assert "RPA-9002" not in _labels(build_digest(centre, today=TODAY))

    @pytest.mark.django_db
    def test_another_cost_centres_expiry_stays_out(self, centre):
        """El digest se manda al responsable de **esta** faena."""
        other = CostCenter.objects.create(code="CC861", name="Otra")
        Aircraft.objects.create(
            registration="RPA-9003",
            type="RPA",
            model="M3",
            manufacturer="DJI",
            cost_center=other,
            status="active",
            insurance_expiry=SOON,
        )

        assert "RPA-9003" not in _labels(build_digest(centre, today=TODAY))


class TestWhatAlreadyWorkedKeepsWorking:
    @pytest.mark.django_db
    def test_qualifications_and_documents_are_still_there(self, centre):
        """Las dos fuentes que el correo sí cubría. Se afirman juntas porque lo que
        esta fila cambia es **de dónde salen**, y un traslado que gana cuatro
        fuentes perdiendo las dos que había no sería una mejora."""
        operator = Operator.objects.create(
            employee_id="E1", full_name="Ana Pérez", cost_center=centre
        )
        qtype = QualificationType.objects.create(code="mavic", name="Serie Mavic")
        Qualification.objects.create(
            operator=operator, qualification_type=qtype, expiry_date=SOON
        )
        aircraft = Aircraft.objects.create(
            registration="RPA-9004",
            type="RPA",
            model="M3",
            manufacturer="DJI",
            cost_center=centre,
            status="active",
        )
        dtype = DocumentType.objects.create(
            code="airworthiness", name="Aeronavegabilidad"
        )
        Document.objects.create(
            title="Certificado",
            doc_type=dtype,
            content_type=ContentType.objects.get_for_model(Aircraft),
            object_id=aircraft.pk,
            file_path="doc.pdf",
            issue_date=TODAY,
            expiry_date=SOON,
        )

        labels = _labels(build_digest(centre, today=TODAY))

        assert "Ana Pérez — Serie Mavic" in labels
        assert "Certificado" in labels

    @pytest.mark.django_db
    def test_every_line_still_carries_a_link(self, centre):
        """Las plantillas del correo componen `base_url` + `url_path`; una línea sin
        enlace deja al lector sin dónde ir a resolverla."""
        Aircraft.objects.create(
            registration="RPA-9005",
            type="RPA",
            model="M3",
            manufacturer="DJI",
            cost_center=centre,
            status="active",
            insurance_expiry=SOON,
        )

        buckets = build_digest(centre, today=TODAY)

        items = [item for group in buckets.values() for item in group]
        assert items
        assert all(item["url_path"].startswith("/") for item in items)
