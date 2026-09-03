"""LV-220: de dónde salió la región y la comuna de un permiso.

**Sin backfill, y es la decisión de la migración.** Las filas que ya existen se
cargaron antes de que hubiera marcador, y no hay forma honesta de saber cuáles se
teclearon del papel DGAC y cuáles las escribió `fill_permission_from_plan` desde
el polígono: comparar contra `locate()` hoy tampoco sirve, porque una persona
pudo haber tecleado exactamente el mismo nombre. Poner `declared` en todas
inventaría una procedencia para cada permiso cargado hasta hoy, que es
literalmente el defecto que esta fila vino a corregir.

Quedan en blanco, que es el tercer estado —*no se sabe*— y se dibuja como
siempre: el valor a secas, sin aviso. Nada retrocede y lo nuevo sí queda marcado.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("operations", "0025_flightpermission_max_altitude_m"),
    ]

    operations = [
        migrations.AddField(
            model_name="flightpermission",
            name="commune_source",
            field=models.CharField(
                blank=True,
                choices=[
                    ("declared", "Declared"),
                    ("derived", "Derived from the coordinates"),
                ],
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="flightpermission",
            name="region_source",
            field=models.CharField(
                blank=True,
                choices=[
                    ("declared", "Declared"),
                    ("derived", "Derived from the coordinates"),
                ],
                max_length=10,
            ),
        ),
    ]
