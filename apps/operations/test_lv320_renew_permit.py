"""LV-320: renovar un permiso con la misma área (PR 1).

La DGAC no renueva sola: cada renovación es un permiso **nuevo**. Lo que se
quería evitar es volver a armar a mano el mismo contrato, la misma gente y la
misma área. Decisión de diseño aceptada por el usuario (opción B): **el plan
geoespacial se COPIA, no se mueve**. El original sigue siendo el expediente del
permiso anterior, que continúa vigente hasta que `expire_permissions` lo cierre.
"""

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from apps.compliance.models import Document, DocumentType
from apps.core.models import OperationalTenant
from apps.core.testing import login_as
from apps.geo.kml.canonical import empty_document
from apps.geo.models import GeoPlan, GeoPlanHistory, GeoPlanVersion
from apps.operations.dossier import operational_dossier
from apps.operations.models import FlightPermission
from apps.registry.models import Aerodrome, Aircraft, CostCenter, Operator

TODAY = timezone.localdate()
ADD = ("add_flightpermission", "add_geoplan", "view_flightpermission")


@pytest.fixture
def cost_center(db):
    return CostCenter.objects.create(code="CC738", name="MLP")


@pytest.fixture
def author(db):
    from django.contrib.auth.models import User

    return User.objects.create_user("author", password="pw")  # nosec B106


@pytest.fixture
def previous(cost_center):
    operator = Operator.objects.create(employee_id="E-1", full_name="Ana Rivas")
    aircraft = Aircraft.objects.create(
        registration="RPA-4883", type="Multirotor", model="M3E", manufacturer="DJI"
    )
    aerodrome = Aerodrome.objects.create(
        code="SCER", name="Quintero", latitude=-32.79, longitude=-71.52
    )
    permit = FlightPermission.objects.create(
        permission_number="DGAC-123",
        cost_center=cost_center,
        purpose="photogrammetry",
        purpose_detail="Detalle",
        location="Quebradas MLP",
        region="Coquimbo",
        commune="Salamanca",
        region_source="declared",
        commune_source="derived",
        area_name="Quebrada 13",
        latitude="-31.894392",
        longitude="-70.702208",
        radius_km="0.50",
        amc=aerodrome,
        amc_distance_km="120.5",
        max_altitude_m=120,
        area_type="unpopulated",
        status="approved",
        valid_from=TODAY - timezone.timedelta(days=60),
        valid_until=TODAY + timezone.timedelta(days=30),
        validity_override_reason="",
    )
    permit.operators.add(operator)
    permit.aircraft_fleet.add(aircraft)
    permit.refresh_from_db()
    return permit


@pytest.fixture
def plan(previous, author):
    doc_type = DocumentType.objects.create(
        code="GEO_SOURCE", name="KMZ", requires_expiry=False
    )
    document = Document.objects.create(
        doc_type=doc_type,
        content_type=ContentType.objects.get_for_model(GeoPlan),
        object_id=previous.pk,
        title="area.kmz",
        issue_date="2026-08-26",
        file_path="",
    )
    plan = GeoPlan.objects.create(
        title="Quebradas MLP",
        cost_center=previous.cost_center,
        created_by=author,
        flight_permission=previous,
        source_document=document,
    )
    plan.current_version = GeoPlanVersion.objects.create(
        plan=plan,
        version_number=1,
        content=empty_document(),
        content_checksum="a" * 64,
        source="import",
        feature_count=0,
        size_bytes=10,
        created_by=author,
    )
    plan.save(update_fields=["current_version", "updated_at"])
    # Aprobado de verdad, con su historial, como en producción.
    plan.status = GeoPlan.STATUS_APPROVED
    plan._changed_by = "reviewer"
    plan.save(update_fields=["status", "updated_at"])
    return plan


def _url(previous):
    return f"{reverse('permission-create')}?renueva={previous.pk}"


def _post(previous, **overrides):
    data = {
        "status": "requested",
        "permission_number": "",
        "operators": [str(o.pk) for o in previous.operators.all()],
        "aircraft_fleet": [str(a.pk) for a in previous.aircraft_fleet.all()],
        "cost_center": str(previous.cost_center_id),
        "purpose": "photogrammetry",
        "purpose_detail": "Detalle",
        "valid_from": "",
        "valid_until": "",
        "validity_override_reason": "",
        "location": "Quebradas MLP",
        "region": "Coquimbo",
        "commune": "Salamanca",
        "area_name": "Quebrada 13",
        "latitude": "-31.894392",
        "longitude": "-70.702208",
        "radius_km": "0.50",
        "max_altitude_m": "120",
        "area_type": "unpopulated",
    }
    data.update(overrides)
    return data


@pytest.mark.django_db
class TestPermissions:
    def test_without_add_flightpermission_it_is_forbidden(self, previous, plan):
        client = login_as("add_geoplan", "view_flightpermission")
        assert client.get(_url(previous)).status_code == 403
        assert client.post(_url(previous), _post(previous)).status_code == 403
        assert FlightPermission.objects.count() == 1

    def test_without_add_geoplan_it_is_forbidden(self, previous, plan):
        client = login_as("add_flightpermission", "view_flightpermission")
        assert client.get(_url(previous)).status_code == 403
        assert client.post(_url(previous), _post(previous)).status_code == 403
        assert FlightPermission.objects.count() == 1
        assert GeoPlan.objects.count() == 1

    def test_another_tenant_gets_a_404(self, previous, plan):
        other = OperationalTenant.objects.create(name="Otra", slug="otra")
        client = login_as(*ADD, member_of=other)
        assert client.get(_url(previous)).status_code == 404
        assert client.post(_url(previous), _post(previous)).status_code == 404
        assert FlightPermission.objects.count() == 1

    def test_the_button_needs_both_permissions(self, previous, plan):
        url = reverse("permission-detail", args=[previous.pk])
        both = login_as(*ADD).get(url).content.decode()
        only_one = login_as("add_flightpermission", "view_flightpermission").get(url)
        assert "Renovar permiso" in both or "Renew permit" in both
        assert "?renueva=" not in only_one.content.decode()


@pytest.mark.django_db
class TestTheDraft:
    def test_the_form_arrives_filled_without_dates_or_number(self, previous, plan):
        response = login_as(*ADD).get(_url(previous))
        assert response.status_code == 200
        form = response.context["form"]
        assert form.initial["location"] == "Quebradas MLP"
        assert form.initial["latitude"] == previous.latitude
        assert form.initial["max_altitude_m"] == 120
        assert form.initial["cost_center"] == previous.cost_center_id
        assert set(form.initial["operators"]) == {
            o.pk for o in previous.operators.all()
        }
        for name in ("permission_number", "valid_from", "valid_until", "status"):
            assert form.initial.get(name) in (None, "", "requested")
        # La geografía se ve para revisarla, y el selector de plan no se ofrece.
        assert "latitude" in form.fields and "source_plan" not in form.fields

    def test_the_renewal_is_born_requested_without_number_dates_or_documents(
        self, previous, plan
    ):
        response = login_as(*ADD).post(_url(previous), _post(previous))
        assert response.status_code == 302, (
            response.context and response.context["form"].errors
        )
        new = FlightPermission.objects.exclude(pk=previous.pk).get()
        assert new.renews == previous
        assert new.status == "requested"
        assert new.permission_number is None
        assert new.valid_from is None and new.valid_until is None
        assert new.validity_override_reason == ""
        assert not Document.objects.filter(
            content_type=ContentType.objects.get_for_model(FlightPermission),
            object_id=new.pk,
        ).exists()
        assert not new.history.exclude(new_status="requested").exists()
        # Lo que el formulario no dibuja pero la renovación hereda.
        assert new.amc == previous.amc
        assert new.amc_distance_km == previous.amc_distance_km
        assert (new.region_source, new.commune_source) == ("declared", "derived")
        assert new.max_altitude_ft is None

    def test_the_previous_permit_is_not_touched(self, previous, plan):
        before = FlightPermission.objects.values().get(pk=previous.pk)
        login_as(*ADD).post(_url(previous), _post(previous))
        after = FlightPermission.objects.values().get(pk=previous.pk)
        assert {**before, "updated_at": 0} == {**after, "updated_at": 0}
        assert previous.operators.count() == 1

    def test_the_three_month_ceiling_still_applies(self, previous, plan):
        response = login_as(*ADD).post(
            _url(previous),
            _post(
                previous,
                valid_from=TODAY.isoformat(),
                valid_until=(TODAY + timezone.timedelta(days=200)).isoformat(),
            ),
        )
        assert response.status_code == 200
        assert "valid_until" in response.context["form"].errors
        assert FlightPermission.objects.count() == 1
        assert GeoPlan.objects.count() == 1


@pytest.mark.django_db
class TestThePlanIsCopied:
    def test_the_copy_shares_the_kmz_and_the_content(self, previous, plan):
        login_as(*ADD).post(_url(previous), _post(previous))
        new = FlightPermission.objects.exclude(pk=previous.pk).get()
        copy = new.geo_plans.get()
        assert copy.pk != plan.pk
        assert copy.folio and copy.folio != plan.folio
        assert copy.copied_from == plan
        assert copy.source_document_id == plan.source_document_id
        assert Document.objects.count() == 1
        version = copy.versions.get()
        assert version.version_number == 1 and version.source == "renewal"
        assert version.content_checksum == plan.current_version.content_checksum
        assert version.content == plan.current_version.content
        assert plan.folio in version.summary
        assert copy.current_version == version

    def test_the_status_is_inherited_and_the_history_names_who_renewed(
        self, previous, plan
    ):
        client = login_as(*ADD)
        client.post(_url(previous), _post(previous))
        copy = GeoPlan.objects.get(copied_from=plan)
        assert copy.status == GeoPlan.STATUS_APPROVED
        row = GeoPlanHistory.objects.get(plan=copy)
        assert (row.previous_status, row.new_status) == ("draft", "approved")
        assert row.changed_by == client.user.get_username()
        assert row.changed_by_user == client.user

    def test_the_previous_dossier_still_shows_its_plan(self, previous, plan):
        login_as(*ADD).post(_url(previous), _post(previous))
        items = {item.key: item for item in operational_dossier(previous)["items"]}
        assert items["geo_plan"].status != "unknown"
        assert list(previous.geo_plans.all()) == [plan]
        plan.refresh_from_db()
        assert plan.flight_permission_id == previous.pk
        assert plan.status == GeoPlan.STATUS_APPROVED

    def test_a_permit_without_a_plan_renews_all_the_same(self, previous):
        response = login_as(*ADD).post(_url(previous), _post(previous))
        assert response.status_code == 302
        new = FlightPermission.objects.exclude(pk=previous.pk).get()
        assert new.renews == previous
        assert GeoPlan.objects.count() == 0

    def test_the_audit_context_records_the_renewal(self, previous, plan):
        from apps.core.models import AuditEvent

        login_as(*ADD).post(_url(previous), _post(previous))
        new = FlightPermission.objects.exclude(pk=previous.pk).get()
        event = AuditEvent.objects.filter(action="permission_renewed").get()
        assert event.object_id == str(new.pk)
        assert event.metadata["previous"] == previous.internal_folio
        assert event.metadata["new"] == new.internal_folio
        assert event.metadata["plan_copied"] == new.geo_plans.get().folio


@pytest.mark.django_db
class TestOnlyOneRenewal:
    def test_a_second_renewal_is_refused_by_the_view(self, previous, plan):
        client = login_as(*ADD)
        client.post(_url(previous), _post(previous))
        response = client.post(_url(previous), _post(previous))
        assert response.status_code == 302
        assert FlightPermission.objects.filter(renews=previous).count() == 1
        assert GeoPlan.objects.filter(copied_from=plan).count() == 1
        assert client.get(_url(previous)).status_code == 302

    def test_a_second_renewal_is_refused_by_the_constraint(self, previous):
        FlightPermission.objects.create(
            cost_center=previous.cost_center,
            purpose="photogrammetry",
            location="x",
            area_type="unpopulated",
            renews=previous,
        )
        with pytest.raises(IntegrityError), transaction.atomic():
            FlightPermission.objects.create(
                cost_center=previous.cost_center,
                purpose="photogrammetry",
                location="x",
                area_type="unpopulated",
                renews=previous,
            )

    def test_archiving_the_renewal_frees_the_previous_one(self, previous):
        first = FlightPermission.objects.create(
            cost_center=previous.cost_center,
            purpose="photogrammetry",
            location="x",
            area_type="unpopulated",
            renews=previous,
        )
        assert not previous.can_be_renewed
        first.is_active = False
        first.save(update_fields=["is_active"])
        assert previous.can_be_renewed

    def test_the_button_is_replaced_by_the_link_to_the_renewal(self, previous):
        new = FlightPermission.objects.create(
            cost_center=previous.cost_center,
            purpose="photogrammetry",
            location="x",
            area_type="unpopulated",
            renews=previous,
        )
        client = login_as(*ADD)
        html = client.get(reverse("permission-detail", args=[previous.pk])).content
        html = html.decode()
        assert "?renueva=" not in html and new.internal_folio in html
        html = client.get(reverse("permission-detail", args=[new.pk])).content.decode()
        assert previous.internal_folio in html


@pytest.mark.django_db
class TestTheModelRules:
    def test_a_permit_cannot_renew_itself(self, previous):
        previous.renews = previous
        with pytest.raises(IntegrityError), transaction.atomic():
            previous.save()

    def test_the_cost_center_must_match(self, previous):
        other = CostCenter.objects.create(code="CC999", name="Otra faena")
        permit = FlightPermission(
            cost_center=other,
            purpose="photogrammetry",
            location="x",
            area_type="unpopulated",
            renews=previous,
        )
        with pytest.raises(ValidationError) as caught:
            permit.full_clean()
        assert "cost_center" in caught.value.message_dict

    @pytest.mark.parametrize("status", ["requested", "denied"])
    def test_a_requested_or_denied_permit_cannot_be_renewed(self, previous, status):
        previous.status = status
        previous.save(update_fields=["status"])
        permit = FlightPermission(
            cost_center=previous.cost_center,
            purpose="photogrammetry",
            location="x",
            area_type="unpopulated",
            renews=previous,
        )
        with pytest.raises(ValidationError):
            permit.full_clean()
        assert not previous.can_be_renewed
        client = login_as(*ADD)
        assert client.get(_url(previous)).status_code == 302

    @pytest.mark.parametrize("status", ["approved", "completed", "expired"])
    def test_these_statuses_can_be_renewed(self, previous, status):
        previous.status = status
        previous.save(update_fields=["status"])
        assert previous.can_be_renewed
