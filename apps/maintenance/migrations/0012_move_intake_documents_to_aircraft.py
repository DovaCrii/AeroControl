"""LV-388: los documentos de un ingreso a servicio técnico cuelgan de la aeronave.

Hasta ahora `WorkshopIntakeConfirm` creaba el `Document` con la mantención como
sujeto. El documento es del equipo (la ficha de la aeronave lo muestra en
«Documentos»), y la mantención lo sigue apuntando con `source_document` /
`quote_document`. Esta migración mueve a la aeronave **sólo** los documentos que
algún ingreso apunta y que todavía cuelgan de la mantención de ese ingreso;
ningún otro documento se toca.

Idempotente (lo que ya cuelga de la aeronave no se vuelve a mover) y sin reversa
útil: volver a la mantención no recupera nada que alguien necesite, así que la
reversa es un no-op explícito.
"""

from django.db import migrations

DOCUMENT_FIELDS = ("source_document_id", "quote_document_id")


def move_intake_documents_to_aircraft(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    Document = apps.get_model("compliance", "Document")
    WorkshopIntake = apps.get_model("maintenance", "WorkshopIntake")
    MaintenanceRecord = apps.get_model("maintenance", "MaintenanceRecord")
    Aircraft = apps.get_model("registry", "Aircraft")

    record_ct = ContentType.objects.filter(
        app_label="maintenance", model="maintenancerecord"
    ).first()
    aircraft_ct = ContentType.objects.filter(
        app_label="registry", model="aircraft"
    ).first()
    if record_ct is None or aircraft_ct is None:
        return  # base nueva: no hay nada que mover

    # `values_list`, nunca `.all()`: sólo las columnas que ya existen.
    rows = WorkshopIntake.objects.values_list("record_id", *DOCUMENT_FIELDS)
    for record_id, source_id, quote_id in rows:
        document_ids = [pk for pk in (source_id, quote_id) if pk]
        if not document_ids:
            continue
        aircraft_id = MaintenanceRecord.objects.values_list(
            "aircraft_id", flat=True
        ).get(pk=record_id)
        tenant_id = Aircraft.objects.values_list("tenant_id", flat=True).get(
            pk=aircraft_id
        )
        Document.objects.filter(
            pk__in=document_ids, content_type=record_ct, object_id=record_id
        ).update(content_type=aircraft_ct, object_id=aircraft_id, tenant_id=tenant_id)


class Migration(migrations.Migration):
    dependencies = [
        ("compliance", "0027_lv290_flight_log_txt_type"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("maintenance", "0011_workshop_intake_quote"),
        ("registry", "0042_operator_left_company"),
    ]

    operations = [
        migrations.RunPython(
            move_intake_documents_to_aircraft,
            migrations.RunPython.noop,
            elidable=False,
        )
    ]
