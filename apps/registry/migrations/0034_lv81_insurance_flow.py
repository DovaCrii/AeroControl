"""LV-81: the JAC insurance filing gets the four states the real cycle has.

Besides the new choices and the trace table, this carries a **data fix**: every
aircraft claiming `active` while having no expiry date on file is set to
`missing`. That pair is not a state the DGAC has -- it is what R5.7's old
default produced for an aircraft nobody had entered insurance for, and
production has three of them (`RPA-2019`, `RPA-3696`, `RPA-7126`, per HANDOFF).
Left alone they would keep reading "Vigente" with no date beside them, which is
the exact reading the user asked to fix.

`pending` rows are excluded from the fix: someone deliberately marked those as
being arranged, and a migration must not overwrite a human's answer.
"""

import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


def missing_when_no_expiry(apps, schema_editor):
    Aircraft = apps.get_model("registry", "Aircraft")
    Aircraft.objects.filter(insurance_expiry__isnull=True).exclude(
        insurance_status="pending"
    ).update(insurance_status="missing")


def back_to_active(apps, schema_editor):
    """Reverse in the only sense that matters: those rows said `active` before."""
    Aircraft = apps.get_model("registry", "Aircraft")
    Aircraft.objects.filter(insurance_status="missing").update(
        insurance_status="active"
    )


class Migration(migrations.Migration):

    dependencies = [
        ('registry', '0033_r84_costcenter_coordinates'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name='aircraft',
            name='insurance_status',
            field=models.CharField(blank=True, choices=[('missing', 'Missing or to be renewed'), ('pending', 'Filing in progress'), ('filed', 'Filed in SIGO, awaiting the JAC'), ('active', 'Policy in force')], default='missing', max_length=20, verbose_name='Insurance status'),
        ),
        migrations.CreateModel(
            name='InsuranceHistory',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_active', models.BooleanField(default=True)),
                ('sequence', models.PositiveBigIntegerField(default=0, editable=False)),
                ('previous_status', models.CharField(choices=[('missing', 'Missing or to be renewed'), ('pending', 'Filing in progress'), ('filed', 'Filed in SIGO, awaiting the JAC'), ('active', 'Policy in force')], max_length=20)),
                ('new_status', models.CharField(choices=[('missing', 'Missing or to be renewed'), ('pending', 'Filing in progress'), ('filed', 'Filed in SIGO, awaiting the JAC'), ('active', 'Policy in force')], max_length=20)),
                ('changed_by', models.CharField(max_length=150)),
                ('notes', models.TextField(blank=True)),
                ('aircraft', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='insurance_history', to='registry.aircraft')),
                ('changed_by_user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='insurance_history_events', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'insurance history',
                'verbose_name_plural': 'insurance histories',
                'ordering': ['-sequence'],
            },
        ),
        migrations.RunPython(missing_when_no_expiry, back_to_active),
    ]
