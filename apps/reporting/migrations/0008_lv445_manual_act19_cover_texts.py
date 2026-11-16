"""LV-445: los textos de portada de la Act. 19 en el bloque editable activo.

Llena `manual_reference` y `internal_control_note` **sólo si están vacíos**, y
cambia el alcance **sólo si sigue valiendo el texto de fábrica**: lo que alguien
editó a mano en «Textos del informe» no se pisa (patrón de LV-442). La reversa
devuelve el alcance si todavía vale el nuevo y vacía los dos textos nuevos si
conservan el valor sembrado.
"""

from django.db import migrations

OLD_SCOPE = "Vigencia de permisos de vuelo ante la DGAC"
NEW_SCOPE = (
    "Vigencia de permisos de vuelo y cumplimiento del Manual de Operaciones"
)
REFERENCE = (
    "Manual de Operaciones AOC N° 1485 · Actualización N° 19 "
    "(aprobada DGAC 10-11-2026)"
)
NOTE = (
    "Desde la Act. 19 este informe no es exigencia del Manual de Operaciones: "
    "se emite como control interno (INS-096)."
)


def apply_cover_texts(apps, schema_editor):
    Template = apps.get_model("reporting", "ReportTemplate")
    for pk, scope, reference, note in Template.objects.filter(
        is_active=True
    ).values_list("pk", "scope", "manual_reference", "internal_control_note"):
        changes = {}
        if scope == OLD_SCOPE:
            changes["scope"] = NEW_SCOPE
        if not reference:
            changes["manual_reference"] = REFERENCE
        if not note:
            changes["internal_control_note"] = NOTE
        if changes:
            Template.objects.filter(pk=pk).update(**changes)


def revert_cover_texts(apps, schema_editor):
    Template = apps.get_model("reporting", "ReportTemplate")
    for pk, scope, reference, note in Template.objects.filter(
        is_active=True
    ).values_list("pk", "scope", "manual_reference", "internal_control_note"):
        changes = {}
        if scope == NEW_SCOPE:
            changes["scope"] = OLD_SCOPE
        if reference == REFERENCE:
            changes["manual_reference"] = ""
        if note == NOTE:
            changes["internal_control_note"] = ""
        if changes:
            Template.objects.filter(pk=pk).update(**changes)


class Migration(migrations.Migration):
    dependencies = [("reporting", "0007_lv445_manual_act19_fields")]

    operations = [migrations.RunPython(apply_cover_texts, revert_cover_texts)]
