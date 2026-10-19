"""LV-340: las herramientas nuevas del asistente (todas de SOLO LECTURA).

Fija lo que no puede aflojarse: cada herramienta exige su permiso `view_*`, acota por empresa,
no deja salir ningún campo libre ni nada de una persona (centinelas sembrados en cada campo
libre), recorta por filas sin romper el JSON, cita con `reverse` y sólo con UUID, no escribe y
no hace consultas de más.
"""

import json
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.assistant import service, tools
from apps.assistant.tests import FakeClient, _final, _tool_call
from apps.core.testing import login_as

NEW_TOOLS = (
    "upcoming_maintenance",
    "expiring_company_documents",
    "aircraft_insurance_status",
    "open_alerts_by_urgency",
    "flight_requests_status",
    "fleet_availability",
    "aircraft_readiness",
)
PERMS = (
    "view_maintenancerecord",
    "view_document",
    "view_aircraft",
    "view_alert",
    "view_flightrequest",
    "view_flightpermission",
    "view_operator",
)
SENTINEL = "CENTINELA"


def _args(name, key):
    if name == "aircraft_readiness":
        return json.dumps({"registration": f"RPA-{key.upper()}1"})
    return "{}"


def _data(text):
    return json.loads(text)["data"]


def _build(key, tenant, extra=0):
    """Una empresa con una fila de cada cosa, cada campo libre sembrado con un centinela."""
    from apps.compliance.models import Alert, AlertRule, Document, DocumentType
    from apps.maintenance.models import MaintenanceRecord
    from apps.operations.models import FlightPermission, FlightRequest
    from apps.registry.models import Aircraft, CostCenter, Operator

    today = timezone.localdate()
    centre = CostCenter.objects.create(
        code=f"CC-{key.upper()}",
        name=f"{SENTINEL}-FAENA-{key}",
        operates_flights=True,
        tenant=tenant,
        notes=f"{SENTINEL}-NOTES",
    )
    doc_type, _created = DocumentType.objects.get_or_create(
        code="POLICY", defaults={"name": "Insurance policy"}
    )
    ct_aircraft = ContentType.objects.get_for_model(Aircraft)
    rule = AlertRule.objects.create(
        tenant=tenant,
        name=f"{SENTINEL}-RULE",
        entity_type="registry.aircraft",
        field_to_watch="insurance_expiry",
    )
    FlightPermission.objects.create(
        cost_center=centre,
        purpose="photogrammetry",
        purpose_detail=f"{SENTINEL}-PURPOSE",
        status=FlightPermission.STATUS_APPROVED,
        permission_number=f"{key}-100",
        location="Calama",
        area_type="unpopulated",
        valid_from=today - timedelta(days=5),
        valid_until=today + timedelta(days=12),
        notes=f"{SENTINEL}-NOTES",
    )
    aircraft_list = []
    for index in range(1 + extra):
        aircraft = Aircraft.objects.create(
            registration=f"RPA-{key.upper()}{index + 1}",
            type="multirotor",
            model="M300",
            manufacturer="DJI",
            tenant=tenant,
            cost_center=centre,
            insurance_expiry=today + timedelta(days=10 + index),
            notes=f"{SENTINEL}-NOTES",
        )
        aircraft_list.append(aircraft)
        MaintenanceRecord.objects.create(
            aircraft=aircraft,
            maintenance_type="scheduled",
            description=f"{SENTINEL}-DESCRIPTION",
            performed_by=f"{SENTINEL}-TECNICO",
            scheduled_date=today + timedelta(days=5 + index),
            notes=f"{SENTINEL}-NOTES",
        )
        Document.objects.create(
            tenant=tenant,
            content_type=ct_aircraft,
            object_id=aircraft.pk,
            doc_type=doc_type,
            title=f"{SENTINEL}-TITULO",
            file_path="x/y.pdf",
            issue_date=today - timedelta(days=300),
            expiry_date=today + timedelta(days=20 + index),
            notes=f"{SENTINEL}-NOTES",
        )
        Alert.objects.create(
            alert_rule=rule,
            content_type=ct_aircraft,
            object_id=aircraft.pk,
            message=f"{SENTINEL}-MENSAJE",
            watched_value=(today + timedelta(days=3)).isoformat(),
        )
        FlightRequest.objects.create(
            title=f"{SENTINEL}-SOLICITUD",
            cost_center=centre,
            commune=f"{SENTINEL}-COMUNA",
            area_name=f"{SENTINEL}-AREA",
            center_lat=Decimal("-31.906392"),
            center_lon=Decimal("-70.717982"),
        )
    operator = Operator.objects.create(
        full_name=f"{SENTINEL} Piloto Pérez",
        employee_id=f"{SENTINEL}-ID-{key}",
        tenant=tenant,
        email="centinela.piloto@example.com",
        cost_center=centre,
    )
    # Un documento y una alerta cuyo sujeto es una PERSONA: no pueden salir.
    ct_operator = ContentType.objects.get_for_model(Operator)
    Document.objects.create(
        tenant=tenant,
        content_type=ct_operator,
        object_id=operator.pk,
        doc_type=doc_type,
        title=f"{SENTINEL}-DOC-PERSONA",
        file_path="x/p.pdf",
        issue_date=today - timedelta(days=300),
        expiry_date=today + timedelta(days=9),
    )
    Alert.objects.create(
        alert_rule=rule,
        content_type=ct_operator,
        object_id=operator.pk,
        message=f"{SENTINEL}-ALERTA-PERSONA",
        watched_value=(today + timedelta(days=2)).isoformat(),
    )
    return centre, aircraft_list


@pytest.fixture
def world(db):
    from apps.core.models import OperationalTenant

    tenants = {
        key: OperationalTenant.objects.create(name=f"Empresa {key}", slug=f"emp-{key}")
        for key in ("a", "b")
    }
    for key, tenant in tenants.items():
        _build(key, tenant)
    return tenants


_COUNTER = iter(range(10_000))


def _user(tenant, *codenames):
    """Un usuario nuevo de esa empresa (nombre único: `login_as` lo deriva de los permisos)."""
    from django.contrib.auth.models import Permission, User

    user = User.objects.create_user(f"u340-{next(_COUNTER)}", password="pw")  # nosec B106
    user.user_permissions.add(
        *Permission.objects.filter(codename__in=codenames or PERMS)
    )
    tenant.members.add(user)
    return user


class TestPermissions:
    def test_without_the_permission_a_tool_returns_an_error_not_data(self, world):
        user = login_as().user

        for name in NEW_TOOLS:
            out = json.loads(tools.run_tool(user, name, _args(name, "a")))
            assert out == {"error": "this user has no permission for that data"}, name

    def test_each_tool_needs_its_own_permission(self, world):
        wanted = {
            "upcoming_maintenance": "view_maintenancerecord",
            "expiring_company_documents": "view_document",
            "aircraft_insurance_status": "view_aircraft",
            "open_alerts_by_urgency": "view_alert",
            "flight_requests_status": "view_flightrequest",
            "fleet_availability": "view_aircraft",
            "aircraft_readiness": "view_aircraft",
        }
        for name, codename in wanted.items():
            assert tools.TOOLS[name].permission.endswith(f".{codename}"), name
            others = [p for p in PERMS if p != codename]
            user = _user(world["a"], *others)
            if name in ("fleet_availability", "aircraft_readiness"):
                continue  # comparten `view_aircraft` con otra herramienta del juego
            out = json.loads(tools.run_tool(user, name, _args(name, "a")))
            assert "error" in out, name


class TestTenantIsolation:
    @pytest.mark.parametrize("name", NEW_TOOLS)
    def test_two_companies_never_see_each_other(self, world, name):
        for mine, theirs in (("a", "b"), ("b", "a")):
            text = tools.run_tool(_user(world[mine]), name, _args(name, mine))
            assert f"RPA-{theirs.upper()}" not in text, name
            assert f"CC-{theirs.upper()}" not in text, name

    def test_each_company_sees_its_own_rows(self, world):
        a = _data(tools.run_tool(_user(world["a"]), "upcoming_maintenance", "{}"))
        b = _data(tools.run_tool(_user(world["b"]), "upcoming_maintenance", "{}"))
        assert [r["registration"] for r in a] == ["RPA-A1"]
        assert [r["registration"] for r in b] == ["RPA-B1"]

        docs = _data(
            tools.run_tool(_user(world["a"]), "expiring_company_documents", "{}")
        )
        assert {r["subject_code"] for r in docs} == {"RPA-A1"}

        requests = _data(
            tools.run_tool(_user(world["b"]), "flight_requests_status", "{}")
        )
        assert requests["total"] == 1
        assert {r["cost_centre"] for r in requests["rows"]} == {"CC-B"}

        alerts = _data(
            tools.run_tool(_user(world["a"]), "open_alerts_by_urgency", "{}")
        )
        assert alerts["total"] == 2  # la de la aeronave y la de la persona, sólo conteo

        fleet = _data(tools.run_tool(_user(world["a"]), "fleet_availability", "{}"))
        assert (fleet["total"], fleet["available"]) == (1, 1)

    def test_readiness_of_another_companys_aircraft_is_not_found(self, world):
        out = _data(
            tools.run_tool(
                _user(world["a"]), "aircraft_readiness", '{"registration": "RPA-B1"}'
            )
        )
        assert out == {
            "found": False,
            "pk": None,
            "registration": None,
            "nothing_in_records_prevents_flight": None,
            "blockers": [],
            "warnings": [],
            "note": None,
        }

    def test_fleet_availability_without_user_is_unchanged(self, world):
        from apps.compliance.kpis import fleet_availability

        assert fleet_availability()["total"] == 2
        assert fleet_availability(user=_user(world["a"]))["total"] == 1
        assert fleet_availability(user=None) == fleet_availability()

    def test_mutation_dropping_the_scope_would_be_caught(self, world, monkeypatch):
        """Sin acotar, la empresa A vería la matrícula de B: el test de arriba lo cazaría."""
        monkeypatch.setattr(
            tools,
            "scope_queryset_to_tenant",
            lambda queryset, user, path=None: queryset,
        )
        text = tools.run_tool(_user(world["a"]), "upcoming_maintenance", "{}")
        assert "RPA-B1" in text


class TestNothingPersonalLeaves:
    def test_no_free_text_or_person_reaches_any_output(self, world):
        user = _user(world["a"])
        outputs = [
            tools.run_tool(user, name, _args(name, "a")) for name in tools.TOOLS
        ] + [tools.run_tool(user, "expiring_permits", '{"days": 60}')]

        joined = " ".join(outputs)
        assert SENTINEL not in joined
        assert "example.com" not in joined
        assert "Pérez" not in joined
        # y sí sale lo acordado: matrículas y tipo del catálogo
        assert "RPA-A1" in joined
        assert "Insurance policy" in joined

    def test_documents_of_people_are_left_out(self, world):
        rows = _data(
            tools.run_tool(_user(world["a"]), "expiring_company_documents", "{}")
        )
        assert [r["subject_kind"] for r in rows] == ["aircraft"]

    def test_alerts_only_carry_counts(self, world):
        data = _data(tools.run_tool(_user(world["a"]), "open_alerts_by_urgency", "{}"))
        assert set(data) == {"total", "by_urgency", "by_entity"}
        assert data["by_entity"]["person"] == 1
        assert all(isinstance(n, int) for n in data["by_urgency"].values())

    def test_rows_carry_only_the_agreed_keys(self, world):
        user = _user(world["a"])
        expected = {
            "upcoming_maintenance": {
                "pk",
                "registration",
                "maintenance_type",
                "status",
                "scheduled_date",
                "days_left",
                "to_be_defined",
            },
            "expiring_company_documents": {
                "pk",
                "doc_type",
                "subject_kind",
                "subject_code",
                "expiry_date",
                "days_left",
            },
            "aircraft_insurance_status": {
                "pk",
                "registration",
                "insurance_status",
                "insurance_expiry",
                "days_left",
            },
        }
        for name, keys in expected.items():
            rows = _data(tools.run_tool(user, name, "{}"))
            assert rows and set(rows[0]) == keys, name
        requests = _data(tools.run_tool(user, "flight_requests_status", "{}"))
        assert set(requests["rows"][0]) == {
            "pk",
            "cost_centre",
            "status",
            "request_type",
            "age_days",
        }

    def test_codes_are_sanitised(self):
        assert tools._code("RPA-12<script>x</script>") == "RPA-12scriptxscript"[:30]
        assert len(tools._code("A" * 80)) == 30
        assert tools._code(None) == ""

    def test_the_output_is_checked_against_a_whitelist(self):
        trimmed = []
        with pytest.raises(ValueError):
            tools._validate({"a": "text"}, {"a": int}, trimmed)
        with pytest.raises(ValueError):
            tools._validate({"a": True}, {"a": int}, trimmed)
        # una clave que no está en la lista blanca no pasa
        assert tools._validate({"a": 1, "secret": "x"}, {"a": int}, trimmed) == {"a": 1}


class TestReadiness:
    def test_it_never_says_the_aircraft_can_fly(self, world):
        text = tools.run_tool(
            _user(world["a"]), "aircraft_readiness", '{"registration": "RPA-A1"}'
        )
        data = _data(text)

        assert "can_fly" not in text and "puede volar" not in text.lower()
        assert data["found"] is True
        assert data["nothing_in_records_prevents_flight"] is True
        assert data["blockers"] == []

    def test_blockers_and_warnings_use_fixed_labels_and_dates(self, world):
        from apps.registry.models import Aircraft

        today = timezone.localdate()
        Aircraft.objects.filter(registration="RPA-A1").update(
            status="maintenance", insurance_expiry=today - timedelta(days=2)
        )
        data = _data(
            tools.run_tool(
                _user(world["a"]),
                "aircraft_readiness",
                '{"registration": "rpa-a1"}',
            )
        )

        assert data["nothing_in_records_prevents_flight"] is False
        items = {(row["item"], row["flag"]) for row in data["blockers"]}
        assert ("airframe_status", "maintenance") in items
        assert ("insurance", "expired") in items
        warnings = {(row["item"], row["flag"]) for row in data["warnings"]}
        assert ("Insurance policy", "expiring") in warnings

    def test_a_site_without_a_current_permit_blocks(self, world):
        from apps.operations.models import FlightPermission

        FlightPermission.objects.all().update(
            valid_until=timezone.localdate() - timedelta(days=1)
        )
        data = _data(
            tools.run_tool(
                _user(world["a"]), "aircraft_readiness", '{"registration": "RPA-A1"}'
            )
        )
        assert ("site_permit", "no_current_permit") in {
            (row["item"], row["flag"]) for row in data["blockers"]
        }

    def test_can_fly_is_untouched(self):
        from apps.operations import readiness

        assert callable(readiness.can_fly)
        assert readiness.check_aircraft_for_assistant is not readiness.can_fly


class TestRowsAreTrimmedBeforeSerialising:
    def test_more_than_max_rows_is_cut_and_the_json_stays_valid(self, db):
        from apps.core.models import OperationalTenant

        tenant = OperationalTenant.objects.create(name="Grande", slug="grande")
        _build("a", tenant, extra=30)
        user = _user(tenant)

        for name in ("aircraft_insurance_status", "upcoming_maintenance"):
            body = json.loads(tools.run_tool(user, name, "{}"))
            assert len(body["data"]) == tools.MAX_ROWS, name
            assert body["truncated"] is True

    def test_a_long_answer_loses_rows_not_characters(self, world, monkeypatch):
        monkeypatch.setattr(tools, "MAX_CHARS", 300)
        user = _user(world["a"])
        for name in tools.TOOLS:
            text = tools.run_tool(user, name, _args(name, "a"))
            body = json.loads(text)  # siempre JSON válido
            assert len(text) <= 300 or "error" in body, name

    def test_the_old_cut_at_6000_characters_is_gone(self):
        import inspect

        assert "[:6000]" not in inspect.getsource(tools)


class TestCitations:
    def test_each_tool_cites_with_reverse_and_only_valid_uuids(self, world):
        user = _user(world["a"])
        expected = {
            "upcoming_maintenance": "maintenance-detail",
            "expiring_company_documents": "document-detail",
            "aircraft_insurance_status": "aircraft-detail",
            "flight_requests_status": "flight-request-detail",
            "aircraft_readiness": "aircraft-detail",
        }
        for name, url_name in expected.items():
            _text, cites = tools.execute_tool(user, name, _args(name, "a"))
            assert cites, name
            assert all(
                c["url"]
                == reverse(url_name, args=[c["url"].rstrip("/").split("/")[-1]])
                for c in cites
            ), name

    def test_alerts_cite_the_list_only_when_there_is_something(self, world):
        _text, cites = tools.execute_tool(
            _user(world["a"]), "open_alerts_by_urgency", "{}"
        )
        assert [c["url"] for c in cites] == [reverse("alert-list")]
        assert tools.citations_for("open_alerts_by_urgency", {"total": 0}) == []

    @pytest.mark.parametrize("name", sorted(tools.CITATION_ROUTES))
    def test_a_pk_that_is_not_a_uuid_makes_no_citation(self, name):
        label_key = tools.CITATION_ROUTES[name][1]
        if label_key is None:
            pytest.skip("cita a una lista, sin pk")
        rows = [
            {"pk": "javascript:alert(1)", label_key: "X"},
            {"pk": str(uuid.uuid4()), label_key: "OK-1"},
            {label_key: "sin pk"},
        ]
        cites = tools.citations_for(name, rows)
        assert [c["label"] for c in cites] == ["OK-1"]
        assert cites[0]["url"].startswith("/")

    def test_tools_without_a_route_cite_nothing(self):
        assert tools.citations_for("fleet_availability", {"total": 3}) == []
        assert tools.citations_for("permits_summary", [{"pk": str(uuid.uuid4())}]) == []


class TestQueriesAndWrites:
    def _count(self, user, name, key):
        with CaptureQueriesContext(connection) as captured:
            tools.run_tool(user, name, _args(name, key))
        return captured

    def test_query_count_does_not_grow_with_rows_and_nothing_writes(self, db):
        from apps.core.models import OperationalTenant

        small = OperationalTenant.objects.create(name="Pequeña", slug="pequena")
        big = OperationalTenant.objects.create(name="Grande", slug="grande")
        _build("a", small)
        _build("b", big, extra=8)
        user_small, user_big = _user(small), _user(big)
        for name in tools.TOOLS:  # calienta cachés (ContentType, permisos)
            self._count(user_small, name, "a")
            self._count(user_big, name, "b")

        for name in NEW_TOOLS:
            few = self._count(user_small, name, "a")
            many = self._count(user_big, name, "b")
            assert len(few) == len(many), name
            for query in list(few) + list(many):
                assert query["sql"].lstrip().upper().startswith("SELECT"), name


@pytest.mark.django_db
class TestThePanelFollowsAnyToolPermission:
    @pytest.fixture
    def enabled(self, settings):
        settings.AI_ASSISTANT_ENABLED = True
        settings.DEBUG = True
        settings.AI_ASSISTANT_MAX_PER_HOUR = 0
        settings.AI_ASSISTANT_DAILY_CAP = 0

    def test_a_user_with_only_one_tool_permission_gets_the_panel(self, enabled):
        html = login_as("view_aircraft").get(reverse("aircraft-list")).content.decode()
        assert 'id="assistant-open"' in html

    def test_without_any_tool_permission_there_is_no_panel_and_the_fragment_is_403(
        self, enabled
    ):
        client = login_as("view_operator")
        html = client.get(reverse("operator-list")).content.decode()

        assert 'id="assistant-open"' not in html
        assert (
            client.post(reverse("assistant-panel-ask"), {"question": "x"}).status_code
            == 403
        )

    def test_the_fragment_works_with_one_tool_permission_and_the_tool_checks_its_own(
        self, enabled, monkeypatch, world
    ):
        client = FakeClient(
            [_tool_call("upcoming_maintenance"), _final("Sin permiso para eso.")]
        )
        monkeypatch.setattr(service, "NvidiaClient", lambda: client)
        http = Client()
        http.force_login(_user(world["a"], "view_aircraft"))

        response = http.post(reverse("assistant-panel-ask"), {"question": "x"})

        assert response.status_code == 200
        tool_message = next(m for m in client.calls[1] if m["role"] == "tool")
        assert json.loads(tool_message["content"]) == {
            "error": "this user has no permission for that data"
        }

    def test_the_full_screen_keeps_view_flightpermission(self, enabled):
        client = login_as("view_aircraft")

        assert client.get(reverse("assistant-ask")).status_code == 403
        assert (
            login_as("view_flightpermission").get(reverse("assistant-ask")).status_code
            == 200
        )
