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
