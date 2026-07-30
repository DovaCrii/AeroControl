"""B4.3: structured operator qualifications.

`Qualification.qualification_type` becomes a FK to a new `QualificationType`
catalog (was free text). The table holds zero rows in every environment, so
the char→FK swap is a clean remove + add with nothing to migrate; the FK is
added nullable and then tightened to non-null in the same migration so it
applies on an empty table without a one-off default.
"""

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("registry", "0013_aircraft_current_location_aircraft_current_site_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="QualificationType",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(default=True)),
                ("notes", models.TextField(blank=True)),
                ("name", models.CharField(max_length=150)),
                ("code", models.CharField(max_length=50, unique=True)),
                (
                    "model_keywords",
                    models.CharField(
                        blank=True,
                        help_text=(
                            "Comma-separated fragments matched against the "
                            "aircraft model (e.g. 'mavic, matrice'). Used to "
                            "check operator–aircraft fit."
                        ),
                        max_length=250,
                        verbose_name="Aircraft model keywords",
                    ),
                ),
            ],
            options={
                "verbose_name": "qualification type",
                "verbose_name_plural": "qualification types",
            },
        ),
        migrations.RemoveField(
            model_name="qualification",
            name="qualification_type",
        ),
        migrations.AddField(
            model_name="qualification",
            name="qualification_type",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="qualifications",
                to="registry.qualificationtype",
            ),
        ),
        migrations.AlterField(
            model_name="qualification",
            name="qualification_type",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="qualifications",
                to="registry.qualificationtype",
            ),
        ),
    ]
