"""LV-156 y LV-157: aprobar exige el papel de la DGAC y su número.

Dos puertas traseras alrededor de la regla que el usuario llamó **crítica**
(*"si no se sube la aprobación de la DGAC no se puede pasar a estado de
aprobado"*):

- `LV-157`: `status` es un campo del formulario de **alta**, así que crear el
  permiso eligiendo "Aprobado" en el desplegable lo dejaba aprobado sin pasar
  nunca por `RequireDgacPermitPdfMixin`. Y en el alta la compuerta no se puede
  cumplir: no hay dónde adjuntar un documento a un permiso que no existe. Es la
  misma puerta que `LV-101` cerró en la pantalla de edición.
- `LV-156`: la regla *"un permiso aprobado necesita su número de la DGAC"* vivía
  sólo en `FlightPermissionForm.clean`, y el botón que aprueba de verdad no la
  comprobaba. De ahí `JEJ-2026-003`, aprobado y luego completado con el
  subtítulo `DGAC: En proceso`.

`objects.create()` sigue pudiendo montar un permiso aprobado: no llama
`full_clean`, y es el camino de los importadores y de los tests que necesitan un
permiso ya autorizado sin simular el trámite. Hay un test que lo fija.
"""

from datetime import timedelta

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from apps.compliance.models import Document, DocumentType
from apps.core.testing import login_as
from apps.operations.forms import FlightPermissionForm
from apps.operations.models import FlightPermission
from apps.registry.models import Aircraft, CostCenter, Operator

TODAY = timezone.localdate()


def _cost_center():
    return CostCenter.objects.create(code="CC738", name="MLP")


def _permission(**kwargs):
    return FlightPermission.objects.create(
        cost_center=kwargs.pop("cost_center", None) or _cost_center(),
        purpose="photogrammetry",
        area_type="unpopulated",
        status=kwargs.pop("status", "requested"),
        valid_from=TODAY,
        valid_until=TODAY + timedelta(days=30),
        **kwargs,
    )


def _authorization_for(permission):
    """El PDF firmado que la DGAC devuelve, en ficha."""
    doc_type = DocumentType.objects.create(
        name="Autorización de Operación RPA",
        code="dgac-rpa-operation-authorization",
    )
    return Document.objects.create(
        doc_type=doc_type,
        title="Autorización 6405",
        issue_date=TODAY,
        content_type=ContentType.objects.get_for_model(FlightPermission),
        object_id=permission.pk,
    )


def _form_data(cost_center, **overrides):
    # El roster es obligatorio (OPS-4): un permiso autoriza a alguien a volar
    # algo, así que el payload mínimo trae un operador y una aeronave.
    operator = Operator.objects.create(employee_id="E-1", full_name="Ana Rivas")
    aircraft = Aircraft.objects.create(
        registration="RPA-4883", type="Multirotor", model="M3E", manufacturer="DJI"
    )
    data = {
        "status": "requested",
        "permission_number": "",
        "operators": [operator.pk],
        "aircraft_fleet": [aircraft.pk],
        "cost_center": cost_center.pk,
        "purpose": "photogrammetry",
        "purpose_detail": "",
        "valid_from": TODAY.isoformat(),
        "valid_until": (TODAY + timedelta(days=30)).isoformat(),
        "location": "Salamanca",
        "region": "",
        "commune": "",
        "area_name": "",
        "latitude": "",
        "longitude": "",
        "radius_km": "",
        "max_altitude_ft": "",
        "area_type": "unpopulated",
    }
    data.update(overrides)
    return data


@pytest.mark.django_db
class TestANewPermitCannotBeBornApproved:
    def test_the_create_form_does_not_offer_approved(self):
        offered = {
            value for value, _label in FlightPermissionForm().fields["status"].choices
        }

        assert offered == {"requested", "denied"}

    def test_posting_approved_to_the_create_form_is_rejected(self):
        # Sin el fix esto creaba un permiso aprobado sin la autorización en
        # ficha, que es lo que el usuario llamó crítico.
        cost_center = _cost_center()

        form = FlightPermissionForm(data=_form_data(cost_center, status="approved"))

        assert not form.is_valid()
        assert "status" in form.errors

    def test_a_permit_can_still_be_born_requested(self):
        cost_center = _cost_center()

        form = FlightPermissionForm(data=_form_data(cost_center))

        assert form.is_valid(), form.errors

    def test_a_permit_can_still_be_born_denied(self):
        # Denegado no es un paso del flujo, es donde se detiene: no exige papel
        # porque no autoriza nada.
        cost_center = _cost_center()

        form = FlightPermissionForm(data=_form_data(cost_center, status="denied"))

        assert form.is_valid(), form.errors

    def test_the_model_mirrors_the_rule(self):
        permission = FlightPermission(
            cost_center=_cost_center(),
            purpose="photogrammetry",
            area_type="unpopulated",
            status="approved",
            valid_from=TODAY,
            valid_until=TODAY + timedelta(days=30),
        )

        with pytest.raises(ValidationError) as raised:
            permission.full_clean()

        assert "status" in raised.value.message_dict

    def test_objects_create_can_still_build_an_approved_permit(self):
        # A propósito: `objects.create()` no llama `full_clean`, y es el camino
        # de los importadores y de los tests que montan un permiso ya autorizado.
        permission = _permission(status="approved", permission_number="6405")

        assert permission.status == "approved"

    def test_editing_an_approved_permit_is_not_blocked_by_the_rule(self):
        # La regla es sobre **nacer** aprobado. Editar la ubicación de un permiso
        # ya aprobado no puede quedar bloqueado por ella.
        permission = _permission(status="approved", permission_number="6405")

        permission.location = "Salamanca"
        permission.full_clean()


@pytest.mark.django_db
class TestApprovingNeedsTheNumber:
    def test_approving_without_the_number_is_refused(self):
        permission = _permission()
        _authorization_for(permission)
        client = login_as("change_flightpermission", "view_flightpermission")

        response = client.post(
            reverse("permission-approve", args=[permission.pk]), follow=True
        )
        permission.refresh_from_db()

        assert permission.status == "requested"
        assert any("DGAC" in str(m) for m in response.context["messages"])

    def test_approving_with_the_number_and_the_pdf_works(self):
        permission = _permission(permission_number="6405")
        _authorization_for(permission)
        client = login_as("change_flightpermission", "view_flightpermission")

        client.post(reverse("permission-approve", args=[permission.pk]))
        permission.refresh_from_db()

        assert permission.status == "approved"

    def test_the_pdf_is_still_required(self):
        # La compuerta de LV-64 no se pierde al agregar la del número: sin el
        # PDF no se aprueba aunque el número esté.
        permission = _permission(permission_number="6405")
        client = login_as("change_flightpermission", "view_flightpermission")

        client.post(reverse("permission-approve", args=[permission.pk]))
        permission.refresh_from_db()

        assert permission.status == "requested"

    def test_it_is_403_without_change_permission(self):
        permission = _permission(permission_number="6405")

        response = login_as("view_flightpermission").post(
            reverse("permission-approve", args=[permission.pk])
        )

        assert response.status_code == 403
