"""LV-442: la Act. 19 del Manual de Operaciones cambia los registros."""

from datetime import date
from importlib import import_module

import pytest
from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.urls import reverse

from apps.compliance.forms import selectable_document_types
from apps.compliance.management.commands.seed_document_types import (
    DOCUMENT_TYPE_GUIDE,
    DOCUMENT_TYPES,
)
from apps.compliance.models import Document, DocumentType
from apps.compliance.monthly import MONTHLY_RECORD_CODES
from apps.compliance.upload_context import suggested_codes_for
from apps.core.testing import login_as
from apps.registry.models import CostCenter

migration = import_module("apps.compliance.migrations.0030_lv442_act19_document_types")

NEW = (
    "operator-qualification-intake",
    "operator-theory-evaluations",
    "rpa-service-life",
)


def _old(code, **extra):
    """Una fila como la dejaba la 0028: lo sembrado antes de la Act. 19."""
    fields = {
        field: values[0] for field, values in migration.CHANGES.get(code, {}).items()
    }
    fields.setdefault("name", extra.pop("name", code))
    return DocumentType.objects.update_or_create(code=code, defaults=fields)[0]


def _seed_row(code):
    return next(row for row in DOCUMENT_TYPES if row[0] == code)


class TestTheSeed:
    def test_the_migration_and_the_seed_agree(self):
        for code, fields in migration.CHANGES.items():
            _c, name, req_expiry, _i, _o, category = _seed_row(code)
            description, reference, order = DOCUMENT_TYPE_GUIDE[code]
            new = {field: values[1] for field, values in fields.items()}
            assert new.get("name", name) == name, code
            assert new.get("description", description) == description, code
            assert new.get("reference_code", reference) == reference, code
            assert new.get("sort_order", order) == order, code
            assert new.get("category", category) == category, code
            assert new.get("requires_expiry", req_expiry) == req_expiry, code
        for code, (
            name,
            description,
            reference,
            order,
            category,
        ) in migration.NEW_TYPES.items():
            row = _seed_row(code)
            assert (row[1], row[5]) == (name, category), code
            assert DOCUMENT_TYPE_GUIDE[code] == (description, reference, order), code

    @pytest.mark.django_db
    def test_the_new_types_exist_and_belong_to_the_right_subject(self):
        call_command("seed_document_types")

        expected = {
            "operator-qualification-intake": ("personnel", "REG-018 R0"),
            "operator-theory-evaluations": ("personnel", "REG-019 R0"),
            "rpa-service-life": ("aircraft", "REG-020 R0"),
        }
        for code, (category, reference) in expected.items():
            kind = DocumentType.objects.get(code=code)
            assert (kind.category, kind.reference_code) == (category, reference)
            assert kind.requires_expiry is False
            assert "provisorio" in kind.description
        assert set(NEW) <= set(suggested_codes_for("registry", "operator")) | set(
            suggested_codes_for("registry", "aircraft")
        )
        assert "rpa-service-life" in suggested_codes_for("registry", "aircraft")
        assert "operator-theory-evaluations" in suggested_codes_for(
            "registry", "operator"
        )

    @pytest.mark.django_db
    def test_a_fresh_install_has_lve_003_archived_and_lve_002_as_aircraft(self):
        DocumentType.objects.filter(
            code__in=("flight-log", "rpa-checklist", "drone-inspection", *NEW)
        ).delete()

        call_command("seed_document_types")

        assert DocumentType.objects.get(code="rpa-checklist").is_active is False
        inspection = DocumentType.objects.get(code="drone-inspection")
        assert (inspection.category, inspection.requires_expiry) == ("aircraft", True)
        log = DocumentType.objects.get(code="flight-log")
        assert log.reference_code == "REG-016 Rev. 2"
        assert "REG-015" in log.description and "NEO" in log.description


@pytest.mark.django_db
class TestTheDataMigration:
    def _apply(self):
        migration.apply_act19(apps, None)

    def _reverse(self):
        migration.revert_act19(apps, None)

    def test_it_moves_the_old_rows_to_act_19(self):
        for code in migration.CHANGES:
            _old(code)

        self._apply()

        log = DocumentType.objects.get(code="flight-log")
        assert (log.name, log.reference_code) == (
            "Registro único de misión",
            "REG-016 Rev. 2",
        )
        assert DocumentType.objects.get(code="rpa-checklist").is_active is False
        inspection = DocumentType.objects.get(code="drone-inspection")
        assert (inspection.category, inspection.requires_expiry) == ("aircraft", True)
        assert DocumentType.objects.filter(code__in=NEW).count() == 3

    def test_it_is_idempotent_and_respects_an_edited_name(self):
        _old("flight-log")
        DocumentType.objects.filter(code="flight-log").update(name="Mi bitácora")

        self._apply()
        self._apply()

        assert DocumentType.objects.get(code="flight-log").name == "Mi bitácora"
        assert DocumentType.objects.filter(code__in=NEW).count() == 3

    def test_the_reverse_restores_the_previous_text(self):
        for code in migration.CHANGES:
            _old(code)
        self._apply()

        self._reverse()

        log = DocumentType.objects.get(code="flight-log")
        assert (log.name, log.reference_code) == ("Bitácora de vuelo", "REG-015")
        assert DocumentType.objects.get(code="rpa-checklist").is_active is True
        inspection = DocumentType.objects.get(code="drone-inspection")
        assert (inspection.category, inspection.requires_expiry) == (
            "operational",
            False,
        )
        assert inspection.sort_order == 30
        assert not DocumentType.objects.filter(code__in=NEW).exists()

    def test_the_reverse_keeps_a_new_type_that_already_has_documents(self):
        self._apply()
        kind = DocumentType.objects.get(code="rpa-service-life")
        _document(_centre("CC1"), kind, date(2026, 8, 10))

        self._reverse()

        assert DocumentType.objects.filter(code="rpa-service-life").exists()


def _centre(code):
    return CostCenter.objects.create(code=code, name=f"Faena {code}")


def _document(centre, kind, when):
    return Document.objects.create(
        title=f"{kind.code} {when}",
        doc_type=kind,
        content_type=ContentType.objects.get_for_model(type(centre)),
        object_id=centre.pk,
        file_path=f"rec/{centre.code}-{kind.code}-{when}.pdf",
        issue_date=when,
    )


@pytest.mark.django_db
class TestLve003IsArchivedButItsDocumentsStay:
    def test_it_is_not_offered_at_upload_but_its_documents_are_listed(self):
        call_command("seed_document_types")
        checklist = DocumentType.objects.get(code="rpa-checklist")
        checklist.is_active = True
        checklist.save()
        document = _document(_centre("CC1"), checklist, date(2026, 8, 10))
        checklist.is_active = False
        checklist.save()

        assert "rpa-checklist" not in {
            kind.code for kind in selectable_document_types()
        }
        response = login_as("view_document", "view_costcenter").get(
            reverse("operational-records")
        )
        assert document in response.context["documents"]


@pytest.mark.django_db
class TestTheMonthlyCloseCountsOnlyTheMissionRecord:
    def test_only_reg_016_counts_and_is_demanded(self):
        assert MONTHLY_RECORD_CODES == ("flight-log",)
        call_command("seed_document_types")
        centre = _centre("CC1")
        empty = _centre("CC2")
        by_code = {
            code: DocumentType.objects.get(code=code)
            for code in ("flight-log", "rpa-checklist", "drone-inspection")
        }
        for kind in by_code.values():
            _document(centre, kind, date(2026, 8, 10))

        response = login_as("view_monthlycompliancereview").get(
            reverse("monthly-review"), {"month": "2026-08"}
        )

        rows = {r["cost_center"].code: r for r in response.context["rows"]}
        row = rows["CC1"]
        counts = {item["doc_type"].code: item["count"] for item in row["records"]}
        assert counts == {"flight-log": 1}
        assert row["records_total"] == 1
        assert row["missing_types"] == []
        # Sin REG-016 en el mes, lo que falta es sólo el REG-016.
        assert [t.code for t in rows["CC2"]["missing_types"]] == ["flight-log"]
        assert empty.pk

        from apps.compliance.monthly import records_in_month

        assert records_in_month(centre, date(2026, 8, 1)) == 1
