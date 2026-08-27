"""LV-169: `employee_id` pasa a `blank=True` para poder derivarlo del RUT.

**No emite SQL.** `blank` es un atributo de validación, no de esquema, así que
Django la marca `(no-op)` -- verificado con `manage.py sqlmigrate registry 0037`
antes de subirla. No toca la tabla, no la reconstruye y no hay dato en riesgo:
al desplegar, el `migrate` sólo escribe la fila en `django_migrations`.

Y el campo **no se vuelve opcional**: `Operator.clean()` exige que quede con
valor, y la unicidad por tenant (`registry_operator_tenant_employee_uniq`) sigue
igual. Lo único que cambia es que `clean_fields()` ya no corta antes de que
`clean()` alcance a derivarlo.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("registry", "0036_lv158_knowledge_assessment"),
    ]

    operations = [
        migrations.AlterField(
            model_name="operator",
            name="employee_id",
            field=models.CharField(
                blank=True, max_length=50, verbose_name="Employee ID"
            ),
        ),
    ]
