"""LV-230: fusiona el tipo de documento que `LV-225` duplicó.

`dgac-flight-permit` **es** la carta del mandante — confirmado con el usuario. Se
llamaba "Autorización DGAC (carta de permiso)" mientras su documentación decía que
va *hacia* la DGAC, y ese nombre contradictorio hizo que `LV-225` creara
`client-authorization-letter` para el mismo papel.

El daño no fue teórico: el expediente pedía los dos, el usuario subió el mismo PDF
dos veces y la bandeja mostró **dos alertas por un solo vencimiento**.

Esta migración hace tres cosas y ninguna borra evidencia:

1. **Renombra** el tipo que se queda. Va acá y no en el sembrado porque
   `seed_document_types` es idempotente por `code` y usa `defaults`: **no toca una
   fila que ya existe**, así que renombrar sólo en el sembrado dejaría el nombre
   confuso en producción para siempre.
2. **Traslada** los documentos del tipo duplicado al que se queda. Los documentos
   no se tocan más que en su `doc_type`: mismo archivo, misma fecha, mismo sujeto.
3. **Borra** el tipo duplicado, y sólo si ya no le cuelga ningún documento — si
   quedara alguno, la migración se detiene en vez de arrastrar un `PROTECT` o de
   dejar documentos huérfanos.
"""

from django.db import migrations

KEEP = "dgac-flight-permit"
DROP = "client-authorization-letter"
NEW_NAME = "Carta del mandante (autorización para operar)"
OLD_NAME = "Autorización DGAC (carta de permiso)"


def merge(apps, schema_editor):
    DocumentType = apps.get_model("compliance", "DocumentType")
    Document = apps.get_model("compliance", "Document")

    keep = DocumentType.objects.filter(code=KEEP).first()
    if keep is None:
        # Una instalación que nunca sembró el catálogo: nada que fusionar, y el
        # sembrado ya creará el tipo con el nombre nuevo.
        return

    keep.name = NEW_NAME
    # El nombre viejo decía que la carta vence porque se la creía una autorización
    # de la DGAC. No toda carta del mandante trae plazo escrito, y exigirlo
    # obligaría a inventar la fecha para poder cargar el papel (`LV-219`).
    keep.requires_expiry = False
    keep.save(update_fields=["name", "requires_expiry", "updated_at"])

    drop = DocumentType.objects.filter(code=DROP).first()
    if drop is None:
        return

    Document.objects.filter(doc_type=drop).update(doc_type=keep)
    remaining = Document.objects.filter(doc_type=drop).count()
    if remaining:
        raise RuntimeError(
            f"{remaining} documentos siguen apuntando a '{DROP}' tras el "
            "traslado: no se borra el tipo para no dejarlos huérfanos."
        )
    drop.delete()


def unmerge(apps, schema_editor):
    """Devuelve el nombre viejo y recrea el tipo duplicado, vacío.

    **No se puede deshacer el traslado**, y hay que decirlo: una vez que los
    documentos de los dos tipos están juntos, nada distingue cuál venía de cuál —
    era el mismo papel, que es justamente el motivo de la fusión. Revertir deja el
    catálogo como estaba y los documentos donde quedaron.
    """
    DocumentType = apps.get_model("compliance", "DocumentType")

    keep = DocumentType.objects.filter(code=KEEP).first()
    if keep is not None:
        keep.name = OLD_NAME
        keep.requires_expiry = True
        keep.save(update_fields=["name", "requires_expiry", "updated_at"])
    DocumentType.objects.get_or_create(
        code=DROP,
        defaults={"name": NEW_NAME, "requires_expiry": False},
    )


class Migration(migrations.Migration):
    dependencies = [
        ("compliance", "0024_lv180_geo_source_gets_a_readable_name"),
    ]

    operations = [
        migrations.RunPython(merge, unmerge),
    ]
