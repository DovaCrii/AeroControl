"""LV-10a: prefix existing cost-center codes with the fixed 'CC'.

New/edited codes get the prefix from CostCenterForm.clean_code(); this brings
the legacy rows (e.g. "410" -> "CC410") into line so the prefix is the single
source of truth everywhere. Idempotent and reversible.
"""

from django.db import migrations


def add_prefix(apps, schema_editor):
    CostCenter = apps.get_model("registry", "CostCenter")
    for center in CostCenter.objects.all():
        code = (center.code or "").strip()
        if code and not code.upper().startswith("CC"):
            center.code = f"CC{code}"
            center.save(update_fields=["code"])


def remove_prefix(apps, schema_editor):
    CostCenter = apps.get_model("registry", "CostCenter")
    for center in CostCenter.objects.all():
        code = (center.code or "").strip()
        if code.upper().startswith("CC"):
            center.code = code[2:]
            center.save(update_fields=["code"])


class Migration(migrations.Migration):
    dependencies = [
        ("registry", "0014_qualificationtype"),
    ]

    operations = [
        migrations.RunPython(add_prefix, remove_prefix),
    ]
