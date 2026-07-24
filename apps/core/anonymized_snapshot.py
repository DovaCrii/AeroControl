"""Shared model registry and deterministic anonymization for test snapshots."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from django.apps import apps
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models

SNAPSHOT_VERSION = 1
DATE_OFFSET_DAYS = 180

# Authentication, audit and import records are deliberately absent. They can
# contain credentials, personal data or source documents that must not enter a
# test snapshot.
MODEL_LABELS = (
    "core.OperationalTenant",
    "registry.CostCenter",
    "registry.Aircraft",
    "registry.Operator",
    "registry.Assignment",
    "registry.Qualification",
    "operations.FlightPermission",
    "operations.FlightRecord",
    "operations.PermissionHistory",
    "maintenance.MaintenanceRecord",
    "maintenance.MaintenanceHistory",
    "compliance.DocumentType",
    "compliance.Document",
    "compliance.AlertRule",
    "compliance.Alert",
    "workboard.KanbanBoard",
    "workboard.KanbanStage",
    "workboard.KanbanLabel",
    "workboard.KanbanTask",
    "workboard.KanbanTaskLabel",
    "workboard.KanbanChecklistItem",
)

SENSITIVE_FIELDS = {
    "address",
    "authorized_services",
    "authorizations",
    "changed_by",
    "code",
    "created_by",
    "dgac_credential",
    "description",
    "employee_id",
    "email",
    "full_name",
    "location",
    "manufacturer",
    "model",
    "name",
    "notes",
    "operator_type",
    "permission_number",
    "performed_by",
    "phone",
    "purpose",
    "registration",
    "responsible",
    "rut",
    "serial_number",
    "title",
    "type",
}


def get_snapshot_models():
    return [(label, apps.get_model(label)) for label in MODEL_LABELS]


def model_label(model: type[models.Model]) -> str:
    return f"{model._meta.app_label}.{model.__name__}"


def is_generic_content_type(field: models.Field) -> bool:
    return field.name in {"content_type", "source_content_type"}


def shift_temporal(value):
    if isinstance(value, datetime):
        return value + timedelta(days=DATE_OFFSET_DAYS)
    if isinstance(value, date):
        return value + timedelta(days=DATE_OFFSET_DAYS)
    return value


def anonymize_value(field_name: str, value, label: str, index: int):
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return shift_temporal(value)
    if field_name in SENSITIVE_FIELDS:
        if field_name == "email":
            return f"operator-{index:04d}@example.test"
        if field_name in {"phone", "rut"}:
            return f"TEST-{index:04d}"
        if field_name == "code":
            return f"TEST-{index:04d}"
        if field_name == "employee_id":
            return f"EMP-TEST-{index:04d}"
        if field_name == "registration":
            return f"TEST-{index:04d}"
        if field_name == "permission_number":
            return f"PERM-TEST-{index:04d}"
        if field_name == "serial_number":
            return f"SN-TEST-{index:04d}"
        if field_name == "dgac_credential":
            return f"DGAC-TEST-{index:04d}"
        return f"Datos de prueba {label}-{index:04d}"
    if isinstance(value, Decimal):
        return value
    return value


def json_default(value):
    return DjangoJSONEncoder().default(value)


def is_inside_repo(path: Path, repo_root: Path) -> bool:
    try:
        path.resolve().relative_to(repo_root.resolve())
    except ValueError:
        return False
    return True
