"""LV-431: las filas existentes toman su centro de costo del permiso (y la aeronave, si se deduce)."""

from django.db import migrations

from apps.operations.flightlog.backfill import backfill


def forwards(apps, schema_editor):
    backfill(apps)


class Migration(migrations.Migration):
    dependencies = [
        ("operations", "0035_lv431_flight_log_cost_center_aircraft"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]