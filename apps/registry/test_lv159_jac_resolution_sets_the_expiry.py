"""LV-159: la Resolución de la JAC pone la vigencia del seguro en la aeronave.

Reportado por el usuario con captura de producción sobre `RPA-5534`: *"revisar,
subí la resolución JAC, sigue el error, revisar esta situación y corregir"*. La
ficha decía **"Póliza en ficha vigente hasta el 2026-08-08 · Vencida"** teniendo
adjunta la *Resolución Exenta JAC (aprueba seguro RPA)* con vencimiento
**2027-08-24**.

El círculo estaba cortado en el último tramo: `LV-117` creó el tipo de documento
y lo llamó "el papel que cierra el ciclo", `LV-81` modeló el ciclo del estado y
`LV-81b` arregló la presentación — y nadie llevaba la fecha del papel al campo.

Y la regla de fondo la fijó el usuario el mismo día, textual: *"ahí lo que manda
más que la póliza es la resolución de la JAC; que esté hoy autorizado, es el
verificador"*. Por eso la resolución mueve **la fecha y el estado**: si el acto
que autoriza está en ficha y vigente, la aeronave está autorizada.

El test que reproduce el reporte es
`test_the_reported_case_stops_saying_the_policy_lapsed`, y falla sin el fix.
"""

from datetime import timedelta

import pytest
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from apps.compliance.models import Document, DocumentType
from apps.registry.insurance import jac_approval_expiry, sync_insurance_expiry
from apps.registry.models import Aircraft

TODAY = timezone.localdate()


@pytest.fixture
def resolution_type(db):
    return DocumentType.objects.create(
        name="Resolución Exenta JAC (aprueba seguro RPA)",
        code="jac-insurance-approval",
        requires_expiry=True,
    )


@pytest.fixture
def other_type(db):
    return DocumentType.objects.create(
        name="Certificado de seguro de responsabilidad civil",
        code="liability-insurance",
        requires_expiry=True,
    )


def _aircraft(**kwargs):
    return Aircraft.objects.create(
        registration=kwargs.pop("registration", "RPA-5534"),
        type="Multirotor",
        model="MATRICE 4 ENTERPRISE",
        manufacturer="DJI",
        **kwargs,
    )


def _document(doc_type, aircraft, expiry, **kwargs):
    return Document.objects.create(
        doc_type=doc_type,
        title=f"{doc_type.name} · {aircraft.registration}",
        issue_date=kwargs.pop("issue_date", TODAY),
        expiry_date=expiry,
        content_type=ContentType.objects.get_for_model(Aircraft),
        object_id=aircraft.pk,
        **kwargs,
    )


@pytest.mark.django_db
class TestTheReportedCase:
    def test_the_reported_case_stops_saying_the_policy_lapsed(self, resolution_type):
        # El caso exacto de la captura: póliza en ficha vencida el 2026-08-08 y
        # la resolución que la renueva hasta 2027-08-24, adjunta.
        aircraft = _aircraft(
            insurance_expiry=TODAY - timedelta(days=18),
            insurance_status=Aircraft.INSURANCE_STATUS_ACTIVE,
        )

        _document(resolution_type, aircraft, TODAY + timedelta(days=363))
        aircraft.refresh_from_db()

        assert aircraft.insurance_expiry == TODAY + timedelta(days=363)
        assert aircraft.insurance_is_overdue is False

    def test_the_stepper_no_longer_ends_in_lapsed(self, resolution_type):
        aircraft = _aircraft(
            insurance_expiry=TODAY - timedelta(days=18),
            insurance_status=Aircraft.INSURANCE_STATUS_ACTIVE,
        )

        _document(resolution_type, aircraft, TODAY + timedelta(days=363))
        aircraft.refresh_from_db()

        assert aircraft.insurance_steps()[-1]["state"] != "blocked"


@pytest.mark.django_db
class TestTheResolutionIsTheVerifier:
    def test_it_also_declares_the_policy_in_force(self, resolution_type):
        # Decisión del usuario: la resolución es el verificador, así que el estado
        # sigue al papel. No es adelantarse al papel -- es lo contrario.
        aircraft = _aircraft(insurance_status=Aircraft.INSURANCE_STATUS_FILED)

        _document(resolution_type, aircraft, TODAY + timedelta(days=365))
        aircraft.refresh_from_db()

        assert aircraft.insurance_status == Aircraft.INSURANCE_STATUS_ACTIVE

    def test_it_lifts_a_filing_that_never_had_a_date(self, resolution_type):
        aircraft = _aircraft(insurance_status=Aircraft.INSURANCE_STATUS_MISSING)

        _document(resolution_type, aircraft, TODAY + timedelta(days=365))
        aircraft.refresh_from_db()

        assert aircraft.insurance_expiry == TODAY + timedelta(days=365)
        assert aircraft.insurance_status == Aircraft.INSURANCE_STATUS_ACTIVE

    def test_the_jump_is_recorded_in_the_filing_history(self, resolution_type):
        # El historial del trámite tiene que contar este salto igual que si
        # alguien hubiera apretado el botón: es evidencia, no un efecto interno.
        aircraft = _aircraft(insurance_status=Aircraft.INSURANCE_STATUS_FILED)

        _document(resolution_type, aircraft, TODAY + timedelta(days=365))

        assert aircraft.insurance_history.filter(
            new_status=Aircraft.INSURANCE_STATUS_ACTIVE
        ).exists()

    def test_an_expired_resolution_does_not_demote_the_status(self, resolution_type):
        # Decir "vencida" es más honesto que borrar que alguna vez estuvo
        # autorizada: de eso se encarga la presentación de LV-81b.
        aircraft = _aircraft(
            insurance_expiry=TODAY + timedelta(days=200),
            insurance_status=Aircraft.INSURANCE_STATUS_ACTIVE,
        )

        _document(resolution_type, aircraft, TODAY - timedelta(days=30))
        aircraft.refresh_from_db()

        assert aircraft.insurance_status == Aircraft.INSURANCE_STATUS_ACTIVE
        assert aircraft.insurance_expiry == TODAY + timedelta(days=200)


@pytest.mark.django_db
class TestWhatItRefusesToTouch:
    def test_an_older_resolution_does_not_pull_the_date_back(self, resolution_type):
        # Una renovación siempre empuja hacia adelante: un papel con fecha
        # anterior es un documento viejo que se archiva, no una renovación.
        aircraft = _aircraft(insurance_expiry=TODAY + timedelta(days=300))

        _document(resolution_type, aircraft, TODAY + timedelta(days=100))
        aircraft.refresh_from_db()

        assert aircraft.insurance_expiry == TODAY + timedelta(days=300)

    def test_another_document_type_changes_nothing(self, other_type):
        # El certificado de la póliza no es el acto que autoriza. Si cualquier
        # documento con vencimiento moviera la fecha, la columna de seguro pasaría
        # a depender de qué se subió último.
        aircraft = _aircraft(insurance_expiry=TODAY + timedelta(days=10))

        _document(other_type, aircraft, TODAY + timedelta(days=900))
        aircraft.refresh_from_db()

        assert aircraft.insurance_expiry == TODAY + timedelta(days=10)

    def test_a_resolution_without_an_expiry_changes_nothing(self, resolution_type):
        aircraft = _aircraft(insurance_expiry=TODAY + timedelta(days=10))

        _document(resolution_type, aircraft, None)
        aircraft.refresh_from_db()

        assert aircraft.insurance_expiry == TODAY + timedelta(days=10)

    def test_a_resolution_on_another_aircraft_does_not_cross_over(
        self, resolution_type
    ):
        mine = _aircraft(registration="RPA-5534", insurance_expiry=TODAY)
        other = _aircraft(registration="RPA-4436")

        _document(resolution_type, other, TODAY + timedelta(days=365))
        mine.refresh_from_db()

        assert mine.insurance_expiry == TODAY

    def test_an_archived_resolution_is_ignored(self, resolution_type):
        aircraft = _aircraft(insurance_expiry=TODAY)
        document = _document(resolution_type, aircraft, TODAY + timedelta(days=365))
        document.is_active = False
        document.save(update_fields=["is_active"])
        aircraft.insurance_expiry = TODAY
        aircraft.save(update_fields=["insurance_expiry"])

        assert jac_approval_expiry(aircraft) is None


@pytest.mark.django_db
class TestTheHelperOnItsOwn:
    def test_it_takes_the_furthest_of_two_resolutions(self, resolution_type):
        # Con dos resoluciones vigentes -- pasa al ampliar cobertura -- la que
        # importa es la que llega más lejos: es la que de verdad tiene autorizada
        # la aeronave.
        aircraft = _aircraft()
        _document(resolution_type, aircraft, TODAY + timedelta(days=100))
        _document(resolution_type, aircraft, TODAY + timedelta(days=400))

        assert jac_approval_expiry(aircraft) == TODAY + timedelta(days=400)

    def test_it_reports_nothing_to_move_when_the_date_is_already_further(
        self, resolution_type
    ):
        aircraft = _aircraft(
            insurance_expiry=TODAY + timedelta(days=500),
            insurance_status=Aircraft.INSURANCE_STATUS_ACTIVE,
        )
        _document(resolution_type, aircraft, TODAY + timedelta(days=100))
        aircraft.refresh_from_db()

        assert sync_insurance_expiry(aircraft) is None

    def test_it_reports_nothing_without_a_resolution(self):
        aircraft = _aircraft()

        assert sync_insurance_expiry(aircraft) is None


@pytest.mark.django_db
class TestTheBackfillCommand:
    """La señal arregla de aquí en adelante; esto arregla lo que ya está cargado.

    `RPA-5534` tenía su resolución adjunta desde el 2026-08-24 y la ficha seguía
    diciendo "Vencida": sin una pasada, el reporte del usuario no se resuelve
    hasta que alguien vuelva a subir el mismo papel.
    """

    def _stale(self, resolution_type):
        """Una aeronave con la resolución en ficha y la fecha vieja, como en producción.

        Se escribe la fecha vieja **después** de crear el documento, porque la
        señal ya la habría corregido: así el estado inicial es el de producción.
        """
        aircraft = _aircraft(insurance_status=Aircraft.INSURANCE_STATUS_FILED)
        _document(resolution_type, aircraft, TODAY + timedelta(days=363))
        Aircraft.objects.filter(pk=aircraft.pk).update(
            insurance_expiry=TODAY - timedelta(days=18),
            insurance_status=Aircraft.INSURANCE_STATUS_FILED,
        )
        return Aircraft.objects.get(pk=aircraft.pk)

    def test_a_dry_run_changes_nothing(self, resolution_type):
        from io import StringIO

        from django.core.management import call_command

        aircraft = self._stale(resolution_type)
        out = StringIO()

        call_command("sync_jac_insurance", stdout=out)
        aircraft.refresh_from_db()

        assert aircraft.insurance_expiry == TODAY - timedelta(days=18)
        assert "RPA-5534" in out.getvalue()
        assert "1 aircraft would change" in out.getvalue()

    def test_apply_writes_the_resolution_date(self, resolution_type):
        from io import StringIO

        from django.core.management import call_command

        aircraft = self._stale(resolution_type)

        call_command("sync_jac_insurance", "--apply", stdout=StringIO())
        aircraft.refresh_from_db()

        assert aircraft.insurance_expiry == TODAY + timedelta(days=363)
        assert aircraft.insurance_status == Aircraft.INSURANCE_STATUS_ACTIVE

    def test_it_is_idempotent(self, resolution_type):
        from io import StringIO

        from django.core.management import call_command

        self._stale(resolution_type)
        call_command("sync_jac_insurance", "--apply", stdout=StringIO())
        out = StringIO()

        call_command("sync_jac_insurance", "--apply", stdout=out)

        assert "0 aircraft updated" in out.getvalue()

    def test_an_aircraft_without_a_resolution_is_left_alone(self, resolution_type):
        from io import StringIO

        from django.core.management import call_command

        aircraft = _aircraft(registration="RPA-4436", insurance_expiry=TODAY)
        out = StringIO()

        call_command("sync_jac_insurance", "--apply", stdout=out)
        aircraft.refresh_from_db()

        assert aircraft.insurance_expiry == TODAY
        assert "RPA-4436" not in out.getvalue()
