"""Seed the QualificationType catalog (B4.3).

Families derived from the real fleet models (Mavic, Matrice, Elios, Wingtra…)
and the ratings operators already list in free text. Idempotent by `code`, so
a rerun after a name/keyword edit in the UI leaves that edit alone. See
docs/compliance-setup.md.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.registry.models import QualificationType

# (code, name, model_keywords)
QUALIFICATION_TYPES = [
    ("mavic", "Serie Mavic", "mavic"),
    ("matrice", "Serie Matrice", "matrice"),
    ("phantom", "Serie Phantom", "phantom"),
    ("wingtra", "Wingtra", "wingtra"),
    ("elios", "Flyability Elios", "elios"),
    ("autel-evo", "Autel EVO", "autel, evo"),
    ("ebee", "senseFly eBee", "ebee, sensefly"),
]


class Command(BaseCommand):
    help = "Create the standard QualificationType catalog for the fleet."

    @transaction.atomic
    def handle(self, *args, **options):
        created_count = 0
        for code, name, keywords in QUALIFICATION_TYPES:
            _obj, created = QualificationType.objects.get_or_create(
                code=code,
                defaults={"name": name, "model_keywords": keywords},
            )
            created_count += int(created)
        self.stdout.write(
            self.style.SUCCESS(
                f"Ensured {len(QUALIFICATION_TYPES)} qualification types "
                f"({created_count} created)."
            )
        )
