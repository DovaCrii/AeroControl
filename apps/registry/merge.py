"""Operator de-duplication.

The Chapter 1 import left groups of operators that are the same person entered
twice with contradictory data (BACKLOG.md). Merging has to move every reference
before the duplicate is archived, or history silently loses its subject -- and
because the operational FKs are PROTECT, a missed reference would also make the
archive fail loudly rather than corrupt data.
"""

import re
import unicodedata

from django.contrib.contenttypes.models import ContentType
from django.db import transaction

from apps.registry.models import Operator

# Fields compared when reporting what differs inside a group. Bookkeeping
# columns are excluded: they always differ and say nothing about the person.
COMPARED_FIELDS = [
    "employee_id",
    "full_name",
    "email",
    "phone",
    "rut",
    "dgac_credential",
    "operator_type",
    "address",
    "authorizations",
    "cost_center",
    "tenant",
]


def normalize_name(value):
    """Casefold, strip accents and collapse whitespace for grouping."""
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", text).strip().lower()


def group_key(operator):
    return re.sub(r"[^a-z0-9]+", "-", normalize_name(operator.full_name)).strip("-")


def find_duplicate_groups(include_archived=False):
    """Return [{key, operators, differences}] for names held by >1 operator.

    Grouping is by normalised full name: the imported duplicates share a person
    but not an employee_id, so employee_id cannot be the key. RUT would be
    ideal but is blank in the imported data.
    """
    queryset = Operator.objects.select_related("cost_center", "tenant")
    if not include_archived:
        queryset = queryset.filter(is_active=True)

    buckets = {}
    for operator in queryset.order_by("created_at", "employee_id"):
        key = group_key(operator)
        if not key:
            continue
        buckets.setdefault(key, []).append(operator)

    groups = []
    for key, operators in sorted(buckets.items()):
        if len(operators) < 2:
            continue
        groups.append(
            {
                "key": key,
                "operators": operators,
                "differences": _differences(operators),
                "suggested": suggest_canonical(operators),
            }
        )
    return groups


def _differences(operators):
    """{field: [value per operator]} for fields that are not identical."""
    differences = {}
    for field in COMPARED_FIELDS:
        values = [_display(getattr(operator, field, None)) for operator in operators]
        if len(set(values)) > 1:
            differences[field] = values
    return differences


def _display(value):
    if value is None or value == "":
        return "—"
    return str(value)


def completeness(operator):
    return sum(
        1
        for field in COMPARED_FIELDS
        if _display(getattr(operator, field, None)) != "—"
    )


def suggest_canonical(operators):
    """Most-referenced record wins, then most complete, then oldest.

    References outrank field count on purpose: the record the rest of the system
    already points at (assignments, permissions, flight records) is the one
    people recognise, and keeping it means moving the least history. Field
    completeness alone would have picked a thinly-referenced duplicate that
    merely had one extra phone number filled in.
    """
    return sorted(
        operators,
        key=lambda op: (
            -sum(reference_counts(op).values()),
            -completeness(op),
            op.created_at,
        ),
    )[0]


def reference_counts(operator):
    """{'app.Model.field': count} of live references to this operator."""
    counts = {}
    for relation in Operator._meta.related_objects:
        related_model = relation.related_model
        field_name = relation.field.name
        count = related_model.objects.filter(**{field_name: operator}).count()
        if count:
            counts[f"{related_model._meta.label}.{field_name}"] = count
    for label, model in _generic_models().items():
        count = model.objects.filter(
            content_type=_operator_content_type(), object_id=operator.pk
        ).count()
        if count:
            counts[label] = count
    return counts


def _generic_models():
    """Models that point at an operator through a generic foreign key.

    These are invisible to _meta.related_objects, so they are listed explicitly;
    forgetting one would leave documents attached to an archived duplicate.
    """
    from apps.compliance.models import Alert, Document

    return {
        "compliance.Document.content_object": Document,
        "compliance.Alert.content_object": Alert,
    }


def _operator_content_type():
    return ContentType.objects.get_for_model(Operator)


@transaction.atomic
def merge_operators(canonical, duplicates, actor=None):
    """Move every reference onto `canonical`, then archive the duplicates.

    Returns {'moved': {label: count}, 'archived': [employee_id]}. Never deletes:
    the duplicate stays as an archived record so the audit trail keeps its
    subject.
    """
    moved = {}
    operator_ct = _operator_content_type()

    for duplicate in duplicates:
        if duplicate.pk == canonical.pk:
            continue

        for relation in Operator._meta.related_objects:
            related_model = relation.related_model
            field_name = relation.field.name
            if relation.many_to_many:
                # A M2M reverse relation (e.g. FlightPermission.operators,
                # OPS-4): there is no bulk .update() for M2M, so swap
                # membership row by row instead.
                updated = 0
                for obj in related_model.objects.filter(**{field_name: duplicate}):
                    manager = getattr(obj, field_name)
                    manager.remove(duplicate)
                    manager.add(canonical)
                    updated += 1
            else:
                updated = related_model.objects.filter(
                    **{field_name: duplicate}
                ).update(**{field_name: canonical})
            if updated:
                label = f"{related_model._meta.label}.{field_name}"
                moved[label] = moved.get(label, 0) + updated

        for label, model in _generic_models().items():
            updated = model.objects.filter(
                content_type=operator_ct, object_id=duplicate.pk
            ).update(object_id=canonical.pk)
            if updated:
                moved[label] = moved.get(label, 0) + updated

        duplicate.is_active = False
        note = (
            f"Fusionado en {canonical.employee_id} ({canonical.full_name}) "
            f"por duplicado de datos."
        )
        duplicate.notes = (
            f"{duplicate.notes}\n{note}".strip() if duplicate.notes else note
        )
        duplicate.save(update_fields=["is_active", "notes", "updated_at"])
        _record_audit(canonical, duplicate, moved, actor)

    return {"moved": moved, "archived": [d.employee_id for d in duplicates]}


def _record_audit(canonical, duplicate, moved, actor):
    from apps.core.models import AuditEvent

    AuditEvent.objects.create(
        actor=actor,
        action="operator_merged",
        # Not an HTTP request: method marks the origin and status_code is unused.
        method="CLI",
        path="manage.py find_duplicate_operators --apply",
        status_code=0,
        model_label=Operator._meta.label,
        object_id=str(canonical.pk),
        metadata={
            "merged_employee_id": duplicate.employee_id,
            "merged_object_id": str(duplicate.pk),
            "canonical_employee_id": canonical.employee_id,
            "moved_references": moved,
        },
    )
