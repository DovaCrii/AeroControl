"""Report serials that are not upper-case, before normalizing them (X.4c).

ADR-0002 §2 settled that the cross key with AeroLink is the serial number,
normalized "mayúsculas, sin espacios". AeroControl only ever implemented the
whitespace half: `Aircraft.save()` and `Battery.save()` do `"".join(split())`
and leave case alone. AeroLink is about to implement the rule as written, and
then two things break **silently**:

- `sync_batteries` resolves `aircraft_serial` with an exact dict lookup, so an
  aircraft stored with any lower-case character stops linking. No error, just a
  battery that never finds its airframe.
- `Battery.objects.filter(serial_number=...)` is exact too, so a hand-entered
  battery would be *duplicated* rather than updated when the upper-cased serial
  arrives -- and `serial_number` is unique, so the create fails instead.

Run this **before** the migration that normalizes, and especially before the
first real sync. It only reads.

The collision check is the part that matters: two rows whose serials differ
only in case cannot both be upper-cased, because the column is unique. That
needs a human to decide which one is right (ADR-0002 §2: against the DGAC's
RPAS certificate, not against the app), so the migration refuses to guess.
"""

from django.core.management.base import BaseCommand

from apps.registry.models import Aircraft, Battery


class Command(BaseCommand):
    help = "Report serial numbers that are not upper-case, and any collisions."

    def handle(self, *args, **options):
        problems = 0
        for model, label in ((Aircraft, "Aircraft"), (Battery, "Battery")):
            problems += self._report(model, label)
        if problems:
            self.stdout.write(
                self.style.WARNING(
                    f"{problems} row(s) need attention before normalizing."
                )
            )
        else:
            self.stdout.write(self.style.SUCCESS("Every serial is already upper-case."))

    def _report(self, model, label):
        rows = [
            (obj.pk, obj.serial_number)
            for obj in model.objects.exclude(serial_number=None).exclude(
                serial_number=""
            )
        ]
        mixed = [(pk, serial) for pk, serial in rows if serial != serial.upper()]
        for pk, serial in mixed:
            self.stdout.write(f"  {label} {pk}: {serial!r} -> {serial.upper()!r}")

        # Collisions: rows that would land on the same value once upper-cased.
        # The column is unique, so these cannot both be normalized.
        by_upper = {}
        for pk, serial in rows:
            by_upper.setdefault(serial.upper(), []).append(serial)
        collisions = {
            upper: variants for upper, variants in by_upper.items() if len(variants) > 1
        }
        for upper, variants in collisions.items():
            self.stdout.write(
                self.style.ERROR(
                    f"  COLLISION {label} {upper!r}: {variants} -- resolve against "
                    f"the DGAC RPAS certificate before normalizing."
                )
            )

        self.stdout.write(
            f"{label}: {len(rows)} with a serial, {len(mixed)} not upper-case, "
            f"{len(collisions)} collision(s)."
        )
        return len(mixed) + len(collisions)
