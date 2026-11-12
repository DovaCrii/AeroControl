"""LV-427: de un `Document` de log de vuelo a su `FlightLogAnalysis`."""

from __future__ import annotations

import io
import logging
import tempfile
from pathlib import Path, PurePosixPath

from django.db import transaction
from django.utils import timezone

from . import parse_flight_log
from .types import FlightLogError

logger = logging.getLogger(__name__)

FLIGHT_LOG_TYPE = "flight-log-txt"
# Subirla cuando cambia lo que se extrae del log: `analyze_flight_logs --outdated` rehace los
# análisis guardados con otra versión. dji-2 (LV-434): cronología sin filas duplicadas.
PARSER_VERSION = "dji-2"
KEYCHAIN_PREFIX = "flightlog-keychains"


def is_flight_log(document) -> bool:
    """¿Es el `.TXT` de log de vuelo colgado de un permiso o (LV-431) de una aeronave?"""
    from apps.registry.models import Aircraft

    from .. import models

    return document.doc_type.code == FLIGHT_LOG_TYPE and (
        document.content_type.model_class() in (models.FlightPermission, Aircraft)
    )


def _owner_defaults(document) -> dict:
    """Lo que ubica al análisis según de qué cuelga el documento (permiso o aeronave)."""
    from apps.registry.models import Aircraft

    from ..models import FlightPermission

    if document.content_type.model_class() is Aircraft:
        aircraft = Aircraft.objects.filter(pk=document.object_id).first()
        return {
            "aircraft_id": document.object_id,
            "cost_center_id": aircraft.cost_center_id if aircraft else None,
        }
    permission = FlightPermission.objects.filter(pk=document.object_id).first()
    return {
        "permission_id": document.object_id,
        "cost_center_id": permission.cost_center_id if permission else None,
    }


def _restore_keychains(storage, key, cache: Path) -> None:
    """Si ya hay llaves guardadas de este log, las deja en `cache`: así se lee sin red."""
    try:
        if storage.exists(key):
            with storage.open(key) as source:
                cache.write_bytes(source.read())
    except Exception:  # noqa: BLE001 - sin caché se vuelven a pedir; no es un fallo del análisis
        logger.warning("flight log keychain cache not readable for %s", key)


def _store_keychains(storage, key, cache: Path) -> None:
    """Guarda las llaves que el lector dejó en `cache` en el almacenamiento privado."""
    try:
        if cache.is_file() and cache.stat().st_size:
            storage.save(key, io.BytesIO(cache.read_bytes()))
    except Exception:  # noqa: BLE001 - la caché es una comodidad
        logger.warning("flight log keychain cache not stored for %s", key)


def _parse_document(document):
    """Trae el archivo del almacenamiento a un temporal con su nombre original y lo lee."""
    from apps.compliance.storage import get_document_storage

    name = PurePosixPath((document.title or "log.txt").replace("\\", "/")).name
    storage = get_document_storage()
    with tempfile.TemporaryDirectory() as folder:
        target = Path(folder) / name
        try:
            with storage.open(document.file_path) as source:
                target.write_bytes(source.read())
        except Exception as exc:  # noqa: BLE001 - un archivo ilegible es un log incompleto
            raise FlightLogError(
                FlightLogError.INCOMPLETE, "file not readable"
            ) from exc
        cache = Path(folder) / "keychains.json"
        key = f"{KEYCHAIN_PREFIX}/{document.pk}.json"
        _restore_keychains(storage, key, cache)
        track = parse_flight_log(target, keychain_cache=cache)
        _store_keychains(storage, key, cache)
        return track


def analyze_document(document, analysis=None):
    """Crea o actualiza el análisis de `document`. Nunca lanza por un fallo del lector."""
    from ..models import FlightLogAnalysis

    if analysis is None:
        analysis, _created = FlightLogAnalysis.objects.get_or_create(
            document=document, defaults=_owner_defaults(document)
        )
    try:
        track = _parse_document(document).downsampled()
    except FlightLogError as exc:
        analysis.status = FlightLogAnalysis.STATUS_ERROR
        analysis.error_code = exc.code
        analysis.error_message = exc.message[:300]
        analysis.result = {}
    else:
        analysis.status = FlightLogAnalysis.STATUS_OK
        analysis.error_code = ""
        analysis.error_message = ""
        analysis.result = track.to_dict()
    analysis.parser_version = PARSER_VERSION
    analysis.analyzed_at = timezone.now()
    analysis.save()
    return analysis


def on_document_saved(sender, instance, created, update_fields=None, **kwargs):
    """Señal `post_save` de `Document`: analiza el log cuando ya tiene archivo.

    Un `Document` se guarda dos veces al subirse (la fila y luego su `file_path`), así que se
    espera a que haya ruta. Todo va aislado: un error acá jamás rompe la subida.
    """
    if not instance.file_path or not instance.is_active:
        return
    if update_fields is not None and "file_path" not in update_fields:
        return
    try:
        if not is_flight_log(instance):
            return
        with transaction.atomic():
            analyze_document(instance)
    except Exception:  # noqa: BLE001 - el análisis es accesorio de la subida
        logger.exception("flight log analysis failed for document %s", instance.pk)
