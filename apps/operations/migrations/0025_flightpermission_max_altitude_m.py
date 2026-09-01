"""LV-221: la altitud del permiso pasa a metros.

El campo `max_altitude_ft` decía pies en su nombre y en su etiqueta, pero medido
en producción los **tres** permisos que lo tenían cargado decían `120`, y los tres
eran metros — el usuario lo confirmó: *"todos los 120 fueron pensados en metro
cuando se escribieron y deberían ser 394 ft"*.

⚠️ **Por eso esta migración copia el número tal cual y NO lo convierte.**

Es lo contrario de lo que haría una conversión de unidades correcta, y es
deliberado: no se está convirtiendo pies a metros, se está **corrigiendo la
etiqueta de un dato que siempre estuvo en metros**. Aplicar `/ 3.28084` dejaría
36 m donde la operación quiso 120, que es precisamente el error que esta fila vino
a cerrar.

Esa decisión sólo es válida porque se midió primero: 3 filas, todas con el mismo
valor, todas en trámite y ninguna aprobada. `check_altitudes` es el comando que
dio esa foto, y está en el repo para volver a mirarla.

**`max_altitude_ft` no se borra.** Queda como el valor original tal como se
escribió, por si alguna de las tres solicitudes ya se presentó al SIGO con el
número anterior y hay que reconstruir qué se declaró. Retiro de pantalla y no de
base, el patrón de `LV-78`, `LV-103` y `LV-155`.
"""

from django.db import migrations, models


def copy_the_number_unchanged(apps, schema_editor):
    """Copia `max_altitude_ft` a `max_altitude_m` sin convertir.

    `values_list` y `bulk_update` en vez de recorrer objetos: la migración corre
    con el código nuevo sobre la base vieja, y un `SELECT *` pediría columnas que
    esta misma migración acaba de crear — la lección de `AGENTS.md` sobre los
    chequeos previos a una migración.
    """
    FlightPermission = apps.get_model("operations", "flightpermission")
    rows = list(
        FlightPermission.objects.filter(max_altitude_ft__isnull=False).only(
            "pk", "max_altitude_ft", "max_altitude_m"
        )
    )
    for row in rows:
        row.max_altitude_m = row.max_altitude_ft
    if rows:
        FlightPermission.objects.bulk_update(rows, ["max_altitude_m"])


def undo(apps, schema_editor):
    """Vaciar la columna nueva, sin tocar la vieja.

    La vieja nunca se modificó, así que revertir es sólo soltar lo copiado: el
    dato original sigue donde estaba y no se pierde nada.
    """
    FlightPermission = apps.get_model("operations", "flightpermission")
    FlightPermission.objects.update(max_altitude_m=None)


class Migration(migrations.Migration):
    dependencies = [
        ("operations", "0024_flightpermission_validity_override_reason"),
    ]

    operations = [
        migrations.AddField(
            model_name="flightpermission",
            name="max_altitude_m",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.RunPython(copy_the_number_unchanged, undo),
    ]
