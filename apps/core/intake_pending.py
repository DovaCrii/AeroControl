"""LV-425: purga de los PDF provisionales abandonados del ingreso.

El ingreso a taller y el alta de operador con credencial guardan el PDF bajo
`workshop-intake-pending/` mientras la persona revisa lo extraído. Confirmar lo
mueve a su lugar definitivo y cancelar lo borra (LV-388), pero cerrar la pestaña
lo deja ahí para siempre, con credenciales y RUT dentro. Esta función borra lo
que lleva más de `max_age_hours` sin tocarse; un archivo reciente (alguien lo
está revisando) no se toca.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from apps.compliance.storage import (
    DocumentStorageError,
    LocalDocumentStorage,
    S3DocumentStorage,
    get_document_storage,
)

logger = logging.getLogger(__name__)

PENDING_ROOT = "workshop-intake-pending"
DEFAULT_MAX_AGE_HOURS = 24


def _stale_local(storage, cutoff):
    base = (storage.root / PENDING_ROOT).resolve()
    if storage.root not in base.parents or not base.is_dir():
        return []
    stale = []
    for path in base.rglob("*"):
        # Ni symlinks ni nada que resuelva fuera del prefijo.
        if path.is_symlink() or not path.is_file():
            continue
        if base not in path.resolve().parents:
            continue
        if path.stat().st_mtime < cutoff:
            stale.append(path.relative_to(storage.root).as_posix())
    return stale


def _stale_s3(storage, cutoff):
    stale = []
    paginator = storage.client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=storage.bucket, Prefix=f"{PENDING_ROOT}/"):
        for item in page.get("Contents", []):
            modified = item["LastModified"]
            if modified.tzinfo is None:
                modified = modified.replace(tzinfo=timezone.utc)
            if modified.timestamp() < cutoff:
                stale.append(item["Key"])
    return stale


def purge_stale_pending(max_age_hours=DEFAULT_MAX_AGE_HOURS, now=None, dry_run=False):
    """Borra los provisionales más viejos que el umbral y devuelve cuántos eran.

    Con `dry_run` no borra nada y devuelve la lista de claves que borraría.
    `now` es un `datetime` o un timestamp (para fijar el reloj en pruebas).
    """
    if isinstance(now, datetime):
        now = now.timestamp()
    if now is None:
        now = time.time()
    cutoff = now - max_age_hours * 3600
    storage = get_document_storage()
    if isinstance(storage, LocalDocumentStorage):
        keys = _stale_local(storage, cutoff)
    elif isinstance(storage, S3DocumentStorage):
        keys = _stale_s3(storage, cutoff)
    else:
        logger.warning("Pending purge skipped: backend cannot list objects.")
        return [] if dry_run else 0
    if dry_run:
        return keys
    removed = 0
    for key in keys:
        if not key.startswith(f"{PENDING_ROOT}/"):
            continue
        try:
            storage.delete(key)
            removed += 1
        except (DocumentStorageError, OSError):
            logger.warning("Could not purge pending intake file %s", key)
    if removed:
        logger.info(
            "Purged %d stale intake PDF(s) older than %s h", removed, max_age_hours
        )
    return removed


def purge_stale_pending_safely():
    """Limpieza oportunista: un fallo aquí nunca debe romper la subida."""
    try:
        purge_stale_pending()
    except Exception:  # noqa: BLE001 - la limpieza jamás rompe el ingreso
        logger.exception("Opportunistic intake purge failed")
