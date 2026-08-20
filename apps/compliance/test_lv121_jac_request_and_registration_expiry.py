"""LV-121: los dos huecos que aparecieron al ir a cargar RPA-7126 y RPA-7213.

1. No había tipo para la **solicitud** de aprobación de seguro que se manda a
   la JAC — sólo para la resolución que contesta (`LV-117`). Es el mismo par que
   `LV-64` separó para la DGAC: la carta que va, la autorización que vuelve.

2. El certificado del **Registro Nacional de RPA** de la DGAC no trae fecha de
   término, pero `aircraft-registration` exigía una, así que el formulario
   rechazaba el PDF real y la única salida era inventar un vencimiento.
"""

import pytest
from django.core.management import call_command

from apps.compliance.models import DocumentType


@pytest.fixture
def catalog(db):
    call_command("seed_document_types")
    return DocumentType.objects


class TestTheJacPair:
    @pytest.mark.django_db
    def test_both_halves_of_the_jac_filing_exist(self, catalog):
        """Con uno solo no se puede distinguir "presentado y esperando" de
        "aprobado", que son dos estados distintos de `Aircraft.insurance_status`
        (`LV-81`)."""
        request = catalog.get(code="jac-insurance-request")
        approval = catalog.get(code="jac-insurance-approval")

        assert request.category == DocumentType.CATEGORY_AIRCRAFT
        assert approval.category == DocumentType.CATEGORY_AIRCRAFT

    @pytest.mark.django_db
    def test_the_request_does_not_expire_but_the_resolution_does(self, catalog):
        """Una solicitud no vence: ocurrió. La resolución sí -- trae "TÉRMINO DE
        VIGENCIA" y caduca con la póliza que aprueba."""
        assert catalog.get(code="jac-insurance-request").requires_expiry is False
        assert catalog.get(code="jac-insurance-approval").requires_expiry is True


class TestTheRegistrationDoesNotExpire:
    @pytest.mark.django_db
    def test_the_seed_no_longer_demands_a_date(self, catalog):
        assert catalog.get(code="aircraft-registration").requires_expiry is False

    @pytest.mark.django_db
    def test_the_upload_form_accepts_it_without_one(self, db):
        """La mitad que importa: el defecto no era el valor de una bandera, era
        que no se podía subir el PDF que la DGAC emite."""
        from django.contrib.contenttypes.models import ContentType

        from apps.compliance.forms import DocumentForm
        from apps.registry.models import Aircraft, CostCenter

        call_command("seed_document_types")
        cost_center = CostCenter.objects.create(code="CC743", name="Faena")
        aircraft = Aircraft.objects.create(
            registration="RPA-7213",
            serial_number="1581F7FVC266P00DEDA2",
            cost_center=cost_center,
        )
        form = DocumentForm(
            data={
                "doc_type": DocumentType.objects.get(code="aircraft-registration").pk,
                "entity_type": ContentType.objects.get_for_model(Aircraft).pk,
                "object_id": str(aircraft.pk),
                "title": "Registro Nacional de RPA · RPA-7213",
                "issue_date": "2026-08-17",
                # Sin `expiry_date` a propósito: el certificado no trae ninguna.
            }
        )
        form.is_valid()

        assert "expiry_date" not in form.errors

    @pytest.mark.django_db
    def test_a_type_that_really_expires_still_demands_one(self, db):
        """El contrapeso: la exigencia sigue viva donde corresponde. Sin este
        test, relajar una bandera podría relajarlas todas sin que nadie lo note.
        """
        from django.contrib.contenttypes.models import ContentType

        from apps.compliance.forms import DocumentForm
        from apps.registry.models import Aircraft, CostCenter

        call_command("seed_document_types")
        cost_center = CostCenter.objects.create(code="CC743", name="Faena")
        aircraft = Aircraft.objects.create(
            registration="RPA-7213",
            serial_number="1581F7FVC266P00DEDA2",
            cost_center=cost_center,
        )
        form = DocumentForm(
            data={
                "doc_type": DocumentType.objects.get(code="liability-insurance").pk,
                "entity_type": ContentType.objects.get_for_model(Aircraft).pk,
                "object_id": str(aircraft.pk),
                "title": "Póliza 95131 · certificado 178",
                "issue_date": "2026-08-18",
            }
        )
        form.is_valid()

        assert "expiry_date" in form.errors


@pytest.mark.django_db
def test_the_migration_reaches_an_installation_that_already_has_the_row():
    """`seed_document_types` es idempotente por `code`, así que **no** corrige
    una fila existente -- que es el caso de todas las instalaciones en marcha.
    Sin la migración `0023`, el arreglo no llegaría a producción.
    """
    DocumentType.objects.create(
        code="aircraft-registration",
        name="Registro / matrícula de aeronave",
        requires_expiry=True,
        category=DocumentType.CATEGORY_AIRCRAFT,
    )

    call_command("seed_document_types")

    # El seed la deja intacta: esto es lo que hace necesaria la migración.
    assert (
        DocumentType.objects.get(code="aircraft-registration").requires_expiry is True
    )
