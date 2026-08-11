"""Seed the DocumentType catalog for a DGAC RPAS operation (LV-1).

Idempotent by `code` (get_or_create): safe to run more than once, and a rerun
after a name is edited in the UI leaves that edit alone -- it only fills in
codes that are still missing. See docs/compliance-setup.md.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.compliance.models import DocumentType

# (code, name, requires_expiry, is_insurance, is_operational_record)
DOCUMENT_TYPES = [
    ("dgac-credential", "Credencial DGAC", True, False, False),
    ("medical-cert", "Certificado médico / aptitud", True, False, False),
    ("aircraft-registration", "Registro / matrícula de aeronave", True, False, False),
    ("airworthiness-cert", "Certificado de aeronavegabilidad", True, False, False),
    ("liability-insurance", "Seguro de responsabilidad civil", True, True, False),
    ("dgac-flight-permit", "Autorización DGAC (carta de permiso)", True, False, False),
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
    ),
    # LV-30: the per-flight operational records. They do not expire (a record of
    # what happened, not a validity), so requires_expiry=False.
    ("flight-log", "Bitácora de vuelo (REG-015)", False, False, True),
    ("rpa-checklist", "Check list RPA (LVE-003)", False, False, True),
    ("drone-inspection", "Inspección de dron (LVE-002)", False, False, True),
    # R4.1/R4.8: pulled forward from R4.8 because import_document_repository
    # cannot classify anything under the Z: repository's "02.-"/"03.-"/"04.-"
    # subfolders without them. Historical records, not validities that lapse
    # -- requires_expiry=False, same reasoning as the flight-log group above.
    ("flight-request", "Solicitud de vuelo (histórico)", False, False, False),
    (
        "incident-investigation-record",
        "Registro de investigación de incidente",
        False,
        False,
        False,
    ),
    ("maintenance-certificate", "Certificado de mantención", False, False, False),
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
    ),
    # R4.6/R4.8: the remaining company-wide document types the new "Documentos
    # de la empresa" repository needs to actually be usable -- without these,
    # nobody could classify an AOC or a procedure upload there at all.
    # aoc-certificate: confirmed with the user 2026-08-11 -- unlike a DGAC
    # credential or an insurance policy, the AOC is a single internal
    # document that is not periodically renewed/re-uploaded.
    # requires_expiry=False, same reasoning as company-procedure below (a
    # static reference document, not a vigencia to watch).
    ("aoc-certificate", "Certificado AOC", False, False, False),
    # company-procedure: manuals and procedures (e.g. the flyaway/emergency
    # response procedure ISO 45001 8.2 asks for). Revised through
    # is_current_version, not a vigencia -- same reasoning as
    # maintenance-certificate above.
    ("company-procedure", "Procedimiento o manual de la empresa", False, False, False),
    # monthly-non-operation-notice: the DGAC filing for a month with no RPAS
    # activity. A historical record of what (did not) happen, not a validity.
    (
        "monthly-non-operation-notice",
        "Aviso Mensual de No Operación",
        False,
        False,
        False,
    ),
]


class Command(BaseCommand):
    help = "Create the standard DocumentType catalog for a DGAC RPAS operation."

    @transaction.atomic
    def handle(self, *args, **options):
        created_count = 0
        for code, name, requires_expiry, is_insurance, is_op_record in DOCUMENT_TYPES:
            _obj, created = DocumentType.objects.get_or_create(
                code=code,
                defaults={
                    "name": name,
                    "requires_expiry": requires_expiry,
                    "is_insurance": is_insurance,
                    "is_operational_record": is_op_record,
                },
            )
            created_count += int(created)
        self.stdout.write(
            self.style.SUCCESS(
                f"Ensured {len(DOCUMENT_TYPES)} document types "
                f"({created_count} created)."
            )
        )
