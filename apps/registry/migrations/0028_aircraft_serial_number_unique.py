"""X.1: `Aircraft.serial_number` becomes the cross-reference key.

The 4 discrepancies found against the Z: folder names are now resolved --
confirmed with the user 2026-08-10 against the physical record, not guessed:

- RPA-4401 / RPA-4436: a stray internal space, fixed by migration 0027.
- RPA-4647: the app's value (zeros) is correct; the Z: folder ("OO") is the
  one that is wrong and will be renamed there directly, outside this app.
- RPA-4884: the app's value (`1581...`) is correct; the Z: folder
  (`CC717-1582...`) is the one that is wrong, same as above.

No further data change is needed in this app -- both disputed values already
matched the correct record. Converts blank "" to NULL first (several blank
aircraft must not collide on the new unique index; see
FlightPermission.permission_number for the same pattern) before adding the
uniqueness constraint.

Three steps, not two, and in this exact order -- caught 2026-08-10 running
against a real demo database with several genuinely blank aircraft (the
restored-backup copy this migration was first tested against had none, so
the bug was silent there): the column has to become nullable *before* the
data migration can set it to NULL (`UPDATE ... SET serial_number = NULL`
against a still-NOT-NULL column raises `IntegrityError`), and only *after*
the blanks are converted can `unique=True` be added without every blank row
colliding with every other blank row.
"""

from django.db import migrations, models


def blank_to_null(apps, schema_editor):
    Aircraft = apps.get_model("registry", "Aircraft")
    Aircraft.objects.filter(serial_number="").update(serial_number=None)


def null_to_blank(apps, schema_editor):
    Aircraft = apps.get_model("registry", "Aircraft")
    Aircraft.objects.filter(serial_number__isnull=True).update(serial_number="")


class Migration(migrations.Migration):
    dependencies = [
        ("registry", "0027_normalize_aircraft_serial_number"),
    ]

    operations = [
        migrations.AlterField(
            model_name="aircraft",
            name="serial_number",
            field=models.CharField(max_length=100, blank=True, null=True),
        ),
        migrations.RunPython(blank_to_null, null_to_blank),
        migrations.AlterField(
            model_name="aircraft",
            name="serial_number",
            field=models.CharField(max_length=100, blank=True, null=True, unique=True),
        ),
    ]
