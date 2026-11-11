"""LV-427: de un `Document` de log de vuelo a su `FlightLogAnalysis`."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path, PurePosixPath

from django.db import transaction
from django.utils import timezone

from . import parse_flight_log
from .types import FlightLogError

logger = logging.getLogger(__name__)

FLIGHT_LOG_TYPE = "flight-log-txt"
PARSER_VERSION = "phase1-stub"


def is_flight_log(document) -> bool:
    """¿Es el `.TXT` de log de vuelo colgado de un permiso?"""
    from .. import models

    return (
        document.doc_type.code == FLIGHT_LOG_TYPE
        and document.content_type.model_class() is models.FlightPermission
    )


def _parse_document(document):
    """Trae el archivo del almacenamiento a un temporal con su nombre original y lo lee."""
    from apps.compliance.storage import get_document_storage

    name = PurePosixPath((document.title or "log.txt").replace("\\", "/")).name
    with tempfile.TemporaryDirectory() as folder:
        target = Path(folder) / name
        try:
            with get_document_storage().open(document.file_path) as source:
                target.write_bytes(source.read())
        except Exception as exc:  # noqa: BLE001 - un archivo ilegible es un log incompleto
            raise FlightLogError(
                FlightLogError.INCOMPLETE, "file not readable"
            ) from exc
        return parse_flight_log(target)


def analyze_document(document, analysis=None):
    """Crea o actualiza el análisis de `document`. Nunca lanza por un fallo del lector."""
    from ..models import FlightLogAnalysis

    if analysis is None:
        analysis, _created = FlightLogAnalysis.objects.get_or_create(
            document=document, defaults={"permission_id": document.object_id}
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
