from datetime import date, time

import pytest
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.db.models import ProtectedError
from django.test import Client
from django.urls import reverse

from apps.compliance.models import Document, DocumentType
from apps.core.models import AuditEvent
from apps.registry.models import Aircraft, CostCenter, Operator
from .forms import FlightPermissionForm, FlightRecordForm
from .models import FlightPermission, FlightRecord, PermissionHistory


def _attach_dgac_permit_pdf(permission):
    """LV-51/LV-64: the document FlightPermissionApprove requires on file --
    the signed authorization the DGAC returns, not the request letter (those
    are two distinct real documents; see FlightPermissionApprove.post)."""
    doc_type, _created = DocumentType.objects.get_or_create(
        code="dgac-rpa-operation-authorization",
        defaults={"name": "Autorización de Operación RPA (DGAC aprobada)"},
    )
    return Document.objects.create(
        doc_type=doc_type,
        content_type=ContentType.objects.get_for_model(FlightPermission),
        object_id=permission.pk,
        title="Autorización SIGO",
        issue_date=date(2026, 7, 20),
        file_path="permits/sigo.pdf",
    )


def _permission(cost_center, operator, aircraft, **kwargs):
    """A FlightPermission with the given operator/aircraft as its sole roster
    member (OPS-4: operators/aircraft_fleet are M2M, so they cannot be passed
    as .create() kwargs like the old single FKs could)."""
    kwargs.setdefault("permission_number", "PERM-1")
    kwargs.setdefault("purpose", "Training")
    kwargs.setdefault("valid_from", date(2026, 7, 22))
    kwargs.setdefault("valid_until", kwargs["valid_from"])
    kwargs.setdefault("location", "Santiago")
    permission = FlightPermission.objects.create(cost_center=cost_center, **kwargs)
    permission.operators.add(operator)
    permission.aircraft_fleet.add(aircraft)
    return permission


def _permission_form_data(cost_center, operator, aircraft, **overrides):
    data = {
        "status": "requested",
        "permission_number": "PERM-1",
        "operators": [operator.pk],
        "aircraft_fleet": [aircraft.pk],
        "cost_center": cost_center.pk,
        "purpose": "Training",
        "valid_from": "2026-07-22",
        "valid_until": "2026-07-22",
        "location": "Santiago",
        "area_type": "populated",
    }
    data.update(overrides)
    return data


@pytest.mark.django_db
def test_flight_permission_form_requires_an_area_type():
    """R2.6: DAN 151 (populated) vs. DAN 91 (unpopulated) is a real normative
    distinction the audit guide asks to have on record (clause 6.1.3) --
    required from now on, though existing permissions predate the field."""
    cost_center = CostCenter.objects.create(code="OPS", name="Operations")
    operator = Operator.objects.create(
        employee_id="P1", full_name="Pilot One", cost_center=cost_center
    )
    aircraft = Aircraft.objects.create(
        registration="CC-AAA",
        type="Fixed",
        model="A",
        manufacturer="Maker",
        cost_center=cost_center,
    )
    data = _permission_form_data(cost_center, operator, aircraft, area_type="")

    form = FlightPermissionForm(data=data)

    assert not form.is_valid()
    assert "area_type" in form.errors


@pytest.mark.django_db
def test_flight_permission_form_accepts_each_area_type_choice():
    cost_center = CostCenter.objects.create(code="OPS", name="Operations")
    operator = Operator.objects.create(
        employee_id="P1", full_name="Pilot One", cost_center=cost_center
    )
    aircraft = Aircraft.objects.create(
        registration="CC-AAA",
        type="Fixed",
        model="A",
        manufacturer="Maker",
        cost_center=cost_center,
    )
    for choice, _label in FlightPermission.AREA_TYPE_CHOICES:
        data = _permission_form_data(
            cost_center,
            operator,
            aircraft,
            permission_number=f"PERM-{choice}",
            area_type=choice,
        )

        form = FlightPermissionForm(data=data)

        assert form.is_valid(), form.errors
        assert form.save().area_type == choice


@pytest.mark.django_db
def test_existing_permission_without_an_area_type_still_renders():
    """Existing rows predate the field (null, not one of the three choices) --
    the detail page must not blow up on get_area_type_display() for them."""
    cost_center = CostCenter.objects.create(code="OPS", name="Operations")
    operator = Operator.objects.create(
        employee_id="P1", full_name="Pilot One", cost_center=cost_center
    )
    aircraft = Aircraft.objects.create(
        registration="CC-AAA",
        type="Fixed",
        model="A",
        manufacturer="Maker",
        cost_center=cost_center,
    )
    permission = _permission(cost_center, operator, aircraft)
    assert permission.area_type is None
    User.objects.create_superuser("dispatcher", "dispatcher@test.com", "password")
    client = Client()
    assert client.login(username="dispatcher", password="password")

    response = client.get(reverse("permission-detail", args=[permission.pk]))

    assert response.status_code == 200


@pytest.mark.django_db
def test_flight_record_form_rejects_data_that_does_not_match_its_permission():
    cost_center = CostCenter.objects.create(code="OPS", name="Operations")
    operator = Operator.objects.create(
        employee_id="P1", full_name="Pilot One", cost_center=cost_center
    )
    other_operator = Operator.objects.create(
        employee_id="P2", full_name="Pilot Two", cost_center=cost_center
    )
    aircraft = Aircraft.objects.create(
        registration="CC-AAA",
        type="Fixed",
        model="A",
        manufacturer="Maker",
        cost_center=cost_center,
    )
    other_aircraft = Aircraft.objects.create(
        registration="CC-BBB",
        type="Fixed",
        model="B",
        manufacturer="Maker",
        cost_center=cost_center,
    )
    permission = _permission(cost_center, operator, aircraft)

    form = FlightRecordForm(
        data={
            "permission": permission.pk,
            "actual_date": date(2026, 7, 23),
            "departure_time": time(10, 0),
            "arrival_time": time(9, 0),
            "pilot": other_operator.pk,
            "aircraft": other_aircraft.pk,
        }
    )

    assert not form.is_valid()
    assert {"actual_date", "arrival_time", "pilot", "aircraft"}.issubset(form.errors)


@pytest.mark.django_db
def test_flight_record_form_narrows_pickers_to_the_permission_roster():
    # T5.5: with a permission prefilled, the pilot and aircraft pickers only
    # offer that permission's roster, not the whole registry.
    cost_center = CostCenter.objects.create(code="OPS", name="Operations")
    operator = Operator.objects.create(
        employee_id="P1", full_name="Pilot One", cost_center=cost_center
    )
    other_operator = Operator.objects.create(
        employee_id="P2", full_name="Pilot Two", cost_center=cost_center
    )
    aircraft = Aircraft.objects.create(
        registration="CC-AAA",
        type="Fixed",
        model="A",
        manufacturer="M",
        cost_center=cost_center,
    )
    other_aircraft = Aircraft.objects.create(
        registration="CC-BBB",
        type="Fixed",
        model="B",
        manufacturer="M",
        cost_center=cost_center,
    )
    permission = _permission(cost_center, operator, aircraft)

    form = FlightRecordForm(initial={"permission": permission.pk})

    assert list(form.fields["pilot"].queryset) == [operator]
    assert other_operator not in form.fields["pilot"].queryset
    assert list(form.fields["aircraft"].queryset) == [aircraft]
    assert other_aircraft not in form.fields["aircraft"].queryset


@pytest.mark.django_db
def test_flight_record_form_without_permission_offers_the_full_registry():
    cost_center = CostCenter.objects.create(code="OPS", name="Operations")
    Operator.objects.create(
        employee_id="P1", full_name="Pilot One", cost_center=cost_center
    )
    Operator.objects.create(
        employee_id="P2", full_name="Pilot Two", cost_center=cost_center
    )
    form = FlightRecordForm()
    assert form.fields["pilot"].queryset.count() == 2


@pytest.mark.django_db
def test_flight_record_form_permission_picker_excludes_archived_ones():
    """LV-59: the picker someone actually sees when creating a flight record
    from the standalone Vuelos list (T5.5's narrowing only kicks in once a
    permission is already chosen) had no queryset override at all -- every
    permission ever created, unfiltered and in raw pk order."""
    cost_center = CostCenter.objects.create(code="OPS", name="Operations")
    operator = Operator.objects.create(
        employee_id="P1", full_name="Pilot One", cost_center=cost_center
    )
    aircraft = Aircraft.objects.create(
        registration="CC-AAA",
        type="Fixed",
        model="A",
        manufacturer="Maker",
        cost_center=cost_center,
    )
    active = _permission(cost_center, operator, aircraft, permission_number="ACTIVE-1")
    archived = _permission(
        cost_center, operator, aircraft, permission_number="ARCHIVED-1"
    )
    archived.is_active = False
    archived.save(update_fields=["is_active"])

    form = FlightRecordForm()

    assert list(form.fields["permission"].queryset) == [active]


@pytest.mark.django_db
def test_flight_record_form_uses_operational_date_and_time_controls():
    form = FlightRecordForm()

    assert form.fields["actual_date"].widget.input_type == "date"
    assert form.fields["departure_time"].widget.input_type == "time"
    assert form.fields["arrival_time"].widget.input_type == "time"


@pytest.mark.django_db
def test_permission_update_requires_the_change_permission():
    """R2.1: before this view existed, /admin/ was the only place to fix a
    permission -- editing here is protected the same way the transitions are."""
    cost_center = CostCenter.objects.create(code="OPS", name="Operations")
    operator = Operator.objects.create(
        employee_id="P1", full_name="Pilot One", cost_center=cost_center
    )
    aircraft = Aircraft.objects.create(
        registration="CC-AAA",
        type="Fixed",
        model="A",
        manufacturer="Maker",
        cost_center=cost_center,
    )
    permission = _permission(cost_center, operator, aircraft)
    User.objects.create_user("viewer", password="password")
    client = Client()
    assert client.login(username="viewer", password="password")

    response = client.get(reverse("permission-update", args=[permission.pk]))

    assert response.status_code == 403


@pytest.mark.django_db
def test_permission_update_edits_the_permission_and_redirects_to_the_list():
    cost_center = CostCenter.objects.create(code="OPS", name="Operations")
    operator = Operator.objects.create(
        employee_id="P1", full_name="Pilot One", cost_center=cost_center
    )
    aircraft = Aircraft.objects.create(
        registration="CC-AAA",
        type="Fixed",
        model="A",
        manufacturer="Maker",
        cost_center=cost_center,
    )
    permission = _permission(cost_center, operator, aircraft)
    editor = User.objects.create_user("editor", password="password")
    editor.user_permissions.add(
        Permission.objects.get(codename="change_flightpermission")
    )
    client = Client()
    assert client.login(username="editor", password="password")

    response = client.post(
        reverse("permission-update", args=[permission.pk]),
        {
            "status": permission.status,
            "permission_number": "PERM-EDITED",
            "operators": [operator.pk],
            "aircraft_fleet": [aircraft.pk],
            "cost_center": cost_center.pk,
            "purpose": permission.purpose,
            "valid_from": permission.valid_from,
            "valid_until": permission.valid_until,
            "location": "Valparaiso",
            "area_type": "populated",
        },
    )

    assert response.status_code == 302
    assert response.url == reverse("permission-list")
    permission.refresh_from_db()
    assert permission.permission_number == "PERM-EDITED"
    assert permission.location == "Valparaiso"


@pytest.mark.django_db
def test_permission_transition_requires_the_change_permission():
    cost_center = CostCenter.objects.create(code="OPS", name="Operations")
    operator = Operator.objects.create(
        employee_id="P1", full_name="Pilot One", cost_center=cost_center
    )
    aircraft = Aircraft.objects.create(
        registration="CC-AAA",
        type="Fixed",
        model="A",
        manufacturer="Maker",
        cost_center=cost_center,
    )
    permission = _permission(cost_center, operator, aircraft)
    User.objects.create_user("viewer", password="password")
    client = Client()
    assert client.login(username="viewer", password="password")

    response = client.post(reverse("permission-approve", args=[permission.pk]))

    assert response.status_code == 403
    permission.refresh_from_db()
    assert permission.status == "requested"


@pytest.mark.django_db
def test_permission_transition_records_history_with_actor_and_notes():
    cost_center = CostCenter.objects.create(code="OPS", name="Operations")
    operator = Operator.objects.create(
        employee_id="P1", full_name="Pilot One", cost_center=cost_center
    )
    aircraft = Aircraft.objects.create(
        registration="CC-AAA",
        type="Fixed",
        model="A",
        manufacturer="Maker",
        cost_center=cost_center,
    )
    permission = _permission(cost_center, operator, aircraft)
    _attach_dgac_permit_pdf(permission)  # LV-51: required before approval
    User.objects.create_superuser("dispatcher", "dispatcher@test.com", "password")
    client = Client()
    assert client.login(username="dispatcher", password="password")

    response = client.post(
        reverse("permission-approve", args=[permission.pk]),
        {"notes": "Approved after dispatch review."},
    )

    assert response.status_code == 302
    permission.refresh_from_db()
    history = PermissionHistory.objects.get(permission=permission)
    assert permission.status == "approved"
    assert history.previous_status == "requested"
    assert history.new_status == "approved"
    assert history.changed_by == "dispatcher"
    assert history.notes == "Approved after dispatch review."


@pytest.mark.django_db
def test_permission_history_notes_are_rendered_on_the_detail_page():
    """R2.5: the model already captured the transition's notes (see the test
    above), but the template had no column for them -- typing a reason on
    approve/deny had nowhere to show up afterwards."""
    cost_center = CostCenter.objects.create(code="OPS", name="Operations")
    operator = Operator.objects.create(
        employee_id="P1", full_name="Pilot One", cost_center=cost_center
    )
    aircraft = Aircraft.objects.create(
        registration="CC-AAA",
        type="Fixed",
        model="A",
        manufacturer="Maker",
        cost_center=cost_center,
    )
    permission = _permission(cost_center, operator, aircraft)
    User.objects.create_superuser("dispatcher", "dispatcher@test.com", "password")
    client = Client()
    assert client.login(username="dispatcher", password="password")
    client.post(
        reverse("permission-deny", args=[permission.pk]),
        {"notes": "Missing insurance paperwork."},
    )

    content = client.get(
        reverse("permission-detail", args=[permission.pk])
    ).content.decode()

    assert "Missing insurance paperwork." in content


@pytest.mark.django_db
def test_permission_detail_shows_one_status_dropdown_not_a_button_per_action():
    """R2.5: "no siempre se harán cambios" -- one dropdown + notes field
    instead of a button per transition, and it degrades to the first option
    without JS (permission-status.js only overwrites the form's action to
    match whatever was actually selected)."""
    cost_center = CostCenter.objects.create(code="OPS", name="Operations")
    operator = Operator.objects.create(
        employee_id="P1", full_name="Pilot One", cost_center=cost_center
    )
    aircraft = Aircraft.objects.create(
        registration="CC-AAA",
        type="Fixed",
        model="A",
        manufacturer="Maker",
        cost_center=cost_center,
    )
    permission = _permission(cost_center, operator, aircraft)
    User.objects.create_superuser("dispatcher", "dispatcher@test.com", "password")
    client = Client()
    assert client.login(username="dispatcher", password="password")

    content = client.get(
        reverse("permission-detail", args=[permission.pk])
    ).content.decode()

    assert 'id="permission-status-action"' in content
    assert 'id="permission-status-notes"' in content
    approve_url = reverse("permission-approve", args=[permission.pk])
    deny_url = reverse("permission-deny", args=[permission.pk])
    assert f'value="{approve_url}"' in content
    assert f'value="{deny_url}"' in content
    # The form's static action is the first option, so it still works with
    # JS disabled.
    assert f'action="{approve_url}"' in content


@pytest.mark.django_db
def test_permission_detail_back_link_does_not_rely_on_browser_history():
    """R2.5: reproduced live -- every status action (success or failure)
    redirects back to this same URL, which pushes a fresh history entry each
    time. data-history-back's window.history.back() then lands on an earlier
    render of this page instead of the permit list, so "Back" needed two
    clicks. The link already has one well-defined destination."""
    cost_center = CostCenter.objects.create(code="OPS", name="Operations")
    operator = Operator.objects.create(
        employee_id="P1", full_name="Pilot One", cost_center=cost_center
    )
    aircraft = Aircraft.objects.create(
        registration="CC-AAA",
        type="Fixed",
        model="A",
        manufacturer="Maker",
        cost_center=cost_center,
    )
    permission = _permission(cost_center, operator, aircraft)
    User.objects.create_superuser("dispatcher", "dispatcher@test.com", "password")
    client = Client()
    assert client.login(username="dispatcher", password="password")

    content = client.get(
        reverse("permission-detail", args=[permission.pk])
    ).content.decode()

    assert "data-history-back" not in content
    assert reverse("permission-list") in content


@pytest.mark.django_db
def test_permission_approval_is_blocked_without_the_dgac_permit_pdf():
    """LV-51: AeroControl's "approved" must not outrun the real DGAC paperwork
    -- the SIGO-issued authorization letter has to be on file first."""
    cost_center = CostCenter.objects.create(code="OPS", name="Operations")
    operator = Operator.objects.create(
        employee_id="P1", full_name="Pilot One", cost_center=cost_center
    )
    aircraft = Aircraft.objects.create(
        registration="CC-AAA",
        type="Fixed",
        model="A",
        manufacturer="Maker",
        cost_center=cost_center,
    )
    permission = _permission(cost_center, operator, aircraft)
    User.objects.create_superuser("dispatcher", "dispatcher@test.com", "password")
    client = Client()
    assert client.login(username="dispatcher", password="password")

    response = client.post(reverse("permission-approve", args=[permission.pk]))

    assert response.status_code == 302
    permission.refresh_from_db()
    assert permission.status == "requested"
    assert not PermissionHistory.objects.filter(permission=permission).exists()


@pytest.mark.django_db
def test_permission_approval_succeeds_once_the_dgac_permit_pdf_is_attached():
    cost_center = CostCenter.objects.create(code="OPS", name="Operations")
    operator = Operator.objects.create(
        employee_id="P1", full_name="Pilot One", cost_center=cost_center
    )
    aircraft = Aircraft.objects.create(
        registration="CC-AAA",
        type="Fixed",
        model="A",
        manufacturer="Maker",
        cost_center=cost_center,
    )
    permission = _permission(cost_center, operator, aircraft)
    _attach_dgac_permit_pdf(permission)
    User.objects.create_superuser("dispatcher", "dispatcher@test.com", "password")
    client = Client()
    assert client.login(username="dispatcher", password="password")

    response = client.post(reverse("permission-approve", args=[permission.pk]))

    assert response.status_code == 302
    permission.refresh_from_db()
    assert permission.status == "approved"


@pytest.mark.django_db
def test_permission_approval_is_not_satisfied_by_the_request_letter_alone():
    """LV-64: the letter that goes *to* the DGAC as part of the request and
    the signed authorization that comes *back* once approved are two
    distinct real documents -- only the latter (dgac-rpa-operation-
    authorization) certifies an actual DGAC approval."""
    cost_center = CostCenter.objects.create(code="OPS", name="Operations")
    operator = Operator.objects.create(
        employee_id="P1", full_name="Pilot One", cost_center=cost_center
    )
    aircraft = Aircraft.objects.create(
        registration="CC-AAA",
        type="Fixed",
        model="A",
        manufacturer="Maker",
        cost_center=cost_center,
    )
    permission = _permission(cost_center, operator, aircraft)
    letter_type, _created = DocumentType.objects.get_or_create(
        code="dgac-flight-permit",
        defaults={"name": "Autorización DGAC (carta de permiso)"},
    )
    Document.objects.create(
        doc_type=letter_type,
        content_type=ContentType.objects.get_for_model(FlightPermission),
        object_id=permission.pk,
        title="Carta SIGO",
        issue_date=date(2026, 7, 20),
        file_path="permits/letter.pdf",
    )
    User.objects.create_superuser("dispatcher", "dispatcher@test.com", "password")
    client = Client()
    assert client.login(username="dispatcher", password="password")

    response = client.post(reverse("permission-approve", args=[permission.pk]))

    assert response.status_code == 302
    permission.refresh_from_db()
    assert permission.status == "requested"


@pytest.mark.django_db
def test_permission_approval_ignores_a_non_current_or_archived_permit_pdf():
    """A superseded version or an archived upload should not satisfy the
    guard -- only a current, active document counts as "on file"."""
    cost_center = CostCenter.objects.create(code="OPS", name="Operations")
    operator = Operator.objects.create(
        employee_id="P1", full_name="Pilot One", cost_center=cost_center
    )
    aircraft = Aircraft.objects.create(
        registration="CC-AAA",
        type="Fixed",
        model="A",
        manufacturer="Maker",
        cost_center=cost_center,
    )
    permission = _permission(cost_center, operator, aircraft)
    stale = _attach_dgac_permit_pdf(permission)
    stale.is_current_version = False
    stale.save(update_fields=["is_current_version"])
    User.objects.create_superuser("dispatcher", "dispatcher@test.com", "password")
    client = Client()
    assert client.login(username="dispatcher", password="password")

    client.post(reverse("permission-approve", args=[permission.pk]))

    permission.refresh_from_db()
    assert permission.status == "requested"


@pytest.mark.django_db
def test_permission_completion_is_blocked_without_the_dgac_permit_pdf():
    """R2.4: completing used to have no document guard at all -- a permit
    could reach 'approved' with the PDF on file and then 'completed' after
    it was removed/superseded, same risk the approve guard (LV-64) exists to
    prevent."""
    cost_center = CostCenter.objects.create(code="OPS", name="Operations")
    operator = Operator.objects.create(
        employee_id="P1", full_name="Pilot One", cost_center=cost_center
    )
    aircraft = Aircraft.objects.create(
        registration="CC-AAA",
        type="Fixed",
        model="A",
        manufacturer="Maker",
        cost_center=cost_center,
    )
    permission = _permission(cost_center, operator, aircraft, status="approved")
    User.objects.create_superuser("dispatcher", "dispatcher@test.com", "password")
    client = Client()
    assert client.login(username="dispatcher", password="password")

    response = client.post(reverse("permission-complete", args=[permission.pk]))

    assert response.status_code == 302
    permission.refresh_from_db()
    assert permission.status == "approved"


@pytest.mark.django_db
def test_permission_completion_succeeds_once_the_dgac_permit_pdf_is_attached():
    cost_center = CostCenter.objects.create(code="OPS", name="Operations")
    operator = Operator.objects.create(
        employee_id="P1", full_name="Pilot One", cost_center=cost_center
    )
    aircraft = Aircraft.objects.create(
        registration="CC-AAA",
        type="Fixed",
        model="A",
        manufacturer="Maker",
        cost_center=cost_center,
    )
    permission = _permission(cost_center, operator, aircraft, status="approved")
    _attach_dgac_permit_pdf(permission)
    User.objects.create_superuser("dispatcher", "dispatcher@test.com", "password")
    client = Client()
    assert client.login(username="dispatcher", password="password")

    response = client.post(reverse("permission-complete", args=[permission.pk]))

    assert response.status_code == 302
    permission.refresh_from_db()
    assert permission.status == "completed"


@pytest.mark.django_db
def test_flight_permission_with_history_cannot_be_hard_deleted():
    cost_center = CostCenter.objects.create(code="OPS", name="Operations")
    operator = Operator.objects.create(
        employee_id="P1", full_name="Pilot One", cost_center=cost_center
    )
    aircraft = Aircraft.objects.create(
        registration="CC-AAA",
        type="Fixed",
        model="A",
        manufacturer="Maker",
        cost_center=cost_center,
    )
    permission = _permission(cost_center, operator, aircraft)
    PermissionHistory.objects.create(
        permission=permission,
        previous_status="requested",
        new_status="approved",
        changed_by="dispatcher",
    )

    with pytest.raises(ProtectedError):
        permission.delete()


@pytest.mark.django_db
def test_flight_record_form_allows_any_roster_operator_and_fleet_aircraft():
    """OPS-4: a permission's roster can be several operators/aircraft; a flight
    record is valid against any of them, not just "the" first one added."""
    cost_center = CostCenter.objects.create(code="OPS", name="Operations")
    operator_one = Operator.objects.create(
        employee_id="P1", full_name="Pilot One", cost_center=cost_center
    )
    operator_two = Operator.objects.create(
        employee_id="P2", full_name="Pilot Two", cost_center=cost_center
    )
    aircraft = Aircraft.objects.create(
        registration="CC-AAA",
        type="Fixed",
        model="A",
        manufacturer="Maker",
        cost_center=cost_center,
    )
    permission = _permission(
        cost_center,
        operator_one,
        aircraft,
        valid_from=date(2026, 7, 20),
        valid_until=date(2026, 7, 25),
    )
    permission.operators.add(operator_two)

    form = FlightRecordForm(
        data={
            "permission": permission.pk,
            "actual_date": date(2026, 7, 23),  # inside the range, not the start
            "departure_time": time(9, 0),
            "arrival_time": time(10, 0),
            "pilot": operator_two.pk,  # the *second* operator, not the first
            "aircraft": aircraft.pk,
        }
    )

    assert form.is_valid(), form.errors


@pytest.mark.django_db
def test_flight_record_archive_is_audited_as_archived():
    cost_center = CostCenter.objects.create(code="OPS", name="Operations")
    operator = Operator.objects.create(
        employee_id="P1", full_name="Pilot One", cost_center=cost_center
    )
    aircraft = Aircraft.objects.create(
        registration="CC-AAA",
        type="Fixed",
        model="A",
        manufacturer="Maker",
        cost_center=cost_center,
    )
    permission = _permission(cost_center, operator, aircraft)
    record = FlightRecord.objects.create(
        permission=permission,
        actual_date=date(2026, 7, 22),
        departure_time=time(9, 0),
        arrival_time=time(10, 0),
        pilot=operator,
        aircraft=aircraft,
    )
    User.objects.create_superuser("admin", "admin@test.com", "password")
    client = Client()
    assert client.login(username="admin", password="password")

    response = client.post(reverse("record-delete", args=[record.pk]))

    assert response.status_code == 302
    record.refresh_from_db()
    assert record.is_active is False
    event = AuditEvent.objects.latest("created_at")
    assert event.action == "archived"
    assert event.model_label == "operations.FlightRecord"
    assert event.object_id == str(record.pk)


@pytest.mark.django_db
def test_flight_record_detail_back_link_does_not_rely_on_browser_history():
    """R2.5: same fix as the flight permission detail page -- a redirect
    back to this same URL (e.g. after Archive) pushes a fresh history entry,
    which breaks data-history-back's window.history.back()."""
    cost_center = CostCenter.objects.create(code="OPS", name="Operations")
    operator = Operator.objects.create(
        employee_id="P1", full_name="Pilot One", cost_center=cost_center
    )
    aircraft = Aircraft.objects.create(
        registration="CC-AAA",
        type="Fixed",
        model="A",
        manufacturer="Maker",
        cost_center=cost_center,
    )
    permission = _permission(cost_center, operator, aircraft)
    record = FlightRecord.objects.create(
        permission=permission,
        actual_date=date(2026, 7, 22),
        departure_time=time(9, 0),
        arrival_time=time(10, 0),
        pilot=operator,
        aircraft=aircraft,
    )
    User.objects.create_superuser("admin2", "admin2@test.com", "password")
    client = Client()
    assert client.login(username="admin2", password="password")

    content = client.get(reverse("record-detail", args=[record.pk])).content.decode()

    assert "data-history-back" not in content
    assert reverse("record-list") in content


@pytest.mark.parametrize(
    ("departure", "arrival", "expected"),
    [
        (time(9, 0), time(10, 30), "1h 30min"),
        (time(9, 0), time(9, 45), "45min"),
        (time(9, 0), time(11, 0), "2h 00min"),
        # LV-59: FlightRecordForm rejects arrival <= departure, but that is
        # not a model-level constraint -- a record created outside the form
        # (admin, fixture) crossing midnight must not show a negative length.
        (time(23, 0), time(1, 0), "2h 00min"),
    ],
)
def test_flight_record_duration_is_computed_from_departure_and_arrival(
    departure, arrival, expected
):
    record = FlightRecord(departure_time=departure, arrival_time=arrival)
    record.actual_date = date(2026, 7, 22)

    assert record.duration_display == expected


@pytest.mark.django_db
def test_record_list_shows_real_columns_not_the_generic_ones(admin_client):
    """LV-59: was the only list in the area still on the generic Name/
    Created/Status columns -- this is why a screenshot of it showed "Nombre"
    as a column header."""
    cost_center = CostCenter.objects.create(code="OPS", name="Operations")
    operator = Operator.objects.create(
        employee_id="P1", full_name="Pilot One", cost_center=cost_center
    )
    aircraft = Aircraft.objects.create(
        registration="CC-AAA",
        type="Fixed",
        model="A",
        manufacturer="Maker",
        cost_center=cost_center,
    )
    permission = _permission(cost_center, operator, aircraft)
    FlightRecord.objects.create(
        permission=permission,
        actual_date=date(2026, 7, 22),
        departure_time=time(9, 0),
        arrival_time=time(10, 30),
        pilot=operator,
        aircraft=aircraft,
    )

    content = admin_client.get(reverse("record-list")).content.decode()

    assert "Pilot One" in content
    assert "CC-AAA" in content
    assert "1h 30min" in content
    assert reverse("permission-detail", args=[permission.pk]) in content


@pytest.mark.django_db
def test_record_list_htmx_search_keeps_its_own_columns(admin_client):
    """F-13: a live-search HTMX response must carry this list's own columns,
    not collapse to the generic ones (same regression class as LV-53)."""
    cost_center = CostCenter.objects.create(code="OPS", name="Operations")
    operator = Operator.objects.create(
        employee_id="P1", full_name="Pilot One", cost_center=cost_center
    )
    aircraft = Aircraft.objects.create(
        registration="CC-AAA",
        type="Fixed",
        model="A",
        manufacturer="Maker",
        cost_center=cost_center,
    )
    permission = _permission(cost_center, operator, aircraft)
    FlightRecord.objects.create(
        permission=permission,
        actual_date=date(2026, 7, 22),
        departure_time=time(9, 0),
        arrival_time=time(10, 30),
        pilot=operator,
        aircraft=aircraft,
    )

    response = admin_client.get(
        reverse("record-list"), {"q": "CC-AAA"}, HTTP_HX_REQUEST="true"
    )
    content = response.content.decode()

    assert "Pilot One" in content
    assert "1h 30min" in content
