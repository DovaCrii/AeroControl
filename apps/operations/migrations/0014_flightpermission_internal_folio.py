"""R2.2/R2.3: give every existing permission its annual correlative folio.

Hand-written (not autodetected) because Django's autodetector cannot prompt
for a one-off default non-interactively when adding a required unique field
to a table with existing rows. Backfilled in creation order (`created_at`,
then `pk` to break ties) so earlier permits get lower numbers within their
year -- the same ordering `FlightPermission.save()` would have produced had
this field existed from the start.
"""

from django.db import migrations, models


def backfill_forward(apps, schema_editor):
    FlightPermission = apps.get_model("operations", "FlightPermission")
    counters = {}
    for permission in FlightPermission.objects.order_by("created_at", "pk"):
        year = permission.created_at.year
        counters[year] = counters.get(year, 0) + 1
        permission.internal_folio = f"JEJ-{year}-{counters[year]:03d}"
        permission.save(update_fields=["internal_folio"])


class Migration(migrations.Migration):
    dependencies = [
        ("operations", "0013_flightpermission_area_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="flightpermission",
            name="internal_folio",
            field=models.CharField(
                max_length=20, unique=True, null=True, editable=False
            ),
        ),
        migrations.RunPython(backfill_forward, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="flightpermission",
            name="internal_folio",
            field=models.CharField(max_length=20, unique=True, editable=False),
        ),
    ]
