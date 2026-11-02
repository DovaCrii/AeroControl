"""LV-383 PR 3: la pantalla «Registrar ingreso a servicio técnico» (subir, revisar, confirmar).

PDF sintético y datos ficticios solamente: OT `TEST-00003`, serie `TESTSERIAL00000003`,
correos @example.test, RUT 11.111.111-1. El almacenamiento de documentos apunta a un
`tmp_path`, así que ninguna prueba escribe fuera de él.
"""

import io
import json
import re

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core import signing
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.urls import reverse
from django.utils.translation import gettext, override
from reportlab.pdfgen import canvas

from apps.compliance.models import Document, DocumentType
from apps.compliance.storage import get_document_storage
from apps.core.models import AuditEvent, OperationalTenant
from apps.core.testing import login_as
from apps.maintenance import intake_views
from apps.maintenance.forms import WorkshopIntakeForm
from apps.maintenance.intake_views import (
    INTAKE_SALT,
    PENDING_PREFIX,
    RECEIPT_TYPE_CODE,
    make_token,
)
from apps.maintenance.models import (
    MaintenanceHistory,
    MaintenanceRecord,
    WorkshopIntake,
)
from apps.maintenance.test_intake_quote import QUOTE_LINES
from apps.maintenance.test_intake_readers import PAGE_1, PAGE_2
from apps.registry.models import Aircraft, CostCenter

pytestmark = pytest.mark.django_db

ORDER = "TEST-00003"
SERIAL = "TESTSERIAL00000003"
NEW_URL = "maintenance-intake-new"
CONFIRM_URL = "maintenance-intake-confirm"


def _pdf(pages):
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    for lines in pages:
        y = 800
        for line in lines:
            pdf.drawString(40, y, line)
            y -= 15 if line else 18
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def reception_pdf(findings=None):
    pages = [
        [line.replace("00001", "00003") for line in PAGE_1],
        [line.replace("00001", "00003") for line in PAGE_2],
    ]
    if findings:
        pages[1] = [
            findings if line.startswith("Se recibe") else line for line in pages[1]
        ]
    return _pdf(pages)


def quote_pdf():
    return _pdf([[line.replace("00002", "00003") for line in QUOTE_LINES]])


def unreadable_pdf():
    return _pdf([["Documento cualquiera sin datos de taller"]])


def aircraft(registration="TST-1", serial=SERIAL, **extra):
    extra.setdefault("model", "TEST")
    return Aircraft.objects.create(
        registration=registration,
        type="Multirotor",
        manufacturer="Maker",
        serial_number=serial,
        **extra,
    )


def operator_client(*extra):
    return login_as("add_maintenancerecord", "add_document", *extra)


@pytest.fixture(autouse=True)
def documents_root(settings, tmp_path):
    settings.DOCUMENTS_ROOT = tmp_path
    return tmp_path


def upload(client, data, name="taller.pdf", **extra):
    file = SimpleUploadedFile(name, data, content_type="application/pdf")
    return client.post(reverse(NEW_URL), {"file": file, **extra})


def token_of(response):
    return re.search(r'name="token" value="([^"]+)"', response.content.decode()).group(
        1
    )


def confirm_data(token, aircraft_obj=None, **extra):
    data = {
        "token": token,
        "aircraft": str(aircraft_obj.pk) if aircraft_obj else "",
        "workshop_name": "Geocom",
        "workshop_order": ORDER,
        "received_at": "2026-01-01T10:00",
        "sent_by": "head_office",
        "sender_cost_center": "",
        "delivered_by": "Persona Ejemplo",
        "accessories": "Control remoto",
        "findings": "Helice danada",
    }
    data.update(extra)
    return data


def confirm(client, token, aircraft_obj=None, **extra):
    return client.post(reverse(CONFIRM_URL), confirm_data(token, aircraft_obj, **extra))


def register(client, data, aircraft_obj, **extra):
    """Sube `data` y lo confirma: devuelve la respuesta de la confirmación."""
    token = token_of(upload(client, data))
    return confirm(client, token, aircraft_obj, **extra)


def steps(record):
    rows = MaintenanceHistory.objects.filter(record=record).order_by("sequence")
    return [(r.previous_status, r.new_status) for r in rows]


class TestPermissions:
    @pytest.mark.parametrize(
        "codenames",
        [("add_maintenancerecord",), ("add_document",), ("view_maintenancerecord",)],
    )
    def test_each_permission_is_required_on_every_endpoint(self, codenames):
        client = login_as(*codenames)
        assert client.get(reverse(NEW_URL)).status_code == 403
        assert upload(client, reception_pdf()).status_code == 403
        assert client.post(reverse(CONFIRM_URL), {"token": "x"}).status_code == 403

    def test_the_confirm_view_does_not_answer_get(self):
        assert operator_client().get(reverse(CONFIRM_URL)).status_code == 405

    def test_anonymous_goes_to_login(self, client):
        response = client.get(reverse(NEW_URL))
        assert response.status_code == 302 and "login" in response.url

    def test_the_upload_form_opens_with_both_permissions(self):
        response = operator_client().get(reverse(NEW_URL))
        assert response.status_code == 200
        assert 'type="file"' in response.content.decode()


class TestUploadGuards:
    def test_no_file_and_wrong_types_are_refused_with_a_message(self):
        client = operator_client()
        empty = client.post(reverse(NEW_URL), {})
        assert empty.status_code == 200 and empty.context["errors"]
        text = upload(client, b"hola", name="taller.txt")
        assert text.status_code == 200 and text.context["errors"]
        fake = upload(client, b"MZ not a pdf", name="taller.pdf")
        assert fake.status_code == 200 and fake.context["errors"]
        assert 'name="token"' not in fake.content.decode()

    def test_nothing_is_left_in_storage_when_the_upload_is_refused(
        self, documents_root
    ):
        upload(operator_client(), b"MZ not a pdf")
        assert not list(documents_root.rglob("*.pdf"))

    def test_the_aircraft_hint_is_only_kept_for_the_users_company(self):
        mine = aircraft()
        other = OperationalTenant.objects.create(name="Otra", slug="otra")
        theirs = aircraft("OTH-1", serial="TESTSERIAL00000009", tenant=other)
        client = operator_client()
        own = client.get(reverse(NEW_URL), {"aircraft": str(mine.pk)})
        foreign = client.get(reverse(NEW_URL), {"aircraft": str(theirs.pk)})
        junk = client.get(reverse(NEW_URL), {"aircraft": "no-es-un-uuid"})
        assert f'name="aircraft" value="{mine.pk}"' in own.content.decode()
        assert 'name="aircraft"' not in foreign.content.decode()
        assert junk.status_code == 200


class TestReception:
    def test_preview_prefills_from_the_stored_file_and_matches_the_serial(
        self, documents_root
    ):
        plane = aircraft()
        response = upload(operator_client(), reception_pdf())

        assert response.status_code == 200
        content = response.content.decode()
        assert 'data-intake-serial="match"' in content
        assert f"Serie leída: {SERIAL}." in content
        form = response.context["form"]
        assert form.initial["aircraft"] == plane.pk
        assert form.initial["workshop_order"] == ORDER
        assert form.initial["workshop_name"] == "Geocom"
        assert form.initial["delivered_by"] == "Persona Ejemplo"
        # Provisional file, under the pending prefix and nothing else yet.
        stored = [p for p in documents_root.rglob("*") if p.is_file()]
        assert len(stored) == 1
        assert (
            stored[0].relative_to(documents_root).as_posix().startswith(PENDING_PREFIX)
        )
        assert not Document.objects.exists() and not WorkshopIntake.objects.exists()

    def test_happy_path_registers_the_intake_moves_the_aircraft_and_files_the_document(
        self, documents_root
    ):
        plane = aircraft()
        client = operator_client()
        response = register(client, reception_pdf(), plane)

        intake = WorkshopIntake.objects.get()
        record = intake.record
        assert response.status_code == 302
        assert response.url == record.get_absolute_url()
        assert (intake.workshop_name, intake.workshop_order) == ("Geocom", ORDER)
        assert intake.reader == "geocom"
        assert intake.sent_by == "head_office"
        assert intake.received_at is not None
        plane.refresh_from_db()
        assert plane.status == "maintenance"
        assert plane.current_location == "maintenance"
        assert record.status == "at_workshop"
        assert steps(record) == [("pending", "sent"), ("sent", "at_workshop")]

        document = Document.objects.get()
        assert document.doc_type.code == RECEIPT_TYPE_CODE
        assert document.doc_type.requires_expiry is False
        assert document.expiry_date is None
        assert document.content_type == ContentType.objects.get_for_model(
            MaintenanceRecord
        )
        assert document.object_id == record.pk
        assert document.tenant_id == plane.tenant_id
        assert intake.source_document == document and intake.quote_document is None
        assert get_document_storage().exists(document.file_path)
        assert not document.file_path.startswith(PENDING_PREFIX)
        # The provisional copy is gone: only the final file remains.
        assert len([p for p in documents_root.rglob("*") if p.is_file()]) == 1

    def test_the_audit_event_carries_no_personal_data(self):
        plane = aircraft()
        register(operator_client(), reception_pdf(), plane)

        event = AuditEvent.objects.get(action="workshop_intake_registered")
        assert event.model_label == "maintenance.MaintenanceRecord"
        assert event.metadata["order"] == ORDER
        assert event.metadata["reader"] == "geocom"
        assert event.metadata["sent_by"] == "head_office"
        dump = json.dumps(event.metadata) + event.path
        assert "Persona Ejemplo" not in dump and "delivered_by" not in dump
        assert not AuditEvent.objects.filter(metadata__has_key="delivered_by").exists()

    def test_the_template_draws_every_field(self):
        """Un campo del formulario que la plantilla no dibuja se guarda vacío."""
        aircraft()
        response = upload(operator_client(), reception_pdf())
        content = response.content.decode()
        for name in response.context["form"].fields:
            assert f'name="{name}"' in content, name


class TestQuote:
    def test_a_quote_alone_registers_an_intake_without_a_reception_date(self):
        plane = aircraft()
        client = operator_client()
        token = token_of(upload(client, quote_pdf()))
        response = confirm(client, token, plane, received_at="")

        intake = WorkshopIntake.objects.get()
        assert response.status_code == 302
        assert intake.received_at is None
        assert intake.reader == "geocom_quote"
        assert intake.quote_net == 100000 and intake.quote_total == 119000
        assert intake.quote_document is not None and intake.source_document is None
        assert intake.quote_document.title.endswith(ORDER)
        assert intake.record.status == "at_workshop"

    def test_the_quote_section_is_read_only_and_ignores_what_the_client_posts(self):
        plane = aircraft()
        client = operator_client()
        preview = upload(client, quote_pdf())
        content = preview.content.decode()
        assert "data-intake-quote" in content
        assert preview.context["form"].fields["quote_net"].disabled is True
        for name in preview.context["form"].fields:
            assert f'name="{name}"' in content, name

        confirm(
            client,
            token_of(preview),
            plane,
            received_at="",
            quote_net="1",
            quote_total="1",
            diagnosis="inventado por el cliente",
        )

        intake = WorkshopIntake.objects.get()
        assert intake.quote_net == 100000 and intake.quote_total == 119000
        assert "inventado" not in intake.diagnosis

    def test_a_reception_after_the_quote_completes_the_same_intake(self):
        plane = aircraft()
        client = operator_client()
        confirm(client, token_of(upload(client, quote_pdf())), plane, received_at="")
        again = upload(client, reception_pdf())
        assert "data-intake-existing" in again.content.decode()
        response = confirm(client, token_of(again), plane)

        assert response.status_code == 302
        intake = WorkshopIntake.objects.get()
        assert intake.received_at is not None
        assert intake.quote_net == 100000  # the quote stays
        assert intake.quote_document is not None
        assert intake.source_document is not None
        assert intake.quote_document != intake.source_document
        assert Document.objects.filter(object_id=intake.record_id).count() == 2
        assert MaintenanceRecord.objects.count() == 1


class TestDuplicateOrder:
    def test_a_known_order_warns_with_a_link_and_updates_without_duplicating(self):
        plane = aircraft()
        client = operator_client()
        register(client, reception_pdf(), plane, findings="Primer hallazgo")
        intake = WorkshopIntake.objects.get()

        second = upload(client, reception_pdf())
        content = second.content.decode()
        assert "data-intake-existing" in content
        assert intake.record.get_absolute_url() in content
        response = confirm(
            client,
            token_of(second),
            plane,
            findings="Otro hallazgo",
            accessories="Estuche",
        )

        assert response.status_code == 302
        assert WorkshopIntake.objects.count() == 1
        assert MaintenanceRecord.objects.count() == 1
        intake.refresh_from_db()
        assert intake.findings == "Primer hallazgo"  # never overwritten
        assert intake.accessories == "Control remoto"
        assert steps(intake.record) == [("pending", "sent"), ("sent", "at_workshop")]

    def test_the_same_order_for_another_aircraft_is_an_error_not_a_merge(self):
        first = aircraft()
        second = aircraft("TST-2", serial="TESTSERIAL00000010")
        client = operator_client()
        register(client, reception_pdf(), first)

        preview = upload(client, reception_pdf())
        response = confirm(client, token_of(preview), second)

        assert response.status_code == 200
        assert WorkshopIntake.objects.count() == 1
        assert Document.objects.count() == 1


class TestAircraftChoice:
    def test_an_unmatched_serial_needs_an_explicit_choice(self):
        # Same serial but the letter O where the zero is: ADR-0002, never substituted.
        lookalike = aircraft(serial="TESTSERIALO0000003")
        client = operator_client()
        preview = upload(client, reception_pdf())
        content = preview.content.decode()

        assert 'data-intake-serial="none"' in content
        assert f"Serie leída: {SERIAL}, sin coincidencia." in content
        assert "aircraft" not in preview.context["form"].initial
        assert lookalike.pk in [
            a.pk for a in preview.context["form"].fields["aircraft"].queryset
        ]

        refused = confirm(client, token_of(preview), None)
        assert refused.status_code == 200
        assert not WorkshopIntake.objects.exists()
        assert "aircraft" in refused.context["form"].errors

        accepted = confirm(client, token_of(preview), lookalike)
        assert accepted.status_code == 302
        assert WorkshopIntake.objects.get().record.aircraft == lookalike

    def test_a_serial_with_the_zero_changed_is_not_substituted(self):
        aircraft(serial="TESTSERIAL0000OOO3")
        preview = upload(operator_client(), reception_pdf())
        assert preview.context["form"].initial.get("aircraft") is None
        assert 'data-intake-serial="none"' in preview.content.decode()

    def test_another_companys_aircraft_is_neither_offered_nor_linked(self):
        other = OperationalTenant.objects.create(name="Otra", slug="otra")
        theirs = aircraft("OTH-1", tenant=other)  # the very serial that is read
        client = operator_client()
        preview = upload(client, reception_pdf())

        assert 'data-intake-serial="none"' in preview.content.decode()
        offered = [a.pk for a in preview.context["form"].fields["aircraft"].queryset]
        assert theirs.pk not in offered
        assert str(theirs.registration) not in preview.content.decode()

        response = confirm(client, token_of(preview), theirs)
        assert response.status_code == 200
        assert "aircraft" in response.context["form"].errors
        assert not WorkshopIntake.objects.exists() and not Document.objects.exists()

    def test_several_matches_limit_the_selector_to_them(self):
        one = aircraft("TST-1", serial="SERIAL-A")
        two = aircraft("TST-2", serial="SERIAL-B")
        outsider = aircraft("TST-3", serial="SERIAL-C")
        form = WorkshopIntakeForm(
            user=operator_client().user, aircraft_matches=[one, two]
        )
        assert {a.pk for a in form.fields["aircraft"].queryset} == {one.pk, two.pk}
        assert outsider.pk not in {a.pk for a in form.fields["aircraft"].queryset}

    def test_same_model_aircraft_come_first_in_the_selector(self):
        aircraft("AAA-1", serial="SERIAL-A", model="Otro modelo")
        wanted = aircraft("ZZZ-1", serial="SERIAL-B", model="TEST")
        preview = upload(operator_client(), reception_pdf())
        options = list(preview.context["form"].fields["aircraft"].queryset)
        assert options[0].pk == wanted.pk

    def test_the_cost_center_of_the_aircraft_is_preselected_but_must_be_confirmed(self):
        center = CostCenter.objects.create(name="Centro Ejemplo", code="CC-EJ")
        plane = aircraft(cost_center=center)
        client = operator_client()
        preview = upload(client, reception_pdf())

        form = preview.context["form"]
        assert form.initial["sent_by"] == "cost_center"
        assert form.initial["sender_cost_center"] == center.pk
        assert form.fields["sent_by"].required is True

        blank = confirm(client, token_of(preview), plane, sent_by="")
        assert blank.status_code == 200 and "sent_by" in blank.context["form"].errors
        missing = confirm(client, token_of(preview), plane, sent_by="cost_center")
        assert missing.status_code == 200
        assert "sender_cost_center" in missing.context["form"].errors
        ok = confirm(
            client,
            token_of(preview),
            plane,
            sent_by="cost_center",
            sender_cost_center=str(center.pk),
        )
        assert ok.status_code == 302
        assert WorkshopIntake.objects.get().sender_cost_center == center

    def test_nothing_is_preselected_for_the_origin_when_there_is_no_match(self):
        preview = upload(operator_client(), reception_pdf())
        assert preview.context["form"].initial["sent_by"] == ""

    def test_the_aircraft_chosen_from_its_fiche_is_preselected(self):
        plane = aircraft("TST-9", serial="SERIAL-Z")
        client = operator_client()
        preview = upload(client, reception_pdf(), aircraft=str(plane.pk))
        assert preview.context["form"].initial["aircraft"] == plane.pk


class TestUnreadable:
    def test_an_unreadable_pdf_gives_an_empty_manual_form_and_a_notice(self):
        plane = aircraft()
        client = operator_client()
        preview = upload(client, unreadable_pdf())
        content = preview.content.decode()

        assert preview.status_code == 200
        assert "data-intake-unreadable" in content
        assert "No se pudo leer el documento; complete los datos a mano." in content
        assert not preview.context["form"].initial.get("workshop_name")
        assert AuditEvent.objects.filter(action="intake_unreadable").exists()

        response = confirm(
            client,
            token_of(preview),
            plane,
            workshop_name="Taller Ejemplo",
            workshop_order="",
        )
        assert response.status_code == 302
        intake = WorkshopIntake.objects.get()
        assert intake.reader == "" and intake.workshop_order == ""
        assert intake.source_document is not None
        assert intake.workshop_name == "Taller Ejemplo"


class TestTheToken:
    def test_a_tampered_token_is_refused_and_nothing_is_saved(self):
        plane = aircraft()
        client = operator_client()
        token = token_of(upload(client, reception_pdf()))
        response = confirm(client, token[:-2] + "xx", plane)

        assert response.status_code == 302 and response.url == reverse(NEW_URL)
        assert not WorkshopIntake.objects.exists() and not Document.objects.exists()

    def test_an_expired_token_is_refused(self, monkeypatch):
        plane = aircraft()
        client = operator_client()
        token = token_of(upload(client, reception_pdf()))
        path, sha = intake_views.read_token(token, client.user)
        real_time = signing.time.time
        with monkeypatch.context() as patch:
            patch.setattr(signing.time, "time", lambda: real_time() - 7200)
            old = make_token(path, sha, client.user)

        response = confirm(client, old, plane)
        assert response.status_code == 302 and response.url == reverse(NEW_URL)
        assert not WorkshopIntake.objects.exists()

    def test_a_token_is_only_good_for_the_person_it_was_issued_to(self):
        plane = aircraft()
        mine = operator_client()
        token = token_of(upload(mine, reception_pdf()))
        # Same permissions, another person.
        other = login_as("add_maintenancerecord", "add_document", "view_aircraft")

        response = confirm(other, token, plane)
        assert response.status_code == 302 and response.url == reverse(NEW_URL)
        assert not WorkshopIntake.objects.exists()

    def test_a_signed_token_for_a_path_outside_the_pending_area_is_refused(self):
        plane = aircraft()
        client = operator_client()
        # A real stored document of somebody else, signed with the right salt.
        storage = get_document_storage()
        victim = "other/model/00000000/secret.pdf"
        storage.save(victim, io.BytesIO(reception_pdf()))
        import hashlib

        sha = hashlib.sha256(reception_pdf()).hexdigest()
        forged = signing.dumps(
            {"p": victim, "h": sha, "u": str(client.user.pk)}, salt=INTAKE_SALT
        )

        response = confirm(client, forged, plane)
        assert response.status_code == 302 and response.url == reverse(NEW_URL)
        assert not WorkshopIntake.objects.exists()
        assert storage.exists(victim)  # untouched

    def test_a_token_signed_with_another_salt_is_refused(self):
        plane = aircraft()
        client = operator_client()
        token = token_of(upload(client, reception_pdf()))
        path, sha = intake_views.read_token(token, client.user)
        foreign = signing.dumps(
            {"p": path, "h": sha, "u": str(client.user.pk)}, salt="otra.sal"
        )
        response = confirm(client, foreign, plane)
        assert response.status_code == 302 and response.url == reverse(NEW_URL)

    def test_a_file_changed_after_upload_is_refused(self, documents_root):
        plane = aircraft()
        client = operator_client()
        token = token_of(upload(client, reception_pdf()))
        stored = next(p for p in documents_root.rglob("*.pdf"))
        stored.write_bytes(quote_pdf())

        response = confirm(client, token, plane)
        assert response.status_code == 302 and response.url == reverse(NEW_URL)
        assert not WorkshopIntake.objects.exists()

    def test_the_file_path_never_comes_from_the_client(self):
        plane = aircraft()
        client = operator_client()
        token = token_of(upload(client, reception_pdf()))
        response = confirm(
            client,
            token,
            plane,
            path="../../etc/passwd",
            file_path="evil/path.pdf",
            workshop_name="Geocom",
        )
        assert response.status_code == 302
        document = Document.objects.get()
        assert "evil" not in document.file_path and "passwd" not in document.file_path
        assert document.file_path.startswith(f"{RECEIPT_TYPE_CODE}/")


class TestDocumentType:
    def test_the_seed_creates_the_type_with_its_guide(self):
        call_command("seed_document_types")
        doc_type = DocumentType.objects.get(code=RECEIPT_TYPE_CODE)
        assert doc_type.category == DocumentType.CATEGORY_MAINTENANCE
        assert doc_type.requires_expiry is False
        assert doc_type.name == "Recepción en servicio técnico"
        assert doc_type.description and doc_type.sort_order > 0

    def test_the_view_and_the_seed_create_the_same_row(self):
        created_by_view = intake_views._receipt_type()
        fields = (
            "name",
            "category",
            "requires_expiry",
            "is_insurance",
            "is_operational_record",
            "description",
            "reference_code",
            "sort_order",
        )
        snapshot = {f: getattr(created_by_view, f) for f in fields}
        call_command("seed_document_types")
        created_by_view.refresh_from_db()
        assert {f: getattr(created_by_view, f) for f in fields} == snapshot
        assert DocumentType.objects.filter(code=RECEIPT_TYPE_CODE).count() == 1


class TestButtonsAndTranslations:
    def test_the_list_shows_the_button_only_with_both_permissions(self):
        allowed = operator_client("view_maintenancerecord")
        only_maintenance = login_as("add_maintenancerecord", "view_maintenancerecord")
        url = reverse(NEW_URL)
        assert url in allowed.get(reverse("maintenance-list")).content.decode()
        assert (
            url
            not in only_maintenance.get(reverse("maintenance-list")).content.decode()
        )

    def test_the_aircraft_fiche_links_the_screen_with_the_aircraft(self):
        plane = aircraft()
        client = operator_client("view_aircraft", "view_maintenancerecord")
        response = client.get(reverse("aircraft-detail", args=[plane.pk]))
        assert response.status_code == 200
        assert f"{reverse(NEW_URL)}?aircraft={plane.pk}" in response.content.decode()

    def test_the_new_strings_are_translated(self):
        with override("es"):
            assert (
                gettext("Workshop intake saved.")
                == "Ingreso a servicio técnico guardado."
            )
            assert (
                gettext("Register workshop intake")
                == "Registrar ingreso a servicio técnico"
            )
        with override("en"):
            assert gettext("Workshop intake saved.") == "Workshop intake saved."
