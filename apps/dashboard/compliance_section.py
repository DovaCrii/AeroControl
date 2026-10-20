"""La sección «Cumplimiento» del panel (LV-359): `GET /dashboard/compliance/`.

Contesta una sola pregunta: **«¿estamos al día hoy y qué vence primero?»**. El panel deja un hueco al
final (`_compliance_slot.html`) que pide esta sección por htmx cuando entra en pantalla, así que
armar el panel no cuesta ni una consulta más (`test_lv237`). Sin htmx, la misma sección se abre como
página completa (`compliance.html`): es también el enlace del `<noscript>`.

Permisos (decisión D2): la vista pide sesión, no un permiso de modelo —cruza cinco fuentes y no
tiene un modelo propio—, y **cada bloque se dibuja sólo si quien mira puede ver su fuente**, como el
panel. Sin ninguna fuente visible devuelve un hueco vacío, sin nombres de registros. La faena
elegida viaja explícita en la URL y, a diferencia del panel, se acota por tenant.

«Hoy» y el corte del informe DGAC no se mezclan nunca: el aviso del informe se **lee** del último
`ReportRun` con su propia fecha de corte, no se recalcula.
"""

from datetime import date

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from django.utils import timezone

from apps.compliance.expirations import EXPIRATION_PERMISSIONS
from apps.core.tenancy import visible_tenant_ids
from apps.reporting.models import ReportRun

from .compliance_data import alert_ages, expiry_data, visible_categories
from .selection import resolve_cost_center

# Las fuentes que alimentan la sección. Los cinco `view_*` del diseño, más los de padrones que
# `upcoming_expirations` ya gatea por fuente: sin ellos quien sólo ve aeronaves tendría los
# vencimientos de su flota en el panel y ninguna sección que los desglose.
ALERT_PERMISSION = "compliance.view_alert"
MAINTENANCE_PERMISSION = "maintenance.view_maintenancerecord"
REPORT_PERMISSION = "reporting.view_reportrun"
EXPIRATION_SOURCES = tuple(EXPIRATION_PERMISSIONS.values())
SOURCE_PERMISSIONS = (
    *EXPIRATION_SOURCES,
    ALERT_PERMISSION,
    MAINTENANCE_PERMISSION,
    "compliance.view_monthlycompliancereview",
)


def can_see_compliance(user):
    """¿Puede ver al menos una fuente? Decide si el panel dibuja el hueco. No cuesta consultas."""
    return bool(getattr(user, "is_authenticated", False)) and any(
        user.has_perm(code) for code in SOURCE_PERMISSIONS
    )


def blocks_for(user):
    """Qué bloques ve esta persona: cada uno exige el permiso de su fuente."""
    # Anillos y mapa de calor se dibujan si hay al menos UNA categoría visible (cada una con el
    # permiso de sus fuentes, ver `compliance_data.CATEGORY_PERMISSIONS`).
    categories = bool(visible_categories(user))
    return {
        "expirations": any(user.has_perm(code) for code in EXPIRATION_SOURCES),
        "rings": categories,
        "heat": categories,
        "alerts": user.has_perm(ALERT_PERMISSION),
        "maintenance": user.has_perm(MAINTENANCE_PERMISSION),
    }


def report_notice(user):
    """El último informe mensual DGAC: su corte y su estado, tal como se congelaron.

    Se lee del modelo; no se recalcula ni se compara con «hoy». Sólo con `view_reportrun` (el permiso
    de la pantalla del informe). `None` si no hay informe o la persona no puede verlo.
    """
    if not user.has_perm(REPORT_PERMISSION):
        return None
    run = (
        ReportRun.objects.filter(is_active=True)
        .order_by("-period", "-revision")
        .first()
    )
    if run is None:
        return None
    cutoff = None
    raw = (run.payload or {}).get("meta", {}).get("cutoff")
    if isinstance(raw, str):
        try:
            cutoff = date.fromisoformat(raw[:10])
        except ValueError:
            cutoff = None
    return {
        "cutoff": cutoff,
        "period": run.period,
        "status": run.status,
        "status_label": run.get_status_display(),
    }


def section_context(request):
    user = request.user
    cost_center = resolve_cost_center(request, scope_user=user)
    blocks = blocks_for(user)
    context = {
        "cx_visible": any(blocks.values()),
        "cx_blocks": blocks,
        "cx_today": timezone.localdate(),
        "cx_cost_center": cost_center,
    }
    if context["cx_visible"]:
        context["cx_report"] = report_notice(user)
        today = context["cx_today"]
        tenant_ids = visible_tenant_ids(user)
        if blocks["rings"]:
            data = expiry_data(user, cost_center, today, tenant_ids) or {}
            context.update({f"cx_{key}": value for key, value in data.items()})
        if blocks["alerts"]:
            context["cx_alerts"] = alert_ages(user, cost_center, today, tenant_ids)
    return context


@login_required
def compliance_section(request):
    """El fragmento (htmx) o la página completa (sin htmx) de «Cumplimiento»."""
    context = section_context(request)
    if request.headers.get("HX-Request") == "true":
        # Sin `request`: el fragmento no necesita ni sesión ni `perms`, y así no corre ningún context
        # processor (la barra lateral cuenta alertas y consulta grupos: tres consultas por nada).
        return HttpResponse(
            render_to_string("dashboard/_compliance_section.html", context)
        )
    return render(request, "dashboard/compliance.html", context)
