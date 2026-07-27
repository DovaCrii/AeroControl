"""OPS-4 data migration: seed the M2M rosters and the date range, then drop the
old single-FK/single-date shape.

Hand-written (not autodetected) so the RunPython step runs while `operator`,
`aircraft` and `flight_date` still exist, before they are removed later in
this same migration. Every existing permission gets its one operator/aircraft
as the sole initial roster member and a single-day range (valid_from ==
valid_until == the old flight_date) -- a faithful, lossless read of the data
as it stood.

Irreversible on purpose: reconstructing a single FK from a roster of several
is lossy (which one was "the" operator?), so reversing is a no-op. Take a
database backup before deploying, as with every OPS data migration.
"""

from django.db import migrations, models


def backfill_forward(apps, schema_editor):
    FlightPermission = apps.get_model("operations", "FlightPermission")
    for permission in FlightPermission.objects.all():
        permission.operators.add(permission.operator_id)
        permission.aircraft_fleet.add(permission.aircraft_id)
        permission.valid_from = permission.flight_date
        permission.valid_until = permission.flight_date
        permission.save(update_fields=["valid_from", "valid_until"])


class Migration(migrations.Migration):
    dependencies = [
        ("operations", "0009_flightpermission_aircraft_fleet_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill_forward, migrations.RunPython.noop),
        migrations.RemoveIndex(
            model_name="flightpermission",
            name="ops_permission_date_idx",
        ),
        migrations.RemoveField(
            model_name="flightpermission",
            name="operator",
        ),
        migrations.RemoveField(
            model_name="flightpermission",
            name="aircraft",
        ),
        migrations.RemoveField(
            model_name="flightpermission",
            name="flight_date",
        ),
        migrations.AlterField(
            model_name="flightpermission",
            name="valid_from",
            field=models.DateField(),
        ),
        migrations.AlterField(
            model_name="flightpermission",
            name="valid_until",
            field=models.DateField(),
        ),
        migrations.AddIndex(
            model_name="flightpermission",
            index=models.Index(
                fields=["valid_from", "valid_until", "is_active"],
                name="ops_permission_range_idx",
            ),
        ),
    ]
