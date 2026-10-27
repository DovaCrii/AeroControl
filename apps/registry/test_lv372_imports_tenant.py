"""LV-372 (F-08, fase 2): las importaciones CSV y su reversión acotan por empresa.

`ImportBatch` no lleva empresa: la de un lote es la de las filas que creó. Antes, revertir
resolvía el lote por `pk` (cualquier empresa), el ofrecimiento de deshacer mostraba el último
lote de cualquiera, los códigos «existentes» y los centros se buscaban en todas las empresas
y las filas nuevas nacían siempre en la empresa por defecto. Datos ficticios.
"""

import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

from apps.core.models import ImportBatch, OperationalTenant
from apps.core.testing import login_as
from apps.core.tenancy import get_default_tenant
from apps.registry.models import Aircraft, CostCenter, Operator
from apps.registry.views import import_target_tenant

PERMS = ("add_costcenter", "add_aircraft", "add_operator", "change_importbatch")


@pytest.fixture
def world(db):
    data = {}
    for key in ("a", "b"):
        tenant = OperationalTenant.objects.create(
            name=f"Empresa {key}", slug=f"emp-{key}"
        )
        center = CostCenter.objects.create(
            code="FAENA-01", name=f"Faena {key}", tenant=tenant
        )
        data[key] = {"tenant": tenant, "center": center}
    return data


def _csv(body):
    return SimpleUploadedFile("lote.csv", body.encode(), content_type="text/csv")


def _import_centers(client, *codes):
    body = "code,name\n" + "".join(f"{code},Faena {code}\n" for code in codes)
    return client.post(reverse("costcenter-import"), {"file": _csv(body), "apply": "1"})


@pytest.fixture
def batch_of_b(world):
    client = login_as(*PERMS, member_of=world["b"]["tenant"])
    # El usuario del cliente de B no se repite con el de A: `login_as` deriva el nombre de
    # los permisos, así que el de A se crea con otro conjunto.
    assert _import_centers(client, "CC901").status_code == 302
    return ImportBatch.objects.get(entity="registry.costcenter")


def _client_of_a(world):
    return login_as(
        "add_costcenter",
        "add_aircraft",
        "add_operator",
        "change_importbatch",
        "view_costcenter",
        member_of=world["a"]["tenant"],
    )


@pytest.mark.django_db
class TestRevert:
    def test_reverting_a_batch_of_b_as_a_is_a_404_and_archives_nothing(
        self, world, batch_of_b
    ):
        response = _client_of_a(world).post(
            reverse("costcenter-import-revert", args=[batch_of_b.pk])
        )
        assert response.status_code == 404
        assert CostCenter.objects.get(code="CC901").is_active
        batch_of_b.refresh_from_db()
        assert batch_of_b.status == "applied"

    def test_the_owner_can_still_revert_its_own_batch(self, world, batch_of_b):
        client = login_as(*PERMS, "view_costcenter", member_of=world["b"]["tenant"])
        response = client.post(
            reverse("costcenter-import-revert", args=[batch_of_b.pk])
        )
        assert response.status_code == 302
        assert not CostCenter.objects.get(code="CC901").is_active

    def test_without_the_permission_it_is_forbidden(self, world, batch_of_b):
        client = login_as("add_costcenter", member_of=world["b"]["tenant"])
        response = client.post(
            reverse("costcenter-import-revert", args=[batch_of_b.pk])
        )
        assert response.status_code == 403
        assert CostCenter.objects.get(code="CC901").is_active

    def test_a_batch_with_rows_in_two_tenants_is_not_visible_to_either(self, world):
        mixed = ImportBatch.objects.create(
            entity="registry.costcenter",
            created_ids=[str(world["a"]["center"].pk), str(world["b"]["center"].pk)],
        )
        response = _client_of_a(world).post(
            reverse("costcenter-import-revert", args=[mixed.pk])
        )
        assert response.status_code == 404

    def test_root_can_revert_any_batch(self, world, batch_of_b):
        root = User.objects.create_superuser("root372i", password="pw")  # nosec B106
        client = Client()
        client.force_login(root)
        response = client.post(
            reverse("costcenter-import-revert", args=[batch_of_b.pk])
        )
        assert response.status_code == 302


@pytest.mark.django_db
class TestOffer:
    def test_the_offer_does_not_show_the_batch_of_b(self, world, batch_of_b):
        response = _client_of_a(world).get(reverse("costcenter-import"))
        assert response.status_code == 200
        assert response.context["last_batch"] is None

    def test_the_offer_shows_the_own_batch_and_skips_the_other(self, world):
        a = _client_of_a(world)
        assert _import_centers(a, "CC902").status_code == 302
        own = ImportBatch.objects.get()
        # El lote de B es **más reciente**: el de A debe seguir ofreciéndose.
        b = login_as(*PERMS, member_of=world["b"]["tenant"])
        assert _import_centers(b, "CC903").status_code == 302
        response = a.get(reverse("costcenter-import"))
        assert response.context["last_batch"] == own


@pytest.mark.django_db
class TestImportTarget:
    def test_cost_centers_are_created_in_the_tenant_of_the_importer(self, world):
        _import_centers(_client_of_a(world), "CC904")
        assert CostCenter.objects.get(code="CC904").tenant == world["a"]["tenant"]

    def test_a_code_that_exists_only_in_b_is_free_in_a(self, world, batch_of_b):
        response = _import_centers(_client_of_a(world), "CC901")
        assert response.status_code == 302
        assert CostCenter.objects.filter(code="CC901").count() == 2

    def test_a_code_that_exists_in_a_is_rejected(self, world):
        response = _import_centers(_client_of_a(world), "FAENA-01")
        assert response.status_code == 200
        assert response.context["errors"]

    def test_the_aircraft_import_resolves_the_center_of_a_even_if_b_has_the_code(
        self, world
    ):
        body = (
            "registration,type,model,manufacturer,year,cost_center,status\n"
            "CC-L372,RPA,M3,DJI,2026,FAENA-01,active\n"
        )
        response = _client_of_a(world).post(
            reverse("aircraft-import"), {"file": _csv(body), "apply": "1"}
        )
        assert response.status_code == 302
        aircraft = Aircraft.objects.get(registration="CC-L372")
        assert aircraft.cost_center == world["a"]["center"]
        assert aircraft.tenant == world["a"]["tenant"]

    def test_the_aircraft_import_does_not_see_a_center_of_another_tenant(self, world):
        CostCenter.objects.create(
            code="SOLO-B", name="Solo B", tenant=world["b"]["tenant"]
        )
        body = (
            "registration,type,model,manufacturer,year,cost_center,status\n"
            "CC-L373,RPA,M3,DJI,2026,SOLO-B,active\n"
        )
        response = _client_of_a(world).post(
            reverse("aircraft-import"), {"file": _csv(body), "apply": "1"}
        )
        assert response.status_code == 200
        assert not Aircraft.objects.filter(registration="CC-L373").exists()

    def test_the_employee_id_is_unique_per_tenant(self, world):
        Operator.objects.create(
            employee_id="E-372",
            full_name="Persona B",
            cost_center=world["b"]["center"],
            tenant=world["b"]["tenant"],
        )
        body = (
            "employee_id,full_name,email,phone,cost_center\n"
            "E-372,Persona A,a@test.com,+56900000000,FAENA-01\n"
        )
        response = _client_of_a(world).post(
            reverse("operator-import"), {"file": _csv(body), "apply": "1"}
        )
        assert response.status_code == 302
        created = Operator.objects.get(full_name="Persona A")
        assert created.tenant == world["a"]["tenant"]
        assert created.cost_center == world["a"]["center"]

    def test_with_several_memberships_the_import_is_refused(self, world):
        client = _client_of_a(world)
        world["b"]["tenant"].members.add(client.user)
        response = _import_centers(client, "CC905")
        assert response.status_code == 200
        assert response.context["errors"] == [import_target_tenant(client.user)[1]]
        assert not CostCenter.objects.filter(code="CC905").exists()
        assert not ImportBatch.objects.exists()

    def test_root_keeps_the_default_tenant(self, world):
        root = User.objects.create_superuser("root372j", password="pw")  # nosec B106
        client = Client()
        client.force_login(root)
        _import_centers(client, "CC906")
        assert CostCenter.objects.get(code="CC906").tenant_id == get_default_tenant()

    def test_without_the_permission_it_is_forbidden(self, world):
        client = login_as("view_costcenter", member_of=world["a"]["tenant"])
        assert _import_centers(client, "CC907").status_code == 403
        assert not CostCenter.objects.filter(code="CC907").exists()
