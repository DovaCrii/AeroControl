import json
import logging
import time
import uuid


logger = logging.getLogger("aerocontrol.request")
csp_logger = logging.getLogger("aerocontrol.csp")


def build_csp(report_uri="", frame_ancestors="'none'"):
    """Assemble the Content-Security-Policy directive string.

    V.11/T5.9 vendored Bootstrap, htmx, Chart.js, FullCalendar and Sortable
    under static/vendor/ with SRI, so no third-party script/style origin
    remains. V.10 extracted every inline <script>, so script-src is a bare
    'self' with no 'unsafe-inline'. 'unsafe-inline' stays on style-src only,
    for inline style attributes and the login page's <style> block.

    `frame_ancestors` is a parameter for exactly one caller (LV-85, the document
    preview). Everything this app serves refuses to be framed, which is the
    clickjacking protection; a PDF shown inside its own document fiche has to be
    framed **by this same origin**, which is not that attack. The exception is
    per response and never global -- see `apps/compliance/views.py`.
    """
    directives = [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline'",
        # Tile hosts for the geo map island (GEO-7); keep in sync with
        # settings.GEO_TILE_PROVIDERS.
        "img-src 'self' data: https://*.tile.openstreetmap.org "
        "https://server.arcgisonline.com",
        "font-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        f"frame-ancestors {frame_ancestors}",
        "form-action 'self'",
    ]
    if report_uri:
        directives.append("report-uri " + report_uri)
    return "; ".join(directives)


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

        # LV-85: a view may ask to be framable by this same origin (the document
        # preview, embedded in its own fiche). Opt-in, per response, and the
        # only thing it can relax -- every other directive is still built here.
        policy = build_csp(
            getattr(settings, "CSP_REPORT_URI", ""),
            frame_ancestors=(
                "'self'"
                if getattr(response, "frame_ancestors_self", False)
                else "'none'"
            ),
        )
        # V.10: emit the *enforcing* header when CSP_REPORT_ONLY is False. The
        # old code only set the Report-Only header and, when enforcing was asked
        # for, wrote nothing at all -- so turning enforcing "on" silently removed
        # the policy. Now one of the two headers is always present.
        header = (
            "Content-Security-Policy-Report-Only"
            if getattr(settings, "CSP_REPORT_ONLY", True)
            else "Content-Security-Policy"
        )
        response[header] = policy
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
            "blocked_uri",
            "violated_directive",
            "document_uri",
        ):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)
