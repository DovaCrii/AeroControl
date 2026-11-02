"""LV-385: la taxonomía de los tipos de documento (PR 2 de 4).

Agrega `description`, `reference_code` y `sort_order`, y lleva el catálogo ya
sembrado a los nombres estandarizados (sustantivo + calificador, sin paréntesis;
el código del formulario pasa a `reference_code`).

Idempotente **por `code`** y respetuosa de la interfaz: el nombre sólo cambia si
sigue siendo el sembrado anterior (uno renombrado a mano se deja); la guía sólo
llena lo que está vacío. Nunca crea filas, ni toca `code`, ni la categoría, y los
documentos ya subidos conservan su tipo. La reversa devuelve el nombre anterior
si el actual sigue siendo el nuevo.

`seed_document_types` lleva los mismos datos; un guardián los cruza.
"""

from django.db import migrations, models

# code: (old_name, new_name, description, reference_code, sort_order)
TAXONOMY = {
    "dgac-credential": (
        "Credencial DGAC",
        "Credencial DGAC de operador",
        "Habilita al piloto; vence",
        "",
        10,
    ),
    "medical-cert": (
        "Certificado médico / aptitud",
        "Certificado de aptitud médica",
        "Acredita la aptitud médica del piloto; vence",
        "",
        20,
    ),
    "aircraft-registration": (
        "Registro / matrícula de aeronave",
        "Certificado de inscripción RPA",
        "Inscripción DGAC; no vence ni autoriza a operar",
        "",
        10,
    ),
    "airworthiness-cert": (
        "Certificado de aeronavegabilidad",
        "Certificado de aeronavegabilidad",
        "Acredita que la aeronave está en condiciones de volar; vence",
        "",
        20,
    ),
    "liability-insurance": (
        "Seguro de responsabilidad civil",
        "Póliza de responsabilidad civil",
        "Cubre los daños a terceros; vence",
        "",
        30,
    ),
    "jac-insurance-request": (
        "Solicitud de aprobación de seguro RPA (a la JAC)",
        "Solicitud de aprobación de seguro a la JAC",
        "Se envía a la JAC para que apruebe el seguro; no vence",
        "",
        40,
    ),
    "jac-insurance-approval": (
        "Resolución Exenta JAC (aprueba seguro RPA)",
        "Resolución JAC que aprueba el seguro",
        "Respuesta de la JAC; vence con la póliza",
        "",
        50,
    ),
    "dgac-flight-permit": (
        "Carta del mandante (autorización para operar)",
        "Carta del mandante",
        "La firma el cliente; acompaña la solicitud",
        "",
        10,
    ),
    "dgac-rpa-operation-authorization": (
        "Autorización de Operación RPA (DGAC aprobada)",
        "Autorización de operación RPA",
        "La entrega la DGAC al aprobar la operación; vence",
        "",
        20,
    ),
    "flight-log-txt": (
        "Registro de vuelo DGAC (.TXT)",
        "Archivo de registro de vuelo",
        "El archivo que pide el portal DGAC",
        ".TXT",
        30,
    ),
    "flight-request": (
        "Solicitud de vuelo (histórico)",
        "Solicitud de vuelo presentada",
        "Solicitud ya presentada ante la DGAC; no vence",
        "",
        40,
    ),
    "monthly-non-operation-notice": (
        "Aviso Mensual de No Operación",
        "Aviso mensual de no operación",
        "Se presenta a la DGAC el mes en que no hubo operación",
        "",
        50,
    ),
    "flight-log": (
        "Bitácora de vuelo (REG-015)",
        "Bitácora de vuelo",
        "Registro interno de cada vuelo realizado",
        "REG-015",
        10,
    ),
    "rpa-checklist": (
        "Check list RPA (LVE-003)",
        "Lista de chequeo RPA",
        "Verificación del RPA antes del vuelo",
        "LVE-003",
        20,
    ),
    "drone-inspection": (
        "Inspección de dron (LVE-002)",
        "Inspección de RPA",
        "Revisión del estado del RPA",
        "LVE-002",
        30,
    ),
    "incident-investigation-record": (
        "Registro de investigación de incidente",
        "Investigación de incidente",
        "Análisis de un incidente y de sus causas",
        "",
        40,
    ),
    "maintenance-certificate": (
        "Certificado de mantención",
        "Certificado de mantención",
        "Respalda una mantención realizada; no vence",
        "",
        10,
    ),
    "calibration-certificate": (
        "Certificado de calibración (GNSS/RTK/cámara)",
        "Certificado de calibración",
        "GNSS/RTK/cámara; la norma exige que esté vigente",
        "",
        20,
    ),
    "aoc-certificate": (
        "Certificado AOC",
        "Certificado AOC",
        "Documento único de la empresa; no se renueva",
        "",
        10,
    ),
    "company-procedure": (
        "Procedimiento o manual de la empresa",
        "Procedimiento o manual",
        "Procedimientos y manuales; se revisan por versión",
        "",
        20,
    ),
}


def apply_taxonomy(apps, schema_editor):
    DocumentType = apps.get_model("compliance", "DocumentType")
    for code, (old, new, description, reference, order) in TAXONOMY.items():
        row = DocumentType.objects.filter(code=code).first()
        if row is None:
            continue
        if row.name == old:
            row.name = new
        if not row.description:
            row.description = description
        if not row.reference_code:
            row.reference_code = reference
        if not row.sort_order:
            row.sort_order = order
        row.save(update_fields=["name", "description", "reference_code", "sort_order"])


def revert_names(apps, schema_editor):
    DocumentType = apps.get_model("compliance", "DocumentType")
    for code, (old, new, *_rest) in TAXONOMY.items():
        DocumentType.objects.filter(code=code, name=new).update(name=old)


class Migration(migrations.Migration):
    dependencies = [
        ("compliance", "0027_lv290_flight_log_txt_type"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="documenttype",
            options={
                "ordering": ["sort_order", "name"],
                "verbose_name": "document type",
                "verbose_name_plural": "document types",
            },
        ),
        migrations.AddField(
            model_name="documenttype",
            name="description",
            field=models.CharField(
                blank=True,
                help_text="One line saying what this document is for.",
                max_length=200,
                verbose_name="Description",
            ),
        ),
        migrations.AddField(
            model_name="documenttype",
            name="reference_code",
            field=models.CharField(
                blank=True,
                help_text="The code the paper carries, if any (for example REG-015).",
                max_length=20,
                verbose_name="Form code",
            ),
        ),
        migrations.AddField(
            model_name="documenttype",
            name="sort_order",
            field=models.PositiveSmallIntegerField(
                default=0,
                help_text="Orders the types inside their category; lower comes first.",
                verbose_name="Sort order",
            ),
        ),
        migrations.AlterField(
            model_name="documenttype",
            name="category",
            field=models.CharField(
                choices=[
                    ("personnel", "Personnel"),
                    ("aircraft", "Aircraft"),
                    ("dgac", "DGAC filings"),
                    ("operational", "Operational records"),
                    ("maintenance", "Maintenance and calibration"),
                    ("company", "Company"),
                    ("other", "Other"),
                ],
                default="other",
                help_text="Groups this type inside the document-type picker.",
                max_length=20,
                verbose_name="Category",
            ),
        ),
        migrations.RunPython(apply_taxonomy, revert_names),
    ]
