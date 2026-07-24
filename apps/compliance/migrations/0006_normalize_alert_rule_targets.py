"""Normalise AlertRule.entity_type and archive rules that cannot be resolved.

entity_type used to be free text matched fuzzily against every installed
model, so the stored values are inconsistent ("Qualification", "document").
This rewrites the recognisable ones to the canonical "app_label.modelname" key
and archives the rest (is_active=False, never deleted) with a note explaining
why, so nothing disappears silently.
"""

from django.db import migrations

NOTE_PREFIX = "[migración 0006]"


def normalize(apps, schema_editor):
    AlertRule = apps.get_model("compliance", "AlertRule")
    # Imported here so the mapping lives in one place; it contains no model
    # references, so it is safe to use from a migration.
    from apps.compliance.watchables import (
        canonical_entity_type,
        resolve_model,
        watchable_fields,
    )

    for rule in AlertRule.objects.all():
        key = canonical_entity_type(rule.entity_type)
        if key is None:
            _archive(
                rule,
                f"entidad no reconocida: {rule.entity_type!r}",
            )
            continue

        model = resolve_model(key)
        allowed = watchable_fields(model)
        if rule.field_to_watch not in allowed:
            _archive(
                rule,
                f"campo vigilado inválido: {rule.field_to_watch!r} "
                f"(disponibles: {', '.join(allowed) or '-'})",
            )
            continue

        if rule.entity_type != key:
            rule.entity_type = key
            rule.save(update_fields=["entity_type", "updated_at"])


def _archive(rule, reason):
    note = f"{NOTE_PREFIX} archivada automáticamente: {reason}."
    rule.is_active = False
    rule.enabled = False
    rule.notes = f"{rule.notes}\n{note}".strip() if rule.notes else note
    rule.save(update_fields=["is_active", "enabled", "notes", "updated_at"])


def unnormalize(apps, schema_editor):
    """Reverse leaves data as-is.

    The original free-text values are not recoverable, and reactivating rules
    that were archived for being invalid would reintroduce silent no-ops.
    """


class Migration(migrations.Migration):
    dependencies = [
        ("compliance", "0005_alter_document_options"),
    ]

    operations = [
        migrations.RunPython(normalize, unnormalize),
    ]
