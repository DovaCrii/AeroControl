"""LV-219: la vigencia la da la DGAC, así que el alta ya no la exige.

Textual del usuario: *"voy a pedir un permiso pero no sé cuándo parte la
vigencia; ésta me la da cuando entro al SIGO de la DGAC, antes yo no lo sé"*.
Hasta acá "Vigente desde" y "Vigente hasta" eran obligatorios en el alta, así que
para poder guardar había que **inventar dos fechas** — y esas fechas alimentan el
motor de vencimientos, el panel, el informe y `expire_permissions`.

**El grueso de estos tests no es sobre el formulario, es sobre los lectores.** Un
`NULL` en una vigencia no puede leerse como "vencido" ni como "vigente": es
"todavía no se sabe". Casi todos aciertan solos porque SQL no hace coincidir un
NULL en una comparación, y precisamente por eso hay que fijarlo con tests — es un
acierto por omisión, y un `Coalesce` o un `isnull=False` añadido de buena fe en
cualquiera de esas consultas lo rompería sin que nada más se quejara.
"""

from datetime import date, timedelta

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from apps.core.testing import login_as
from apps.registry.models import Aircraft, CostCenter, Operator

from .forms import FlightPermissionForm, FlightPermissionUpdateForm
from .models import FlightPermission


def _cc(code="CC1"):
    return CostCenter.objects.create(code=code, name=code, operates_flights=True)


def _requested(cc, **extra):
    """Un permiso como el que el usuario describe: pedido, sin vigencia."""
    extra.setdefault("status", FlightPermission.STATUS_REQUESTED)
    return FlightPermission.objects.create(
        cost_center=cc,
        purpose="photogrammetry",
        location="Site",
        area_type="unpopulated",
        **extra,
    )


def _roster(cc):
    """Un operador y una aeronave, que el formulario del permiso exige."""
    operator = Operator.objects.create(
        employee_id="P1", full_name="Pilot One", cost_center=cc
    )
    aircraft = Aircraft.objects.create(
        registration="CC-AAA",
        type="Fixed",
        model="A",
        manufacturer="Maker",
        cost_center=cc,
    )
    return operator, aircraft


def _attach_signed_authorization(permission):
    """La autorización firmada en ficha, que la compuerta de aprobación exige.

    Sin esto, `RequireDgacPermitPdfMixin` rechaza antes y el test de la compuerta
    de vigencia no llega a ejecutarse (ver su docstring).
    """
    from django.contrib.contenttypes.models import ContentType

    from apps.compliance.models import Document, DocumentType
    from apps.operations.dossier import SIGNED_AUTHORIZATION

    doc_type, _made = DocumentType.objects.get_or_create(
        code=SIGNED_AUTHORIZATION,
        defaults={"name": SIGNED_AUTHORIZATION, "requires_expiry": False},
    )
    return Document.objects.create(
        title=SIGNED_AUTHORIZATION,
        doc_type=doc_type,
        content_type=ContentType.objects.get_for_model(FlightPermission),
        object_id=permission.pk,
        issue_date=date(2026, 8, 14),
        file_path=f"{SIGNED_AUTHORIZATION}/x.pdf",
    )


_FORM_BASE = {
    "purpose": "photogrammetry",
    "location": "Site",
    "area_type": "unpopulated",
}


class TestAPermitCanBeRequestedWithoutDates:
    """El caso literal del usuario."""

    @pytest.mark.django_db
    def test_the_model_accepts_a_requested_permit_with_no_validity(self, db):
        permission = _requested(_cc())

        permission.full_clean()  # no levanta

        assert permission.valid_from is None
        assert permission.valid_until is None

    @pytest.mark.django_db
    def test_the_creation_form_does_not_ask_for_them(self, db):
        cc = _cc()
        operator, aircraft = _roster(cc)
        form = FlightPermissionForm(
            data={
                **_FORM_BASE,
                "status": "requested",
                "cost_center": str(cc.pk),
                "operators": [str(operator.pk)],
                "aircraft_fleet": [str(aircraft.pk)],
            }
        )

        assert form.is_valid(), form.errors
        assert form.cleaned_data["valid_from"] is None

    @pytest.mark.django_db
    def test_a_denied_permit_also_needs_none(self, db):
        """Rechazado nunca tuvo vigencia: no hubo autorización."""
        permission = _requested(_cc(), status=FlightPermission.STATUS_DENIED)

        permission.full_clean()  # no levanta


class TestApprovingStillNeedsThem:
    """Aflojar el alta sin cerrar la aprobación dejaría permisos sin plazo."""

    @pytest.mark.django_db
    def test_the_model_rejects_an_approved_permit_with_no_validity(self, db):
        permission = _requested(_cc())
        permission.status = FlightPermission.STATUS_APPROVED

        with pytest.raises(ValidationError) as raised:
            permission.clean()

        assert "valid_from" in raised.value.message_dict
        assert "valid_until" in raised.value.message_dict

    # No hay test del **alta** con estado "aprobado", y no por olvido: `LV-157`
    # dejó el desplegable del alta en `CREATABLE_STATUSES`, así que `approved` no
    # es una opción válida ahí y el formulario lo rechaza antes de llegar a mirar
    # las fechas. Los dos caminos por los que un permiso se aprueba de verdad son
    # los dos que siguen: editar uno ya aprobado, y la compuerta del botón.

    @pytest.mark.django_db
    def test_the_edit_form_rejects_clearing_the_validity_of_an_approved_permit(
        self, db
    ):
        """El caso que la regla del folio demuestra que se olvida.

        `FlightPermissionUpdateForm` saca `status` de los campos (`LV-101`), así
        que la regla no puede leer el estado de `cleaned_data`. La del folio se
        resolvió repitiéndose en la subclase; ésta lee de las dos fuentes, y este
        test es el que lo comprueba.
        """
        cc = _cc()
        operator, aircraft = _roster(cc)
        permission = _requested(
            cc,
            status=FlightPermission.STATUS_APPROVED,
            permission_number="P-1",
            valid_from=date(2026, 7, 1),
            valid_until=date(2026, 7, 10),
        )
        form = FlightPermissionUpdateForm(
            instance=permission,
            data={
                **_FORM_BASE,
                "permission_number": "P-1",
                "cost_center": str(cc.pk),
                "operators": [str(operator.pk)],
                "aircraft_fleet": [str(aircraft.pk)],
                # las dos casillas vaciadas
                "valid_from": "",
                "valid_until": "",
            },
        )

        assert not form.is_valid()
        assert "valid_from" in form.errors

    @pytest.mark.django_db
    def test_the_approve_button_refuses_without_the_validity(self, db):
        """La compuerta, no sólo el formulario: `LV-156` en esta misma regla.

        **Se le dan folio y autorización firmada a propósito**, y el test
        comprueba *qué* compuerta habló. La primera versión de este test no
        adjuntaba el PDF: pasaba en verde por `RequireDgacPermitPdfMixin`, que
        corre antes en el MRO, sin ejecutar una sola línea de lo que venía a
        probar. Un test verde por la razón equivocada es peor que no tenerlo,
        porque nadie vuelve a mirarlo.
        """
        cc = _cc()
        permission = _requested(cc, permission_number="P-1")
        _attach_signed_authorization(permission)
        client = login_as("view_flightpermission", "change_flightpermission")

        response = client.post(
            reverse("permission-approve", args=[permission.pk]),
            follow=True,
        )

        permission.refresh_from_db()
        assert permission.status == FlightPermission.STATUS_REQUESTED
        # **Se compara contra el mensaje de la clase, no contra un texto.** Buscar
        # "vigencia" en el HTML también pasaba en verde, pero por la etiqueta
        # "Vigencia" que la ficha ya dibuja — el segundo falso positivo del mismo
        # test. Y buscar el texto en inglés sería la trampa de `LV-95`: pasa en
        # aislado y falla en la suite completa, donde otro test deja el español
        # activo. El mensaje de la clase es el mismo objeto en cualquier idioma.
        from .views import FlightPermissionApprove

        shown = [str(message) for message in response.context["messages"]]
        assert str(FlightPermissionApprove.missing_validity_message) in shown

    @pytest.mark.django_db
    def test_the_approve_button_lets_it_through_once_the_dates_are_in(self, db):
        """El complemento obligado: la compuerta nueva no bloquea el camino real."""
        cc = _cc()
        permission = _requested(
            cc,
            permission_number="P-1",
            valid_from=date(2026, 7, 1),
            valid_until=date(2026, 7, 10),
        )
        _attach_signed_authorization(permission)
        client = login_as("view_flightpermission", "change_flightpermission")

        client.post(reverse("permission-approve", args=[permission.pk]), follow=True)

        permission.refresh_from_db()
        assert permission.status == FlightPermission.STATUS_APPROVED


class TestTheExpiryEngineLeavesItAlone:
    """El motor de vencimientos es la razón por la que inventar fechas dolía."""

    @pytest.mark.django_db
    def test_expire_permissions_does_not_close_a_permit_with_no_validity(self, db):
        from django.core.management import call_command

        permission = _requested(_cc())

        call_command("expire_permissions")

        permission.refresh_from_db()
        assert permission.status == FlightPermission.STATUS_REQUESTED

    @pytest.mark.django_db
    def test_a_permit_with_no_validity_is_neither_in_force_nor_lapsed(self, db):
        from apps.compliance.kpis import permit_counts

        today = timezone.localdate()
        _requested(_cc())

        counts = permit_counts(today)

        assert counts["in_force"] == 0
        assert counts["lapsed"] == 0
        # Tiene su propio grupo, y ya existía: `awaiting` es exactamente esto.
        assert counts["awaiting"] == 1
        assert counts["total"] == 1

    @pytest.mark.django_db
    def test_it_is_not_announced_as_an_upcoming_expiration(self, db):
        from apps.compliance.expirations import upcoming_expirations

        _requested(_cc())

        today = timezone.localdate()
        rows = upcoming_expirations(today, today + timedelta(days=365))

        assert not [row for row in rows if row.get("model") == "flightpermission"]


class TestTheFlightRecordFormSaysWhy:
    """El único sitio que hacía aritmética con las fechas sin filtro por delante."""

    @pytest.mark.django_db
    def test_a_permit_with_no_validity_is_refused_with_its_own_reason(self, db):
        """Antes de LV-219 esto era un TypeError: un 500 al registrar un vuelo."""
        from .forms import FlightRecordForm

        cc = _cc()
        operator, aircraft = _roster(cc)
        permission = _requested(cc)
        permission.operators.add(operator)
        permission.aircraft_fleet.add(aircraft)

        form = FlightRecordForm(
            data={
                "permission": str(permission.pk),
                "pilot": str(operator.pk),
                "aircraft": str(aircraft.pk),
                "actual_date": date(2026, 7, 5).isoformat(),
                "departure_time": "09:00",
                "arrival_time": "10:00",
            }
        )

        assert not form.is_valid()
        # El motivo va en `permission`, no en `actual_date`: mandar a corregir la
        # fecha cuando no hay vigencia manda a arreglar lo que no está mal.
        assert "permission" in form.errors
        assert "actual_date" not in form.errors

    @pytest.mark.django_db
    def test_a_permit_with_validity_still_checks_the_range(self, db):
        """La regla vieja sigue en pie: esto no aflojó la comprobación."""
        from .forms import FlightRecordForm

        cc = _cc()
        operator, aircraft = _roster(cc)
        permission = _requested(
            cc,
            status=FlightPermission.STATUS_APPROVED,
            permission_number="P-1",
            valid_from=date(2026, 7, 1),
            valid_until=date(2026, 7, 10),
        )
        permission.operators.add(operator)
        permission.aircraft_fleet.add(aircraft)

        form = FlightRecordForm(
            data={
                "permission": str(permission.pk),
                "pilot": str(operator.pk),
                "aircraft": str(aircraft.pk),
                "actual_date": date(2026, 8, 20).isoformat(),  # fuera de rango
                "departure_time": "09:00",
                "arrival_time": "10:00",
            }
        )

        assert not form.is_valid()
        assert "actual_date" in form.errors


class TestTheScreenSaysWhatIsMissing:
    @pytest.mark.django_db
    def test_the_list_says_it_is_awaiting_the_dgac(self, db):
        permission = _requested(_cc())
        client = login_as("view_flightpermission")

        response = client.get(reverse("permission-list"))

        body = response.content.decode()
        assert "DGAC" in body
        # Y no un guion suelto entre dos huecos, que se lee como un descuido.
        assert " – </td>" not in body
        assert str(permission.internal_folio) in body

    @pytest.mark.django_db
    def test_the_calendar_does_not_draw_it(self, db):
        """Sin vigencia no se sabe cuándo vuela, así que no tiene día."""
        _requested(_cc())
        client = login_as("view_flightpermission")

        response = client.get(reverse("calendar"))

        assert response.status_code == 200


class TestTheValidityRuleIsDeclaredOnce:
    def test_the_statuses_that_require_validity_are_the_authorized_ones(self):
        """Un literal disperso es lo que `LV-156` y `LV-193` vinieron a arreglar."""
        assert FlightPermission.REQUIRE_VALIDITY_STATUSES == frozenset(
            {
                FlightPermission.STATUS_APPROVED,
                FlightPermission.STATUS_COMPLETED,
                FlightPermission.STATUS_EXPIRED,
            }
        )
        # Los dos que admiten nulos son exactamente los que pueden nacer.
        assert not (
            FlightPermission.CREATABLE_STATUSES
            & FlightPermission.REQUIRE_VALIDITY_STATUSES
        )
