"""LV-249: siembra los bloques editables con los textos que el código tenía.

**El primer informe después del despliegue tiene que salir idéntico al anterior**,
y por eso esto no arranca vacío: copia la portada de `builder.collect_meta`, el
texto de apertura de la página 5, las cuatro fases de `builder.PLAN_PHASES` y la
matriz de exigibilidad que estaba escrita en `_page5_plan.html`, con sus niveles
por mes (SEP–DIC 2026).

Los textos van **copiados acá** y no importados del código: una migración tiene que
seguir haciendo lo mismo el día que el módulo de origen cambie o desaparezca, que
es justo lo que esta fila le hace a `PLAN_PHASES`.

No se marca `elidable`: si un squash la descartara, una base nueva arrancaría sin
bloques. `builder` cae a los textos de fábrica en ese caso, pero sin fases ni
matriz — mejor que la siembra viaje con el esquema.
"""

from datetime import date

from django.db import migrations

COVER = {
    "issued_by": "Gerente de Operaciones Aéreas ante la DGAC",
    "jointly_with": "Jefe Seguridad Aérea ante la DGAC",
    "standard": "JEJ-GRI-SS-INS-096 Rev. 0",
    "addressed_to": (
        "Gerencia General · Gerencia de Riesgo · "
        "Gerencia de Ingeniería · Administradores de Contrato"
    ),
    "scope": "Vigencia de permisos de vuelo ante la DGAC",
    "sources": "AeroControl · SIGO — DGAC",
    "plan_lede": (
        "Cuatro fases de un mes. Ninguna exige lo que la anterior no dejó "
        "instalado: primero se cierra la habilitación vigente, luego se automatiza "
        "su renovación, después se instala el registro de vuelo y solo al final se "
        "exige completitud."
    ),
}

PHASES = [
    (
        date(2026, 9, 1),
        "Cierre de brechas de habilitación",
        "Renovar los permisos que vencen dentro del período. Definir cuáles de los "
        "Centros de Costo sin permiso tendrán operación aérea y tramitar su carta "
        "del mandante y su solicitud en SIGO.",
        "ningún CC con operación prevista opera sin permiso vigente.",
    ),
    (
        date(2026, 10, 1),
        "Calendario de renovación automático",
        "AeroControl calcula el vencimiento sobre la fecha real de cada resolución "
        "—no sobre un plazo supuesto— y dispara alertas a 45 y 30 días: a los 45 el "
        "ADC solicita la carta del mandante; a los 30 el Jefe Seguridad Aérea "
        "presenta en SIGO y, sin carta, escala al Gerente Operaciones Aéreas.",
        "ninguna renovación depende de que alguien la recuerde.",
    ),
    (
        date(2026, 11, 1),
        "Bitácora digital de vuelo",
        "Se habilita el registro por vuelo: bitácora (JEJ-GTE-CT-REG-015), check "
        "list pre-vuelo (LVE-003) e inspección (LVE-002). Cada vuelo se asocia al "
        "permiso que lo autoriza, de modo que el sistema no admita registrar un "
        "vuelo sin permiso vigente en esa fecha.",
        "completitud reportada como línea base, sin sanción interna.",
    ),
    (
        date(2026, 12, 1),
        "Exigibilidad plena y auditoría",
        "La completitud de bitácoras pasa a indicador exigible por Centro de Costo "
        "y se contrasta la coherencia entre vuelos ejecutados y vuelos autorizados. "
        "Auditoría interna regulatoria conforme al numeral 5.4.2 del INS-096.",
        "informe anual consolidado y plan de acción 2027.",
    ),
]

MONTHS = ["2026-09", "2026-10", "2026-11", "2026-12"]
MATRIX = [
    ("Permisos de vuelo vigentes por CC", False, ["due", "due", "due", "due"]),
    ("Renovación anticipada (carta + solicitud)", False, ["info", "due", "due", "due"]),
    ("Bitácora, check list e inspección por vuelo", True, ["na", "na", "info", "due"]),
    ("Coherencia vuelos ejecutados vs. autorizados", False, ["na", "na", "info", "due"]),
]


def seed(apps, schema_editor):
    ReportTemplate = apps.get_model("reporting", "ReportTemplate")
    PlanPhase = apps.get_model("reporting", "PlanPhase")
    ExigibilityRow = apps.get_model("reporting", "ExigibilityRow")

    # Idempotente: si alguien ya creó uno a mano, no se siembra encima.
    if ReportTemplate.objects.exists():
        return
    template = ReportTemplate.objects.create(**COVER)
    for month, title, text, close in PHASES:
        PlanPhase.objects.create(
            template=template, month=month, title=title, text=text, close=close
        )
    for order, (label, emphasis, levels) in enumerate(MATRIX):
        ExigibilityRow.objects.create(
            template=template,
            order=order,
            label=label,
            emphasis=emphasis,
            levels=dict(zip(MONTHS, levels, strict=True)),
        )


class Migration(migrations.Migration):
    dependencies = [
        ("reporting", "0004_lv249_editable_report_blocks"),
    ]

    operations = [
        # Sin reversa de datos: deshacer la migración de esquema borra las tablas,
        # y con ellas lo sembrado. Un `noop` evita que la reversa falle.
        migrations.RunPython(seed, migrations.RunPython.noop),
    ]
