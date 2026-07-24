import pytest
from django.core.exceptions import ValidationError

from apps.maintenance.models import MaintenanceRecord
from apps.registry.models import Qualification
from .forms import AlertRuleForm
from .models import AlertRule
from .watchables import canonical_entity_type, resolve_model, watchable_fields


def test_canonical_entity_type_accepts_keys_and_legacy_values():
    assert canonical_entity_type("registry.qualification") == "registry.qualification"
    # Values already stored in the database before the registry existed
    assert canonical_entity_type("Qualification") == "registry.qualification"
    assert canonical_entity_type("document") == "compliance.document"
    assert (
        canonical_entity_type("maintenance_record") == "maintenance.maintenancerecord"
    )
    assert canonical_entity_type("not_a_model") is None
    assert canonical_entity_type("") is None


def test_resolve_model_returns_the_right_class():
    assert resolve_model("registry.qualification") is Qualification
    assert resolve_model("maintenance") is MaintenanceRecord
    assert resolve_model("bogus") is None


def test_watchable_fields_excludes_inherited_timestamps():
    fields = watchable_fields(Qualification)

    assert "expiry_date" in fields
    assert "issue_date" in fields
    # created_at/updated_at come from BaseModel and are never what a rule means
    assert "created_at" not in fields
    assert "updated_at" not in fields


def test_watchable_fields_includes_status_when_it_has_choices():
    assert "status" in watchable_fields(MaintenanceRecord)
    assert "scheduled_date" in watchable_fields(MaintenanceRecord)


@pytest.mark.django_db
def test_rule_with_unknown_entity_is_rejected():
    rule = AlertRule(
        name="Bad entity", entity_type="not_a_model", field_to_watch="expiry_date"
    )

    with pytest.raises(ValidationError) as excinfo:
        rule.clean()
    assert "entity_type" in excinfo.value.message_dict


@pytest.mark.django_db
def test_rule_with_field_not_on_the_model_is_rejected():
    rule = AlertRule(
        name="Bad field",
        entity_type="registry.qualification",
        field_to_watch="scheduled_date",  # belongs to MaintenanceRecord
    )

    with pytest.raises(ValidationError) as excinfo:
        rule.clean()
    assert "field_to_watch" in excinfo.value.message_dict


@pytest.mark.django_db
def test_valid_rule_passes_clean():
    AlertRule(
        name="Good",
        entity_type="registry.qualification",
        field_to_watch="expiry_date",
    ).clean()


@pytest.mark.django_db
def test_form_rejects_free_text_entity_type():
    form = AlertRuleForm(
        data={
            "name": "Free text",
            "entity_type": "whatever",
            "field_to_watch": "expiry_date",
            "days_before_expiry": 30,
        }
    )

    assert not form.is_valid()
    assert "entity_type" in form.errors


@pytest.mark.django_db
def test_form_narrows_field_choices_to_the_selected_entity():
    form = AlertRuleForm(
        data={
            "name": "Quals",
            "entity_type": "registry.qualification",
            "field_to_watch": "expiry_date",
            "days_before_expiry": 30,
        }
    )

    assert form.is_valid(), form.errors
    offered = [
        value for value, _label in form.fields["field_to_watch"].choices if value
    ]
    assert set(offered) == set(watchable_fields(Qualification))
    assert "scheduled_date" not in offered


@pytest.mark.django_db
def test_form_rejects_field_that_belongs_to_another_model():
    form = AlertRuleForm(
        data={
            "name": "Mismatch",
            "entity_type": "registry.qualification",
            "field_to_watch": "scheduled_date",
            "days_before_expiry": 30,
        }
    )

    assert not form.is_valid()
    assert "field_to_watch" in form.errors
