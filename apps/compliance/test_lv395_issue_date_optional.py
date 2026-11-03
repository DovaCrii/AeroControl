"""LV-395: la fecha de emisión es opcional **según el tipo** de documento.

Pedido del usuario (2026-11-03): el certificado de inscripción del drone no
necesita fecha de ingreso. Es una inscripción, no un hecho con fecha: exigirla
invitaba a inventarla.

Lo que se fija, y cada punto tiene su contrapeso:

- un tipo con `requires_issue_date=False` guarda sin emisión en los **tres**
  formularios (carga, lote, tipo); uno que la pide **la sigue exigiendo** —sin eso,
  relajar una bandera relajaría todas sin que nadie lo notara—;
- la migración `0029` es idempotente y reversible, y sólo toca ese tipo;
- quien lee la fecha aguanta un nulo: listados, ficha, orden y cierre mensual.
"""

import importlib
from datetime import date, datetime, timezone

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.urls import reverse

from apps.compliance.forms import (
    DocumentBulkUploadForm,
    DocumentForm,
    DocumentTypeForm,
    issue_date_is_required,
)
from apps.compliance.models import Document, DocumentType
from apps.compliance.monthly import monthly_close_rows, operational_records_qs
from apps.core.testing import login_as
from apps.registry.models import Aircraft, CostCenter

MIGRATION = importlib.import_module(
    "apps.compliance.migrations.0029_lv395_issue_date_optional"
)


@pytest.fixture
def aircraft(db):
    centre = CostCenter.objects.create(code="CC743", name="Faena")
    return Aircraft.objects.create(
        registration="RPA-7213",
        serial_number="1581F7FVC266P00DEDA2",
        cost_center=centre,
    )


@pytest.fixture
def no_issue_type(db):
    return DocumentType.objects.create(
        code="registration-x",
        name="Inscripción",
        requires_expiry=False,
        requires_issue_date=False,
        category=DocumentType.CATEGORY_AIRCRAFT,
    )


@pytest.fixture
def issue_type(db):
    return DocumentType.objects.create(
        code="certificate-x",
        name="Certificado",
        requires_expiry=False,
        category=DocumentType.CATEGORY_AIRCRAFT,
    )


def _data(doc_type, aircraft, **extra):
    data = {
        "doc_type": doc_type.pk,
        "entity_type": ContentType.objects.get_for_model(Aircraft).pk,
        "object_id": str(aircraft.pk),
        "title": "Documento",
    }
    data.update(extra)
    return data


class TestTheUploadFormsHonourTheType:
    @pytest.mark.django_db
    def test_a_type_without_issue_date_saves_without_one(self, aircraft, no_issue_type):
        form = DocumentForm(data=_data(no_issue_type, aircraft))
        form.is_valid()

        assert "issue_date" not in form.errors

    @pytest.mark.django_db
    def test_a_type_that_asks_for_it_still_demands_it(self, aircraft, issue_type):
        form = DocumentForm(data=_data(issue_type, aircraft))
        form.is_valid()

        assert "issue_date" in form.errors

    @pytest.mark.django_db
    def test_the_batch_form_follows_the_same_rule(
        self, aircraft, no_issue_type, issue_type
    ):
        relaxed = DocumentBulkUploadForm(data=_data(no_issue_type, aircraft))
        relaxed.is_valid()
        strict = DocumentBulkUploadForm(data=_data(issue_type, aircraft))
        strict.is_valid()

        assert "issue_date" not in relaxed.errors
        assert "issue_date" in strict.errors

    def test_a_missing_type_keeps_the_old_rule(self):
        assert issue_date_is_required(None) is True

    @pytest.mark.django_db
    def test_the_type_form_can_switch_the_flag(self):
        form = DocumentTypeForm(
            data={
                "name": "Inscripción",
                "code": "registration-y",
                "category": DocumentType.CATEGORY_AIRCRAFT,
                "sort_order": 0,
            }
        )
        assert form.is_valid(), form.errors
        saved = form.save()

        # Un checkbox sin marcar llega ausente: el tipo queda sin pedir emisión.
        assert saved.requires_issue_date is False

    @pytest.mark.django_db
    def test_the_picker_options_carry_data_issue(
        self, aircraft, no_issue_type, issue_type
    ):
        html = str(DocumentForm()["doc_type"])

        assert 'data-issue="no"' in html
        assert 'data-issue="yes"' in html

    @pytest.mark.django_db
    def test_the_hidden_field_marker_is_on_both_pages(self):
        client = login_as("add_document")
        for name in ("document-create", "document-bulk-upload"):
            html = client.get(reverse(name)).content.decode()
            assert "data-issue-date-field" in html


class TestTheSeedAndTheMigration:
    @pytest.mark.django_db
    def test_the_seed_marks_only_the_registration(self):
        call_command("seed_document_types")

        without = set(
            DocumentType.objects.filter(requires_issue_date=False).values_list(
                "code", flat=True
            )
        )
        assert without == {"aircraft-registration"}

    @pytest.mark.django_db
    def test_it_reaches_an_installation_that_already_has_the_row(self):
        DocumentType.objects.create(
            code="aircraft-registration",
            name="Certificado de inscripción RPA",
            category=DocumentType.CATEGORY_AIRCRAFT,
        )
        other = DocumentType.objects.create(
            code="airworthiness-cert",
            name="Aeronavegabilidad",
            category=DocumentType.CATEGORY_AIRCRAFT,
        )

        from django.apps import apps

        MIGRATION.stop_requiring_issue_date(apps, None)
        MIGRATION.stop_requiring_issue_date(apps, None)  # idempotente

        assert not DocumentType.objects.get(
            code="aircraft-registration"
        ).requires_issue_date
        assert DocumentType.objects.get(pk=other.pk).requires_issue_date

    @pytest.mark.django_db
    def test_it_reverses_and_fills_the_missing_dates(self, aircraft, no_issue_type):
        from django.apps import apps

        DocumentType.objects.filter(pk=no_issue_type.pk).update(
            code="aircraft-registration"
        )
        document = Document.objects.create(
            title="Sin emisión",
            doc_type=no_issue_type,
            content_type=ContentType.objects.get_for_model(Aircraft),
            object_id=aircraft.pk,
            file_path="x/y.pdf",
        )
        Document.objects.filter(pk=document.pk).update(
            created_at=datetime(2026, 8, 12, 15, 0, tzinfo=timezone.utc)
        )

        MIGRATION.fill_missing_issue_dates(apps, None)
        MIGRATION.require_issue_date_again(apps, None)

        document.refresh_from_db()
        assert document.issue_date == date(2026, 8, 12)
        assert DocumentType.objects.get(
            code="aircraft-registration"
        ).requires_issue_date


def _undated(doc_type, content_object, **extra):
    return Document.objects.create(
        title=extra.pop("title", "Sin emisión"),
        doc_type=doc_type,
        content_type=ContentType.objects.get_for_model(type(content_object)),
        object_id=content_object.pk,
        file_path=extra.pop("file_path", "x/y.pdf"),
        **extra,
    )


class TestReadersSurviveANull:
    @pytest.mark.django_db
    def test_the_detail_and_the_listings_render_a_dash(self, aircraft, no_issue_type):
        document = _undated(no_issue_type, aircraft)

        client = login_as("view_document")
        detail = client.get(reverse("document-detail", args=[document.pk]))
        assert detail.status_code == 200
        html = detail.content.decode()
        assert '<dd class="col-sm-9">None</dd>' not in html
        assert '<dd class="col-sm-9">—</dd>' in html

        listing = client.get(reverse("document-list"))
        assert listing.status_code == 200

    @pytest.mark.django_db
    def test_undated_documents_sort_after_dated_ones(self, aircraft, no_issue_type):
        from apps.compliance.models import newest_first

        undated = _undated(no_issue_type, aircraft, title="A")
        old = _undated(no_issue_type, aircraft, title="B", issue_date=date(2020, 1, 1))
        new = _undated(no_issue_type, aircraft, title="C", issue_date=date(2026, 1, 1))

        ordered = list(
            Document.objects.filter(pk__in=[undated.pk, old.pk, new.pk]).order_by(
                *newest_first()
            )
        )

        assert ordered == [new, old, undated]

    @pytest.mark.django_db
    def test_the_monthly_close_counts_an_undated_record_by_its_upload_day(self):
        centre = CostCenter.objects.create(code="CC1", name="Faena CC1")
        doc_type = DocumentType.objects.create(
            code="flight-log-x",
            name="Bitácora",
            requires_issue_date=False,
            is_operational_record=True,
        )
        document = _undated(doc_type, centre)
        Document.objects.filter(pk=document.pk).update(
            created_at=datetime(2026, 8, 12, 15, 0, tzinfo=timezone.utc)
        )
        dated = _undated(
            doc_type, centre, title="Con emisión", issue_date=date(2026, 8, 3)
        )

        period = date(2026, 8, 1)
        counted = set(
            operational_records_qs(centre, period).values_list("pk", flat=True)
        )
        rows = monthly_close_rows(period, [centre], [doc_type])

        assert counted == {document.pk, dated.pk}
        assert rows[0]["records_total"] == 2
        assert operational_records_qs(centre, date(2026, 9, 1)).count() == 0

    @pytest.mark.django_db
    def test_the_records_page_and_the_month_filter_accept_undated_ones(self):
        centre = CostCenter.objects.create(code="CC1", name="Faena CC1")
        doc_type = DocumentType.objects.create(
            code="flight-log-y",
            name="Bitácora",
            requires_issue_date=False,
            is_operational_record=True,
        )
        document = _undated(doc_type, centre, title="Bitácora sin fecha")
        Document.objects.filter(pk=document.pk).update(
            created_at=datetime(2026, 8, 12, 15, 0, tzinfo=timezone.utc)
        )

        client = login_as("view_document")
        page = client.get(reverse("operational-records"), {"month": "2026-08"})

        assert page.status_code == 200
        assert "Bitácora sin fecha" in page.content.decode()
        other = client.get(reverse("operational-records"), {"month": "2026-09"})
        assert "Bitácora sin fecha" not in other.content.decode()
