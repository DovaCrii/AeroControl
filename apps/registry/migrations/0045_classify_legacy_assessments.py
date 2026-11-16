"""LV-444: clasifica los intentos ya guardados como `legacy` y les da sus partes.

Los intentos anteriores a las evaluaciones del Manual (Act. 19, REG-019) se rindieron
con la prueba única de 25 preguntas y 80 %. Siguen leyéndose igual: `kind="legacy"`
(ya es el valor por omisión de la columna; se fija igual, explícito) y un
`part_scores` de una sola parte «A» con el 80 % con que se evaluaron, para que la
revisión muestre el puntaje contra su umbral real. Se conserva lo guardado: no se
toca `answers`, `expires_on` ni `passed`. Sólo se completan los vacíos, así que
correrla dos veces no cambia nada.
"""

from django.db import migrations

LEGACY_PASS_PERCENT = 80  # el umbral de entonces, fijo: la migración no importa constantes vivas.


def classify_legacy_attempts(apps, schema_editor):
    KnowledgeAssessment = apps.get_model("registry", "KnowledgeAssessment")
    for attempt in KnowledgeAssessment.objects.filter(part_scores={}).iterator():
        attempt.kind = "legacy"
        attempt.part_scores = {
            "A": {
                "correct": attempt.correct_count,
                "total": attempt.question_count,
                "percent": float(attempt.score_percent),
                "threshold": LEGACY_PASS_PERCENT,
                "passed": attempt.passed,
            }
        }
        attempt.save(update_fields=["kind", "part_scores"])


class Migration(migrations.Migration):
    dependencies = [
        ("registry", "0044_evaluaciones_act19_banco_en_base"),
    ]

    operations = [
        migrations.RunPython(classify_legacy_attempts, migrations.RunPython.noop),
    ]
