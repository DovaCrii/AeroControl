"""LV-177: dos columnas auxiliares para ordenar el padrón por apellido.

**Esta sí toca la base, a diferencia de `0037`.** SQLite no sabe agregar una
columna `NOT NULL` sin default, así que Django **reconstruye la tabla**: crea
`new__registry_operator`, copia las filas, hace `DROP TABLE` y renombra
(verificado con `manage.py sqlmigrate registry 0038` antes de subirla). Todo va
en una transacción y no hay pérdida esperada, pero es exactamente el caso donde
`AGENTS.md` pide **respaldo previo y verificado** antes de migrar: `manage.py
backup` y `verify_backup <ruta>`.

Las dos columnas nacen **vacías**, y eso es la decisión, no una omisión: dónde
empieza el apellido no se deduce sin equivocarse, y un corte inventado ordena mal
justo los casos raros —partículas, dos nombres y dos apellidos— sin que nadie lo
note, porque la lista igual se ve ordenada. Se completan con
`split_operator_names`, que propone y sólo escribe con `--apply`, y a mano en la
ficha para los que el patrón no alcanza.

Mientras estén vacías **no se rompe nada**: el listado ordena por apellido cuando
está cargado y por nombre completo cuando no.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("registry", "0037_alter_operator_employee_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="operator",
            name="given_names",
            field=models.CharField(
                blank=True, max_length=100, verbose_name="Given names"
            ),
        ),
        migrations.AddField(
            model_name="operator",
            name="surnames",
            field=models.CharField(blank=True, max_length=100, verbose_name="Surnames"),
        ),
    ]
