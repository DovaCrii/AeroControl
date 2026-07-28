"""The generic detail page used to render Django's English field names
(ID, CREATED AT, FULL NAME...) because fields_detail skipped gettext while
AeroModelForm applied it, so a record's detail page and its edit form
disagreed. These tests pin both the translation and the hiding of
bookkeeping columns."""

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse
from django.utils.translation import override

from apps.core.forms import translate_field_label
from apps.core.templatetags.aero_tags import fields_detail
from apps.registry.models import (
    Aircraft,
    Assignment,
    CostCenter,
    Operator,
    OperatorAssignment,
)


@pytest.fixture
def operator(db):
    cost_center = CostCenter.objects.create(code="OPS", name="Operations")
    return Operator.objects.create(
        employee_id="OP-01",
        full_name="Maria Gonzalez",
        email="maria@example.test",
        cost_center=cost_center,
    )


@pytest.mark.django_db
def test_detail_labels_are_translated(operator):
    with override("es"):
        labels = [field["label"] for field in fields_detail(operator)]

    assert "Nombre completo" in labels
    assert "Centro de costo" in labels
    assert "Full name" not in labels


def test_translate_field_label_preserves_acronyms():
    # Lowercasing these produced lookups ("Dgac credential") that never matched
    # the catalog, so the labels silently rendered in English.
    assert translate_field_label("DGAC credential") == "DGAC credential"
    assert translate_field_label("Employee ID") == "Employee ID"
    assert translate_field_label("RUT") == "RUT"
    # Ordinary words keep the previous normalisation
    assert translate_field_label("full_name") == "Full name"
    assert translate_field_label("SCHEDULED DATE") == "SCHEDULED DATE"


@pytest.mark.django_db
def test_acronym_labels_are_translated(operator):
    with override("es"):
        labels = [field["label"] for field in fields_detail(operator)]

    assert "Credencial DGAC" in labels
    assert "ID de empleado" in labels
    assert "DGAC credential" not in labels
    assert "Employee ID" not in labels


@pytest.mark.django_db
def test_technical_fields_are_hidden_from_the_detail_page(operator):
    keys = {field["label"].lower() for field in fields_detail(operator)}

    for hidden in ("id", "created at", "updated at", "is active", "tenant"):
        assert hidden not in keys


@pytest.mark.django_db
def test_costcenter_form_label_overrides_are_translated_on_detail():
    # Meta.labels on CostCenterForm gives these fields a hand-picked label
    # different from the auto-derived verbose_name ("Responsible contact
    # name"). fields_detail must agree with the form instead of falling back
    # to the untranslated auto-derived label.
    cost_center = CostCenter.objects.create(
        code="OPS",
        name="Operations",
        responsible_contact_name="Jane Doe",
        responsible_contact_email="jane@example.test",
    )
    with override("es"):
        labels = [field["label"] for field in fields_detail(cost_center)]

    assert "Nombre del contacto externo" in labels
    assert "Correo del contacto externo" in labels
    assert "Responsible contact name" not in labels
    assert "Responsible contact email" not in labels


@pytest.mark.django_db
def test_aircraft_form_label_overrides_are_translated_on_detail():
    # Same gap as above, for AircraftForm's max_takeoff_weight_kg/
    # basic_weight_kg, which used "Maximum"/"(kg)" wording the auto-derived
    # verbose_name did not match.
    aircraft = Aircraft.objects.create(
        registration="CC-ABC",
        type="Multirotor",
        model="X1",
        manufacturer="Acme",
    )
    with override("es"):
        labels = [field["label"] for field in fields_detail(aircraft)]

    assert "Peso máximo de despegue (kg)" in labels
    assert "Peso básico (kg)" in labels
    assert "Max takeoff weight kg" not in labels
    assert "Basic weight kg" not in labels


@pytest.mark.django_db
def test_assignment_form_label_override_is_translated_on_detail(operator):
    # AssignmentForm's Meta.labels renames "purpose" to "Operation or
    # purpose"; the auto-derived verbose_name ("Purpose") is a different
    # msgid and used to fall back to English on the detail page.
    aircraft = Aircraft.objects.create(
        registration="CC-XYZ", type="Multirotor", model="X1", manufacturer="Acme"
    )
    assignment = Assignment.objects.create(
        operator=operator, aircraft=aircraft, start_date="2026-01-01"
    )
    with override("es"):
        labels = [field["label"] for field in fields_detail(assignment)]

    assert "Operación o propósito" in labels
    assert "Purpose" not in labels


@pytest.mark.django_db
def test_resource_assignment_form_label_override_is_translated_on_detail(operator):
    # Same gap as above, for the abstract ResourceAssignment.purpose field
    # shared by OperatorAssignment and AircraftAssignment.
    cost_center = CostCenter.objects.create(code="OPS2", name="Operations 2")
    assignment = OperatorAssignment.objects.create(
        operator=operator, cost_center=cost_center, start_date="2026-01-01"
    )
    with override("es"):
        labels = [field["label"] for field in fields_detail(assignment)]

    assert "Operación o propósito" in labels
    assert "Purpose" not in labels


@pytest.mark.django_db
def test_operator_detail_page_renders_translated_labels(operator):
    User.objects.create_superuser("admin", "a@test.com", "password")
    client = Client()
    assert client.login(username="admin", password="password")

    response = client.get(reverse("operator-detail", args=[operator.pk]))
    content = response.content.decode()

    assert response.status_code == 200
    assert "Nombre completo" in content
    assert "CREATED AT" not in content.upper() or "Creado" in content
    # The UUID may appear inside action URLs (edit/archive), but never as
    # visible cell text - that is what this test exists to prevent.
    assert f">{operator.pk}<" not in content
