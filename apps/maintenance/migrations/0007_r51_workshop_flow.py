"""R5.1: the workshop chain (sent/at_workshop/finished/in_transit) added
alongside the existing pending/in_progress/completed -- both paths from
"pending" stay valid (see MaintenanceRecord.STATUSES).

Backfills status_changed_at from updated_at for existing rows: there is no
real record of when each one last changed status before this field existed,
and updated_at is the closest available proxy (it moves on every save, not
only status changes, so it can overstate freshness for a row that was
touched for another reason -- acceptable, this only matters going forward
for dwell-time flagging, not for historical rows).
"""

from django.db import migrations, models


def backfill_status_changed_at(apps, schema_editor):
    MaintenanceRecord = apps.get_model("maintenance", "MaintenanceRecord")
    for record in MaintenanceRecord.objects.filter(status_changed_at__isnull=True):
        record.status_changed_at = record.updated_at
        record.save(update_fields=["status_changed_at"])


class Migration(migrations.Migration):
    dependencies = [
        ("maintenance", "0006_remove_maintenancerecord_cost_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="maintenancerecord",
            name="status_changed_at",
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.AlterField(
            model_name="maintenancerecord",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("in_progress", "In progress"),
                    ("sent", "Sent to workshop"),
                    ("at_workshop", "At the workshop"),
                    ("finished", "Finished at workshop"),
                    ("in_transit", "In transit back"),
                    ("completed", "Completed"),
                ],
                default="pending",
                max_length=20,
            ),
        ),
        migrations.RunPython(backfill_status_changed_at, migrations.RunPython.noop),
    ]
