"""X.1: strip whitespace out of Aircraft.serial_number.

Verified against production: 16/16 aircraft have the field populated, but 2
(RPA-4401, RPA-4436) carry a stray internal space typed into the serial --
confirmed against the Z: folder names, which have no space in the same
position. Idempotent and reversible-as-noop (there is no way to recover
whitespace that carried no information).
"""

from django.db import migrations


def normalize(apps, schema_editor):
    Aircraft = apps.get_model("registry", "Aircraft")
    for aircraft in Aircraft.objects.exclude(serial_number=""):
        cleaned = "".join(aircraft.serial_number.split())
        if cleaned != aircraft.serial_number:
            aircraft.serial_number = cleaned
            aircraft.save(update_fields=["serial_number"])


class Migration(migrations.Migration):
    dependencies = [
        ("registry", "0026_purpose_closed_vocabulary"),
    ]

    operations = [
        migrations.RunPython(normalize, migrations.RunPython.noop),
    ]
