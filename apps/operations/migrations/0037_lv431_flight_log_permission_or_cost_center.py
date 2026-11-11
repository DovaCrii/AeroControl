"""LV-431: un log siempre queda ubicado: por su permiso o por su centro de costo."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("operations", "0036_lv431_flight_log_backfill"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="flightloganalysis",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("permission__isnull", False),
                    ("cost_center__isnull", False),
                    _connector="OR",
                ),
                name="ops_flightlog_permission_or_cost_center",
            ),
        ),
    ]