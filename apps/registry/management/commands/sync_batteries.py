"""X.4b: mirror AeroLink's battery inventory into `registry.Battery`.

ADR-0002 assigns battery inventory to AeroLink and leaves this table as the
mirror, so the ISO 7.1.3 evidence (cycles, health, firmware) sits next to the
aircraft and the maintenance history where an auditor already looks. Until this
ran, `Battery` was empty on purpose.

Matched by `serial_number`, the join key ADR-0002 §2 settled on: it is what DJI
reports and the only value both systems can agree on. Normalized the same way
`Battery.save()` does, so a serial typed by a human and one arriving from
telemetry compare equal.

**Never deletes.** A battery missing from one response is far more likely to be
a partial answer than a battery that ceased to exist, and deleting it would
take its cycle history with it. Missing serials are reported instead.

`--from-file` reads a JSON file with the same shape as the endpoint, which is
what makes this testable end to end **before AeroLink exposes anything**: the
contract is in apps/registry/aerolink.py and in ADR-0002.
"""

import logging
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.core.jobs import record_job_run
from apps.registry.aerolink import (
    AeroLinkUnavailable,
    fetch_batteries,
    parse_batteries,
)
from apps.registry.models import Aircraft, Battery

logger = logging.getLogger("aerocontrol.aerolink")


class Command(BaseCommand):
    help = "Mirror AeroLink's battery inventory into the local Battery table."

    def add_arguments(self, parser):
        parser.add_argument(
            "--from-file",
            help=(
                "Read the payload from a JSON file instead of the gateway "
                "(same shape as the endpoint)."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change without writing anything.",
        )

    def handle(self, *args, **options):
        payload = self._load(options)
        dry_run = options["dry_run"]
        with record_job_run("sync_batteries") as run:
            created, updated, skipped, missing = self._sync(payload, dry_run)
            run["summary"] = (
                f"{'[dry-run] ' if dry_run else ''}{created} created, "
                f"{updated} updated, {skipped} skipped, "
                f"{len(missing)} not in the feed"
            )
        self.stdout.write(
            self.style.SUCCESS(
                f"{'[dry-run] ' if dry_run else ''}{created} created, "
                f"{updated} updated, {skipped} skipped."
            )
        )
        if missing:
            # Not an error: a partial feed is likelier than a vanished battery.
            # Said out loud so a shrinking inventory is noticed rather than
            # discovered months later.
            self.stdout.write(
                self.style.WARNING(
                    f"{len(missing)} local battery(ies) were not in this feed: "
                    f"{', '.join(sorted(missing)[:10])}"
                )
            )

    def _load(self, options):
        path = options.get("from_file")
        if path:
            file_path = Path(path)
            if not file_path.exists():
                raise CommandError(f"No such file: {path}")
            return parse_batteries(file_path.read_bytes())
        try:
            return fetch_batteries()
        except AeroLinkUnavailable as exc:
            # Loudly, not as "0 batteries": an empty inventory and an
            # unreachable gateway must not look the same in the job log.
            raise CommandError(f"AeroLink unavailable: {exc}") from exc

    def _sync(self, payload, dry_run):
        created = updated = skipped = 0
        seen = set()
        aircraft_by_serial = {
            serial: pk
            for pk, serial in Aircraft.objects.exclude(serial_number=None)
            .exclude(serial_number="")
            .values_list("pk", "serial_number")
        }

        for entry in payload:
            serial = "".join(str(entry.get("serial_number") or "").split())
            if not serial:
                # A battery with no serial cannot be matched to anything, now
                # or later. Counting it as skipped beats inventing a key.
                skipped += 1
                continue
            seen.add(serial)
            fields = self._fields_from(entry, aircraft_by_serial)
            existing = Battery.objects.filter(serial_number=serial).first()
            if existing is None:
                created += 1
                if not dry_run:
                    Battery.objects.create(serial_number=serial, **fields)
                continue
            if not dry_run:
                for name, value in fields.items():
                    setattr(existing, name, value)
                existing.save()
            updated += 1

        missing = (
            set(
                Battery.objects.filter(is_active=True).values_list(
                    "serial_number", flat=True
                )
            )
            - seen
        )
        return created, updated, skipped, missing

    def _fields_from(self, entry, aircraft_by_serial):
        fields = {
            "source": Battery.SOURCE_AEROLINK,
            "synced_at": timezone.now(),
        }
        # Only what the feed actually carries is written. An absent key means
        # "AeroLink did not say", which is different from "AeroLink said zero"
        # -- overwriting a known cycle count with 0 because a field was omitted
        # would destroy the very evidence this table exists for.
        if entry.get("model"):
            fields["model"] = str(entry["model"])[:100]
        if entry.get("firmware_version"):
            fields["firmware_version"] = str(entry["firmware_version"])[:50]
        if entry.get("status") in dict(Battery.STATUS_CHOICES):
            fields["status"] = entry["status"]
        cycles = entry.get("cycle_count")
        if isinstance(cycles, int) and cycles >= 0:
            fields["cycle_count"] = cycles
        health = entry.get("health_percent")
        if isinstance(health, int) and 0 <= health <= 100:
            fields["health_percent"] = health
        aircraft_serial = "".join(str(entry.get("aircraft_serial") or "").split())
        if aircraft_serial and aircraft_serial in aircraft_by_serial:
            fields["aircraft_id"] = aircraft_by_serial[aircraft_serial]
        return fields
