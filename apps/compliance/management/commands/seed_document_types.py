"""Seed the DocumentType catalog for a DGAC RPAS operation (LV-1).

Idempotent by `code` (get_or_create): safe to run more than once, and a rerun
after a name is edited in the UI leaves that edit alone -- it only fills in
codes that are still missing. See docs/compliance-setup.md.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.compliance.models import DocumentType

# (code, name, requires_expiry, is_insurance)
DOCUMENT_TYPES = [
    ("dgac-credential", "Credencial DGAC", True, False),
    ("medical-cert", "Certificado médico / aptitud", True, False),
    ("aircraft-registration", "Registro / matrícula de aeronave", True, False),
    ("airworthiness-cert", "Certificado de aeronavegabilidad", True, False),
    ("liability-insurance", "Seguro de responsabilidad civil", True, True),
    ("dgac-flight-permit", "Autorización DGAC (carta de permiso)", True, False),
]


class Command(BaseCommand):
    help = "Create the standard DocumentType catalog for a DGAC RPAS operation."

    @transaction.atomic
    def handle(self, *args, **options):
        created_count = 0
        for code, name, requires_expiry, is_insurance in DOCUMENT_TYPES:
            _obj, created = DocumentType.objects.get_or_create(
                code=code,
                defaults={
                    "name": name,
                    "requires_expiry": requires_expiry,
                    "is_insurance": is_insurance,
                },
            )
            created_count += int(created)
        self.stdout.write(
            self.style.SUCCESS(
                f"Ensured {len(DOCUMENT_TYPES)} document types "
                f"({created_count} created)."
            )
        )
