import json
import logging
import time
import uuid

from apps.core.audit_health import record_failure


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
        # `UX-26`: el service worker y el manifiesto, declarados **explícitamente**
        # aunque hoy ya pasarían por herencia — `worker-src` cae en `script-src`
        # y `manifest-src` en `default-src`, y los dos valen `'self'`.
        #
        # Se escriben igual porque de esa herencia depende que la aplicación
        # funcione sin señal, y una directiva heredada se rompe en silencio: el
        # día que alguien acote `script-src` para otra cosa, el worker deja de
        # registrarse y lo único que se nota es que la copia sin conexión dejó de
        # existir. Escrito, el cambio que lo rompería se ve en el diff.
        "worker-src 'self'",
        "manifest-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        f"frame-ancestors {frame_ancestors}",
        "form-action 'self'",
    ]
    if report_uri:
        directives.append("report-uri " + report_uri)
    return "; ".join(directives)


MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class AuditWriteFailed(Exception):
    """T1.4: la auditoría de una mutación no se pudo escribir (modo fail-closed)."""


def audit_unavailable_response(request):
    """T1.4: la respuesta cuando un cambio **no se guardó** por no poder auditarse.

    503 y no 500: no es un defecto del código sino un servicio (el registro de
    auditoría) que no está disponible, y el cambio se deshizo entero. Sin
    `base.html` y **sin `request`** por la misma razón que `csrf_failure` (`LV-215`):
    la página tiene que dibujarse cuando algo ya falló, y `render(request, ...)`
    correría los *context processors*, que consultan la base — justo lo que puede
    estar fallando.
    """
    from django.http import HttpResponse
    from django.template.loader import render_to_string

    response = HttpResponse(
        render_to_string("core/audit_unavailable.html", {"path": request.path}),
        status=503,
    )
    response["Retry-After"] = "30"
    return response


class RequestMetricsMiddleware:
    """Attach a correlation id and emit one structured event per request.

    T1.4: además escribe el `AuditEvent` de cada mutación autenticada, de dos maneras
    según `settings.AUDIT_FAIL_CLOSED`:

    - **Apagado (por omisión): fail-open.** La entrada se escribe *después* de la
      respuesta y fuera de toda transacción; si falla, el cambio ya se confirmó y el
      fallo queda en el log y en la marca de `audit_health`.
    - **Encendido: fail-closed.** Las peticiones que mutan corren **dentro de una
      transacción** y la auditoría se escribe **antes de confirmarla**: si no se
      puede escribir, se deshace el cambio entero y la persona ve un 503. Ninguna
      mutación queda sin su entrada, que es lo que pide la trazabilidad.

    El costo del modo estricto es que, en SQLite, la transacción retiene al único
    escritor hasta que termina la vista; por eso va detrás de un interruptor y se
    enciende en `p340` sólo tras una semana con la marca de fallos en cero.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from django.conf import settings

        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        request.request_id = request_id
        started = time.perf_counter()
        # El interruptor se lee en cada petición y no al arrancar: un test, o un
        # `override_settings`, lo enciende sin reconstruir el middleware.
        strict = (
            getattr(settings, "AUDIT_FAIL_CLOSED", False)
            and request.method in MUTATING_METHODS
            and not request.path.startswith("/accounts/")
        )
        try:
            if strict:
                response = self._call_atomically(request, request_id)
            else:
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
        if not strict:
            try:
                self._write_audit(request, response, request_id)
            except Exception as error:  # noqa: BLE001 - fail-open: no tumba la petición
                self._report_failure(request, request_id, error)
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

    def _call_atomically(self, request, request_id):
        """T1.4 fail-closed: la vista y su auditoría en **una** transacción.

        Se abre para toda mutación (no se sabe aún si la persona está autenticada: el
        usuario lo resuelve un middleware más adentro) y la entrada de auditoría se
        escribe dentro, antes de confirmar. Si falla, salir del bloque con una
        excepción deshace la vista entera — incluida cualquier fila que hayan
        escrito sus propias transacciones anidadas, que sólo son puntos de guardado.
        """
        from django.db import transaction

        try:
            with transaction.atomic():
                response = self.get_response(request)
                try:
                    self._write_audit(request, response, request_id)
                except Exception as error:
                    self._report_failure(request, request_id, error)
                    raise AuditWriteFailed from error
        except AuditWriteFailed:
            return audit_unavailable_response(request)
        return response

    def _write_audit(self, request, response, request_id):
        """Escribe la entrada (o entradas) de auditoría de esta petición.

        No atrapa nada: quien llama decide qué hacer si falla (seguir, o deshacer).
        No escribe nada cuando la petición no se audita: anónima, de lectura o de
        `/accounts/`.
        """
        user = getattr(request, "user", None)
        if (
            user is None
            or not user.is_authenticated
            or request.method not in MUTATING_METHODS
            or request.path.startswith("/accounts/")
        ):
            return
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
        default_action = f"{request.method.lower()}_{outcome}"
        # LV-176: una petición puede mutar varias filas -- archivar un plan
        # junto con sus permisos ligados son N+1 mutaciones en un POST. Cada
        # una necesita su propia entrada o la respuesta a "por qué se cerró
        # esto" no está donde alguien la va a buscar. Comparten `request_id`,
        # que es lo que después deja ver que fue un solo acto.
        rows = [
            {
                "model_label": context.get("model_label", ""),
                "object_id": context.get("object_id", ""),
                "action": context.get("action"),
            }
        ]
        rows.extend(getattr(request, "_audit_siblings", []))
        for row in rows:
            AuditEvent.objects.create(
                actor=user,
                action=row["action"] or default_action,
                method=request.method,
                path=request.path[:500],
                status_code=response.status_code,
                model_label=row["model_label"],
                object_id=row["object_id"],
                request_id=request_id,
                metadata=metadata,
            )

    @staticmethod
    def _report_failure(request, request_id, error):
        logger.exception(
            "audit_write_failed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.path,
            },
        )
        # T1.4 paso 1: además del log, una marca que el centro de administración
        # muestra. Vale en los dos modos.
        record_failure(
            request_id=request_id,
            method=request.method,
            path=request.path,
            error=error,
        )


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
