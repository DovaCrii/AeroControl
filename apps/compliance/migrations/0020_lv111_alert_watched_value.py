"""LV-111: la alerta recuerda de qué valor hablaba.

Sin relleno esta migración no sirve para lo que existe: toda alerta anterior
quedaría con `watched_value` vacío, no coincidiría con el valor actual del
registro, y **volvería a duplicarse una vez más** — justo el defecto que se está
corrigiendo, en la primera corrida después de desplegar.

El relleno lee el valor que el registro tiene **hoy**, que es la única lectura
posible (el valor histórico no se guardó en ninguna parte) y la correcta para el
caso que motivó esto: una alerta resuelta sobre algo que sigue vencido. Si el
registro fue renovado desde entonces, el relleno anota el valor nuevo; eso podría
suprimir una alerta por ese valor nuevo, pero un valor renovado no está vencido
ni próximo, así que no habría alerta que suprimir.

Se salta en silencio las alertas cuyo registro ya no existe o cuya regla apunta a
un campo que el modelo perdió: son datos viejos, no motivo para abortar un
despliegue.
"""

from django.db import migrations, models


def backfill_watched_value(apps, schema_editor):
    from django.apps import apps as live_apps

    Alert = apps.get_model("compliance", "Alert")
    updated = []
    for alert in Alert.objects.select_related("alert_rule", "content_type").iterator():
        content_type = alert.content_type
        try:
            model = live_apps.get_model(content_type.app_label, content_type.model)
        except LookupError:
            continue
        record = model._default_manager.filter(pk=alert.object_id).first()
        if record is None:
            continue
        value = getattr(record, alert.alert_rule.field_to_watch, None)
        if value is None:
            continue
        alert.watched_value = str(value)[:100]
        updated.append(alert)
    if updated:
        Alert.objects.bulk_update(updated, ["watched_value"])


def clear_watched_value(apps, schema_editor):
    """Reverso: la columna se va con `RemoveField`, así que esto sólo existe
    para que `RunPython` sea reversible y el `migrate --plan` inverso no falle."""
    Alert = apps.get_model("compliance", "Alert")
    Alert.objects.update(watched_value="")


class Migration(migrations.Migration):
    dependencies = [
        ("compliance", "0019_lv95_document_type_category"),
    ]

    operations = [
        migrations.AddField(
            model_name="alert",
            name="watched_value",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.RunPython(backfill_watched_value, clear_watched_value),
    ]
