"""Seed the DocumentType catalog for a DGAC RPAS operation (LV-1).

Idempotent by `code` (get_or_create): safe to run more than once, and a rerun
after a name is edited in the UI leaves that edit alone -- it only fills in
codes that are still missing. See docs/compliance-setup.md.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.compliance.models import DocumentType

# LV-95: the category is part of the catalog definition, not an afterthought --
# a type seeded without one lands under "Other", which is exactly what the
# grouping exists to avoid. `test_the_seeded_catalog_leaves_nothing_under_other`
# (test_lv94_lv95_upload_form.py) fails if any row here leaves it at the default.
PERSONNEL = DocumentType.CATEGORY_PERSONNEL
AIRCRAFT = DocumentType.CATEGORY_AIRCRAFT
DGAC = DocumentType.CATEGORY_DGAC
OPERATIONAL = DocumentType.CATEGORY_OPERATIONAL
MAINTENANCE = DocumentType.CATEGORY_MAINTENANCE
COMPANY = DocumentType.CATEGORY_COMPANY

# (code, name, requires_expiry, is_insurance, is_operational_record, category)
DOCUMENT_TYPES = [
    ("dgac-credential", "Credencial DGAC", True, False, False, PERSONNEL),
    ("medical-cert", "Certificado médico / aptitud", True, False, False, PERSONNEL),
    (
        "aircraft-registration",
        "Registro / matrícula de aeronave",
        True,
        False,
        False,
        AIRCRAFT,
    ),
    (
        "airworthiness-cert",
        "Certificado de aeronavegabilidad",
        True,
        False,
        False,
        AIRCRAFT,
    ),
    (
        "liability-insurance",
        "Seguro de responsabilidad civil",
        True,
        True,
        False,
        AIRCRAFT,
    ),
    # LV-117: la Resolución Exenta con que la **JAC** aprueba el seguro RPA --
    # el papel que cierra el ciclo que `Aircraft.insurance_status` modela
    # (`filed` -> `active`). No existía tipo para él, así que el respaldo de una
    # aeronave autorizada no tenía dónde vivir: la póliza y su certificado se
    # cargaban como `liability-insurance` y la resolución que los aprueba, en
    # ninguna parte.
    #
    # Va en AIRCRAFT y no en DGAC a propósito: la JAC no es la DGAC (esa
    # categoría es de presentaciones y autorizaciones DGAC), y quien busca este
    # papel lo busca junto al seguro de la aeronave, que es de lo que habla.
    #
    # requires_expiry=True -- la resolución trae "TÉRMINO DE VIGENCIA" y caduca
    # con la póliza que aprueba. is_insurance=False: esa bandera pinta la
    # columna de seguro de la lista de aeronaves, y desde LV-29 la fecha
    # canónica es `Aircraft.insurance_expiry`; marcar un segundo tipo pondría
    # dos documentos compitiendo por la misma columna (gana el que venza antes).
    (
        "jac-insurance-approval",
        "Resolución Exenta JAC (aprueba seguro RPA)",
        True,
        False,
        False,
        AIRCRAFT,
    ),
    (
        "dgac-flight-permit",
        "Autorización DGAC (carta de permiso)",
        True,
        False,
        False,
        DGAC,
    ),
    # LV-64: two distinct real documents, not one -- the letter above is what
    # goes *to* the DGAC as part of the request; this is what comes *back*,
    # signed and folio'd, once the DGAC actually approves the operation
    # ("Autorización de Operación RPA" in the DGAC's own wording). Approving a
    # permission in the app now requires this one (see
    # FlightPermissionApprove), not the letter -- only the signed
    # authorization actually certifies DGAC approval.
    (
        "dgac-rpa-operation-authorization",
        "Autorización de Operación RPA (DGAC aprobada)",
        True,
        False,
        False,
        DGAC,
    ),
    # LV-30: the per-flight operational records. They do not expire (a record of
    # what happened, not a validity), so requires_expiry=False.
    ("flight-log", "Bitácora de vuelo (REG-015)", False, False, True, OPERATIONAL),
    ("rpa-checklist", "Check list RPA (LVE-003)", False, False, True, OPERATIONAL),
    (
        "drone-inspection",
        "Inspección de dron (LVE-002)",
        False,
        False,
        True,
        OPERATIONAL,
    ),
    # R4.1/R4.8: pulled forward from R4.8 because import_document_repository
    # cannot classify anything under the Z: repository's "02.-"/"03.-"/"04.-"
    # subfolders without them. Historical records, not validities that lapse
    # -- requires_expiry=False, same reasoning as the flight-log group above.
    ("flight-request", "Solicitud de vuelo (histórico)", False, False, False, DGAC),
    (
        "incident-investigation-record",
        "Registro de investigación de incidente",
        False,
        False,
        False,
        OPERATIONAL,
    ),
    (
        "maintenance-certificate",
        "Certificado de mantención",
        False,
        False,
        False,
        MAINTENANCE,
    ),
    # R7.3 (ISO 7.1.5): GNSS/RTK and camera calibration certificates. A real
    # "Certificado Calibración.pdf" already sits in Z:\CC706-...\04.- Mantenciones
    # waiting for a place to live. requires_expiry=True -- unlike
    # maintenance-certificate above, ISO 7.1.5 asks for a *vigente* one, so a
    # lapsed calibration should watch and alert like airworthiness-cert does.
    (
        "calibration-certificate",
        "Certificado de calibración (GNSS/RTK/cámara)",
        True,
        False,
        False,
        MAINTENANCE,
    ),
    # R4.6/R4.8: the remaining company-wide document types the new "Documentos
    # de la empresa" repository needs to actually be usable -- without these,
    # nobody could classify an AOC or a procedure upload there at all.
    # aoc-certificate: confirmed with the user 2026-08-11 -- unlike a DGAC
    # credential or an insurance policy, the AOC is a single internal
    # document that is not periodically renewed/re-uploaded.
    # requires_expiry=False, same reasoning as company-procedure below (a
    # static reference document, not a vigencia to watch).
    ("aoc-certificate", "Certificado AOC", False, False, False, COMPANY),
    # company-procedure: manuals and procedures (e.g. the flyaway/emergency
    # response procedure ISO 45001 8.2 asks for). Revised through
    # is_current_version, not a vigencia -- same reasoning as
    # maintenance-certificate above.
    (
        "company-procedure",
        "Procedimiento o manual de la empresa",
        False,
        False,
        False,
        COMPANY,
    ),
    # monthly-non-operation-notice: the DGAC filing for a month with no RPAS
    # activity. A historical record of what (did not) happen, not a validity.
    (
        "monthly-non-operation-notice",
        "Aviso Mensual de No Operación",
        False,
        False,
        False,
        DGAC,
    ),
]


class Command(BaseCommand):
    help = "Create the standard DocumentType catalog for a DGAC RPAS operation."

    @transaction.atomic
    def handle(self, *args, **options):
        created_count = 0
        for (
            code,
            name,
            requires_expiry,
            is_insurance,
            is_op_record,
            category,
        ) in DOCUMENT_TYPES:
            _obj, created = DocumentType.objects.get_or_create(
                code=code,
                defaults={
                    "name": name,
                    "requires_expiry": requires_expiry,
                    "is_insurance": is_insurance,
                    "is_operational_record": is_op_record,
                    "category": category,
                },
            )
            created_count += int(created)
        self.stdout.write(
            self.style.SUCCESS(
                f"Ensured {len(DOCUMENT_TYPES)} document types "
                f"({created_count} created)."
            )
        )
