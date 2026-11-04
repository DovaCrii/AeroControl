"""LV-395: la fecha de emisión pasa a ser opcional según el tipo de documento.

Pedido del usuario (2026-11-03): el certificado de inscripción del drone no
necesita fecha de ingreso (emisión). Es una inscripción, no un hecho con fecha
que importe: exigirla invitaba a inventarla, como `compliance/0023` ya evitó con
el vencimiento.

Tres pasos, en este orden:

1. `DocumentType.requires_issue_date` (por defecto `True`: todo tipo sigue
   pidiéndola salvo que se diga lo contrario) y `Document.issue_date` admite
   nulos. El esquema acepta nulos para **todos**; quién la exige lo decide el
   formulario según el tipo.
2. Un `RunPython` idempotente por `code` que apaga la exigencia sólo en
   `aircraft-registration`. Va como migración y no sólo en el seed porque el
   sembrado es idempotente por `code` y no toca una fila ya creada.
3. Sólo para el camino de vuelta: rellena con la fecha de creación los
   documentos sin emisión, porque volver a `NOT NULL` fallaría con ellos. En el
   sentido directo no hace nada.

No toca documentos ya cargados: lo que la gente afirmó sigue ahí.
"""

from django.db import migrations, models

CODES_WITHOUT_ISSUE_DATE = ("aircraft-registration",)


def stop_requiring_issue_date(apps, schema_editor):
    DocumentType = apps.get_model("compliance", "DocumentType")
    # `values_list`: el chequeo corre con el código nuevo sobre el esquema que
    # esta migración acaba de crear, y no debe leer nada más.
    pending = DocumentType.objects.filter(
        code__in=CODES_WITHOUT_ISSUE_DATE, requires_issue_date=True
    ).values_list("pk", flat=True)
    DocumentType.objects.filter(pk__in=list(pending)).update(requires_issue_date=False)


def require_issue_date_again(apps, schema_editor):
    """Reverse: vuelve a exigirla, para que una segunda aplicación dé lo mismo."""
    DocumentType = apps.get_model("compliance", "DocumentType")
    DocumentType.objects.filter(code__in=CODES_WITHOUT_ISSUE_DATE).update(
        requires_issue_date=True
    )


def do_nothing(apps, schema_editor):
    """Forward: nada que rellenar; el esquema ya admite nulos."""


def fill_missing_issue_dates(apps, schema_editor):
    """Reverse: `issue_date` vuelve a ser obligatoria, así que se rellena."""
    Document = apps.get_model("compliance", "Document")
    missing = Document.objects.filter(issue_date__isnull=True).values_list(
        "pk", "created_at"
    )
    for pk, created_at in list(missing):
        Document.objects.filter(pk=pk).update(issue_date=created_at.date())


class Migration(migrations.Migration):
    dependencies = [
        ("compliance", "0028_lv385_document_type_taxonomy"),
    ]

    operations = [
        migrations.AddField(
            model_name="documenttype",
            name="requires_issue_date",
            field=models.BooleanField(
                default=True,
                help_text=(
                    "Untick for papers that carry no issue date worth recording "
                    "(for example the RPA registration certificate)."
                ),
                verbose_name="Requires issue date",
            ),
        ),
        migrations.AlterField(
            model_name="document",
            name="issue_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.RunPython(stop_requiring_issue_date, require_issue_date_again),
        migrations.RunPython(do_nothing, fill_missing_issue_dates),
    ]
