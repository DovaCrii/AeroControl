import json
import logging
import time
import uuid


logger = logging.getLogger("aerocontrol.request")


class RequestMetricsMiddleware:
    """Attach a correlation id and emit one structured event per request."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        request.request_id = request_id
        started = time.perf_counter()
        try:
            response = self.get_response(request)
        except Exception:
            logger.exception(
                "request_failed",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.path,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                },
            )
            raise
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        response["X-Request-ID"] = request_id
        from django.conf import settings

        if getattr(settings, "CSP_REPORT_ONLY", True):
            response["Content-Security-Policy-Report-Only"] = (
                # V.11/T5.9: Bootstrap, htmx, Chart.js, FullCalendar and Sortable
                # are now vendored under static/vendor/ with SRI, so no third-party
                # script/style origin remains. 'unsafe-inline' on style-src covers
                # inline style attributes and the login page's <style> block;
                # script-src stays 'self' with no 'unsafe-inline' on purpose, so the
                # report surfaces the inline <script> blocks that V.10 must extract.
                "default-src 'self'; script-src 'self'; "
                "style-src 'self' 'unsafe-inline'; "
                # Tile hosts for the geo map island (GEO-7); keep in sync with
                # settings.GEO_TILE_PROVIDERS.
                "img-src 'self' data: https://*.tile.openstreetmap.org "
                "https://server.arcgisonline.com; "
                "font-src 'self'; "
                "object-src 'none'; base-uri 'self'; frame-ancestors 'none'; "
                "form-action 'self'"
            )
        if (
            request.user.is_authenticated
            and request.method in {"POST", "PUT", "PATCH", "DELETE"}
            and not request.path.startswith("/accounts/")
        ):
            from apps.core.models import AuditEvent

            if response.status_code < 400:
                outcome = "success"
            elif response.status_code in {401, 403}:
                outcome = "denied"
            elif response.status_code < 500:
                outcome = "client_error"
            else:
                outcome = "server_error"
            context = getattr(request, "_audit_context", {})
            metadata = {"query_keys": sorted(request.GET.keys())}
            metadata.update(context.get("metadata", {}))
            try:
                AuditEvent.objects.create(
                    actor=request.user,
                    action=context.get("action")
                    or f"{request.method.lower()}_{outcome}",
                    method=request.method,
                    path=request.path[:500],
                    status_code=response.status_code,
                    model_label=context.get("model_label", ""),
                    object_id=context.get("object_id", ""),
                    request_id=request_id,
                    metadata=metadata,
                )
            except Exception:
                logger.exception(
                    "audit_write_failed",
                    extra={
                        "request_id": request_id,
                        "method": request.method,
                        "path": request.path,
                    },
                )
        logger.info(
            "request_complete",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        return response


class JsonLogFormatter(logging.Formatter):
    """Serialize request events as one JSON object per line."""

    def format(self, record):
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in (
            "request_id",
            "method",
            "path",
            "status_code",
            "duration_ms",
            "rule_id",
            "rule_name",
            "entity_type",
            "field_to_watch",
            "reason",
            "job_command",
            "job_result",
            "job_duration_ms",
            "recipient",
            "item_count",
            "send_result",
        ):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)
