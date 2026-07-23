import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("contenttypes", "0002_remove_content_type_name"),
        ("workboard", "0005_kanbantask_created_by_user"),
    ]

    operations = [
        migrations.AddField(
            model_name="kanbantask",
            name="source_content_type",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="workboard_source_tasks",
                to="contenttypes.contenttype",
            ),
        ),
        migrations.AddField(
            model_name="kanbantask",
            name="source_object_id",
            field=models.UUIDField(blank=True, null=True),
        ),
    ]
