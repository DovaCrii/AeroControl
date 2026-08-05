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

# (kind, key, "YYYY-MM-DD"). Transcribed from the SIGO captures (2026-08-03,
# J.E.J. Ingeniería). Aircraft key = registration "RPA-<N° inscripción DGAC>";
# operator key = DGAC credential number. OCR risk: verify with --dry-run against
# prod (it reports unmatched keys) before the real run.
EMBEDDED_VIGENCIAS: list[tuple[str, str, str]] = [
    # ── Aeronaves RPA · Vigencia Seguro JAC ──
    ("aircraft", "RPA-4884", "2027-01-23"),
    ("aircraft", "RPA-4401", "2026-09-05"),
    ("aircraft", "RPA-2883", "2026-04-16"),
    ("aircraft", "RPA-4436", "2026-09-05"),
    ("aircraft", "RPA-2455", "2025-09-09"),
    ("aircraft", "RPA-2116", "2026-01-30"),
    ("aircraft", "RPA-4025", "2027-05-28"),
    ("aircraft", "RPA-3755", "2027-01-12"),
    ("aircraft", "RPA-2750", "2027-02-06"),
    ("aircraft", "RPA-6691", "2027-07-23"),
    ("aircraft", "RPA-3696", "2026-12-21"),
    ("aircraft", "RPA-6396", "2027-04-10"),
    ("aircraft", "RPA-4883", "2027-07-23"),
    ("aircraft", "RPA-2198", "2026-05-20"),
    ("aircraft", "RPA-5532", "2026-08-08"),
    ("aircraft", "RPA-5534", "2026-08-08"),
    ("aircraft", "RPA-4647", "2026-11-20"),
    # ── Personal Operativo · Vigencia credencial DGAC ──
    ("operator", "5365", "2027-12-04"),
    ("operator", "5173", "2027-10-14"),
    ("operator", "15324", "2027-06-03"),
    ("operator", "15532", "2027-06-19"),
    ("operator", "8476", "2027-06-16"),
    ("operator", "8516", "2027-06-04"),
    ("operator", "16858", "2027-11-04"),
    ("operator", "14057", "2028-04-07"),
    ("operator", "4303", "2025-05-02"),
    ("operator", "8172", "2027-12-05"),
    ("operator", "9049", "2027-07-19"),
    ("operator", "16945", "2027-11-11"),
    ("operator", "14825", "2025-04-08"),
    ("operator", "12431", "2028-05-23"),
    ("operator", "769", "2027-06-03"),
    ("operator", "4350", "2027-08-30"),
    ("operator", "13175", "2028-01-30"),
    ("operator", "7561", "2027-11-28"),
    ("operator", "6439", "2027-12-12"),
    ("operator", "1138", "2028-02-28"),
    ("operator", "11306", "2028-10-20"),
    ("operator", "3079", "2027-11-04"),
    ("operator", "11227", "2028-10-27"),
    ("operator", "7953", "2027-12-11"),
    ("operator", "4126", "2028-06-09"),
    ("operator", "2985", "2027-09-03"),
    ("operator", "8918", "2027-06-24"),
    ("operator", "8345", "2028-07-04"),
    ("operator", "12617", "2027-10-30"),
    ("operator", "17221", "2027-12-04"),
    ("operator", "6428", "2027-10-16"),
    ("operator", "16790", "2027-10-29"),
    ("operator", "8766", "2027-08-19"),
    ("operator", "11678", "2028-01-29"),
    ("operator", "8322", "2028-07-24"),
    ("operator", "20660", "2028-10-03"),
    ("operator", "8220", "2028-01-24"),
    ("operator", "3405", "2027-06-10"),
    ("operator", "7995", "2028-02-14"),
    ("operator", "15581", "2027-06-26"),
    ("operator", "5956", "2027-11-13"),
    ("operator", "2894", "2028-01-08"),
    ("operator", "11489", "2028-06-02"),
    ("operator", "19717", "2028-07-28"),
    ("operator", "20516", "2028-09-30"),
    ("operator", "14923", "2028-03-26"),
    ("operator", "5102", "2027-12-02"),
    ("operator", "17181", "2027-12-02"),
    ("operator", "11446", "2028-01-22"),
    ("operator", "15316", "2027-05-30"),
    ("operator", "8718", "2028-06-09"),
    ("operator", "1619", "2027-10-15"),
    ("operator", "4677", "2027-12-06"),
    ("operator", "11447", "2025-02-06"),
    ("operator", "6788", "2025-01-04"),
]

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
                return [(row["kind"], row["key"], row["expiry"]) for row in reader]
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
