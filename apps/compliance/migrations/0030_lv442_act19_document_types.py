"""LV-442: la Act. 19 del Manual de Operaciones (aprobada DGAC el 2026-11-10).

- `flight-log` pasa a ser el REG-016 Rev. 2 «Registro único de misión», que
  reemplaza la bitácora REG-015, el check list LVE-003, el formulario NEO y el
  registro de baterías.
- `rpa-checklist` (LVE-003) se archiva: sale de las altas nuevas y sus documentos
  siguen donde estaban. **Condición de cierre del paso 2** (borrar la fila): que no
  quede ningún LVE-003 dentro de su plazo de retención y la dirección lo decida;
  mientras haya uno, `Document.doc_type` es PROTECT.
- `drone-inspection` (LVE-002 Rev. 1) pasa a ser de la aeronave, con vencimiento.
- Se crean los tipos nuevos REG-018, REG-019 y REG-020 (códigos provisorios hasta
  que el SMS asigne los definitivos).

`seed_document_types` **no se corre al desplegar**, por eso esto es migración.
Idempotente **por `code`** y respetuosa de la interfaz: un campo sólo cambia si
sigue valiendo lo sembrado anterior (uno editado a mano se deja). La reversa
restaura lo anterior con la misma regla, y borra los tipos nuevos sólo si nadie
los usó. Los chequeos usan `values_list`/`filter`, nunca `SELECT *` de más.
"""

from django.db import migrations

# code: {campo: (anterior, nuevo)}
CHANGES = {
    "flight-log": {
        "name": ("Bitácora de vuelo", "Registro único de misión"),
        "description": (
            "Registro interno de cada vuelo realizado",
            "Reemplaza la bitácora REG-015, el check list LVE-003, el formulario NEO "
            "y el registro de baterías; se carga por misión en el centro de costo "
            "dentro de 24 h",
        ),
        "reference_code": ("REG-015", "REG-016 Rev. 2"),
    },
    "rpa-checklist": {
        "is_active": (True, False),
        "description": (
            "Verificación del RPA antes del vuelo",
            "Retirado por la Act. 19: lo reemplaza el REG-016; sólo se consulta lo "
            "ya cargado",
        ),
    },
    "drone-inspection": {
        "description": (
            "Revisión del estado del RPA",
            "Del RPA: al recibir el equipo, cada 6 meses o 200 h, o tras una falla",
        ),
        "reference_code": ("LVE-002", "LVE-002 Rev. 1"),
        "category": ("operational", "aircraft"),
        "requires_expiry": (False, True),
        "sort_order": (30, 60),
    },
}

# code: (name, description, reference_code, sort_order, category)
NEW_TYPES = {
    "operator-qualification-intake": (
        "Calificación e ingreso del operador",
        "Calificación e ingreso del operador. Código provisorio hasta que el SMS "
        "asigne el definitivo",
        "REG-018 R0",
        30,
        "personnel",
    ),
    "operator-theory-evaluations": (
        "Evaluaciones teóricas del operador",
        "Evaluaciones teóricas del operador. Código provisorio hasta que el SMS "
        "asigne el definitivo",
        "REG-019 R0",
        40,
        "personnel",
    ),
    "rpa-service-life": (
        "Hoja de vida del RPA",
        "Hoja de vida del RPA. Código provisorio hasta que el SMS asigne el "
        "definitivo",
        "REG-020 R0",
        70,
        "aircraft",
    ),
}


def _move(apps, index_from, index_to):
    DocumentType = apps.get_model("compliance", "DocumentType")
    for code, fields in CHANGES.items():
        row = DocumentType.objects.filter(code=code).first()
        if row is None:
            continue
        changed = []
        for field, values in fields.items():
            if getattr(row, field) == values[index_from]:
                setattr(row, field, values[index_to])
                changed.append(field)
        if changed:
            row.save(update_fields=changed)


def apply_act19(apps, schema_editor):
    _move(apps, 0, 1)
    DocumentType = apps.get_model("compliance", "DocumentType")
    for code, (name, description, reference, order, category) in NEW_TYPES.items():
        DocumentType.objects.get_or_create(
            code=code,
            defaults={
                "name": name,
                "description": description,
                "reference_code": reference,
                "sort_order": order,
                "category": category,
                "requires_expiry": False,
                "is_insurance": False,
                "is_operational_record": False,
            },
        )


def revert_act19(apps, schema_editor):
    _move(apps, 1, 0)
    DocumentType = apps.get_model("compliance", "DocumentType")
    Document = apps.get_model("compliance", "Document")
    for code in NEW_TYPES:
        kind = DocumentType.objects.filter(code=code).first()
        # `doc_type` es PROTECT: con documentos colgando no se borra.
        if kind is not None and not Document.objects.filter(doc_type=kind).exists():
            kind.delete()


class Migration(migrations.Migration):
    dependencies = [("compliance", "0029_lv395_issue_date_optional")]

    operations = [migrations.RunPython(apply_act19, revert_act19)]
