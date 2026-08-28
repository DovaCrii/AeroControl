"""LV-180: el tipo de documento "Geo source" pasa a llamarse como lo que es.

En una app cuya interfaz es española y donde los tipos de documento nombran
papeles reales —"Autorización de Operación RPA"—, "Geo source" era el único
anglicismo del conjunto, y encima jerga: ese tipo es, literalmente, el KMZ o KML
que alguien subió.

**Hace falta una migración de datos y no alcanza con cambiar el código**, que es
lo que se anotó al capturar la fila: el nombre se fija en los `defaults` de un
`get_or_create`, y los `defaults` **sólo se usan al crear**. La fila que ya
existe en producción se quedaría con el nombre viejo para siempre, y quien mirara
el código creería que está renombrada.

**El código `GEO_SOURCE` no se toca**: lo referencian otras partes y no lo ve
nadie. Renombrar la llave por cambiar la etiqueta sería romper referencias para
arreglar una palabra.

**Los dos nombres van escritos acá y no importados de `views.py`**, a propósito:
una migración es un hecho fechado. Si mañana alguien vuelve a cambiar la
constante, esta migración tiene que seguir renombrando lo que renombró el día que
corrió — importarla la haría reescribir el pasado.

Se filtra por `name` además de por `code`: si alguien ya lo renombró a mano en el
admin, esto **no le pisa** su elección.
"""

from django.db import migrations

CODE = "GEO_SOURCE"
OLD_NAME = "Geo source"
NEW_NAME = "Archivo KMZ/KML de origen"


def rename(apps, schema_editor):
    DocumentType = apps.get_model("compliance", "DocumentType")
    DocumentType.objects.filter(code=CODE, name=OLD_NAME).update(name=NEW_NAME)


def unrename(apps, schema_editor):
    DocumentType = apps.get_model("compliance", "DocumentType")
    DocumentType.objects.filter(code=CODE, name=NEW_NAME).update(name=OLD_NAME)


class Migration(migrations.Migration):
    dependencies = [
        ("compliance", "0023_lv121_aircraft_registration_does_not_expire"),
    ]

    operations = [migrations.RunPython(rename, unrename)]
