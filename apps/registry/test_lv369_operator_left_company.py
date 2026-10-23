"""LV-369: registrar que una persona salió de la empresa.

Pedido (2026-10-23): *«sumar poder archivar o poner cuando un trabajador sale de la
empresa; no es para borrar, es para identificar que no existe hoy»*.

«Archivar» ya existía (`RegistryArchive`, `is_active=False`) pero no distinguía
«se cargó por error o es un duplicado» de «salió». Esto agrega el hecho con fecha
(`left_company_on`), separado de `is_active`. Estos tests fijan:

- la regla en el **modelo** (`clean`, constraint, `register_departure`, `rejoin`);
- que las asignaciones se cierran **con la fecha de salida**;
- que las alertas abiertas se resuelven con motivo y **no vuelven**;
- que no se ofrece en ningún selector pero **sigue** en lo histórico;
- el borde del informe mensual (antes / en / después del corte);
- permisos (403), aislamiento de tenant (404) y que el motivo y la nota no
  aparecen en auditoría, registros ni exportaciones sin permiso.
"""

import json
import logging
from datetime import date, timedelta

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext

from apps.compliance.models import Alert, AlertRule, Document, DocumentType
from apps.core.models import AuditEvent, OperationalTenant
from apps.core.testing import login_as
from apps.registry.models import (
    CostCenter,
    KnowledgeAssessment,
    Operator,
    OperatorAssignment,
    Qualification,
    QualificationType,
)

TODAY = timezone.localdate()
NOTE_SENTINEL = "SENTINEL-NOTA-QXZ-4471"


@pytest.fixture
def center(db):
    return CostCenter.objects.create(code="CC738", name="MLP")


@pytest.fixture
def operator(center):
    return Operator.objects.create(
        employee_id="RUT-151515150",
        full_name="Nelson Gallardo Aros",
        cost_center=center,
    )


def _assign(operator, center, start=None):
    return OperatorAssignment.objects.create(
        operator=operator,
        cost_center=center,
        start_date=start or TODAY - timedelta(days=200),
        status="active",
    )


def _rule(entity_type, field, days=60):
    return AlertRule.objects.create(
        name=f"Rule {entity_type}",
        entity_type=entity_type,
        field_to_watch=field,
        days_before_expiry=days,
    )


def _qualification(operator, days=10):
    kind = QualificationType.objects.get_or_create(code="mavic", name="Mavic")[0]
    return Qualification.objects.create(
        operator=operator,
        qualification_type=kind,
        issue_date=TODAY - timedelta(days=300),
        expiry_date=TODAY + timedelta(days=days),
    )


def _operator_document(operator, days=10):
    kind = DocumentType.objects.get_or_create(code="lic", name="License")[0]
    return Document.objects.create(
        title="License",
        doc_type=kind,
        content_type=ContentType.objects.get_for_model(Operator),
        object_id=operator.pk,
        file_path="lic/operator/file.pdf",
        issue_date=TODAY - timedelta(days=300),
        expiry_date=TODAY + timedelta(days=days),
    )


def _open_alert(rule, subject, value=""):
    return Alert.objects.create(
        alert_rule=rule,
        content_type=ContentType.objects.get_for_model(subject),
        object_id=subject.pk,
        watched_value=value,
        message="sin valor real",
    )


def _depart_client():
    return login_as("delete_operator", "change_operator", "view_operator")


@pytest.mark.django_db
class TestTheRuleLivesInTheModel:
    def test_registering_sets_the_date_and_switches_the_record_off(self, operator):
        operator.register_departure(left_on=TODAY, reason="resignation", note="x")

        operator.refresh_from_db()
        assert operator.left_company_on == TODAY
        assert operator.is_active is False
        assert operator.has_left_company
        assert operator.departure_reason == "resignation"

    def test_the_departure_can_be_in_the_past(self, operator):
        past = TODAY - timedelta(days=40)

        operator.register_departure(left_on=past)

        operator.refresh_from_db()
        assert operator.left_company_on == past

    def test_a_future_departure_is_refused(self, operator):
        with pytest.raises(ValidationError) as caught:
            operator.register_departure(left_on=TODAY + timedelta(days=1))

        assert "left_company_on" in caught.value.message_dict
        operator.refresh_from_db()
        assert operator.is_active and operator.left_company_on is None

    def test_an_unknown_reason_and_a_long_note_are_refused(self, operator):
        with pytest.raises(ValidationError) as caught:
            operator.register_departure(left_on=TODAY, reason="fired", note="n" * 201)

        assert {"departure_reason", "departure_note"} <= set(caught.value.message_dict)

    def test_it_cannot_be_registered_twice(self, operator):
        operator.register_departure(left_on=TODAY)

        with pytest.raises(ValidationError):
            operator.register_departure(left_on=TODAY)

    def test_a_record_archived_before_this_existed_can_be_marked_as_left(
        self, operator
    ):
        """Quien se retiró y se archivó con el flujo viejo: se le puede dar la fecha."""
        operator.is_active = False
        operator.save()

        operator.register_departure(left_on=TODAY - timedelta(days=90))

        operator.refresh_from_db()
        assert operator.has_left_company and operator.is_active is False

    def test_clean_rejects_a_reason_without_a_date(self, operator):
        operator.departure_reason = "resignation"

        with pytest.raises(ValidationError) as caught:
            operator.full_clean()

        assert "left_company_on" in caught.value.message_dict

    def test_clean_rejects_someone_who_left_but_is_active(self, operator):
        operator.left_company_on = TODAY

        with pytest.raises(ValidationError) as caught:
            operator.full_clean()

        assert "left_company_on" in caught.value.message_dict

    def test_the_database_refuses_a_reason_without_a_date(self, operator):
        """La constraint cubre lo que `clean()` no ve: admin, import, `update()`."""
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                Operator.objects.filter(pk=operator.pk).update(
                    departure_reason="resignation"
                )

    def test_the_database_refuses_a_note_without_a_date(self, operator):
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                Operator.objects.filter(pk=operator.pk).update(departure_note="x")


@pytest.mark.django_db
class TestAssignmentsCloseOnTheDepartureDate:
    def test_open_assignments_end_on_the_departure_date_not_today(
        self, operator, center
    ):
        left = TODAY - timedelta(days=30)
        assignment = _assign(operator, center)

        operator.register_departure(left_on=left)

        assignment.refresh_from_db()
        assert assignment.end_date == left
        assert assignment.status == "ended"

    def test_an_assignment_that_starts_after_the_departure_ends_on_its_start(
        self, operator, center
    ):
        """`end_date` nunca antes de `start_date` (la misma regla de LV-205)."""
        assignment = _assign(operator, center, start=TODAY - timedelta(days=5))

        operator.register_departure(left_on=TODAY - timedelta(days=30))

        assignment.refresh_from_db()
        assert assignment.end_date == assignment.start_date

    def test_the_cost_center_is_noted_in_the_metadata(self, operator, center):
        _assign(operator, center)

        metadata = operator.register_departure(left_on=TODAY)

        assert metadata["cost_centers"] == ["CC738"]
        assert metadata["assignments_closed"] == 1
        assert metadata["left_on"] == TODAY.isoformat()

    def test_archiving_still_closes_on_today(self, operator, center):
        """La refactorización a `close_open_assignments` no cambió LV-205."""
        assignment = _assign(operator, center)

        _depart_client().post(reverse("operator-archive", args=[operator.pk]))

        assignment.refresh_from_db()
        assert assignment.end_date == TODAY and assignment.status == "ended"


@pytest.mark.django_db
class TestAlertsAndExpirations:
    def test_open_alerts_of_the_person_are_resolved_with_the_reason(self, operator):
        operator.credential_expiry = TODAY + timedelta(days=5)
        operator.save()
        qualification = _qualification(operator)
        document = _operator_document(operator)
        alerts = [
            _open_alert(_rule("registry.operator", "credential_expiry"), operator, "a"),
            _open_alert(
                _rule("registry.qualification", "expiry_date"), qualification, "b"
            ),
            _open_alert(_rule("compliance.document", "expiry_date"), document, "c"),
        ]

        metadata = operator.register_departure(left_on=TODAY)

        assert metadata["alerts_resolved"] == 3
        for alert in alerts:
            alert.refresh_from_db()
            assert alert.is_resolved
            assert alert.resolution_reason == gettext(
                "No longer belongs to the company"
            )

    def test_the_closure_opens_no_effectiveness_check(self, operator):
        """Nadie tiene que verificar la eficacia de una acción sobre alguien que ya
        no está: sin esto, cada alerta abre una verificación pendiente."""
        alert = _open_alert(_rule("registry.operator", "credential_expiry"), operator)

        operator.register_departure(left_on=TODAY)

        alert.refresh_from_db()
        assert alert.effectiveness_due_date is None
        assert alert.effectiveness_is_due is False

    def test_a_normal_resolution_still_starts_the_clock(self, operator):
        """Contraste: el parámetro nuevo no apaga el reloj del resto de los cierres."""
        alert = _open_alert(_rule("registry.operator", "credential_expiry"), operator)

        alert.resolve(reason="renewed")

        alert.refresh_from_db()
        assert alert.effectiveness_due_date is not None

    def test_other_peoples_alerts_are_untouched(self, operator, center):
        other = Operator.objects.create(
            employee_id="RUT-161616160", full_name="Otra Persona", cost_center=center
        )
        alert = _open_alert(_rule("registry.operator", "credential_expiry"), other)

        operator.register_departure(left_on=TODAY)

        alert.refresh_from_db()
        assert alert.is_resolved is False

    def test_the_engine_stops_alerting_what_hangs_from_the_person(self, operator):
        """El control va en el mismo test: un compañero activo SÍ genera alerta,
        así que el cero de quien salió prueba la exclusión y no una regla muerta."""
        stays = Operator.objects.create(
            employee_id="RUT-171717170", full_name="Quien Sigue"
        )
        _qualification(operator, days=10)
        _qualification(stays, days=10)
        _rule("registry.qualification", "expiry_date")
        operator.register_departure(left_on=TODAY)

        call_command("generate_alerts")

        subjects = set(Alert.objects.values_list("object_id", flat=True))
        stays_quals = set(stays.qualifications.values_list("pk", flat=True))
        left_quals = set(operator.qualifications.values_list("pk", flat=True))
        assert subjects == stays_quals
        assert not (subjects & left_quals)

    def test_the_engine_skips_the_documents_of_a_person_who_left(self, operator):
        _operator_document(operator, days=10)
        _rule("compliance.document", "expiry_date")
        operator.register_departure(left_on=TODAY)

        call_command("generate_alerts")

        assert Alert.objects.count() == 0

    def test_the_engine_skips_the_assessments_of_a_person_who_left(self, operator):
        KnowledgeAssessment.objects.create(
            operator=operator,
            score_percent=90,
            passed=True,
            correct_count=9,
            question_count=10,
            expires_on=TODAY + timedelta(days=10),
        )
        _rule("registry.knowledgeassessment", "expires_on")
        operator.register_departure(left_on=TODAY)

        call_command("generate_alerts")

        assert Alert.objects.count() == 0

    def test_the_lists_of_expirations_leave_them_out(self, operator, center):
        from apps.compliance.expirations import upcoming_expirations

        stays = Operator.objects.create(
            employee_id="RUT-171717170", full_name="Quien Sigue", cost_center=center
        )
        _qualification(operator, days=10)
        _qualification(stays, days=10)
        operator.credential_expiry = TODAY + timedelta(days=5)
        operator.save()
        _operator_document(operator, days=10)
        operator.register_departure(left_on=TODAY)

        items = upcoming_expirations(TODAY, TODAY + timedelta(days=30))

        labels = " | ".join(f"{i['label']} {i.get('subject', '')}" for i in items)
        assert "Quien Sigue" in labels
        assert "Nelson" not in labels

    def test_the_credential_notice_skips_the_person(self, operator, capsys):
        operator.email = "nelson@test.com"
        operator.credential_expiry = TODAY + timedelta(days=5)
        operator.save()
        operator.register_departure(left_on=TODAY)

        call_command("notify_expiring_credentials", "--dry-run")

        assert "nelson@test.com" not in capsys.readouterr().out

    def test_the_calendar_leaves_out_their_qualifications(self, operator):
        _qualification(operator, days=10)
        operator.register_departure(left_on=TODAY)
        client = login_as("view_qualification", "view_operator", "view_document")

        response = client.get(
            reverse("calendar-events"),
            {
                "start": TODAY.isoformat(),
                "end": (TODAY + timedelta(days=30)).isoformat(),
                "types": "qualification",
            },
        )

        assert response.status_code == 200
        assert response.json() == []


@pytest.mark.django_db
class TestRejoining:
    def test_it_clears_the_departure_and_keeps_the_trail_in_the_audit(
        self, operator, center
    ):
        left = TODAY - timedelta(days=20)
        operator.register_departure(left_on=left, reason="resignation", note="x")

        client = _depart_client()
        response = client.post(reverse("operator-restore", args=[operator.pk]))

        assert response.status_code == 302
        operator.refresh_from_db()
        assert operator.is_active is True
        assert operator.left_company_on is None
        assert operator.departure_reason == "" and operator.departure_note == ""
        event = AuditEvent.objects.get(action="operator_rejoined")
        assert event.metadata["previous_left_on"] == left.isoformat()

    def test_the_alerts_the_departure_resolved_come_back(self, operator):
        """El motor deduplica contra lo resuelto con el mismo valor: sin reabrir, una
        credencial vencida no volvería a avisar jamás."""
        alert = _open_alert(
            _rule("registry.operator", "credential_expiry"), operator, "2026-01-01"
        )
        operator.register_departure(left_on=TODAY)
        operator.refresh_from_db()

        metadata = operator.rejoin()

        alert.refresh_from_db()
        assert metadata["alerts_reopened"] == 1
        assert alert.is_resolved is False

    def test_an_alert_resolved_by_a_person_is_not_reopened(self, operator):
        alert = _open_alert(_rule("registry.operator", "credential_expiry"), operator)
        alert.resolve(reason="Fuera de CC con operación RPA")
        operator.register_departure(left_on=TODAY)
        operator.refresh_from_db()

        operator.rejoin()

        alert.refresh_from_db()
        assert alert.is_resolved is True

    def test_restoring_an_ordinary_archive_is_untouched(self, operator):
        client = _depart_client()
        client.post(reverse("operator-archive", args=[operator.pk]))

        response = client.post(reverse("operator-restore", args=[operator.pk]))

        assert response.status_code == 302
        operator.refresh_from_db()
        assert operator.is_active
        assert not AuditEvent.objects.filter(action="operator_rejoined").exists()

    def test_rejoining_someone_who_had_not_left_returns_none(self, operator):
        assert operator.rejoin() is None


@pytest.mark.django_db
class TestNotOfferedInPickersButStillHistorical:
    def test_the_picker_forms_do_not_offer_them(self, operator):
        from apps.registry.forms import (
            AssignmentForm,
            OperatorAssignmentForm,
            OperatorBulkAssignForm,
            QualificationForm,
        )

        operator.register_departure(left_on=TODAY)

        for form in (
            AssignmentForm(),
            OperatorAssignmentForm(),
            QualificationForm(),
        ):
            assert operator not in form.fields["operator"].queryset
        assert operator not in OperatorBulkAssignForm().fields["operators"].queryset

    def test_the_picker_keeps_the_person_already_on_an_existing_record(
        self, operator, center
    ):
        """Sacarlo del queryset lo borraría al guardar cualquier otra edición."""
        from apps.registry.forms import QualificationForm

        qualification = _qualification(operator)
        operator.register_departure(left_on=TODAY)

        form = QualificationForm(instance=qualification)

        assert operator in form.fields["operator"].queryset

    def test_the_permit_form_does_not_offer_them_for_a_new_permit(self, operator):
        from apps.operations.forms import FlightPermissionForm

        operator.register_departure(left_on=TODAY)

        form = FlightPermissionForm()

        assert operator not in form.fields["operators"].queryset

    def test_an_existing_permit_keeps_their_name(self, operator, center):
        from apps.operations.forms import FlightPermissionForm
        from apps.operations.models import FlightPermission

        permit = FlightPermission.objects.create(
            cost_center=center,
            purpose="photogrammetry",
            area_type="unpopulated",
            status="approved",
            permission_number="6405",
            valid_from=TODAY - timedelta(days=5),
            valid_until=TODAY + timedelta(days=30),
        )
        permit.operators.add(operator)
        operator.register_departure(left_on=TODAY)

        assert operator in permit.operators.all()
        form = FlightPermissionForm(instance=permit)
        assert operator in form.fields["operators"].queryset
        page = login_as("view_flightpermission").get(
            reverse("permission-detail", args=[permit.pk])
        )
        assert page.status_code == 200
        assert "Nelson Gallardo Aros" in page.content.decode()

    def test_the_operator_page_and_the_list_still_show_the_record(self, operator):
        operator.register_departure(left_on=TODAY - timedelta(days=3))
        client = login_as("view_operator")

        detail = client.get(reverse("operator-detail", args=[operator.pk]))
        listing = client.get(reverse("operator-list"), {"is_active": "left"})

        assert detail.status_code == 200 and listing.status_code == 200
        assert "Nelson Gallardo Aros" in listing.content.decode()

    def test_the_roster_report_of_today_leaves_them_out(self, operator, center):
        from apps.registry.catastro import build_catastro

        operator.register_departure(left_on=TODAY)
        user = login_as("view_operator", "view_aircraft").user

        catastro = build_catastro(user)

        assert operator.full_name not in str(catastro)


@pytest.mark.django_db
class TestListFilterAndBadges:
    def test_former_employees_are_their_own_filter_value(self, operator, center):
        mistake = Operator.objects.create(
            employee_id="RUT-171717170", full_name="Cargada Por Error"
        )
        mistake.is_active = False
        mistake.save()
        operator.register_departure(left_on=TODAY - timedelta(days=3))
        client = login_as("view_operator")

        def names(value):
            html = client.get(reverse("operator-list"), {"is_active": value}).content
            return html.decode()

        left, archived = names("left"), names("archived")
        assert "Nelson Gallardo Aros" in left and "Cargada Por Error" not in left
        assert "Cargada Por Error" in archived
        assert "Nelson Gallardo Aros" not in archived

    def test_the_badge_names_the_departure_with_symbol_and_date(self, operator):
        operator.register_departure(left_on=date(2026, 3, 9))
        client = login_as("view_operator")

        html = client.get(
            reverse("operator-list"), {"is_active": "left"}
        ).content.decode()

        assert "09-03-2026" in html
        assert "→" in html

    def test_the_detail_page_shows_the_banner_and_the_chip(self, operator):
        operator.register_departure(left_on=date(2026, 3, 9))

        html = (
            login_as("view_operator")
            .get(reverse("operator-detail", args=[operator.pk]))
            .content.decode()
        )

        assert "data-former-employee" in html
        assert "09-03-2026" in html

    def test_the_departure_button_needs_both_permissions(self, operator):
        def button(*codes):
            html = (
                login_as(*codes)
                .get(reverse("operator-detail", args=[operator.pk]))
                .content.decode()
            )
            return reverse("operator-departure", args=[operator.pk]) in html

        assert button("view_operator", "change_operator", "delete_operator")
        assert not button("view_operator", "change_operator")
        assert not button("view_operator", "delete_operator")
        assert not button("view_operator")


@pytest.mark.django_db
class TestTheViewPermissionsAndScope:
    def _url(self, operator):
        return reverse("operator-departure", args=[operator.pk])

    @pytest.mark.parametrize(
        "codes",
        [(), ("view_operator",), ("change_operator",), ("delete_operator",)],
    )
    def test_without_both_permissions_it_is_403(self, operator, codes):
        client = login_as(*codes)

        assert client.get(self._url(operator)).status_code == 403
        assert client.post(self._url(operator), {}).status_code == 403
        operator.refresh_from_db()
        assert operator.is_active and operator.left_company_on is None

    def test_anonymous_users_are_sent_to_login(self, operator, client):
        assert client.post(self._url(operator), {}).status_code == 302

    def test_there_is_no_way_to_delete(self, operator):
        client = _depart_client()

        assert client.delete(self._url(operator)).status_code == 405
        assert Operator.objects.filter(pk=operator.pk).exists()

    def test_another_tenant_gets_404_and_nothing_changes(self):
        a = OperationalTenant.objects.create(name="A", slug="a")
        b = OperationalTenant.objects.create(name="B", slug="b")
        target = Operator.objects.create(
            employee_id="OA1", full_name="Persona A", tenant=a
        )
        intruder = login_as("delete_operator", "change_operator", member_of=b)

        url = reverse("operator-departure", args=[target.pk])
        assert intruder.get(url).status_code == 404
        assert (
            intruder.post(url, {"left_company_on": TODAY.isoformat()}).status_code
            == 404
        )
        target.refresh_from_db()
        assert target.is_active and target.left_company_on is None

    def test_the_owner_of_the_tenant_can_register(self):
        a = OperationalTenant.objects.create(name="A", slug="a")
        target = Operator.objects.create(
            employee_id="OA1", full_name="Persona A", tenant=a
        )
        owner = login_as("delete_operator", "change_operator", member_of=a)

        response = owner.post(
            reverse("operator-departure", args=[target.pk]),
            {"left_company_on": TODAY.isoformat()},
        )

        assert response.status_code == 302
        target.refresh_from_db()
        assert target.has_left_company

    def test_rejoining_across_tenants_is_404(self):
        a = OperationalTenant.objects.create(name="A", slug="a")
        b = OperationalTenant.objects.create(name="B", slug="b")
        target = Operator.objects.create(
            employee_id="OA1", full_name="Persona A", tenant=a
        )
        target.register_departure(left_on=TODAY)
        intruder = login_as("change_operator", member_of=b)

        response = intruder.post(reverse("operator-restore", args=[target.pk]))

        assert response.status_code == 404
        target.refresh_from_db()
        assert target.has_left_company


@pytest.mark.django_db
class TestTheFormPostEndToEnd:
    def test_a_valid_post_registers_and_audits(self, operator, center):
        _assign(operator, center)
        client = _depart_client()

        response = client.post(
            reverse("operator-departure", args=[operator.pk]),
            {
                "left_company_on": (TODAY - timedelta(days=2)).isoformat(),
                "departure_reason": "contract_end",
                "departure_note": "",
            },
        )

        assert response.status_code == 302
        operator.refresh_from_db()
        assert operator.departure_reason == "contract_end"
        event = AuditEvent.objects.get(action="operator_left_company")
        assert event.metadata["cost_centers"] == ["CC738"]
        assert "departure_reason" in event.metadata["fields"]
        assert "departure_note" not in event.metadata["fields"]

    def test_a_future_date_re_renders_with_the_error(self, operator):
        response = _depart_client().post(
            reverse("operator-departure", args=[operator.pk]),
            {"left_company_on": (TODAY + timedelta(days=2)).isoformat()},
        )

        assert response.status_code == 422
        operator.refresh_from_db()
        assert operator.is_active

    def test_the_date_is_required(self, operator):
        response = _depart_client().post(
            reverse("operator-departure", args=[operator.pk]), {}
        )

        assert response.status_code == 422

    def test_the_form_page_renders_for_a_permitted_user(self, operator, center):
        _assign(operator, center)

        response = _depart_client().get(
            reverse("operator-departure", args=[operator.pk])
        )

        assert response.status_code == 200
        assert "Nelson Gallardo Aros" in response.content.decode()

    def test_asking_again_for_someone_who_left_goes_back_to_the_record(self, operator):
        operator.register_departure(left_on=TODAY)

        response = _depart_client().get(
            reverse("operator-departure", args=[operator.pk])
        )

        assert response.status_code == 302


@pytest.mark.django_db
class TestPrivacy:
    def _register(self, operator, caplog):
        with caplog.at_level(logging.DEBUG):
            return _depart_client().post(
                reverse("operator-departure", args=[operator.pk]),
                {
                    "left_company_on": TODAY.isoformat(),
                    "departure_reason": "dismissal",
                    "departure_note": NOTE_SENTINEL,
                },
            )

    def test_the_note_and_the_reason_are_not_in_the_audit_or_the_logs(
        self, operator, caplog
    ):
        response = self._register(operator, caplog)

        assert response.status_code == 302
        for event in AuditEvent.objects.all():
            dump = json.dumps(
                {
                    key: str(value)
                    for key, value in event.__dict__.items()
                    if key != "_state"
                }
            )
            assert NOTE_SENTINEL not in dump
            assert "dismissal" not in dump
        assert NOTE_SENTINEL not in caplog.text
        messages = [str(m) for m in response.wsgi_request._messages]
        assert not any(NOTE_SENTINEL in m for m in messages)

    def test_the_detail_page_hides_the_detail_without_change_permission(
        self, operator, caplog
    ):
        self._register(operator, caplog)
        url = reverse("operator-detail", args=[operator.pk])

        viewer = login_as("view_operator").get(url).content.decode()
        editor = login_as("view_operator", "change_operator").get(url).content.decode()

        label = gettext("Dismissal")
        assert NOTE_SENTINEL not in viewer and label not in viewer
        assert NOTE_SENTINEL in editor and label in editor

    def test_the_csv_hides_the_departure_columns_without_permission(
        self, operator, caplog
    ):
        self._register(operator, caplog)

        def export(*codes):
            response = login_as(*codes).get(reverse("operator-list"), {"export": "csv"})
            return b"".join(response.streaming_content).decode("utf-8")

        viewer = export("view_operator")
        editor = export("view_operator", "change_operator")
        header = str(Operator._meta.get_field("left_company_on").verbose_name).title()
        assert header not in viewer
        assert NOTE_SENTINEL not in viewer and "dismissal" not in viewer
        assert header in editor
        assert NOTE_SENTINEL in editor

    def test_the_csv_neutralises_formulas_in_the_note(self, operator, caplog):
        """El mixin existente es quien neutraliza; esto prueba que la columna nueva
        pasa por él y no por un camino propio."""
        operator.register_departure(left_on=TODAY, note="=1+1")

        response = login_as("view_operator", "change_operator").get(
            reverse("operator-list"), {"export": "csv"}
        )
        body = b"".join(response.streaming_content).decode("utf-8")

        assert "'=1+1" in body
        assert ",=1+1" not in body


@pytest.mark.django_db
class TestTheRosterIsWhatIsActive:
    """El catastro es lo activo: quien salió queda en los registros, no en el catastro."""

    def test_someone_who_left_is_not_in_the_roster_even_when_archived_are_included(
        self, operator, center
    ):
        from django.contrib.auth import get_user_model

        from apps.registry.catastro import CatastroFilters, build_catastro

        root = get_user_model().objects.create_superuser("root", "root@test.com", "pw")
        duplicate = Operator.objects.create(
            employee_id="RUT-161616160",
            full_name="Ficha duplicada",
            cost_center=center,
            is_active=False,
        )
        operator.register_departure(
            left_on=timezone.localdate(), reason="resignation", user=root
        )

        default = build_catastro(root)
        with_archived = build_catastro(root, CatastroFilters(include_archived=True))

        def names(roster):
            return {row.full_name for row in roster["operators"]}

        assert operator.full_name not in names(default)
        assert operator.full_name not in names(with_archived)
        # lo archivado por error o duplicado sí vuelve con «incluir archivados»
        assert duplicate.full_name in names(with_archived)
        operator.refresh_from_db()
        assert operator.left_company_on is not None  # sigue en los registros
