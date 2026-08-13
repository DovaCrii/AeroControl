"""LV-82: the maintenance history gets a stable order and translatable labels.

The backfill matters: `sequence` defaults to 0, so without it every existing row
would tie at zero and the fiche would print its own history in whatever order
SQLite happened to return -- worse than the `created_at` ordering it replaces.
Existing rows are numbered in the order they were created, which is the best
available reconstruction and is exactly what the column means going forward.
"""

from django.db import migrations, models


def number_existing_rows(apps, schema_editor):
    MaintenanceHistory = apps.get_model("maintenance", "MaintenanceHistory")
    rows = MaintenanceHistory.objects.order_by("created_at", "changed_at", "id")
    for number, row in enumerate(rows, start=1):
        MaintenanceHistory.objects.filter(pk=row.pk).update(sequence=number)


def unnumber(apps, schema_editor):
    apps.get_model("maintenance", "MaintenanceHistory").objects.update(sequence=0)


class Migration(migrations.Migration):

    dependencies = [
        ('maintenance', '0007_r51_workshop_flow'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='maintenancehistory',
            options={'ordering': ['-sequence'], 'verbose_name': 'maintenance history', 'verbose_name_plural': 'maintenance histories'},
        ),
        migrations.AddField(
            model_name='maintenancehistory',
            name='sequence',
            field=models.PositiveBigIntegerField(default=0, editable=False),
        ),
        migrations.AlterField(
            model_name='maintenancehistory',
            name='new_status',
            field=models.CharField(choices=[('pending', 'Pending'), ('in_progress', 'In progress'), ('sent', 'Sent to workshop'), ('at_workshop', 'At the workshop'), ('finished', 'Finished at workshop'), ('in_transit', 'In transit back'), ('completed', 'Completed')], max_length=20),
        ),
        migrations.AlterField(
            model_name='maintenancehistory',
            name='previous_status',
            field=models.CharField(choices=[('pending', 'Pending'), ('in_progress', 'In progress'), ('sent', 'Sent to workshop'), ('at_workshop', 'At the workshop'), ('finished', 'Finished at workshop'), ('in_transit', 'In transit back'), ('completed', 'Completed')], max_length=20),
        ),
        migrations.RunPython(number_existing_rows, unnumber),
    ]
