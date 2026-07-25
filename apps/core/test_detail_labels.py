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
from apps.registry.models import CostCenter, Operator


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
