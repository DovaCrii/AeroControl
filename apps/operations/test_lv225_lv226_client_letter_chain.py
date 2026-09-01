"""LV-225 y LV-226: la carta del mandante y la cadena de renovación.

Del informe mensual de reportabilidad (`SPEC_REPORTE_MENSUAL_RPA.md` §4.1): un
permiso dura 3 meses (`LV-224`) y **renovarlo exige una carta nueva del
mandante** — no es un trámite automático, y la carta hay que pedírsela a un
tercero. De ahí que la cadena de avisos empiece 45 días antes y no 30.

Dos piezas y dos naturalezas distintas, que estos tests mantienen separadas:

- **La carta es un tipo de documento más** (`LV-225`), no un campo ni un modelo.
  Así hereda el expediente, las versiones, el hash de `LV-200` y el motor de
  vencimientos, sin código nuevo.
- **T-45 y T-30 son configuración** (`LV-226`): filas de `AlertRule`. Sólo el
  escalamiento condicional —*si a T-15 no hay carta*— necesita lógica, porque
  "existe un documento de este tipo" no es un campo que `AlertRule` pueda vigilar.
"""

from datetime import date, timedelta
from io import StringIO

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from apps.core.testing import login_as
from apps.registry.models import CostCenter

from .dossier import CLIENT_LETTER, PERMIT_LETTER, SIGNED_AUTHORIZATION
from .models import FlightPermission


def _cc(code="CC1"):
    return CostCenter.objects.create(code=code, name=code, operates_flights=True)


def _permit(cc, **extra):
    extra.setdefault("status", FlightPermission.STATUS_APPROVED)
    extra.setdefault("permission_number", "P-1")
    return FlightPermission.objects.create(
        cost_center=cc,
        purpose="photogrammetry",
        location="Site",
        area_type="unpopulated",
        **extra,
    )


def _attach(permission, code):
    from apps.compliance.models import Document, DocumentType

    doc_type, _made = DocumentType.objects.get_or_create(
        code=code, defaults={"name": code, "requires_expiry": False}
    )
    return Document.objects.create(
        title=code,
        doc_type=doc_type,
        content_type=ContentType.objects.get_for_model(FlightPermission),
        object_id=permission.pk,
        issue_date=date(2026, 8, 14),
        file_path=f"{code}/x.pdf",
    )


class TestTheLetterIsInTheDossier:
    @pytest.mark.django_db
    def test_it_is_listed_as_pending_when_absent(self, db):
        from .dossier import operational_dossier

        items = {
            item.key: item for item in operational_dossier(_permit(_cc()))["items"]
        }

        assert "client_letter" in items

    @pytest.mark.django_db
    def test_it_is_recognised_once_uploaded(self, db):
        from .dossier import OK, operational_dossier

        permit = _permit(_cc())
        _attach(permit, CLIENT_LETTER)

        items = {item.key: item for item in operational_dossier(permit)["items"]}

        assert items["client_letter"].status == OK

    @pytest.mark.django_db
    def test_it_is_not_the_same_paper_as_either_dgac_one(self, db):
        """Tres papeles distintos: uno va, uno vuelve y uno lo emite el cliente."""
        from .dossier import OK, operational_dossier

        permit = _permit(_cc())
        _attach(permit, SIGNED_AUTHORIZATION)
        _attach(permit, PERMIT_LETTER)

        items = {item.key: item for item in operational_dossier(permit)["items"]}

        # Los dos de la DGAC están, y la del mandante sigue faltando.
        assert items["signed_authorization"].status == OK
        assert items["client_letter"].status != OK

    @pytest.mark.django_db
    def test_a_missing_letter_does_not_block_approval(self, db):
        """La carta gobierna la **renovación**, no la aprobación.

        Sumarla a la compuerta habría cambiado la regla de `R2.4`, donde lo que
        certifica la aprobación es la autorización firmada.
        """
        permit = _permit(
            _cc(),
            status=FlightPermission.STATUS_REQUESTED,
            valid_from=date(2026, 7, 4),
            valid_until=date(2026, 10, 4),
        )
        _attach(permit, SIGNED_AUTHORIZATION)
        client = login_as("view_flightpermission", "change_flightpermission")

        client.post(reverse("permission-approve", args=[permit.pk]), follow=True)

        permit.refresh_from_db()
        assert permit.status == FlightPermission.STATUS_APPROVED

    @pytest.mark.django_db
    def test_the_document_type_is_seeded(self, db):
        from apps.compliance.models import DocumentType

        call_command("seed_document_types")

        assert DocumentType.objects.filter(code=CLIENT_LETTER).exists()

    @pytest.mark.django_db
    def test_the_seeded_type_does_not_demand_an_expiry_date(self, db):
        """Decisión, no descuido: no toda carta trae plazo escrito.

        Exigirlo obligaría a inventar una fecha para poder cargar el papel, que
        es el mal que `LV-219` quitó del alta del permiso.
        """
        from apps.compliance.models import DocumentType

        call_command("seed_document_types")

        assert not DocumentType.objects.get(code=CLIENT_LETTER).requires_expiry


class TestTheChainIsConfiguration:
    @pytest.mark.django_db
    def test_the_three_thresholds_are_seeded_rules(self, db):
        from apps.compliance.models import AlertRule

        call_command("seed_alert_rules")

        days = set(
            AlertRule.objects.filter(
                entity_type="operations.flightpermission",
                field_to_watch="valid_until",
            ).values_list("days_before_expiry", flat=True)
        )
        assert {45, 30, 15} <= days

    @pytest.mark.django_db
    def test_seeding_twice_does_not_duplicate_the_chain(self, db):
        """El sembrado es idempotente por nombre, y esto lo fija.

        Importa más de lo que parece: renombrar la regla de 30 días —que ya
        existía— habría creado una cuarta y dejado la vieja activa, duplicando
        los avisos de **todos** los permisos.
        """
        from apps.compliance.models import AlertRule

        call_command("seed_alert_rules")
        call_command("seed_alert_rules")

        assert (
            AlertRule.objects.filter(
                entity_type="operations.flightpermission",
                field_to_watch="valid_until",
            ).count()
            == 3
        )

    @pytest.mark.django_db
    def test_each_threshold_produces_its_own_alert(self, db):
        """Tres reglas sobre el mismo campo = tres alertas escalonadas.

        Es lo que hace posible la cadena sin tocar el motor: su clave
        anti-duplicados es `(regla, registro, valor)` (`LV-111`), así que cada
        regla escribe la suya.
        """
        from apps.compliance.models import Alert

        today = timezone.localdate()
        permit = _permit(
            _cc(),
            valid_from=today - timedelta(days=80),
            valid_until=today + timedelta(days=10),  # dentro de las tres ventanas
            validity_override_reason="rango de prueba",
        )
        call_command("seed_alert_rules")

        call_command("generate_alerts")

        assert Alert.objects.filter(object_id=permit.pk, is_active=True).count() == 3

    @pytest.mark.django_db
    def test_a_permit_with_no_validity_gets_no_alert(self, db):
        """`LV-219`: sin vigencia no hay vencimiento que anunciar."""
        from apps.compliance.models import Alert

        permit = _permit(_cc(), status=FlightPermission.STATUS_REQUESTED)
        call_command("seed_alert_rules")

        call_command("generate_alerts")

        assert not Alert.objects.filter(object_id=permit.pk).exists()


class TestTheConditionalEscalation:
    """Lo único que `AlertRule` no puede expresar: si la carta está o no."""

    @pytest.mark.django_db
    def test_it_reports_a_permit_with_no_letter(self, db):
        today = timezone.localdate()
        permit = _permit(
            _cc(),
            valid_from=today - timedelta(days=60),
            valid_until=today + timedelta(days=40),
        )
        out = StringIO()

        call_command("check_client_letters", stdout=out)

        body = out.getvalue()
        assert permit.internal_folio in body
        assert "MISSING" in body

    @pytest.mark.django_db
    def test_it_escalates_inside_fifteen_days(self, db):
        today = timezone.localdate()
        _permit(
            _cc(),
            valid_from=today - timedelta(days=80),
            valid_until=today + timedelta(days=10),
        )
        out = StringIO()

        call_command("check_client_letters", stdout=out)

        assert "ESCALATE" in out.getvalue()

    @pytest.mark.django_db
    def test_a_permit_with_the_letter_is_not_reported(self, db):
        today = timezone.localdate()
        permit = _permit(
            _cc(),
            valid_from=today - timedelta(days=60),
            valid_until=today + timedelta(days=40),
        )
        _attach(permit, CLIENT_LETTER)
        out = StringIO()

        call_command("check_client_letters", stdout=out)

        body = out.getvalue()
        assert "1 with letter, 0 missing" in body

    @pytest.mark.django_db
    def test_a_requested_permit_is_not_reproached(self, db):
        """Sin vigencia todavía no hay renovación que preparar (`LV-219`)."""
        permit = _permit(_cc(), status=FlightPermission.STATUS_REQUESTED)
        out = StringIO()

        call_command("check_client_letters", stdout=out)

        assert permit.internal_folio not in out.getvalue()

    @pytest.mark.django_db
    def test_an_expired_permit_is_not_reproached(self, db):
        """`LV-113`: un registro en estado terminal no sostiene trabajo."""
        today = timezone.localdate()
        permit = _permit(
            _cc(),
            status=FlightPermission.STATUS_EXPIRED,
            valid_from=today - timedelta(days=100),
            valid_until=today - timedelta(days=5),
        )
        out = StringIO()

        call_command("check_client_letters", stdout=out)

        assert permit.internal_folio not in out.getvalue()

    @pytest.mark.django_db
    def test_it_writes_nothing(self, db):
        """Read-only a propósito: crear la alerta acá duplicaría la de T-15."""
        from apps.compliance.models import Alert

        today = timezone.localdate()
        _permit(
            _cc(),
            valid_from=today - timedelta(days=80),
            valid_until=today + timedelta(days=10),
        )

        call_command("check_client_letters", stdout=StringIO())

        assert not Alert.objects.exists()
