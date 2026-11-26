"""LV-460: cargar el certificado de mantención del taller y cerrar la mantención.

Datos **inventados** que imitan la disposición del certificado y del informe técnico de
Heliboss: serie `TESTSN0000000000460A`, NUI `4600`, personas «Persona Ejemplo» y
«Tecnico Ejemplo», sin teléfono, correo ni RUT. Fechas fijas en el pasado. El
almacenamiento de documentos apunta a un `tmp_path`.
"""

import io
import re
from dataclasses import asdict
from datetime import date
from decimal import Decimal

import pytest
from django.contrib.contenttypes.models import ContentType
from django.contrib.messages import get_messages
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from reportlab.pdfgen import canvas

from apps.compliance.models import Document
from apps.compliance.storage import get_document_storage
from apps.core.models import AuditEvent, OperationalTenant
from apps.core.testing import login_as
from apps.maintenance import certificate_views
from apps.maintenance.certificate_views import CERTIFICATE_TYPE_CODE, make_token
from apps.maintenance.forms import MaintenanceCertificateForm
from apps.maintenance.intake_readers import heliboss, read_intake
from apps.maintenance.intake_readers.closure import (
    CERTIFICATE,
    REPORT,
    merge_closures,
    read_closure,
)
from apps.maintenance.intake_views import PENDING_PREFIX
from apps.maintenance.levels import level_statuses
from apps.maintenance.models import (
    MaintenanceHistory,
    MaintenanceProgram,
    MaintenanceRecord,
)
from apps.maintenance.test_intake_readers import PAGE_1
from apps.registry.models import Aircraft

pytestmark = pytest.mark.django_db

SERIAL = "TESTSN0000000000460A"
NUMBER = "4600"
NEW_URL = "maintenance-certificate-new"
CONFIRM_URL = "maintenance-certificate-confirm"
CANCEL_URL = "maintenance-certificate-cancel"
ISSUED = date(2026, 3, 10)
RECEIVED = date(2026, 3, 2)

CERTIFICATE_LINES = [
    "C  E  R  T  I  F  I  C  A  D  O",
    "Empresa EMPRESA EJEMPLO Fecha 10/03/2026",
    "Contacto Persona Ejemplo NUI 4600 Técnico Tecnico Ejemplo",
    "Tipo Mantención",
    "D A T O S  D E  A E R O N A V E",
    "Marca DJI",
    "Modelo Mavic 3 Enterprise",
    "Payload N/A",
    "Activación 01/01/2025",
    "N° DGAC NA",
    f"S/N AE {SERIAL}",
    "S/N RC TESTRC000460",
    "R E G I S T R O  D E  H O R A S  D E  V U E L O",
    "Ú LT I M O  R E G I S T R O R E G I S T R O  A C T U A L H O R A S",
    "0 h 0 min 12 h 45 min 12 h 45 min",
    "T E S T  Y  C A L I B R A C I Ó N",
    "✓ Verificación de motores",
    "Heliboss certifica que la aeronave Mavic 3 Enterprise, con número de serie",
    f"{SERIAL}, ha cumplido con los requisitos de mantenimiento",
    "correspondientes a las 150 horas de vuelo o 6 meses de operación.",
    "durante las próximas 150 horas de vuelo o 6 meses.",
    "HELIBOSS · DJI AUTHORIZED SERVICE CENTER · 2026",
    "NUI: 4600",
    "10/03/2026",
]

REPORT_LINES = [
    "Servicio Técnico Autorizado DJI · ASC Enterprise",
    "INFORME TÉCNICO DE MANTENCIÓN",
    "Mantención Preventiva",
    "N° INFORME 4600",
    "CLIENTE EMPRESA EJEMPLO",
    f"EQUIPO INSPECCIONADO DJI Mavic 3 Enterprise / {SERIAL}",
    "TIPO DE MANTENCIÓN Mantención preventiva",
    "FECHA DE INGRESO 2 de marzo de 2026",
    "FECHA DEL INFORME 10 de marzo de 2026",
    "TÉCNICO RESPONSABLE Tecnico Ejemplo",
    "HELIBOSS | Informe técnico de mantención · NUI 4600 · Mavic 3 Enterprise",
    "Veredicto APTO PARA VUELO Estado del informe Completado",
    "Tipo de mantención Mantención preventiva Técnico responsable Tecnico Ejemplo",
    f"Modelo Mavic 3 Enterprise N° de serie {SERIAL}",
    "S/N control remoto (RC) TESTRC000460 Horas de vuelo 12 h 45 min",
    "1 Motores Verificar que los motores giran suavemente. OK",
]

CERTIFICATE_TEXT = "\n".join(CERTIFICATE_LINES)
REPORT_TEXT = "\n".join(REPORT_LINES)


def _pdf(lines):
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.setFont("Helvetica", 7)
    y = 800
    for line in lines:
        if "✓" in line:  # not in Helvetica's encoding
            continue
        pdf.drawString(30, y, line)
        y -= 12
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def certificate_pdf():
    return _pdf(CERTIFICATE_LINES)


def report_pdf():
    return _pdf(REPORT_LINES)


def make_aircraft(registration="TST-460", serial=SERIAL, **extra):
    extra.setdefault("model", "Mavic 3 Enterprise")
    return Aircraft.objects.create(
        registration=registration,
        type="Multirotor",
        manufacturer="DJI",
        serial_number=serial,
        **extra,
    )


def data(**extra):
    values = {
        "completed_date": ISSUED,
        "certificate_number": NUMBER,
        "performed_by": "Heliboss",
        "hours_at": Decimal("12.8"),
        "maintenance_type": "scheduled",
        "level": "basic",
        "notes": "Veredicto del taller: APTO PARA VUELO",
        "workshop_name": "Heliboss",
    }
    values.update(extra)
    return values


def walk(record, *statuses):
    for status in statuses:
        record.status = status
        record.save()
    return record


def steps(record):
    rows = MaintenanceHistory.objects.filter(record=record).order_by("sequence")
    return [(r.previous_status, r.new_status) for r in rows]


@pytest.fixture(autouse=True)
def documents_root(settings, tmp_path):
    settings.DOCUMENTS_ROOT = tmp_path
    return tmp_path


def operator_client(*extra):
    return login_as(
        "add_maintenancerecord", "change_maintenancerecord", "add_document", *extra
    )


def upload(client, *files, **extra):
    uploads = [
        SimpleUploadedFile(f"doc{i}.pdf", content, content_type="application/pdf")
        for i, content in enumerate(files)
    ]
    return client.post(reverse(NEW_URL), {"files": uploads, **extra})


def token_of(response):
    return re.search(r'name="token" value="([^"]+)"', response.content.decode()).group(
        1
    )


def confirm(client, token, aircraft, **extra):
    values = {
        "token": token,
        "aircraft": str(aircraft.pk) if aircraft else "",
        "completed_date": "2026-03-10",
        "certificate_number": NUMBER,
        "performed_by": "Heliboss",
        "hours_at": "12.8",
        "maintenance_type": "scheduled",
        "level": "basic",
        "notes": "Veredicto del taller: APTO PARA VUELO",
    }
    values.update(extra)
    return client.post(reverse(CONFIRM_URL), values)


def aircraft_documents(aircraft):
    return Document.objects.filter(
        content_type=ContentType.objects.get_for_model(Aircraft), object_id=aircraft.pk
    )


# --------------------------------------------------------------------------- lector


class TestCertificateReader:
    def test_every_field_of_the_certificate(self):
        proposal = read_closure(CERTIFICATE_TEXT)
        assert proposal.document_kind == CERTIFICATE
        assert proposal.reader == "heliboss_certificate"
        assert proposal.workshop_name == "Heliboss"
        assert proposal.workshop_order == NUMBER
        assert proposal.serial_number == SERIAL
        assert proposal.equipment_label == "DJI Mavic 3 Enterprise"
        assert proposal.issued_on == ISSUED
        # The current record of the hours block (second duration), 12 h 45 min.
        assert proposal.hours == Decimal("12.8")
        assert proposal.maintenance_kind == "Mantención"
        assert (proposal.interval_hours, proposal.interval_months) == (150, 6)
        assert proposal.received_on is None and proposal.verdict is None

    def test_the_hours_are_the_current_record_not_the_last_one(self):
        text = CERTIFICATE_TEXT.replace(
            "0 h 0 min 12 h 45 min 12 h 45 min", "3 h 10 min 12 h 45 min 9 h 35 min"
        )
        assert read_closure(text).hours == Decimal("12.8")

    def test_letter_spacing_with_wider_gaps_is_tolerated(self):
        text = CERTIFICATE_TEXT.replace("  ", "   ")
        proposal = read_closure(text)
        assert proposal.document_kind == CERTIFICATE
        assert proposal.hours == Decimal("12.8")

    def test_a_value_on_the_next_line_is_never_taken(self):
        """pdfminer separates a label from its value: "NUI" then a date below it."""
        text = "\n\n".join(
            [
                "C   E   R   T   I   F   I   C   A   D   O",
                "Fecha",
                "NUI",
                "10/03/2026",
                "4600",
                "S/N AE",
                "TESTRC000460",  # a column layout: the remote's serial, not the aircraft's
                "Heliboss certifica que la aeronave Mavic 3 Enterprise, con número de "
                f"serie {SERIAL}, ha cumplido",
                "HELIBOSS · DJI AUTHORIZED SERVICE CENTER",
            ]
        )
        proposal = read_closure(text)
        assert proposal.workshop_order is None  # not "10"
        assert proposal.issued_on is None
        # The paragraph gives the right serial, and the model.
        assert proposal.serial_number == SERIAL
        assert proposal.equipment_label == "Mavic 3 Enterprise"

    def test_no_personal_data_is_kept(self):
        values = " ".join(
            str(v) for v in asdict(read_closure(CERTIFICATE_TEXT)).values()
        )
        assert "Persona" not in values and "Tecnico" not in values
        assert "EMPRESA" not in values


class TestReportReader:
    def test_every_field_of_the_report(self):
        proposal = read_closure(REPORT_TEXT)
        assert proposal.document_kind == REPORT
        assert proposal.reader == "heliboss_report"
        assert proposal.workshop_order == NUMBER
        assert proposal.serial_number == SERIAL
        assert proposal.equipment_label == "DJI Mavic 3 Enterprise"
        assert proposal.issued_on == ISSUED  # "10 de marzo de 2026"
        assert proposal.received_on == RECEIVED  # "2 de marzo de 2026"
        assert proposal.hours == Decimal("12.8")
        assert proposal.maintenance_kind == "Mantención preventiva"
        assert proposal.verdict == "APTO PARA VUELO"

    def test_the_type_never_drags_the_technicians_name(self):
        text = REPORT_TEXT.replace(
            "TIPO DE MANTENCIÓN Mantención preventiva",
            "TIPO DE MANTENCIÓN Mantención preventiva Técnico responsable Tecnico Ejemplo",
        )
        assert read_closure(text).maintenance_kind == "Mantención preventiva"

    def test_a_date_in_words_with_an_unknown_month_stays_empty(self):
        text = REPORT_TEXT.replace("10 de marzo de 2026", "10 de brumario de 2026")
        assert read_closure(text).issued_on is None

    def test_no_personal_data_is_kept(self):
        values = " ".join(str(v) for v in asdict(read_closure(REPORT_TEXT)).values())
        assert "Persona" not in values and "Tecnico" not in values


class TestReadersContract:
    @pytest.mark.parametrize(
        "text", [None, "", "   ", 42, "Documento cualquiera sin datos de taller"]
    )
    def test_anything_else_is_none(self, text):
        assert read_closure(text) is None

    def test_a_workshop_reception_is_not_a_closure_and_the_other_way_round(self):
        assert read_closure("\n".join(PAGE_1)) is None
        assert read_intake(CERTIFICATE_TEXT) is None
        assert read_intake(REPORT_TEXT) is None

    def test_a_field_that_fails_stays_none_and_the_rest_is_read(self, monkeypatch):
        def broken(text, proposal):
            raise RuntimeError("boom")

        monkeypatch.setattr(
            heliboss.HelibossCertificateReader, "_hours", staticmethod(broken)
        )
        proposal = read_closure(CERTIFICATE_TEXT)
        assert proposal.hours is None
        assert proposal.serial_number == SERIAL

    def test_a_reader_that_fails_entirely_gives_none(self, monkeypatch):
        def broken(self, text):
            raise RuntimeError("boom")

        monkeypatch.setattr(heliboss.HelibossCertificateReader, "matches", broken)
        monkeypatch.setattr(heliboss.HelibossReportReader, "matches", broken)
        assert read_closure(CERTIFICATE_TEXT) is None

    def test_merging_puts_the_certificate_first(self):
        report = read_closure(REPORT_TEXT)
        report.issued_on = date(2026, 3, 11)
        merged = merge_closures([report, read_closure(CERTIFICATE_TEXT)])
        assert merged.document_kind == CERTIFICATE
        assert merged.issued_on == ISSUED  # the certificate's, not the report's
        assert merged.received_on == RECEIVED  # only the report has it
        assert merged.verdict == "APTO PARA VUELO"
        assert merge_closures([None, None]) is None


# ----------------------------------------------------------------- nivel del programa


class TestLevelProposal:
    def test_the_level_whose_month_interval_matches_is_proposed(self):
        plane = make_aircraft()  # Mavic: 6 / 12 / 18 months (seeded programme)
        assert MaintenanceProgram.level_for_interval(plane, 6) == "basic"
        assert MaintenanceProgram.level_for_interval(plane, 12) == "medium"
        assert MaintenanceProgram.level_for_interval(plane, 7) is None
        assert MaintenanceProgram.level_for_interval(plane, None) is None

    def test_two_levels_with_the_same_interval_propose_nothing(self):
        plane = make_aircraft(model="Zeta 460")
        MaintenanceProgram.objects.create(
            name="Zeta A", model_keywords="zeta", level="basic", interval_months=6
        )
        MaintenanceProgram.objects.create(
            name="Zeta B", model_keywords="zeta", level="medium", interval_months=6
        )
        assert MaintenanceProgram.level_for_interval(plane, 6) is None


# ----------------------------------------------------------------------- el modelo


class TestRegisterCertificate:
    def test_an_open_workshop_record_is_walked_to_completed(self):
        plane = make_aircraft()
        record = MaintenanceRecord.objects.create(
            aircraft=plane, maintenance_type="scheduled", description="Envio"
        )
        walk(record, "sent", "at_workshop")
        plane.refresh_from_db()
        assert plane.status == "maintenance"

        closed, outcome = MaintenanceRecord.register_certificate(plane, data())

        assert outcome == MaintenanceRecord.CERTIFICATE_CLOSED
        assert closed.pk == record.pk
        closed.refresh_from_db()
        assert closed.status == "completed"
        assert closed.completed_date == ISSUED
        assert closed.certificate_number == NUMBER
        assert closed.hours_at == Decimal("12.8")
        assert closed.level == "basic"
        assert closed.performed_by == "Heliboss"
        assert "APTO PARA VUELO" in closed.notes
        # One save per state, so the signal brings the aircraft back.
        assert steps(closed)[-3:] == [
            ("at_workshop", "finished"),
            ("finished", "in_transit"),
            ("in_transit", "completed"),
        ]
        plane.refresh_from_db()
        assert (plane.status, plane.current_location) == ("active", "headquarters")

    def test_the_intake_with_the_same_order_wins_over_the_latest(self):
        plane = make_aircraft()
        intake = MaintenanceRecord.register_workshop_intake(
            plane, {"workshop_name": "Heliboss", "workshop_order": NUMBER}
        )
        later = MaintenanceRecord.objects.create(
            aircraft=plane, maintenance_type="unscheduled", description="Otro"
        )
        walk(later, "sent")

        closed, _outcome = MaintenanceRecord.register_certificate(plane, data())

        assert closed.pk == intake.record_id
        later.refresh_from_db()
        assert later.status == "sent"

    def test_without_an_open_record_a_completed_one_is_created(self):
        plane = make_aircraft()
        before = (plane.status, plane.current_location)

        record, outcome = MaintenanceRecord.register_certificate(plane, data())

        assert outcome == MaintenanceRecord.CERTIFICATE_CREATED
        assert record.status == "completed"
        assert record.completed_date == ISSUED
        assert record.maintenance_type == "scheduled"
        assert NUMBER in record.description
        assert steps(record) == []
        plane.refresh_from_db()
        assert (plane.status, plane.current_location) == before

    def test_the_pending_follow_up_of_the_same_level_is_the_one_closed(self):
        plane = make_aircraft()
        follow_up = MaintenanceRecord.objects.create(
            aircraft=plane,
            maintenance_type="scheduled",
            level="basic",
            description="Programada",
            scheduled_date=date(2026, 4, 1),
        )
        record, outcome = MaintenanceRecord.register_certificate(plane, data())
        assert outcome == MaintenanceRecord.CERTIFICATE_CLOSED
        assert record.pk == follow_up.pk
        assert steps(record) == [
            ("pending", "in_progress"),
            ("in_progress", "completed"),
        ]

    def test_a_pending_record_of_another_level_is_left_alone(self):
        plane = make_aircraft()
        other = MaintenanceRecord.objects.create(
            aircraft=plane,
            maintenance_type="scheduled",
            level="medium",
            description="M",
        )
        record, outcome = MaintenanceRecord.register_certificate(plane, data())
        assert outcome == MaintenanceRecord.CERTIFICATE_CREATED
        other.refresh_from_db()
        assert other.status == "pending"

    def test_the_same_certificate_twice_changes_nothing(self):
        plane = make_aircraft()
        first, _ = MaintenanceRecord.register_certificate(plane, data())
        count = MaintenanceRecord.objects.count()
        again, outcome = MaintenanceRecord.register_certificate(
            plane, data(hours_at=Decimal("99.0"))
        )
        assert outcome == MaintenanceRecord.CERTIFICATE_ALREADY
        assert again.pk == first.pk
        assert MaintenanceRecord.objects.count() == count
        again.refresh_from_db()
        assert again.hours_at == Decimal("12.8")

    def test_the_same_number_on_another_aircraft_is_another_certificate(self):
        MaintenanceRecord.register_certificate(make_aircraft(), data())
        other = make_aircraft("TST-461", serial="TESTSN0000000000461A")
        _record, outcome = MaintenanceRecord.register_certificate(other, data())
        assert outcome == MaintenanceRecord.CERTIFICATE_CREATED

    @pytest.mark.parametrize(
        "bad",
        [
            {"completed_date": date(2999, 1, 1)},
            {"completed_date": None},
            {"certificate_number": "  "},
            {"hours_at": Decimal("-1")},
        ],
    )
    def test_invalid_data_is_refused(self, bad):
        plane = make_aircraft()
        with pytest.raises(ValidationError):
            MaintenanceRecord.register_certificate(plane, data(**bad))
        assert not MaintenanceRecord.objects.filter(aircraft=plane).exists()

    def test_the_levels_count_from_the_certificate(self):
        plane = make_aircraft()
        record, _ = MaintenanceRecord.register_certificate(plane, data())
        basic = next(
            s
            for s in level_statuses(plane, today=date(2026, 4, 1))
            if s.level == "basic"
        )
        assert basic.last == record
        assert basic.due_date == date(2026, 9, 10)
        assert basic.due_hours == Decimal("212.8")
        # The programme schedules the next basic maintenance.
        assert MaintenanceRecord.objects.filter(
            aircraft=plane,
            level="basic",
            status="pending",
            scheduled_date=date(2026, 9, 10),
        ).exists()


# ------------------------------------------------------------------------ las vistas


class TestPermissions:
    @pytest.mark.parametrize(
        "codenames",
        [
            ("add_maintenancerecord", "change_maintenancerecord"),
            ("add_maintenancerecord", "add_document"),
            ("change_maintenancerecord", "add_document"),
        ],
    )
    def test_each_permission_is_required_on_every_endpoint(self, codenames):
        client = login_as(*codenames)
        assert client.get(reverse(NEW_URL)).status_code == 403
        assert upload(client, certificate_pdf()).status_code == 403
        assert client.post(reverse(CONFIRM_URL), {"token": "x"}).status_code == 403
        assert client.post(reverse(CANCEL_URL), {"token": "x"}).status_code == 403

    def test_confirm_and_cancel_do_not_answer_get(self):
        client = operator_client()
        assert client.get(reverse(CONFIRM_URL)).status_code == 405
        assert client.get(reverse(CANCEL_URL)).status_code == 405

    def test_anonymous_goes_to_login(self, client):
        response = client.get(reverse(NEW_URL))
        assert response.status_code == 302 and "login" in response.url

    def test_the_upload_form_opens_with_the_three_permissions(self):
        response = operator_client().get(reverse(NEW_URL))
        assert response.status_code == 200
        assert 'name="files"' in response.content.decode()

    def test_the_buttons_need_the_permissions(self):
        plane = make_aircraft()
        url = reverse(NEW_URL)
        allowed = operator_client("view_maintenancerecord", "view_aircraft")
        denied = login_as("view_maintenancerecord", "view_aircraft", "add_document")
        assert url in allowed.get(reverse("maintenance-list")).content.decode()
        assert url not in denied.get(reverse("maintenance-list")).content.decode()
        detail = reverse("aircraft-detail", kwargs={"pk": plane.pk})
        assert f"{url}?aircraft={plane.pk}" in allowed.get(detail).content.decode()


class TestUploadAndPreview:
    def test_both_documents_are_read_and_the_aircraft_found_by_serial(self):
        plane = make_aircraft()
        response = upload(operator_client(), certificate_pdf(), report_pdf())
        html = response.content.decode()
        assert response.status_code == 200
        assert 'data-certificate-serial="match"' in html
        assert f'value="{plane.pk}" selected' in html
        assert 'value="2026-03-10"' in html
        assert f'value="{NUMBER}"' in html
        assert 'value="12.8"' in html
        assert 'value="Heliboss"' in html
        assert "APTO PARA VUELO" in html
        assert "02-03-2026" in html  # the report's reception date, in the notes
        # The level is a proposal, marked as doubtful.
        assert 'data-certificate-level="doubtful"' in html
        assert 'value="basic" selected' in html
        assert AuditEvent.objects.filter(
            action="maintenance_certificate_uploaded"
        ).exists()

    def test_another_companys_aircraft_is_not_found(self):
        other = OperationalTenant.objects.create(name="Otra", slug="otra")
        make_aircraft("OTH-460", tenant=other)
        html = upload(operator_client(), certificate_pdf()).content.decode()
        assert 'data-certificate-serial="none"' in html
        assert "OTH-460" not in html

    def test_an_unknown_serial_asks_for_the_aircraft(self):
        make_aircraft(serial="TESTSN0000000000999Z")
        html = upload(operator_client(), certificate_pdf()).content.decode()
        assert 'data-certificate-serial="none"' in html
        assert 'data-certificate-level="doubtful"' not in html

    def test_an_unreadable_pdf_is_still_reviewable_by_hand(self):
        html = upload(
            operator_client(), _pdf(["Documento cualquiera sin datos de taller"])
        ).content.decode()
        assert "data-certificate-unreadable" in html
        assert 'data-certificate-serial="unread"' in html

    def test_more_than_two_files_or_a_non_pdf_are_refused(self):
        client = operator_client()
        three = upload(client, certificate_pdf(), report_pdf(), certificate_pdf())
        assert "alert-danger" in three.content.decode()
        text = SimpleUploadedFile("nota.txt", b"hola", content_type="text/plain")
        other = client.post(reverse(NEW_URL), {"files": [text]})
        assert "alert-danger" in other.content.decode()
        assert not get_document_storage().exists(PENDING_PREFIX)

    def test_the_template_draws_every_field(self):
        """Un campo del formulario que la plantilla no dibuja se guarda vacío."""
        make_aircraft()
        chosen = make_aircraft("TST-999", serial="TESTSN0000000000999Z")
        # Choosing the aircraft whose serial is not the read one also draws the
        # mismatch confirmation.
        client = operator_client()
        response = upload(client, certificate_pdf())
        response = confirm(client, token_of(response), chosen)
        html = response.content.decode()
        for name in [
            *MaintenanceCertificateForm.Meta.fields,
            "serial_mismatch_confirmed",
        ]:
            assert f'name="{name}"' in html, name


class TestConfirm:
    def test_it_closes_the_open_record_and_attaches_both_documents(self):
        plane = make_aircraft()
        record = MaintenanceRecord.objects.create(
            aircraft=plane, maintenance_type="scheduled", description="Envio"
        )
        walk(record, "sent", "at_workshop")
        client = operator_client()
        token = token_of(upload(client, certificate_pdf(), report_pdf()))

        response = confirm(client, token, plane)

        assert response.status_code == 302
        assert response.url == record.get_absolute_url()
        record.refresh_from_db()
        assert record.status == "completed"
        assert record.certificate_number == NUMBER
        plane.refresh_from_db()
        assert (plane.status, plane.current_location) == ("active", "headquarters")
        documents = list(aircraft_documents(plane).order_by("title"))
        assert len(documents) == 2
        for document in documents:
            assert document.doc_type.code == CERTIFICATE_TYPE_CODE
            assert document.issue_date == ISSUED
            assert document.expiry_date is None  # the type does not expire
            assert document.tenant_id == plane.tenant_id
            assert get_document_storage().exists(document.file_path)
            assert not document.file_path.startswith(PENDING_PREFIX)
        assert any("Heliboss 4600" in d.title for d in documents)
        event = AuditEvent.objects.get(action="maintenance_certificate_registered")
        assert event.metadata["outcome"] == MaintenanceRecord.CERTIFICATE_CLOSED
        assert event.metadata["certificate_number"] == NUMBER
        assert event.metadata["documents"] == 2
        assert "Persona" not in str(event.metadata)

    def test_the_provisional_files_are_removed(self, documents_root):
        plane = make_aircraft()
        client = operator_client()
        token = token_of(upload(client, certificate_pdf()))
        confirm(client, token, plane)
        pending = documents_root / PENDING_PREFIX.rstrip("/")
        assert not pending.exists() or not any(pending.iterdir())

    def test_without_an_open_record_a_completed_one_is_registered(self):
        plane = make_aircraft()
        client = operator_client()
        confirm(client, token_of(upload(client, certificate_pdf())), plane)
        record = MaintenanceRecord.objects.get(
            aircraft=plane, certificate_number=NUMBER
        )
        assert record.status == "completed"
        assert record.completed_date == ISSUED

    def test_the_same_certificate_again_does_not_duplicate(self):
        plane = make_aircraft()
        client = operator_client()
        pdf = certificate_pdf()  # the very same file, byte for byte
        confirm(client, token_of(upload(client, pdf)), plane)
        records = MaintenanceRecord.objects.count()

        response = confirm(client, token_of(upload(client, pdf)), plane)

        assert response.status_code == 302
        assert MaintenanceRecord.objects.count() == records
        assert aircraft_documents(plane).count() == 1
        levels = [m.level_tag for m in get_messages(response.wsgi_request)]
        assert levels == ["warning"]

    def test_the_preview_warns_that_the_certificate_is_already_registered(self):
        plane = make_aircraft()
        client = operator_client()
        confirm(client, token_of(upload(client, certificate_pdf())), plane)
        html = upload(client, report_pdf()).content.decode()
        assert "data-certificate-existing" in html

    def test_the_report_that_arrives_later_is_attached_to_the_same_job(self):
        plane = make_aircraft()
        client = operator_client()
        confirm(client, token_of(upload(client, certificate_pdf())), plane)
        response = confirm(client, token_of(upload(client, report_pdf())), plane)
        assert response.status_code == 302
        assert MaintenanceRecord.objects.filter(certificate_number=NUMBER).count() == 1
        assert aircraft_documents(plane).count() == 2
        event = AuditEvent.objects.filter(
            action="maintenance_certificate_registered"
        ).latest("created_at")
        assert event.metadata["outcome"] == MaintenanceRecord.CERTIFICATE_ALREADY

    def test_a_different_serial_needs_an_explicit_confirmation(self):
        make_aircraft()
        chosen = make_aircraft("TST-999", serial="TESTSN0000000000999Z")
        client = operator_client()
        token = token_of(upload(client, certificate_pdf()))

        refused = confirm(client, token, chosen)
        assert refused.status_code == 200
        assert "data-certificate-mismatch" in refused.content.decode()
        assert not MaintenanceRecord.objects.filter(aircraft=chosen).exists()

        accepted = confirm(client, token, chosen, serial_mismatch_confirmed="on")
        assert accepted.status_code == 302
        assert MaintenanceRecord.objects.filter(aircraft=chosen).exists()

    def test_another_companys_aircraft_cannot_be_chosen(self):
        other = OperationalTenant.objects.create(name="Otra", slug="otra")
        theirs = make_aircraft("OTH-460", tenant=other)
        client = operator_client()
        response = confirm(client, token_of(upload(client, certificate_pdf())), theirs)
        assert response.status_code == 200
        assert not MaintenanceRecord.objects.filter(aircraft=theirs).exists()
        assert not aircraft_documents(theirs).exists()

    def test_a_future_issue_date_is_refused_without_saving(self):
        plane = make_aircraft()
        client = operator_client()
        token = token_of(upload(client, certificate_pdf()))
        response = confirm(client, token, plane, completed_date="2999-01-01")
        assert response.status_code == 200
        assert not MaintenanceRecord.objects.filter(aircraft=plane).exists()
        assert not aircraft_documents(plane).exists()

    def test_a_token_of_another_person_is_refused(self):
        plane = make_aircraft()
        stranger = login_as("add_document")
        token = make_token([(f"{PENDING_PREFIX}x.pdf", "0" * 64)], stranger.user)
        response = confirm(operator_client(), token, plane)
        assert response.status_code == 302
        assert response.url == reverse(NEW_URL)
        assert not MaintenanceRecord.objects.exists()

    def test_cancel_removes_the_provisional_files(self, documents_root):
        client = operator_client()
        token = token_of(upload(client, certificate_pdf(), report_pdf()))
        paths = [
            path for path, _sha in certificate_views.read_token(token, client.user)
        ]
        assert all(get_document_storage().exists(path) for path in paths)
        response = client.post(reverse(CANCEL_URL), {"token": token})
        assert response.status_code == 302
        assert not any(get_document_storage().exists(path) for path in paths)
