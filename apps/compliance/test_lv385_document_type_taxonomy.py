"""LV-385: la taxonomía de los tipos de documento (PR 2 de 4)."""

from importlib import import_module

import pytest
from django.core.management import call_command
from django.urls import reverse
from django.utils.translation import gettext, override

from apps.compliance.forms import DocumentTypeForm, selectable_document_types
from apps.compliance.management.commands.seed_document_types import (
    DOCUMENT_TYPE_GUIDE,
    DOCUMENT_TYPES,
)
from apps.compliance.models import DocumentType
from apps.core.testing import login_as

MIGRATION = "apps.compliance.migrations.0028_lv385_document_type_taxonomy"
# Tipos sembrados DESPUÉS de la migración 0028: el seed y la vista que los crea los
# traen completos (nombre y guía), así que la migración no tiene nada que renombrar.
CODES_AFTER_THE_MIGRATION = {"workshop-intake-receipt"}  # LV-383


def _migration():
    # Un módulo cuyo nombre empieza con dígito no se puede escribir en un `import`.
    return import_module(MIGRATION)


def _old_seed_row(code):
    """Una fila como la dejaba el sembrado anterior: nombre viejo, guía vacía."""
    old_name = _migration().TAXONOMY[code][0]
    category = next(row[5] for row in DOCUMENT_TYPES if row[0] == code)
    return DocumentType.objects.create(code=code, name=old_name, category=category)


class TestTheSeededCatalogIsStandardised:
    def test_every_seeded_type_has_a_guide_and_nothing_else_does(self):
        assert {row[0] for row in DOCUMENT_TYPES} == set(DOCUMENT_TYPE_GUIDE)

    def test_every_type_says_what_it_is_for(self):
        for code, (description, _ref, _order) in DOCUMENT_TYPE_GUIDE.items():
            assert description.strip(), code
            assert len(description) <= 200, code

    def test_the_sort_order_is_unique_inside_each_category(self):
        seen = set()
        for code, _name, *_flags, category in DOCUMENT_TYPES:
            order = DOCUMENT_TYPE_GUIDE[code][2]
            assert order > 0, code
            assert (category, order) not in seen, (code, category, order)
            seen.add((category, order))

    def test_no_name_carries_a_parenthesis(self):
        """El código del formulario va en `reference_code`, no en el nombre."""
        for row in DOCUMENT_TYPES:
            assert "(" not in row[1] and ")" not in row[1], row[0]

    def test_the_migration_and_the_seed_agree(self):
        taxonomy = _migration().TAXONOMY
        names = {row[0]: row[1] for row in DOCUMENT_TYPES}

        assert set(taxonomy) | CODES_AFTER_THE_MIGRATION == set(names)
        assert not set(taxonomy) & CODES_AFTER_THE_MIGRATION
        for code, (_old, new, description, ref, order) in taxonomy.items():
            assert new == names[code], code
            assert (description, ref, order) == DOCUMENT_TYPE_GUIDE[code], code

    def test_the_old_names_in_the_migration_are_not_the_new_ones_by_accident(self):
        for code, (old, new, *_rest) in _migration().TAXONOMY.items():
            assert old and new, code

    @pytest.mark.django_db
    def test_the_seed_writes_the_guide(self):
        call_command("seed_document_types")

        log = DocumentType.objects.get(code="flight-log")
        assert (log.name, log.reference_code, log.sort_order) == (
            "Bitácora de vuelo",
            "REG-015",
            10,
        )
        assert log.description

    @pytest.mark.django_db
    def test_the_seed_fills_only_what_is_empty(self):
        edited = DocumentType.objects.create(
            code="flight-log",
            name="Mi bitácora",
            description="Mía",
            reference_code="X-1",
            sort_order=7,
            category="operational",
        )

        call_command("seed_document_types")
        edited.refresh_from_db()

        assert (edited.name, edited.description, edited.reference_code) == (
            "Mi bitácora",
            "Mía",
            "X-1",
        )
        assert edited.sort_order == 7


@pytest.mark.django_db
class TestTheDataMigration:
    def _apply(self):
        migration = _migration().Migration
        # `RunPython` recibe el registro de apps del estado real: aquí basta el
        # actual, porque el modelo ya tiene los tres campos.
        from django.apps import apps

        migration.operations[-1].code(apps, None)

    def _reverse(self):
        from django.apps import apps

        _migration().Migration.operations[-1].reverse_code(apps, None)

    def test_it_renames_and_fills_a_row_left_by_the_old_seed(self):
        row = _old_seed_row("flight-log")

        self._apply()
        row.refresh_from_db()

        assert row.name == "Bitácora de vuelo"
        assert row.reference_code == "REG-015"
        assert row.sort_order == 10
        assert row.description

    def test_it_respects_a_name_edited_from_the_interface(self):
        row = _old_seed_row("flight-log")
        row.name = "Libro de vuelos"
        row.save()

        self._apply()
        row.refresh_from_db()

        assert row.name == "Libro de vuelos"
        assert row.reference_code == "REG-015"  # la guía sí se llena

    def test_it_never_creates_rows_nor_touches_code_or_category(self):
        before = DocumentType.objects.count()
        row = _old_seed_row("dgac-credential")

        self._apply()
        row.refresh_from_db()

        assert DocumentType.objects.count() == before + 1
        assert (row.code, row.category) == ("dgac-credential", "personnel")

    def test_it_is_idempotent(self):
        row = _old_seed_row("drone-inspection")

        self._apply()
        self._apply()
        row.refresh_from_db()

        assert row.name == "Inspección de RPA"

    def test_it_leaves_documents_on_their_type(self):
        from apps.compliance.models import Document

        row = _old_seed_row("flight-log")
        assert not Document.objects.filter(doc_type=row).exists()
        self._apply()
        row.refresh_from_db()
        assert DocumentType.objects.get(code="flight-log").pk == row.pk

    def test_the_reverse_restores_the_old_name_only_if_unchanged(self):
        kept = _old_seed_row("flight-log")
        edited = _old_seed_row("rpa-checklist")
        self._apply()
        edited.refresh_from_db()
        edited.name = "Chequeo propio"
        edited.save()

        self._reverse()
        kept.refresh_from_db()
        edited.refresh_from_db()

        assert kept.name == "Bitácora de vuelo (REG-015)"
        assert edited.name == "Chequeo propio"


@pytest.mark.django_db
class TestOrdering:
    def test_selectable_types_come_by_sort_order_then_name(self):
        DocumentType.objects.create(code="c", name="A last", sort_order=30)
        DocumentType.objects.create(code="a", name="Z first", sort_order=10)
        DocumentType.objects.create(code="b1", name="B tie", sort_order=20)
        DocumentType.objects.create(code="b2", name="A tie", sort_order=20)

        # La migración 0027 deja una fila sembrada en la base de pruebas.
        names = [
            t.name
            for t in selectable_document_types()
            if t.code in {"a", "b1", "b2", "c"}
        ]

        assert names == ["Z first", "A tie", "B tie", "A last"]


@pytest.mark.django_db
class TestTheTypeForm:
    FIELDS = ("description", "reference_code", "sort_order")

    def test_the_form_declares_the_three_fields(self):
        assert set(self.FIELDS) <= set(DocumentTypeForm().fields)

    def test_the_template_draws_them(self):
        """Un campo en `Meta.fields` que la plantilla no dibuja se guarda vacío."""
        response = login_as("add_documenttype").get(reverse("documenttype-create"))
        content = response.content.decode()

        for name in self.FIELDS:
            assert f'name="{name}"' in content, name

    def test_posting_the_form_saves_them(self):
        client = login_as("add_documenttype", "view_documenttype")

        response = client.post(
            reverse("documenttype-create"),
            {
                "name": "Certificado nuevo",
                "code": "new-cert",
                "category": "company",
                "description": "Sirve para algo",
                "reference_code": "ABC-1",
                "sort_order": "5",
                "requires_expiry": "on",
            },
        )

        assert response.status_code == 302, response.content.decode()[:500]
        saved = DocumentType.objects.get(code="new-cert")
        assert (saved.description, saved.reference_code, saved.sort_order) == (
            "Sirve para algo",
            "ABC-1",
            5,
        )


class TestTheNewStringsAreTranslated:
    def test_category_labels(self):
        with override("es"):
            spanish = {
                value: str(label) for value, label in DocumentType.CATEGORY_CHOICES
            }
        with override("en"):
            english = {
                value: str(label) for value, label in DocumentType.CATEGORY_CHOICES
            }

        assert english["aircraft"] == "Aircraft"
        assert spanish == {
            "personnel": "Personal",
            "aircraft": "Aeronave",
            "dgac": "Trámites ante la DGAC",
            "operational": "Registros operacionales",
            "maintenance": "Mantención y calibración",
            "company": "Empresa",
            "other": "Otros",
        }

    def test_field_labels(self):
        with override("es"):
            assert gettext("Form code") == "Código del formulario"
            assert gettext("Sort order") == "Orden"
