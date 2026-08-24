"""LV-138: el plan gana su folio correlativo anual (`PG-2026-001`).

**Tres pasos y no uno**, y la razón es la que hace fallar la migración ingenua:
el campo es `unique`, así que agregarlo con su valor por omisión (`""`) sobre una
tabla con filas dejaría a todas con la misma cadena vacía y la restricción
reventaría en el primer plan más uno. Así que entra **sin** unicidad, se rellena,
y recién entonces se le pone la restricción.

El relleno respeta el orden de creación **dentro de cada año**, que es lo que un
correlativo significa: el plan más viejo de 2026 es `PG-2026-001`. Se usa el año
de `created_at` y no el actual, para que un plan del año pasado no reciba un
número de este.
"""

from django.db import migrations, models


def assign_folios(apps, _schema_editor):
    GeoPlan = apps.get_model("geo", "GeoPlan")
    counters = {}
    # Sin `is_active`: un plan archivado también ocupa su número. Reutilizarlo
    # haría que dos planes distintos hayan sido `PG-2026-004` en momentos
    # distintos, que es exactamente lo que un identificador no puede permitirse.
    for plan in GeoPlan.objects.order_by("created_at", "id").iterator():
        year = plan.created_at.year
        counters[year] = counters.get(year, 0) + 1
        plan.folio = f"PG-{year}-{counters[year]:03d}"
        plan.save(update_fields=["folio"])


def clear_folios(apps, _schema_editor):
    """Al revertir, vaciarlos: el campo se va igual, pero dejar la migración
    reversible mantiene honesto el `migrate geo 0004` de un rollback."""
    GeoPlan = apps.get_model("geo", "GeoPlan")
    GeoPlan.objects.update(folio="")


class Migration(migrations.Migration):
    dependencies = [
        ("geo", "0004_weather_review"),
    ]

    operations = [
        migrations.AddField(
            model_name="geoplan",
            name="folio",
            field=models.CharField(blank=True, editable=False, max_length=20),
        ),
        migrations.RunPython(assign_folios, clear_folios),
        migrations.AlterField(
            model_name="geoplan",
            name="folio",
            field=models.CharField(
                blank=True, editable=False, max_length=20, unique=True
            ),
        ),
    ]
