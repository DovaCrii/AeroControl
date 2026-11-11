"""LV-431: «Flight logs» como sección propia (centro de costo + aeronave), sin pasar por un permiso.

Datos sintéticos; el lector DJI se simula como en `test_lv429` (`subprocess.run` con monkeypatch).
"""

# ruff: noqa: F811 - las fixtures `fake`, `centre`, `permit` se importan de otras pruebas
from datetime import time

import pytest
from django.apps import apps as django_apps
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.urls import reverse

from apps.compliance.models import Document, DocumentType
from apps.compliance.storage import get_document_storage
from apps.core.models import OperationalTenant
from apps.core.testing import login_as
from apps.operations.flightlog import forms as log_forms
from apps.operations.flightlog.backfill import backfill
from apps.operations.flightlog.independent import serial_mismatch_warning
from apps.operations.flightlog.types import FlightTrack
from apps.operations.models import FlightLogAnalysis, FlightPermission, FlightRecord
from apps.registry.models import Aircraft, CostCenter

from .test_lv427_flight_log_analysis import (  # noqa: F401 - fixtures compartidas
    TODAY,
    _analysis_url,
    centre,
    isolated_storage,
    permit,
)
from .test_lv429_dji_adapter import SERIAL, _attach_dji, fake  # noqa: F401

NAME = "DJIFlightRecord_2030-01-15.txt"
VIEW = "view_flightloganalysis"
ADD = "add_flightloganalysis"


@pytest.fixture
def drone(centre):
    """La aeronave de `centre` cuya serie coincide con la del log simulado."""
    return Aircraft.objects.create(
        registration="RPA-9100",
        serial_number=SERIAL,
        type="RPA",
        model="Mavic 3E",
        manufacturer="DJI",
        cost_center=centre,
    )


@pytest.fixture
def other_centre(db):
    """Otra faena del **mismo** tenant, con su aeronave."""
    return CostCenter.objects.create(
        code="CC902", name="Faena Y", operates_flights=True
    )


@pytest.fixture
def other_drone(other_centre):
    return Aircraft.objects.create(
        registration="RPA-9102",
        serial_number="OTHER-SN-9102",
        type="RPA",
        model="Matrice",
        manufacturer="DJI",
        cost_center=other_centre,
    )


@pytest.fixture
def foreign(db):
    """Un centro y una aeronave de **otro tenant**."""
    tenant = OperationalTenant.objects.create(name="Ajena", slug="ajena-431")
    cc = CostCenter.objects.create(
        code="CC990", name="Faena ajena", operates_flights=True, tenant=tenant
    )
    aircraft = Aircraft.objects.create(
        registration="RPA-9900",
        serial_number="FOREIGN-SN-9900",
        type="RPA",
        model="Ajena",
        manufacturer="DJI",
        cost_center=cc,
        tenant=tenant,
    )
    return tenant, cc, aircraft


def _doc(aircraft, title=NAME):
    return Document.objects.create(
        tenant_id=aircraft.tenant_id,
        content_type=ContentType.objects.get_for_model(Aircraft),
        object_id=aircraft.pk,
        doc_type=DocumentType.objects.get(code="flight-log-txt"),
        title=title,
        file_path="",  # sin ruta la señal no analiza: la fila se arma a mano
    )


def _row(centre, aircraft, status="ok", started="2030-01-15T10:00:00-03:00", **extra):
    """Un análisis ya hecho, con el resultado mínimo que la lista lee."""
    result = {}
    if status == "ok":
        result = {
            "summary": {
                "started_at": started,
                "started_at_utc": started[:10] + "T13:00:00Z",
                "duration_s": 250,
                "distance_m": 1234.4,
                "max_height_m": 101,
            },
            "points": [
                {"t": 0, "lat": 10.0, "lon": 20.0, "battery_pct": 90},
                {"t": 250, "lat": 10.001, "lon": 20.0, "battery_pct": 13},
            ],
            "events": [
                {
                    "t": 1,
                    "level": "info",
                    "code": "",
                    "raw_text": "",
                    "explanation": "",
                },
                {
                    "t": 2,
                    "level": "warning",
                    "code": "",
                    "raw_text": "",
                    "explanation": "",
                },
                {
                    "t": 3,
                    "level": "critical",
                    "code": "",
                    "raw_text": "",
                    "explanation": "",
                },
            ],
            "aircraft": {"serial": SERIAL},
        }
    return FlightLogAnalysis.objects.create(
        cost_center=centre,
        aircraft=aircraft,
        document=_doc(aircraft, extra.pop("title", NAME)),
        status=status,
        result=result,
        **extra,
    )


def _upload(client, centre, aircraft, name=NAME, content=b"\x00binary", **extra):
    data = {
        "cost_center": str(centre.pk),
        "aircraft": str(aircraft.pk),
        "file": SimpleUploadedFile(name, content, content_type="text/plain"),
        **extra,
    }
    return client.post(reverse("flight-log-upload"), data)


# ── el menú ───────────────────────────────────────────────────────────────────


class TestMenu:
    def test_the_item_shows_with_the_permission_and_not_without_it(self, db):
        url = reverse("flight-log-list")

        with_perm = login_as(VIEW).get(reverse("start")).content.decode()
        without = login_as("view_flightrecord").get(reverse("start")).content.decode()

        assert f'href="{url}"' in with_perm
        assert f'href="{url}"' not in without

    def test_the_roles_that_read_flights_get_it(self, db):
        from django.contrib.auth.models import Group
        from django.core.management import call_command

        call_command("bootstrap_roles")
        has = {
            name: Group.objects.get(name=name)
            .permissions.filter(codename=VIEW)
            .exists()
            for name in ("Operations", "Compliance", "Viewer", "Maintenance")
        }
        assert has == {
            "Operations": True,
            "Compliance": True,
            "Viewer": True,
            "Maintenance": False,
        }
        ops = Group.objects.get(name="Operations")
        assert ops.permissions.filter(codename=ADD).exists()
        # Un log es evidencia: nadie lo edita ni lo borra desde un rol.
        assert not Group.objects.filter(
            permissions__codename__in=[
                "change_flightloganalysis",
                "delete_flightloganalysis",
            ],
            name__in=["Operations", "Compliance", "Viewer", "Maintenance"],
        ).exists()


# ── la lista ──────────────────────────────────────────────────────────────────


class TestList:
    def test_it_shows_the_row_with_its_figures(self, drone, centre):
        _row(centre, drone)

        response = login_as(VIEW).get(reverse("flight-log-list"))
        html = response.content.decode()

        assert response.context["objects"][0].digest["warnings"] == 2
        assert "15-01-2030" in html and "10:00" in html
        assert "CC900" in html and "RPA-9100" in html and "Mavic 3E" in html
        assert (
            "4:10" in html and "1234 m" in html and "101 m" in html and "13 %" in html
        )
        # `id-chip` con palabra, y 2 avisos (warning + critical).
        assert "id-chip--ok" in html
        assert 'colspan="10"' not in html  # hay una fila: el vacío no se dibuja

    def test_the_error_row_says_error_and_has_no_figures(self, drone, centre):
        _row(centre, drone, status="error", error_code="incomplete")

        html = login_as(VIEW).get(reverse("flight-log-list")).content.decode()

        assert "id-chip--critical" in html and "id-chip--ok" not in html

    def test_it_filters_by_cost_center_aircraft_and_status(
        self, drone, centre, other_drone, other_centre
    ):
        _row(centre, drone, title="DJIFlightRecord_A.txt")
        _row(other_centre, other_drone, status="error", title="DJIFlightRecord_B.txt")
        client = login_as(VIEW)
        url = reverse("flight-log-list")

        def titles(**query):
            body = client.get(url, query).content.decode()
            return {
                n for n in ("RPA-9100", "RPA-9102") if n in body.split("<tbody")[-1]
            }

        assert titles() == {"RPA-9100", "RPA-9102"}
        assert titles(cost_center=centre.pk) == {"RPA-9100"}
        assert titles(aircraft=other_drone.pk) == {"RPA-9102"}
        assert titles(status="error") == {"RPA-9102"}
        assert titles(status="ok") == {"RPA-9100"}
        # Una aeronave que no es del centro elegido no devuelve nada.
        assert titles(cost_center=centre.pk, aircraft=other_drone.pk) == set()
        # Valores mal escritos no filtran ni fallan.
        assert titles(status="nonsense", date_from="not-a-date") == {
            "RPA-9100",
            "RPA-9102",
        }
        assert titles(cost_center="not-a-uuid") == set()

    def test_the_aircraft_selector_is_limited_to_the_chosen_center(
        self, drone, centre, other_drone, other_centre
    ):
        _row(centre, drone)
        _row(other_centre, other_drone, title="DJIFlightRecord_B.txt")

        response = login_as(VIEW).get(
            reverse("flight-log-list"), {"cost_center": centre.pk}
        )

        options = [a.registration for a in response.context["aircraft_options"]]
        assert options == ["RPA-9100"]

    def test_it_filters_by_date_range_and_searches(self, drone, centre):
        _row(
            centre,
            drone,
            started="2030-01-10T09:00:00-03:00",
            title="DJIFlightRecord_1.txt",
        )
        _row(
            centre,
            drone,
            started="2030-02-20T09:00:00-03:00",
            title="DJIFlightRecord_2.txt",
        )
        client = login_as(VIEW)
        url = reverse("flight-log-list")

        def count(**query):
            return len(client.get(url, query).context["objects"])

        assert count() == 2
        assert count(date_from="2030-02-01") == 1
        assert count(date_to="2030-01-31") == 1
        assert count(date_from="2030-01-01", date_to="2030-12-31") == 2
        assert count(q="RPA-9100") == 2
        assert count(q=SERIAL) == 2
        assert count(q="FlightRecord_2") == 1
        assert count(q="nothing-like-this") == 0

    def test_another_tenant_never_sees_the_row(self, drone, centre, foreign):
        _tenant, f_centre, f_aircraft = foreign
        _row(centre, drone)
        _row(f_centre, f_aircraft, title="DJIFlightRecord_F.txt")

        mine = login_as(VIEW, member_of=centre.tenant).get(reverse("flight-log-list"))
        theirs = login_as(VIEW, ADD, member_of=foreign[0]).get(
            reverse("flight-log-list")
        )

        assert [a.aircraft.registration for a in mine.context["objects"]] == [
            "RPA-9100"
        ]
        assert [a.aircraft.registration for a in theirs.context["objects"]] == [
            "RPA-9900"
        ]
        assert "RPA-9900" not in mine.content.decode()
        # Ni siquiera filtrando por el centro ajeno.
        probe = login_as(VIEW, "view_flightrecord", member_of=centre.tenant).get(
            reverse("flight-log-list"), {"cost_center": f_centre.pk}
        )
        assert list(probe.context["objects"]) == []

    def test_reading_needs_view_flightloganalysis(self, db):
        assert login_as(ADD).get(reverse("flight-log-list")).status_code == 403
        assert login_as().get(reverse("flight-log-list")).status_code == 403

    def test_a_view_only_user_is_not_offered_the_upload(self, drone, centre):
        _row(centre, drone)
        url = reverse("flight-log-upload")

        view_only = login_as(VIEW).get(reverse("flight-log-list")).content.decode()
        both = login_as(VIEW, ADD).get(reverse("flight-log-list")).content.decode()

        assert url not in view_only
        assert url in both

    def test_the_analysis_opens_with_only_the_section_permission(self, drone, centre):
        row = _row(centre, drone)

        response = login_as(VIEW).get(_analysis_url(row))

        assert response.status_code == 200
        html = response.content.decode()
        # Sin permiso: «No informado» y la vuelta es la lista, no un permiso.
        assert reverse("flight-log-list") in html
        assert "RPA-9100" in html and "CC900" in html


# ── el alta ───────────────────────────────────────────────────────────────────


class TestUpload:
    def test_the_form_asks_for_center_aircraft_and_file(self, drone, centre):
        response = login_as(VIEW, ADD).get(reverse("flight-log-upload"))

        assert response.status_code == 200
        html = response.content.decode()
        for field in ("cost_center", "aircraft", "file", "permission"):
            assert f'name="{field}"' in html
        # Cada aeronave lleva su centro para que el JS acote el selector.
        assert f'data-cc="{centre.pk}"' in html
        assert response.content.decode().count("<h1") == 1

    def test_a_valid_upload_creates_the_document_on_the_aircraft_and_the_analysis(
        self, fake, drone, centre
    ):
        client = login_as(VIEW, ADD)

        response = _upload(client, centre, drone)

        analysis = FlightLogAnalysis.objects.get()
        assert response.status_code == 302
        assert response["Location"] == _analysis_url(analysis)
        assert analysis.cost_center == centre and analysis.aircraft == drone
        assert analysis.permission is None
        assert analysis.uploaded_by == client.user
        assert analysis.status == "ok"
        document = analysis.document
        assert document.content_type == ContentType.objects.get_for_model(Aircraft)
        assert document.object_id == drone.pk
        assert document.doc_type.code == "flight-log-txt"
        assert document.tenant_id == drone.tenant_id
        assert document.title == NAME
        assert get_document_storage().exists(document.file_path)
        # Y la pantalla de análisis se abre.
        assert client.get(response["Location"]).status_code == 200

    def test_the_optional_permit_is_kept_when_it_matches_the_center(
        self, fake, permit, drone, centre
    ):
        _upload(login_as(VIEW, ADD), centre, drone, permission=str(permit.pk))

        analysis = FlightLogAnalysis.objects.get()
        assert analysis.permission == permit

    def test_a_permit_of_another_center_is_rejected(
        self, fake, drone, centre, other_centre
    ):
        permit = FlightPermission.objects.create(
            cost_center=other_centre,
            purpose="photogrammetry",
            status=FlightPermission.STATUS_APPROVED,
            permission_number="DGAC-0902",
            location="Sector 2",
            area_type="unpopulated",
            valid_from=TODAY,
            valid_until=TODAY,
        )

        response = _upload(
            login_as(VIEW, ADD), centre, drone, permission=str(permit.pk)
        )

        assert response.status_code == 200
        assert "permission" in response.context["form"].errors
        assert not FlightLogAnalysis.objects.exists()

    def test_an_aircraft_of_another_center_is_rejected(self, fake, centre, other_drone):
        response = _upload(login_as(VIEW, ADD), centre, other_drone)

        assert response.status_code == 200
        assert "aircraft" in response.context["form"].errors
        assert not FlightLogAnalysis.objects.exists()
        assert not Document.objects.filter(object_id=other_drone.pk).exists()

    def test_an_aircraft_of_another_tenant_is_not_even_an_option(
        self, fake, drone, centre, foreign
    ):
        _tenant, f_centre, f_aircraft = foreign
        client = login_as(VIEW, ADD, member_of=centre.tenant)

        response = _upload(client, centre, f_aircraft)
        crossed = _upload(client, f_centre, f_aircraft)

        assert response.status_code == 200 and crossed.status_code == 200
        assert "aircraft" in response.context["form"].errors
        assert "cost_center" in crossed.context["form"].errors
        assert not FlightLogAnalysis.objects.exists()

    def test_center_and_aircraft_are_required(self, fake, drone, centre):
        client = login_as(VIEW, ADD)

        response = client.post(
            reverse("flight-log-upload"),
            {"file": SimpleUploadedFile(NAME, b"\x00x")},
        )

        errors = response.context["form"].errors
        assert "cost_center" in errors and "aircraft" in errors
        assert not FlightLogAnalysis.objects.exists()

    @pytest.mark.parametrize(
        "name",
        ["notes.pdf", "vuelo.json", "random.txt", "DJIFlightRecord_x.txt.exe"],
    )
    def test_a_file_that_is_not_a_dji_txt_is_rejected(self, fake, drone, centre, name):
        response = _upload(login_as(VIEW, ADD), centre, drone, name=name)

        assert response.status_code == 200
        assert "file" in response.context["form"].errors
        assert not FlightLogAnalysis.objects.exists()
        assert not Document.objects.exists()

    def test_an_oversized_or_empty_file_is_rejected(
        self, fake, drone, centre, monkeypatch
    ):
        monkeypatch.setattr(log_forms, "MAX_LOG_BYTES", 10)
        client = login_as(VIEW, ADD)

        big = _upload(client, centre, drone, content=b"x" * 11)
        empty = _upload(client, centre, drone, content=b"")

        assert "file" in big.context["form"].errors
        assert "file" in empty.context["form"].errors
        assert not FlightLogAnalysis.objects.exists()

    def test_uploading_needs_add_flightloganalysis(self, fake, drone, centre):
        view_only = login_as(VIEW)
        nobody = login_as()

        assert view_only.get(reverse("flight-log-upload")).status_code == 403
        assert _upload(view_only, centre, drone).status_code == 403
        assert _upload(nobody, centre, drone).status_code == 403
        assert not FlightLogAnalysis.objects.exists()

    def test_a_reader_failure_still_saves_the_upload_with_its_error(
        self, fake, drone, centre
    ):
        fake.returncode = 1
        fake.stderr = b'{"error": "incomplete", "message": "boom"}'

        response = _upload(login_as(VIEW, ADD), centre, drone)

        analysis = FlightLogAnalysis.objects.get()
        assert response.status_code == 302
        assert analysis.status == "error"
        assert analysis.document.file_path


# ── el aviso de serie ─────────────────────────────────────────────────────────


class TestSerialWarning:
    def test_a_mismatching_serial_warns_on_the_page_but_the_log_is_kept(
        self, fake, centre, other_drone
    ):
        # La aeronave elegida tiene otra serie que la que dice el log (SERIAL).
        mine = Aircraft.objects.create(
            registration="RPA-9101",
            serial_number="MINE-SN-9101",
            type="RPA",
            model="Mavic 3E",
            manufacturer="DJI",
            cost_center=centre,
        )
        client = login_as(VIEW, ADD)

        response = _upload(client, centre, mine)
        html = client.get(response["Location"]).content.decode()

        assert FlightLogAnalysis.objects.filter(aircraft=mine).count() == 1
        assert 'id="fa-serial-warning"' in html
        assert SERIAL in html and "MINE-SN-9101" in html

    def test_a_matching_serial_does_not_warn(self, fake, drone, centre):
        client = login_as(VIEW, ADD)

        response = _upload(client, centre, drone)
        html = client.get(response["Location"]).content.decode()

        assert 'id="fa-serial-warning"' not in html

    def test_no_serial_in_the_log_is_nothing_to_compare(self, drone, centre):
        row = _row(centre, drone)

        assert serial_mismatch_warning(row, FlightTrack()) == ""


# ── el flujo anterior, desde el permiso ───────────────────────────────────────


class TestPermitFlow:
    def test_a_log_attached_to_a_permit_still_creates_its_analysis(self, fake, permit):
        doc = _attach_dji(permit)

        analysis = FlightLogAnalysis.objects.get(document=doc)

        assert analysis.permission == permit
        assert analysis.cost_center == permit.cost_center
        assert analysis.aircraft is None
        assert analysis.status == "ok"

    def test_its_page_goes_back_to_the_permit_and_lists_under_the_center(
        self, fake, permit
    ):
        analysis = FlightLogAnalysis.objects.get(document=_attach_dji(permit))
        client = login_as("view_flightpermission", "view_flightrecord", VIEW)

        page = client.get(_analysis_url(analysis)).content.decode()
        listing = client.get(reverse("flight-log-list")).content.decode()

        assert reverse("permission-operations", args=[permit.pk]) in page
        assert "CC900" in listing

    def test_the_permit_page_links_to_the_list_filtered_by_its_center(
        self, fake, permit
    ):
        client = login_as(
            "view_flightpermission", "view_flightrecord", "add_flightrecord", VIEW
        )

        html = client.get(
            reverse("permission-operations", args=[permit.pk])
        ).content.decode()

        assert (
            f"{reverse('flight-log-list')}?cost_center={permit.cost_center_id}" in html
        )

    def test_linking_an_operation_needs_a_permit(self, drone, centre):
        row = _row(centre, drone)
        client = login_as("view_flightrecord", "change_flightrecord")

        assert client.post(_analysis_url(row), {"flight_record": ""}).status_code == 404


# ── el modelo ─────────────────────────────────────────────────────────────────


class TestModel:
    def test_a_row_needs_a_permit_or_a_cost_center(self, drone, centre):
        document = _doc(drone)

        with pytest.raises(IntegrityError), transaction.atomic():
            FlightLogAnalysis.objects.create(document=document)

    def test_the_aircraft_must_belong_to_the_center(
        self, drone, centre, other_drone, other_centre
    ):
        row = FlightLogAnalysis(
            cost_center=centre, aircraft=other_drone, document=_doc(drone)
        )

        with pytest.raises(ValidationError) as caught:
            row.clean()
        assert "aircraft" in caught.value.message_dict

    def test_the_aircraft_must_belong_to_the_tenant_of_the_center(
        self, drone, centre, foreign
    ):
        _tenant, f_centre, f_aircraft = foreign
        row = FlightLogAnalysis(
            cost_center=f_centre, aircraft=drone, document=_doc(drone)
        )

        with pytest.raises(ValidationError) as caught:
            row.clean()
        assert "aircraft" in caught.value.message_dict
        FlightLogAnalysis(
            cost_center=f_centre, aircraft=f_aircraft, document=_doc(f_aircraft)
        ).clean()

    def test_the_permit_must_belong_to_the_center(self, permit, other_centre):
        row = FlightLogAnalysis(
            permission=permit, cost_center=other_centre, document=_doc(permit._aircraft)
        )

        with pytest.raises(ValidationError) as caught:
            row.clean()
        assert "permission" in caught.value.message_dict

    def test_a_row_placed_only_by_its_permit_takes_its_center(self, permit):
        row = FlightLogAnalysis.objects.create(
            permission=permit, document=_doc(permit._aircraft, "DJIFlightRecord_p.txt")
        )

        assert row.cost_center == permit.cost_center


class TestBackfill:
    """La migración de datos: `cost_center` del permiso y `aircraft` sólo si es inequívoca."""

    def _legacy(self, permit, name, aircraft=None):
        """Una fila como la dejó LV-427: con permiso y sin centro ni aeronave."""
        row = FlightLogAnalysis.objects.create(
            permission=permit, document=_doc(permit._aircraft, name)
        )
        FlightLogAnalysis.objects.filter(pk=row.pk).update(cost_center=None)
        if aircraft is not None:
            record = FlightRecord.objects.create(
                permission=permit,
                actual_date=TODAY,
                departure_time=time(9),
                arrival_time=time(10),
                pilot=permit._pilot,
                aircraft=aircraft,
            )
            FlightLogAnalysis.objects.filter(pk=row.pk).update(flight_record=record)
        return row.pk

    def test_it_fills_the_center_and_the_unambiguous_aircraft(
        self, permit, other_drone
    ):
        plain = self._legacy(permit, "DJIFlightRecord_1.txt")
        linked = self._legacy(permit, "DJIFlightRecord_2.txt", permit._aircraft)
        # El vuelo enlazado usa una aeronave de OTRO centro: ambiguo, queda nula.
        ambiguous = self._legacy(permit, "DJIFlightRecord_3.txt", other_drone)

        changed = backfill(django_apps)

        rows = {
            pk: FlightLogAnalysis.objects.get(pk=pk)
            for pk in (plain, linked, ambiguous)
        }
        assert changed == 3
        assert all(r.cost_center_id == permit.cost_center_id for r in rows.values())
        assert rows[plain].aircraft is None
        assert rows[linked].aircraft == permit._aircraft
        assert rows[ambiguous].aircraft is None
        # Idempotente.
        assert backfill(django_apps) == 0


def test_the_stored_file_is_reachable_through_the_aircraft_document(
    fake, drone, centre
):
    """El `.TXT` cuelga de la aeronave y su análisis se puede repetir con el comando."""
    from django.core.management import call_command

    _upload(login_as(VIEW, ADD), centre, drone)
    analysis = FlightLogAnalysis.objects.get()
    FlightLogAnalysis.objects.filter(pk=analysis.pk).update(status="pending", result={})

    call_command("analyze_flight_logs")

    assert FlightLogAnalysis.objects.get(pk=analysis.pk).status == "ok"
