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
        if (
            request.user.is_authenticated
            and request.method in {"POST", "PUT", "PATCH", "DELETE"}
            and not request.path.startswith("/accounts/")
        ):
            from apps.core.models import AuditEvent

            outcome = "success" if response.status_code < 400 else "denied"
            AuditEvent.objects.create(
                actor=request.user,
                action=f"{request.method.lower()}_{outcome}",
                method=request.method,
                path=request.path[:500],
                status_code=response.status_code,
                request_id=request_id,
                metadata={"query_keys": sorted(request.GET.keys())},
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
        for key in ("request_id", "method", "path", "status_code", "duration_ms"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)
