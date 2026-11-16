"""LV-443: siembra del programa de mantención del Manual Act. 19, Anexo F.

Sólo lo que el Manual dice con número:

* DJI Matrice 300 RTK, Mavic 3 Enterprise y Matrice 4 Enterprise / 4 Thermal: básica
  200 h o 6 meses, media 400 h o 12 meses, avanzada 600 h o 18 meses.
* Flyability Elios 3 y Wingtra One Gen2: «según manual del fabricante; revisión en
  servicio autorizado al menos cada 12 meses» -> **sólo meses** (12), sin horas. Los
  niveles medio y avanzado dicen «según fabricante» y **no se siembran**: se cargan a
  mano cuando alguien tenga la cifra.

Idempotente por (nombre, nivel): `get_or_create`, así que volver a correrla no duplica
ni pisa un intervalo que alguien ya ajustó. La reversa es un no-op: borrar el programa
dejaría las aeronaves sin regla, y eso no es deshacer nada que alguien necesite.
"""

from django.db import migrations

DJI = ("DJI Enterprise (Matrice / Mavic)", "matrice,mavic")
PROGRAMS = [
    # (name, model_keywords, level, interval_hours, interval_months)
    (*DJI, "basic", 200, 6),
    (*DJI, "medium", 400, 12),
    (*DJI, "advanced", 600, 18),
    ("Flyability Elios 3", "elios", "basic", None, 12),
    ("Wingtra One Gen2", "wingtra", "basic", None, 12),
]


def seed_programs(apps, schema_editor):
    MaintenanceProgram = apps.get_model("maintenance", "MaintenanceProgram")
    for name, keywords, level, hours, months in PROGRAMS:
        MaintenanceProgram.objects.get_or_create(
            name=name,
            level=level,
            defaults={
                "model_keywords": keywords,
                "interval_hours": hours,
                "interval_months": months,
            },
        )


class Migration(migrations.Migration):
    dependencies = [("maintenance", "0013_act19_maintenance_levels")]

    operations = [
        migrations.RunPython(seed_programs, migrations.RunPython.noop, elidable=False)
    ]
