"""R4.1: pure classification logic for importing the `Z:` document
repository (`apps.compliance.management.commands.import_document_repository`
does the filesystem/database IO and calls into this module).

Deliberately no fuzzy matching anywhere here (R4.1a) -- attributing the wrong
DGAC certificate to an aircraft is worse than leaving a file for a human to
place by hand. Every ambiguous case comes back as a `REVIEW_*` status the
report can show and the importer refuses to `--apply` while any blocking
status remains (see `BLOCKING_STATUSES`).

Scope: the 16 `CC<code>-<serial>-<model>` aircraft folders only.
`DOCUMENTOS BASES` (AOC certificate, DAN regulations, procedures) is R4.6's
"company documents" repository, a different shape of problem (no aircraft to
attach to, DAN regulations must never become `Document` rows at all) -- the
importer does not walk that folder.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import PurePosixPath

# Status vocabulary matches the plan's own wording (R4.1/R4.1a/R4.4/R4.5) so
# the CLI report reads the same as the audit that specified it.
OK = "OK"
ALREADY_IMPORTED = "ALREADY-IMPORTED"
SKIP_FORMAT = "SKIP-FORMAT"
REVIEW_SENSITIVE = "REVIEW-SENSITIVE"
NEEDS_ANTIVIRUS_GATE = "NEEDS-ANTIVIRUS-GATE"
REVIEW_NEEDS_ANTIVIRUS = "REVIEW-NEEDS-ANTIVIRUS"
REVIEW_NO_MATCH = "REVIEW-NO-MATCH"
REVIEW_UNKNOWN_SUBFOLDER = "REVIEW-UNKNOWN-SUBFOLDER"

# R4.5 (decided 2026-08-07): PII stays in Z:/Nextcloud, never becomes a
# Document -- not even with --apply. This is a *resolved* decision, not a
# pending one, so REVIEW_SENSITIVE does not block --apply the way the other
# REVIEW_* statuses do (see BLOCKING_STATUSES below). Matched as whole words
# against the filename, accent-insensitive, so "escritura" cannot false-hit
# on an unrelated word that merely contains the substring. Singular and
# plural listed explicitly (no stemming) -- the real repository has
# "Transferencias de Fondos de <name>.msg", plural.
SENSITIVE_KEYWORDS = (
    "cedula",
    "cedulas",
    "rut",
    "ruts",
    "comprobante",
    "comprobantes",
    "transferencia",
    "transferencias",
    "escritura",
    "escrituras",
    "notarial",
    "notariales",
)

# R4.4: KMZ has a first-class home in geo.GeoPlan already; a RAR/ZIP defeats
# the point of "giving the repository order" (nothing inside it becomes a
# reviewable Document). Never imported, never blocks --apply.
SKIPPED_FORMAT_SUFFIXES = {".rar", ".zip", ".kmz"}

# Statuses that represent a pending human decision -- import must refuse
# --apply while any of these remain, per R4.1. REVIEW_SENSITIVE is excluded
# on purpose (see the comment on SENSITIVE_KEYWORDS above): the decision
# there is already made, permanently, by policy -- not something a rerun of
# the importer, or a human, is expected to resolve into an import.
BLOCKING_STATUSES = {REVIEW_NEEDS_ANTIVIRUS, REVIEW_NO_MATCH, REVIEW_UNKNOWN_SUBFOLDER}

# The 5 fixed subfolders (LV/R4 audit) -- matched by their leading "NN.-"
# number, not the full name: production has both "04.- Mantenciones" and
# "04.- Mantención" (singular) for the same slot.
SUBFOLDER_PREFIX_RE = re.compile(r"^(\d{2})\.-")

# maintenance-certificate matches R4.8's own naming (pulled forward here
# because the importer cannot classify anything under "04.-" without it).
# flight-request and incident-investigation-record are new -- proposed here,
# not yet validated with the user; see MASTER_PLAN.md R4.1.
SUBFOLDER_DOC_TYPES = {
    "01": "aircraft-registration",
    "02": "flight-request",
    "03": "incident-investigation-record",
    "04": "maintenance-certificate",
    "05": "liability-insurance",
}

NEW_DOCUMENT_TYPE_CODES = frozenset(
    {"flight-request", "incident-investigation-record", "maintenance-certificate"}
)


def _strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def is_sensitive_filename(filename: str) -> bool:
    """R4.5: PII detection by filename, e.g. "Transferencias de Fondos de
    <name>.msg", "04 Cedula de identidad ....pdf", "Escritura publica
    poderes.pdf". Whole-word match only, so short keywords like "rut" cannot
    false-hit on a filename that merely contains the letters."""
    normalized = _strip_accents(filename).lower()
    return any(
        re.search(rf"\b{re.escape(keyword)}\b", normalized)
        for keyword in SENSITIVE_KEYWORDS
    )


def classify_file_format(filename: str) -> str:
    """Format-only classification (R4.4/R4.5), independent of which aircraft
    the file belongs to. Returns one of OK, SKIP_FORMAT, REVIEW_SENSITIVE, or
    NEEDS_ANTIVIRUS_GATE (the caller must resolve this last one against
    whether an antivirus command is actually configured -- that is an IO/
    settings concern this pure function does not have)."""
    suffix = PurePosixPath(filename).suffix.lower()
    if suffix in SKIPPED_FORMAT_SUFFIXES:
        return SKIP_FORMAT
    if is_sensitive_filename(filename):
        return REVIEW_SENSITIVE
    if suffix == ".msg":
        return NEEDS_ANTIVIRUS_GATE
    return OK


def subfolder_doc_type_code(subfolder_name: str) -> str | None:
    match = SUBFOLDER_PREFIX_RE.match(subfolder_name)
    if not match:
        return None
    return SUBFOLDER_DOC_TYPES.get(match.group(1))


def parse_aircraft_folder_name(name: str) -> tuple[str, str, str] | None:
    """Split "CC633-1581F5FHC245700D181D-M3E" into (cc_code, serial, model).

    Exactly 2 splits (`str.split("-", 2)`): the model segment may itself
    contain a space ("M3E RTK", "M3E Revisión") but never another dash in
    the 17 real folder names surveyed 2026-08-10.
    """
    parts = name.split("-", 2)
    if len(parts) != 3:
        return None
    cc_code, serial, model = (part.strip() for part in parts)
    if not cc_code.upper().startswith("CC") or not serial or not model:
        return None
    return cc_code, serial, model


@dataclass(frozen=True)
class AircraftRef:
    """The minimal slice of `registry.Aircraft` the matcher needs -- kept
    separate from the real model so this module stays importable and
    testable without Django's app registry / a database."""

    id: str
    registration: str
    serial_number: str
    cost_center_code: str


@dataclass(frozen=True)
class AircraftFolderMatch:
    folder_name: str
    cc_code: str
    serial: str
    model: str
    aircraft: AircraftRef | None
    status: str  # OK (matched) or REVIEW_NO_MATCH
    # Set only on an unmatched folder when exactly one *other* unmatched
    # aircraft shares the folder's cost center -- a hint for the human
    # deciding by hand, never auto-applied (R4.1a).
    hint: str | None = field(default=None)


def match_aircraft_folders(
    folder_names: list[str], known_aircraft: list[AircraftRef]
) -> list[AircraftFolderMatch]:
    """Exact match only, by `serial_number` -- never Levenshtein, never an
    O/0 or 1/l substitution (R4.1a: misattributing a DGAC certificate is
    worse than a manual fix). The cost-center prefix in the folder name is
    informational only, not part of the match key: it can legitimately
    differ from the aircraft's current `cost_center` (verified in
    production for RPA-2019, CC110 in the app vs the CC717 folder) without
    that making the serial match wrong.
    """
    by_serial = {aircraft.serial_number: aircraft for aircraft in known_aircraft}
    results: list[AircraftFolderMatch] = []
    parsed: list[tuple[str, str, str, str]] = []
    for folder_name in folder_names:
        parsed_name = parse_aircraft_folder_name(folder_name)
        if parsed_name is None:
            continue
        cc_code, serial, model = parsed_name
        parsed.append((folder_name, cc_code, serial, model))

    matched_aircraft_ids = {
        by_serial[serial].id for _, _, serial, _ in parsed if serial in by_serial
    }
    unmatched_aircraft_by_cc: dict[str, list[AircraftRef]] = {}
    for aircraft in known_aircraft:
        if aircraft.id not in matched_aircraft_ids:
            unmatched_aircraft_by_cc.setdefault(aircraft.cost_center_code, []).append(
                aircraft
            )

    for folder_name, cc_code, serial, model in parsed:
        aircraft = by_serial.get(serial)
        if aircraft is not None:
            results.append(
                AircraftFolderMatch(
                    folder_name, cc_code, serial, model, aircraft, OK, None
                )
            )
            continue
        candidates = unmatched_aircraft_by_cc.get(cc_code, [])
        hint = f"near:{candidates[0].registration}" if len(candidates) == 1 else None
        results.append(
            AircraftFolderMatch(
                folder_name, cc_code, serial, model, None, REVIEW_NO_MATCH, hint
            )
        )
    return results
