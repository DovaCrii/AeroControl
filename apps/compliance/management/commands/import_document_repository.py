"""R4.1: report (default) or --apply the Z: aircraft document repository.

See apps/compliance/repository_import.py for the classification rules
(matching, formats, PII) and apps/compliance/test_r4_repository_import.py
for its filesystem-free tests. Scope: the 16 CC<code>-<serial>-<model>
aircraft folders only -- "DOCUMENTOS BASES" is R4.6's separate problem (no
aircraft to attach to, and DAN regulations must never become Document rows).

Always run this locally against a restored backup copy first -- p340
cannot see the Z: drive (decided 2026-08-07, see MASTER_PLAN.md R4).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.compliance.models import Document, DocumentType, document_upload_path
from apps.compliance.repository_import import (
    ALREADY_IMPORTED,
    BLOCKING_STATUSES,
    NEEDS_ANTIVIRUS_GATE,
    OK,
    REVIEW_NEEDS_ANTIVIRUS,
    REVIEW_NO_MATCH,
    REVIEW_UNKNOWN_SUBFOLDER,
    AircraftRef,
    classify_file_format,
    match_aircraft_folders,
    subfolder_doc_type_code,
)
from apps.compliance.security import scan_uploaded_file
from apps.compliance.storage import get_document_storage
from apps.registry.models import Aircraft

EXCLUDED_TOP_LEVEL = {"DOCUMENTOS BASES"}
REVIEW_CONTENT_CHANGED = "REVIEW-CONTENT-CHANGED"
REVIEW_ANTIVIRUS_REJECTED = "REVIEW-ANTIVIRUS-REJECTED"
# BLOCKING_STATUSES (repository_import.py) covers only the statuses that
# module can produce on its own; these two are specific to this command
# (idempotency and the antivirus scan outcome) and block --apply the same way.
LOCAL_BLOCKING_STATUSES = BLOCKING_STATUSES | {
    REVIEW_CONTENT_CHANGED,
    REVIEW_ANTIVIRUS_REJECTED,
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class _PathAsUpload:
    """Adapts a real file path to the interface scan_uploaded_file() expects
    (a Django UploadedFile: .name, .tell(), .seek(), .chunks()) so the
    importer reuses the exact same antivirus gate the web upload form uses,
    instead of a second implementation of it."""

    def __init__(self, path: Path):
        self.name = path.name
        self._file = path.open("rb")

    def tell(self):
        return self._file.tell()

    def seek(self, position):
        self._file.seek(position)

    def chunks(self, chunk_size=1024 * 1024):
        while True:
            data = self._file.read(chunk_size)
            if not data:
                break
            yield data

    def close(self):
        self._file.close()


@dataclass
class FileDecision:
    aircraft_folder: str
    subfolder: str
    filename: str
    relative_path: str
    status: str
    detail: str
    aircraft: AircraftRef | None = None
    doc_type_code: str | None = None
    sha256: str | None = None


class Command(BaseCommand):
    help = (
        "R4.1: report (default) or --apply the Z: aircraft document "
        "repository. Always run locally against a restored backup copy "
        "first -- p340 cannot see the Z: drive."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            type=Path,
            required=True,
            help="Root of the Z: repository (the folder containing the "
            "CC<code>-<serial>-<model> folders).",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Persist Document rows. Without it, only report.",
        )

    def handle(self, *args, **options):
        source: Path = options["source"]
        if not source.is_dir():
            raise CommandError(f"Not a directory: {source}")
        will_apply = options["apply"]

        known_aircraft = [
            AircraftRef(
                id=str(row["id"]),
                registration=row["registration"],
                serial_number=row["serial_number"],
                cost_center_code=row["cost_center__code"] or "",
            )
            for row in Aircraft.objects.exclude(serial_number__isnull=True)
            .exclude(serial_number="")
            .values("id", "registration", "serial_number", "cost_center__code")
        ]

        aircraft_dirs = sorted(
            d
            for d in source.iterdir()
            if d.is_dir() and d.name not in EXCLUDED_TOP_LEVEL
        )
        folder_matches = {
            m.folder_name: m
            for m in match_aircraft_folders(
                [d.name for d in aircraft_dirs], known_aircraft
            )
        }

        decisions = self._classify(aircraft_dirs, folder_matches, will_apply)
        self._report(decisions)

        if will_apply:
            blocking = [d for d in decisions if d.status in LOCAL_BLOCKING_STATUSES]
            if blocking:
                raise CommandError(
                    f"{len(blocking)} filas necesitan una decisión humana "
                    "(REVIEW-NO-MATCH / REVIEW-NEEDS-ANTIVIRUS / "
                    "REVIEW-UNKNOWN-SUBFOLDER / REVIEW-CONTENT-CHANGED / "
                    "REVIEW-ANTIVIRUS-REJECTED). No se aplicó nada."
                )
            self._apply(source, decisions)

    def _classify(self, aircraft_dirs, folder_matches, will_apply):
        decisions = []
        for aircraft_dir in aircraft_dirs:
            folder_match = folder_matches.get(aircraft_dir.name)
            entries = list(aircraft_dir.iterdir())
            # A file loose at the aircraft folder's own root, outside any of
            # the 5 numbered subfolders (production has one: a technical
            # manual PDF directly under CC738-...). `subfolder=aircraft_dir`
            # makes subfolder_doc_type_code() correctly find no "NN.-" prefix
            # and fall through to REVIEW_UNKNOWN_SUBFOLDER -- there is no
            # filing convention for it to guess at.
            for file_path in sorted(f for f in entries if f.is_file()):
                decisions.append(
                    self._classify_file(
                        aircraft_dir, aircraft_dir, file_path, folder_match, will_apply
                    )
                )
            for subfolder in sorted(d for d in entries if d.is_dir()):
                # rglob, not iterdir: production has at least one subfolder
                # with its own nested subfolder ("02.- Solicitud de
                # Vuelos/Junio-Agosto/") -- iterdir() silently dropped those
                # files from the report entirely, which is worse than any
                # REVIEW_* status (a human reviewing the report has no way
                # to know a file was never even looked at).
                for file_path in sorted(f for f in subfolder.rglob("*") if f.is_file()):
                    decisions.append(
                        self._classify_file(
                            aircraft_dir,
                            subfolder,
                            file_path,
                            folder_match,
                            will_apply,
                        )
                    )
        return decisions

    def _classify_file(
        self, aircraft_dir, subfolder, file_path, folder_match, will_apply
    ):
        relative_path = "/".join(
            (aircraft_dir.name, *file_path.relative_to(aircraft_dir).parts)
        )
        base = dict(
            aircraft_folder=aircraft_dir.name,
            subfolder=subfolder.name,
            filename=file_path.name,
            relative_path=relative_path,
        )
        format_status = classify_file_format(file_path.name)

        if format_status == NEEDS_ANTIVIRUS_GATE:
            resolved_status, detail = self._resolve_antivirus_gate(
                file_path, will_apply
            )
            if resolved_status != OK:
                return FileDecision(**base, status=resolved_status, detail=detail)
        elif format_status != OK:
            return FileDecision(
                **base, status=format_status, detail="Formato/PII, nunca se importa."
            )

        if folder_match is None or folder_match.status != OK:
            hint = (
                f" ({folder_match.hint})" if folder_match and folder_match.hint else ""
            )
            return FileDecision(
                **base,
                status=REVIEW_NO_MATCH,
                detail=f"Carpeta de aeronave sin calce exacto por serial{hint}.",
            )

        doc_type_code = subfolder_doc_type_code(subfolder.name)
        if doc_type_code is None:
            return FileDecision(
                **base,
                status=REVIEW_UNKNOWN_SUBFOLDER,
                detail=f"Subcarpeta no reconocida: {subfolder.name!r}.",
                aircraft=folder_match.aircraft,
            )

        sha256 = _sha256(file_path)
        existing = Document.objects.filter(source_reference=relative_path).first()
        if existing is not None:
            if existing.content_sha256 == sha256:
                return FileDecision(
                    **base,
                    status=ALREADY_IMPORTED,
                    detail="Ya importado en una corrida anterior, sin cambios.",
                    aircraft=folder_match.aircraft,
                    doc_type_code=doc_type_code,
                    sha256=sha256,
                )
            return FileDecision(
                **base,
                status=REVIEW_CONTENT_CHANGED,
                detail=(
                    "Ya existe un Document con esta ruta de origen pero el "
                    "contenido cambió -- decidir a mano si crear una versión "
                    "nueva."
                ),
                aircraft=folder_match.aircraft,
                doc_type_code=doc_type_code,
                sha256=sha256,
            )

        return FileDecision(
            **base,
            status=OK,
            detail="Listo para importar.",
            aircraft=folder_match.aircraft,
            doc_type_code=doc_type_code,
            sha256=sha256,
        )

    def _resolve_antivirus_gate(self, file_path, will_apply):
        if not getattr(settings, "DOCUMENTS_ANTIVIRUS_COMMAND", ""):
            return (
                REVIEW_NEEDS_ANTIVIRUS,
                "Formato .msg requiere antivirus configurado (R4.4); hoy "
                "DOCUMENTS_ANTIVIRUS_COMMAND está vacío.",
            )
        if not will_apply:
            # Report mode does not shell out to the antivirus command just to
            # draft the report -- the gate is confirmed configured here, and
            # the real scan runs when --apply actually reads the file.
            return OK, "Antivirus configurado; se escaneará al aplicar."
        upload = _PathAsUpload(file_path)
        try:
            scan_uploaded_file(upload)
        except RuntimeError as exc:
            return REVIEW_ANTIVIRUS_REJECTED, str(exc)
        finally:
            upload.close()
        return OK, "Escaneado y aceptado."

    def _report(self, decisions):
        by_status: dict[str, int] = {}
        for decision in decisions:
            by_status[decision.status] = by_status.get(decision.status, 0) + 1
            self.stdout.write(
                f"{decision.status:<24} {decision.relative_path} -- {decision.detail}"
            )
        self.stdout.write("")
        self.stdout.write("Resumen:")
        for status, count in sorted(by_status.items()):
            self.stdout.write(f"  {status:<24} {count}")

    @transaction.atomic
    def _apply(self, source, decisions):
        aircraft_ct = ContentType.objects.get_for_model(Aircraft)
        needed_codes = {d.doc_type_code for d in decisions if d.doc_type_code}
        doc_types = {
            dt.code: dt for dt in DocumentType.objects.filter(code__in=needed_codes)
        }
        missing_codes = {
            d.doc_type_code
            for d in decisions
            if d.status == OK and d.doc_type_code not in doc_types
        }
        if missing_codes:
            raise CommandError(
                "Faltan estos DocumentType en el catálogo -- correr "
                f"seed_document_types primero: {sorted(missing_codes)}"
            )

        storage = get_document_storage()
        today = timezone.localdate()
        created = 0
        for decision in decisions:
            if decision.status != OK:
                continue
            aircraft_row = Aircraft.objects.get(pk=decision.aircraft.id)
            doc_type = doc_types[decision.doc_type_code]
            document = Document(
                tenant=aircraft_row.tenant,
                content_type=aircraft_ct,
                object_id=aircraft_row.id,
                doc_type=doc_type,
                title=(
                    f"{doc_type.name} · {aircraft_row.registration} · "
                    f"{decision.filename}"
                )[:200],
                issue_date=today,
                content_sha256=decision.sha256,
                source_reference=decision.relative_path,
                notes=(
                    f"Importado desde el repositorio Z: el {today.isoformat()}. "
                    f"Ruta original: {decision.relative_path}. Fecha real del "
                    "documento no disponible sin abrir el archivo -- no se "
                    "infiere (mismo criterio que R4.3 para expiry_date)."
                ),
            )
            key = document_upload_path(document, decision.filename)
            full_path = source / decision.relative_path
            with full_path.open("rb") as fh:
                storage.save(key, fh)
            document.file_path = key
            document.save()
            created += 1
        self.stdout.write(self.style.SUCCESS(f"Creados {created} documentos."))
