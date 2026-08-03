"""Load the DGAC vigencias (LV-29) onto the registry fiches.

The dates come from the SIGO/DGAC screens the user captures: a *Vigencia*
per operator credential and a *Vigencia Seguro JAC* per aircraft. This command
writes those dates into `Operator.credential_expiry` / `Aircraft.insurance_expiry`.

Two input sources, checked in this order:
  * ``--file path.csv`` -- a CSV with the columns ``kind,key,expiry`` where
    ``kind`` is ``operator`` or ``aircraft``; ``key`` is the operator's DGAC
    credential (falling back to full name) or the aircraft registration; and
    ``expiry`` is an ISO date (YYYY-MM-DD). This is the path to use while the
    transcription is being verified -- it needs no code change.
  * the embedded ``EMBEDDED_VIGENCIAS`` table below, transcribed from the
    captures. It ships empty on purpose: the transcription (with its OCR risk)
    is filled in and verified against prod before it is trusted.

Idempotent: it only sets the two date fields, so a rerun with the same data is
a no-op. Unmatched keys are reported, never invented. ``--dry-run`` prints what
would change without saving.
"""

import csv
from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from apps.registry.models import Aircraft, Operator

# (kind, key, "YYYY-MM-DD"). Transcribed from the SIGO captures; empty until the
# transcription is verified. Prefer --file while validating against prod.
EMBEDDED_VIGENCIAS: list[tuple[str, str, str]] = []

VALID_KINDS = {"operator", "aircraft"}


class Command(BaseCommand):
    help = "Load DGAC credential / JAC insurance vigencias onto the registry fiches."

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            dest="file",
            help="CSV with columns kind,key,expiry (overrides the embedded table).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change without saving.",
        )

    def handle(self, *args, **options):
        rows = self._load_rows(options.get("file"))
        if not rows:
            self.stdout.write(
                self.style.WARNING(
                    "No vigencias to load. Pass --file, or fill EMBEDDED_VIGENCIAS "
                    "from the SIGO captures."
                )
            )
            return

        dry_run = options["dry_run"]
        updated = unchanged = 0
        unmatched = []
        for kind, key, expiry in rows:
            resolver = (
                self._apply_operator if kind == "operator" else self._apply_aircraft
            )
            outcome = resolver(key, expiry, dry_run)
            if outcome is None:
                unmatched.append(f"{kind}:{key}")
            elif outcome:
                updated += 1
            else:
                unchanged += 1

        for miss in unmatched:
            self.stdout.write(self.style.WARNING(f"  unmatched: {miss}"))
        self.stdout.write(
            self.style.SUCCESS(
                f"{'[dry-run] ' if dry_run else ''}"
                f"{updated} updated, {unchanged} already current, "
                f"{len(unmatched)} unmatched (of {len(rows)})."
            )
        )

    # -- input -----------------------------------------------------------------
    def _load_rows(self, path):
        raw = self._read_csv(path) if path else list(EMBEDDED_VIGENCIAS)
        rows = []
        for index, (kind, key, expiry) in enumerate(raw, start=1):
            kind = (kind or "").strip().lower()
            key = (key or "").strip()
            if kind not in VALID_KINDS:
                raise CommandError(f"Row {index}: unknown kind {kind!r}.")
            if not key:
                raise CommandError(f"Row {index}: empty key.")
            rows.append((kind, key, self._parse_date(expiry, index)))
        return rows

    @staticmethod
    def _read_csv(path):
        try:
            with open(path, newline="", encoding="utf-8-sig") as handle:
                reader = csv.DictReader(handle)
                missing = {"kind", "key", "expiry"} - set(reader.fieldnames or [])
                if missing:
                    raise CommandError(
                        f"CSV is missing column(s): {', '.join(sorted(missing))}."
                    )
                return [
                    (row["kind"], row["key"], row["expiry"]) for row in reader
                ]
        except FileNotFoundError as exc:
            raise CommandError(f"File not found: {path}") from exc

    @staticmethod
    def _parse_date(value, index):
        try:
            return date.fromisoformat((value or "").strip())
        except ValueError as exc:
            raise CommandError(
                f"Row {index}: {value!r} is not an ISO date (YYYY-MM-DD)."
            ) from exc

    # -- matching --------------------------------------------------------------
    def _apply_operator(self, key, expiry, dry_run):
        """Match by DGAC credential first, then full name. Returns True/False for
        changed/unchanged, or None when no (single) operator matches."""
        operator = (
            Operator.objects.filter(is_active=True)
            .filter(Q(dgac_credential__iexact=key) | Q(full_name__iexact=key))
            .order_by("dgac_credential")
            .first()
        )
        return self._set_field(operator, "credential_expiry", expiry, dry_run)

    def _apply_aircraft(self, key, expiry, dry_run):
        aircraft = Aircraft.objects.filter(
            is_active=True, registration__iexact=key
        ).first()
        return self._set_field(aircraft, "insurance_expiry", expiry, dry_run)

    @staticmethod
    def _set_field(instance, field, expiry, dry_run):
        if instance is None:
            return None
        if getattr(instance, field) == expiry:
            return False
        if not dry_run:
            setattr(instance, field, expiry)
            instance.save(update_fields=[field, "updated_at"])
        return True
