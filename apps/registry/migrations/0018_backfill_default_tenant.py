"""Backfill tenant on the registry root models before making it NOT NULL.

ADR-0001 / T3.2, Fase 0a. Creates the single default tenant and points every
CostCenter / Aircraft / Operator with a NULL tenant at it, so the follow-up
AlterField to null=False has no NULLs to choke on. Idempotent and reversible
(the reverse leaves the rows pointing at the default tenant -- harmless, since
the column was nullable before).
"""

from django.db import migrations

DEFAULT_SLUG = "default"
DEFAULT_NAME = "AeroControl"


def backfill(apps, schema_editor):
    OperationalTenant = apps.get_model("core", "OperationalTenant")
    tenant, _ = OperationalTenant.objects.get_or_create(
        slug=DEFAULT_SLUG, defaults={"name": DEFAULT_NAME}
    )
    for model_name in ("CostCenter", "Aircraft", "Operator"):
        model = apps.get_model("registry", model_name)
        model.objects.filter(tenant__isnull=True).update(tenant=tenant)


class Migration(migrations.Migration):
    dependencies = [
        ("registry", "0017_alter_costcenter_name"),
        ("core", "0004_operationaltenant_tenantmembership_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
