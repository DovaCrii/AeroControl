from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("registry", "0003_aircraft_authorized_services_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="assignment",
            name="cost_center",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="assignments",
                to="registry.costcenter",
            ),
        ),
        migrations.AddField(
            model_name="assignment",
            name="purpose",
            field=models.CharField(blank=True, max_length=250),
        ),
        migrations.AddField(
            model_name="assignment",
            name="status",
            field=models.CharField(
                choices=[
                    ("planned", "Planned"),
                    ("confirmed", "Confirmed"),
                    ("completed", "Completed"),
                    ("cancelled", "Cancelled"),
                ],
                default="planned",
                max_length=20,
            ),
        ),
    ]
