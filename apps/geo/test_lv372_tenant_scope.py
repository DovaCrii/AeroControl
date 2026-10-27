"""LV-372: cada vista y endpoint de `apps/geo` acota por empresa (F-08).

La fase 0 de LV-368 cerró el vínculo plan↔permiso y la API de planes; quedaban
abiertas las vistas web de `geo` (listado, ficha, archivar, restaurar, las seis
transiciones, la revisión meteorológica). Esta prueba recorre **todas** con dos
empresas y un usuario por empresa con los permisos del rol, y afirma lo mismo en
cada una: lo de la otra empresa es 404 (detalle/acción) o no aparece (lista,
CSV), y lo propio sigue funcionando.

Las filas marcadas «fuga» en `MASTER_PLAN.md` fallaban antes del acotado (se
rompió cada arreglo una vez); las demás quedan como guardián. Datos ficticios.
"""

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone

from apps.core.models import OperationalTenant
from apps.core.testing import login_as
from apps.geo.models import GeoPlan, GeoPlanVersion, WeatherReview
from apps.geo.test_views import _kml_upload
from apps.operations.models import FlightPermission
from apps.registry.models import CostCenter

TODAY = timezone.localdate()


@pytest.fixture
def world(db):
    """Dos empresas, cada una con faena, permiso y un plan con una versión."""
    author = User.objects.create_user("autor-372", password="pw")  # nosec B106
    data = {}
    for key in ("a", "b"):
        tenant = OperationalTenant.objects.create(
            name=f"Empresa {key}", slug=f"emp-{key}"
        )
        center = CostCenter.objects.create(
            code=f"CC-{key.upper()}", name=f"Faena {key}", tenant=tenant
        )
        permit = FlightPermission.objects.create(
            internal_folio=f"JEJ-2026-37{key}",
            cost_center=center,
            purpose="patrol",
            valid_from=TODAY,
            valid_until=TODAY + timedelta(days=30),
            location="Sitio ficticio",
            area_type="unpopulated",
        )
        plan = GeoPlan.objects.create(
            title=f"Plan {key}",
            cost_center=center,
            created_by=author,
            status="in_review",
            flight_permission=permit,
        )
        version = GeoPlanVersion.objects.create(
            plan=plan,
            version_number=1,
            content={"schema_version": 1, "children": []},
            content_checksum=key * 64,
            source="import",
            created_by=author,
        )
        plan.current_version = version
        plan.save(update_fields=["current_version", "updated_at"])
        data[key] = {
            "tenant": tenant,
            "center": center,
            "permit": permit,
            "plan": plan,
        }
    return data


def _client(world, *codenames, tenant="a"):
    return login_as(*codenames, member_of=world[tenant]["tenant"])


def _other(world):
    return world["b"]["plan"]


def _own(world):
    return world["a"]["plan"]


@pytest.mark.django_db
class TestListAndDetail:
    def test_list_shows_only_the_own_tenant_plans(self, world):
        """Fuga: el listado traía los planes de todas las empresas."""
        response = _client(world, "view_geoplan").get(reverse("geo-plan-list"))
        plans = list(response.context["plans"])
        assert _own(world) in plans
        assert _other(world) not in plans

    def test_archived_filter_does_not_reveal_other_tenant_plans(self, world):
        other = _other(world)
        other.is_active = False
        other.save(update_fields=["is_active"])
        response = _client(world, "view_geoplan").get(
            reverse("geo-plan-list"), {"is_active": "archived"}
        )
        assert other not in list(response.context["plans"])

    def test_search_does_not_reveal_other_tenant_plans(self, world):
        response = _client(world, "view_geoplan").get(
            reverse("geo-plan-list"), {"q": "Plan b"}
        )
        assert list(response.context["plans"]) == []

    def test_csv_export_does_not_leak_other_tenant_plans(self, world):
        """Fuga: la exportación CSV usa el mismo queryset que la lista."""
        response = _client(world, "view_geoplan").get(
            reverse("geo-plan-list"), {"export": "csv"}
        )
        body = b"".join(response.streaming_content).decode("utf-8-sig")
        assert "Plan a" in body
        assert "Plan b" not in body

    def test_htmx_partial_does_not_leak_other_tenant_plans(self, world):
        response = _client(world, "view_geoplan").get(
            reverse("geo-plan-list"), HTTP_HX_REQUEST="true"
        )
        content = response.content.decode()
        assert "Plan a" in content
        assert "Plan b" not in content

    def test_detail_of_another_tenant_is_404(self, world):
        """Fuga: la ficha abría cualquier plan por su pk."""
        client = _client(world, "view_geoplan")
        assert (
            client.get(reverse("geo-plan-detail", args=[_other(world).pk])).status_code
            == 404
        )
        assert (
            client.get(reverse("geo-plan-detail", args=[_own(world).pk])).status_code
            == 200
        )

    def test_superuser_still_sees_every_tenant(self, world, admin_client):
        response = admin_client.get(reverse("geo-plan-list"))
        plans = list(response.context["plans"])
        assert _own(world) in plans and _other(world) in plans


@pytest.mark.django_db
class TestMutatingViews:
    def test_archive_of_another_tenant_is_404_and_changes_nothing(self, world):
        """Fuga: archivar resolvía el plan por pk."""
        other = _other(world)
        response = _client(world, "delete_geoplan").post(
            reverse("geo-plan-archive", args=[other.pk])
        )
        assert response.status_code == 404
        other.refresh_from_db()
        assert other.is_active is True

    def test_archive_of_own_plan_still_works(self, world):
        own = _own(world)
        reason = next(
            code
            for code, _l in GeoPlan.CLOSE_REASON_CHOICES
            if code != GeoPlan.CLOSE_OTHER
        )
        response = _client(world, "delete_geoplan").post(
            reverse("geo-plan-archive", args=[own.pk]),
            {"confirm": "1", "close_reason": reason},
        )
        assert response.status_code == 302
        own.refresh_from_db()
        assert own.is_active is False

    def test_restore_of_another_tenant_is_404_and_changes_nothing(self, world):
        """Fuga: restaurar resolvía el plan por pk."""
        other = _other(world)
        other.is_active = False
        other.save(update_fields=["is_active"])
        response = _client(world, "change_geoplan").post(
            reverse("geo-plan-restore", args=[other.pk])
        )
        assert response.status_code == 404
        other.refresh_from_db()
        assert other.is_active is False

    def test_restore_of_own_plan_still_works(self, world):
        own = _own(world)
        own.is_active = False
        own.save(update_fields=["is_active"])
        response = _client(world, "change_geoplan").post(
            reverse("geo-plan-restore", args=[own.pk])
        )
        assert response.status_code == 302
        own.refresh_from_db()
        assert own.is_active is True

    @pytest.mark.parametrize(
        "url_name,perm,from_status,to_status",
        [
            ("geo-plan-start-editing", "change_geoplan", "draft", "editing"),
            ("geo-plan-submit-review", "change_geoplan", "editing", "in_review"),
            ("geo-plan-approve", "approve_geoplan", "in_review", "approved"),
            ("geo-plan-reject", "approve_geoplan", "in_review", "rejected"),
            ("geo-plan-resume-editing", "change_geoplan", "rejected", "editing"),
            ("geo-plan-reopen", "approve_geoplan", "approved", "editing"),
        ],
    )
    def test_transitions_of_another_tenant_are_404(
        self, world, url_name, perm, from_status, to_status
    ):
        """Fuga: las seis transiciones usaban `get_object_or_404(model, pk)`."""
        other, own = _other(world), _own(world)
        for plan in (other, own):
            plan.status = from_status
            plan.save(update_fields=["status"])
        client = _client(world, perm)
        assert client.post(reverse(url_name, args=[other.pk])).status_code == 404
        other.refresh_from_db()
        assert other.status == from_status
        assert client.post(reverse(url_name, args=[own.pk])).status_code == 302
        own.refresh_from_db()
        assert own.status == to_status

    def test_weather_review_of_another_tenant_is_404(self, world):
        """Fuga: la revisión meteorológica resolvía el plan por pk."""
        other = _other(world)
        response = _client(world, "add_weatherreview").post(
            reverse("weather-review-create", args=[other.pk])
        )
        assert response.status_code == 404
        assert WeatherReview.objects.count() == 0

    def test_weather_review_of_own_plan_is_not_a_404(self, world):
        """El plan propio sigue resolviéndose (sin área no registra, pero redirige)."""
        response = _client(world, "add_weatherreview").post(
            reverse("weather-review-create", args=[_own(world).pk])
        )
        assert response.status_code == 302


@pytest.mark.django_db
class TestImport:
    def test_import_offers_only_own_cost_centers_and_permits(self, world):
        response = _client(world, "add_geoplan").get(reverse("geo-plan-import"))
        form = response.context["form"]
        assert world["a"]["center"] in form.fields["cost_center"].queryset
        assert world["b"]["center"] not in form.fields["cost_center"].queryset
        assert world["a"]["permit"] in form.fields["flight_permission"].queryset
        assert world["b"]["permit"] not in form.fields["flight_permission"].queryset

    def test_import_into_a_cost_center_of_another_tenant_is_rejected(
        self, world, settings, tmp_path
    ):
        settings.DOCUMENTS_ROOT = str(tmp_path)
        before = GeoPlan.objects.count()
        response = _client(world, "add_geoplan").post(
            reverse("geo-plan-import"),
            {
                "title": "Intruso",
                "cost_center": world["b"]["center"].pk,
                "file": _kml_upload(),
            },
        )
        assert response.status_code == 200
        assert "cost_center" in response.context["form"].errors
        assert GeoPlan.objects.count() == before

    def test_import_prefill_with_a_foreign_cost_center_is_404(self, world):
        response = _client(world, "add_geoplan").get(
            reverse("geo-plan-import"), {"cost_center": world["b"]["center"].pk}
        )
        assert response.status_code == 404


@pytest.mark.django_db
class TestApiGuardians:
    """Las puertas de la API ya estaban acotadas (fase 0); aquí queda el recorrido completo."""

    def test_every_api_door_hides_another_tenant_plan(self, world):
        other = _other(world)
        view = _client(world, "view_geoplan", "change_geoplan")
        urls = [
            reverse("api-v1-geo-plan", args=[other.pk]),
            reverse("api-v1-geo-plan-versions", args=[other.pk]),
            reverse("api-v1-geo-plan-version-content", args=[other.pk, 1]),
            reverse("api-v1-geo-plan-resource", args=[other.pk]) + "?name=a.png",
        ]
        for url in urls:
            assert view.get(url).status_code == 404, url
        restore = view.post(
            reverse("api-v1-geo-plan-version-restore", args=[other.pk, 1]),
            {},
            content_type="application/json",
        )
        assert restore.status_code == 404
        export = view.post(
            reverse("api-v1-geo-plan-export", args=[other.pk]),
            {"format": "kml"},
            content_type="application/json",
        )
        assert export.status_code == 404

    def test_own_plan_api_still_answers(self, world):
        own = _own(world)
        client = _client(world, "view_geoplan")
        assert client.get(reverse("api-v1-geo-plan", args=[own.pk])).status_code == 200
        assert (
            client.get(
                reverse("api-v1-geo-plan-version-content", args=[own.pk, 1])
            ).status_code
            == 200
        )
