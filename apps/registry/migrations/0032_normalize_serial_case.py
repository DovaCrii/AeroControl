"""X.4c: upper-case the serials already stored, per ADR-0002 §2.

Changing `save()` does not rewrite existing rows, and an exact-match lookup is
how both the AeroLink sync and the padrón API resolve a serial -- so a row left
in mixed case stops matching the moment AeroLink normalizes.

**Refuses to run if two rows would collide.** `serial_number` is unique, so two
values differing only in case cannot both be upper-cased. Which one is right is
a question for the DGAC's RPAS certificate (ADR-0002 §2), not for a migration:
picking one here would silently destroy the other. Run
`manage.py audit_serial_case` to see them.

Reversible in the only sense that matters: going back is a no-op, because the
original casing is not recoverable and the whitespace-only rule accepts these
values unchanged.
"""

from django.db import migrations


def _normalized(value):
    return "".join((value or "").split()).upper()


def upper_case_serials(apps, schema_editor):
    for model_name in ("Aircraft", "Battery"):
        model = apps.get_model("registry", model_name)
        rows = [
            (obj.pk, obj.serial_number)
            for obj in model.objects.all()
            if obj.serial_number
        ]

        by_normalized = {}
        for pk, serial in rows:
            by_normalized.setdefault(_normalized(serial), []).append(serial)
        collisions = {
            normalized: variants
            for normalized, variants in by_normalized.items()
            if len(variants) > 1
        }
        if collisions:
            raise RuntimeError(
                f"{model_name}: these serials differ only in case or whitespace "
                f"and cannot both be normalized: {collisions}. Resolve them "
                f"against the DGAC RPAS certificate first "
                f"(manage.py audit_serial_case)."
            )

        for pk, serial in rows:
            normalized = _normalized(serial)
            if normalized != serial:
                model.objects.filter(pk=pk).update(serial_number=normalized)


class Migration(migrations.Migration):
    dependencies = [("registry", "0031_r74_deliverable_quality")]

    operations = [
        migrations.RunPython(upper_case_serials, migrations.RunPython.noop),
    ]
