"""R3.1a: read-only evidence-gathering step, required before R3.1 writes any
migration. Lists every distinct `purpose` value actually in use, per model,
with a proposed closed-vocabulary code -- or `other` when nothing in
apps.core.choices.PURPOSE_LEGACY_MAP matches exactly.

Deliberately no fuzzy matching: "Audiovisual" (a real value found in
production) does not say which of the two SIGO procedures produced it, and
guessing wrong here corrupts a field that ends up in calendar titles. Run
against the real restored backup 2026-08-10: only 3 rows had a value, and
every one of them mixed more than one concept ("Fotogrametría - Fotos -
Videos"), which is why the map only trusts exact, single-concept matches.
"""

from collections import Counter

from django.core.management.base import BaseCommand

from apps.core.choices import PURPOSE_LEGACY_MAP
from apps.operations.models import FlightPermission
from apps.registry.models import AircraftAssignment, Assignment, OperatorAssignment


class Command(BaseCommand):
    help = (
        "R3.1a: report every distinct `purpose` value in use, per model, "
        "with a proposed closed-vocabulary code. Read-only -- writes "
        "nothing. Run this and freeze its output before writing R3.1's "
        "migration."
    )

    def handle(self, *args, **options):
        sources = (
            (
                "operations.FlightPermission",
                FlightPermission.objects.values_list("purpose", flat=True),
            ),
            (
                "registry.Assignment",
                Assignment.objects.values_list("purpose", flat=True),
            ),
            (
                "registry.OperatorAssignment",
                OperatorAssignment.objects.values_list("purpose", flat=True),
            ),
            (
                "registry.AircraftAssignment",
                AircraftAssignment.objects.values_list("purpose", flat=True),
            ),
        )
        unclassified_total = 0
        for label, values in sources:
            counts = Counter(value for value in values if value)
            self.stdout.write(f"{label}:")
            if not counts:
                self.stdout.write("  (sin datos)")
                continue
            for value, count in sorted(counts.items(), key=lambda item: -item[1]):
                code = PURPOSE_LEGACY_MAP.get(value.strip().lower())
                if code:
                    self.stdout.write(f"  {count:>3}x  {value!r} -> {code}")
                else:
                    unclassified_total += count
                    self.stdout.write(
                        f"  {count:>3}x  {value!r} -> other "
                        "(sin match exacto en PURPOSE_LEGACY_MAP, queda como "
                        "detalle libre)"
                    )
        self.stdout.write(
            "\nFilas sin match exacto (irían a 'other' salvo que se "
            f"confirme lo contrario): {unclassified_total}"
        )
