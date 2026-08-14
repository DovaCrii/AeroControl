"""LV-95: group the document-type catalog so its picker can be read.

The column ships with a backfill, not with everything sitting in "other": the
catalog already exists in every installation, so a schema-only migration would
leave the new grouping meaningless until somebody edited eighteen rows by hand.

The backfill is keyed by `code` -- the seed command's stable identity, the same
key `seed_document_types` is idempotent on. Names are user-editable and
translated, so matching on them would classify one installation and skip the
next. A code that is not in this map (a type somebody created in the UI, the
`GEO_SOURCE` type the KML import mints) keeps the "other" default; that is the
honest answer, and the picker shows it under "Other" where it can be fixed.
"""

from django.db import migrations, models

# code -> category, for the catalog `seed_document_types` creates.
CATEGORY_BY_CODE = {
    "dgac-credential": "personnel",
    "medical-cert": "personnel",
    "aircraft-registration": "aircraft",
    "airworthiness-cert": "aircraft",
    "liability-insurance": "aircraft",
    "dgac-flight-permit": "dgac",
    "dgac-rpa-operation-authorization": "dgac",
    "flight-request": "dgac",
    "monthly-non-operation-notice": "dgac",
    "flight-log": "operational",
    "rpa-checklist": "operational",
    "drone-inspection": "operational",
    "incident-investigation-record": "operational",
    "maintenance-certificate": "maintenance",
    "calibration-certificate": "maintenance",
    "aoc-certificate": "company",
    "company-procedure": "company",
}


def classify_seeded_types(apps, schema_editor):
    DocumentType = apps.get_model("compliance", "DocumentType")
    for code, category in CATEGORY_BY_CODE.items():
        DocumentType.objects.filter(code=code).update(category=category)


def unclassify(apps, schema_editor):
    """Reverse: back to the column default.

    Not a no-op -- re-applying the migration forward has to reproduce the same
    state, and leaving hand-made classifications behind after a rollback would
    make the second run's result depend on the first.
    """
    DocumentType = apps.get_model("compliance", "DocumentType")
    DocumentType.objects.filter(code__in=CATEGORY_BY_CODE).update(category="other")


class Migration(migrations.Migration):

    dependencies = [
        ("compliance", "0018_lv80_translatable_model_names"),
    ]

    operations = [
        migrations.AddField(
            model_name="documenttype",
            name="category",
            field=models.CharField(
                choices=[
                    ("personnel", "Personnel documents"),
                    ("aircraft", "Aircraft documents"),
                    ("dgac", "DGAC filings and authorizations"),
                    ("operational", "Operational records"),
                    ("maintenance", "Maintenance and calibration"),
                    ("company", "Company documents"),
                    ("other", "Other"),
                ],
                default="other",
                help_text="Groups this type inside the document-type picker.",
                max_length=20,
                verbose_name="Category",
            ),
        ),
        migrations.RunPython(classify_seeded_types, unclassify),
    ]
