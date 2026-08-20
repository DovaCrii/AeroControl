"""LV-121: el registro DGAC de un RPA no vence, así que deja de exigir fecha.

El "Certificado del Registro Nacional de RPA" que emite la DGAC no trae fecha de
término: es una inscripción —número de registro, marca, modelo, serie, peso,
propietario— y el propio documento aclara que "no constituye autorización para
operación del RPA", que es lo que sí caduca y vive en otros tipos del catálogo.

El tipo `aircraft-registration` estaba marcado con `requires_expiry=True` desde
`LV-1`, así que el formulario **rechazaba el PDF real** y la única salida era
inventar un vencimiento — que después habría disparado una alerta por algo que
no vence. Descubierto el 2026-08-20 al ir a cargar los certificados de
`RPA-7126` y `RPA-7213`.

Va como migración y no sólo como cambio del seed porque `seed_document_types`
es idempotente **por `code`** (`get_or_create`): una fila que ya existe no se
toca, así que sin esto el arreglo no llegaría a ninguna instalación en marcha,
que son todas.

Sólo toca esa fila y sólo esa bandera. No borra vencimientos ya cargados: si
alguien puso una fecha en un registro, sigue ahí y sigue vigilándose — la
migración cambia lo que el formulario **exige de aquí en adelante**, no reescribe
lo que la gente afirmó.
"""

from django.db import migrations

CODE = "aircraft-registration"


def stop_requiring_expiry(apps, schema_editor):
    DocumentType = apps.get_model("compliance", "DocumentType")
    DocumentType.objects.filter(code=CODE).update(requires_expiry=False)


def require_expiry_again(apps, schema_editor):
    """Reverse: vuelve a exigirla.

    No es un no-op. Revertir tiene que dejar el estado anterior para que una
    segunda aplicación hacia adelante produzca el mismo resultado; dejarla en
    `False` haría que el resultado del segundo intento dependiera del primero,
    que es el defecto que `compliance/0019` documentó en su propio reverso.
    """
    DocumentType = apps.get_model("compliance", "DocumentType")
    DocumentType.objects.filter(code=CODE).update(requires_expiry=True)


class Migration(migrations.Migration):
    dependencies = [
        ("compliance", "0022_nonconformity_root_cause_category_and_more"),
    ]

    operations = [
        migrations.RunPython(stop_requiring_expiry, require_expiry_again),
    ]
