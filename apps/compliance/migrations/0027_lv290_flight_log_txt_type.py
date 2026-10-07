"""LV-290: el tipo de documento del registro de vuelo `.TXT` de la DGAC.

`seed_document_types` es idempotente por `code` pero **no se corre al desplegar**, así que
sólo agregar la fila al sembrado dejaría a producción sin el tipo hasta que alguien lo
corriera a mano. Esta migración lo crea donde falta y no toca uno que ya exista (si
alguien lo renombró desde la interfaz, ese nombre se respeta).
"""

from django.db import migrations

CODE = "flight-log-txt"


def create_type(apps, schema_editor):
    DocumentType = apps.get_model("compliance", "DocumentType")
    DocumentType.objects.get_or_create(
        code=CODE,
        defaults={
            "name": "Registro de vuelo DGAC (.TXT)",
            "requires_expiry": False,
            "is_insurance": False,
            "is_operational_record": False,
            "category": "dgac",
        },
    )


def remove_type(apps, schema_editor):
    DocumentType = apps.get_model("compliance", "DocumentType")
    Document = apps.get_model("compliance", "Document")
    # Sólo si nadie lo usó: borrar el tipo con documentos colgando los dejaría
    # huérfanos, y `doc_type` es PROTECT.
    kind = DocumentType.objects.filter(code=CODE).first()
    if kind is not None and not Document.objects.filter(doc_type=kind).exists():
        kind.delete()


class Migration(migrations.Migration):
    dependencies = [("compliance", "0026_ux14_owner")]

    operations = [migrations.RunPython(create_type, remove_type)]
