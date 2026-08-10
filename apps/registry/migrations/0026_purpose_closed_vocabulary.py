"""R3.1: `purpose` becomes a closed-vocabulary code (apps.core.choices,
confirmed against real data + the user directly -- R3.1a) instead of free
text. Hand-written so the backfill runs on the *old*, unconstrained column
(still `max_length=250`, no choices) before narrowing it -- the autodetector
cannot know a data migration has to happen between the AddField and
AlterField steps.

The real data (verified 2026-08-10 via `report_purpose_mapping` against a
restored backup) is 3 rows, all mixing more than one concept
("Fotogrametría - Fotos - Videos") -- none is a clean match for either SIGO
procedure, so all 3 become "other" with the original wording preserved
verbatim in both `purpose_detail` (visible, editable going forward) and
`purpose_legacy` (immutable historical record).
"""

from django.db import migrations, models
from django.db.models import Q


def backfill_forward(apps, schema_editor):
    from apps.core.choices import PURPOSE_LEGACY_MAP

    Assignment = apps.get_model("registry", "Assignment")
    OperatorAssignment = apps.get_model("registry", "OperatorAssignment")
    AircraftAssignment = apps.get_model("registry", "AircraftAssignment")

    for Model in (Assignment, OperatorAssignment, AircraftAssignment):
        for row in Model.objects.all():
            original = row.purpose or ""
            row.purpose_legacy = original
            if not original:
                row.purpose = ""
            else:
                code = PURPOSE_LEGACY_MAP.get(original.strip().lower())
                if code:
                    row.purpose = code
                else:
                    row.purpose = "other"
                    row.purpose_detail = original
            row.save(update_fields=["purpose", "purpose_detail", "purpose_legacy"])


PURPOSE_CHOICES = [
    ("photogrammetry", "Photogrammetry Procedure"),
    ("video", "Video Procedure"),
    ("other", "Other"),
]


class Migration(migrations.Migration):
    dependencies = [
        ("registry", "0025_costcenter_contract_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="assignment",
            name="purpose_detail",
            field=models.CharField(blank=True, default="", max_length=250),
        ),
        migrations.AddField(
            model_name="assignment",
            name="purpose_legacy",
            field=models.CharField(
                blank=True, default="", editable=False, max_length=250
            ),
        ),
        migrations.AddField(
            model_name="operatorassignment",
            name="purpose_detail",
            field=models.CharField(blank=True, default="", max_length=250),
        ),
        migrations.AddField(
            model_name="operatorassignment",
            name="purpose_legacy",
            field=models.CharField(
                blank=True, default="", editable=False, max_length=250
            ),
        ),
        migrations.AddField(
            model_name="aircraftassignment",
            name="purpose_detail",
            field=models.CharField(blank=True, default="", max_length=250),
        ),
        migrations.AddField(
            model_name="aircraftassignment",
            name="purpose_legacy",
            field=models.CharField(
                blank=True, default="", editable=False, max_length=250
            ),
        ),
        migrations.RunPython(backfill_forward, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="assignment",
            name="purpose",
            field=models.CharField(
                blank=True, choices=PURPOSE_CHOICES, max_length=20
            ),
        ),
        migrations.AlterField(
            model_name="operatorassignment",
            name="purpose",
            field=models.CharField(
                blank=True, choices=PURPOSE_CHOICES, max_length=20
            ),
        ),
        migrations.AlterField(
            model_name="aircraftassignment",
            name="purpose",
            field=models.CharField(
                blank=True, choices=PURPOSE_CHOICES, max_length=20
            ),
        ),
        migrations.AddConstraint(
            model_name="assignment",
            constraint=models.CheckConstraint(
                condition=~Q(purpose="other") | ~Q(purpose_detail=""),
                name="reg_assignment_other_purpose_requires_detail",
            ),
        ),
        migrations.AddConstraint(
            model_name="operatorassignment",
            constraint=models.CheckConstraint(
                condition=~Q(purpose="other") | ~Q(purpose_detail=""),
                name="reg_opassign_other_purpose_requires_detail",
            ),
        ),
        migrations.AddConstraint(
            model_name="aircraftassignment",
            constraint=models.CheckConstraint(
                condition=~Q(purpose="other") | ~Q(purpose_detail=""),
                name="reg_acassign_other_purpose_requires_detail",
            ),
        ),
    ]
