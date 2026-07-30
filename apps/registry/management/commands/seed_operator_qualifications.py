"""Populate operator qualifications from the free-text `authorizations` field.

Each operator's `authorizations` (e.g. "Matrice 300 Rtk/ 210 Rtk/ 600 - Mavic 3
- Phantom4") is matched against the QualificationType catalog by
`model_keywords`, creating one Qualification per recognized model family. An
operator commonly has several. No issue/expiry date is set (LV-12a).

Idempotent: skips a (operator, type) pair that already exists. Reports the
operators whose authorizations matched nothing so the catalog can be extended
(models like "Mini" or a bare "DJI" are not covered yet). Re-run after editing
the catalog or importing operators.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.registry.models import Operator, Qualification, QualificationType


class Command(BaseCommand):
    help = "Create operator qualifications from Operator.authorizations text."

    @transaction.atomic
    def handle(self, *args, **options):
        types = list(QualificationType.objects.filter(is_active=True))
        if not types:
            self.stdout.write(
                self.style.WARNING(
                    "No qualification types. Run seed_qualification_types first."
                )
            )
            return

        created = 0
        unmatched = []
        for operator in Operator.objects.filter(is_active=True):
            text = (operator.authorizations or "").lower()
            if not text.strip():
                continue
            matched = [
                qt for qt in types if any(kw in text for kw in qt.keyword_list())
            ]
            if not matched:
                unmatched.append((operator.full_name, operator.authorizations))
                continue
            for qt in matched:
                _obj, was_created = Qualification.objects.get_or_create(
                    operator=operator,
                    qualification_type=qt,
                    defaults={"issue_date": None, "expiry_date": None},
                )
                created += int(was_created)

        self.stdout.write(self.style.SUCCESS(f"Created {created} qualifications."))
        if unmatched:
            self.stdout.write(
                self.style.WARNING(
                    f"{len(unmatched)} operators matched no catalog type "
                    "(extend the catalog and re-run):"
                )
            )
            for name, authorizations in unmatched:
                self.stdout.write(f"  - {name}: {authorizations}")
