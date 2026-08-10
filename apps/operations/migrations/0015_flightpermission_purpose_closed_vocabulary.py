"""R3.1: `purpose` becomes a closed-vocabulary code instead of free text --
see apps/registry/migrations/0026_purpose_closed_vocabulary.py for the full
rationale and the real-data evidence (R3.1a). This is FlightPermission's
half of the same change.

Unlike the registry assignment models, `purpose` is required here (no
blank=True) -- both real rows already have non-empty text, so the backfill
never hits the "nothing to classify" branch.
"""

from django.db import migrations, models
from django.db.models import Q


def backfill_forward(apps, schema_editor):
    from apps.core.choices import PURPOSE_LEGACY_MAP

    FlightPermission = apps.get_model("operations", "FlightPermission")
    for permission in FlightPermission.objects.all():
        original = permission.purpose or ""
        permission.purpose_legacy = original
        code = PURPOSE_LEGACY_MAP.get(original.strip().lower())
        if code:
            permission.purpose = code
        else:
            permission.purpose = "other"
            permission.purpose_detail = original
        permission.save(
            update_fields=["purpose", "purpose_detail", "purpose_legacy"]
        )


PURPOSE_CHOICES = [
    ("photogrammetry", "Photogrammetry Procedure"),
    ("video", "Video Procedure"),
    ("other", "Other"),
]


class Migration(migrations.Migration):
    dependencies = [
        ("operations", "0014_flightpermission_internal_folio"),
    ]

    operations = [
        migrations.AddField(
            model_name="flightpermission",
            name="purpose_detail",
            field=models.CharField(blank=True, default="", max_length=250),
        ),
        migrations.AddField(
            model_name="flightpermission",
            name="purpose_legacy",
            field=models.CharField(
                blank=True, default="", editable=False, max_length=250
            ),
        ),
        migrations.RunPython(backfill_forward, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="flightpermission",
            name="purpose",
            field=models.CharField(choices=PURPOSE_CHOICES, max_length=20),
        ),
        migrations.AddConstraint(
            model_name="flightpermission",
            constraint=models.CheckConstraint(
                condition=~Q(purpose="other") | ~Q(purpose_detail=""),
                name="ops_flightpermission_other_purpose_requires_detail",
            ),
        ),
    ]
