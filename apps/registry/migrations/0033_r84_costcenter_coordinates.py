"""R8.4: coordinates for the site a cost center operates on.

Both nullable, and that is the design: no existing cost center is retroactively
incomplete for not having a point on file. The dashboard simply falls back to
the next flight permit's own coordinates (OPS-4), and shows nothing when
neither is available -- weather is context, never a blocker.

No constraint here: "both or neither" is enforced in `CostCenter.clean()`, the
same place `FlightPermission` enforces it, rather than as a CheckConstraint that
would also have to be taught about the pair rule on every backfill.
"""

import django.core.validators
from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("registry", "0032_normalize_serial_case"),
    ]

    operations = [
        migrations.AddField(
            model_name="costcenter",
            name="latitude",
            field=models.DecimalField(
                blank=True,
                decimal_places=6,
                max_digits=9,
                null=True,
                validators=[
                    django.core.validators.MinValueValidator(Decimal("-90")),
                    django.core.validators.MaxValueValidator(Decimal("90")),
                ],
                verbose_name="Site latitude",
            ),
        ),
        migrations.AddField(
            model_name="costcenter",
            name="longitude",
            field=models.DecimalField(
                blank=True,
                decimal_places=6,
                max_digits=9,
                null=True,
                validators=[
                    django.core.validators.MinValueValidator(Decimal("-180")),
                    django.core.validators.MaxValueValidator(Decimal("180")),
                ],
                verbose_name="Site longitude",
            ),
        ),
    ]
