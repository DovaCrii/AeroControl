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
from django.urls import reverse
from django.utils import timezone
from django.utils.http import urlencode
from django.utils.translation import gettext as _
from django.utils.translation import ngettext, pgettext

from apps.compliance.expirations import EXPIRATION_PERMISSIONS
from apps.compliance.kpis import PERMIT_CRITICAL_DAYS, PERMIT_WARNING_DAYS
from apps.core.tenancy import visible_tenant_ids
from apps.reporting.models import ReportRun

from .compliance_data import (
    REVIEW_PERMISSION,
    alert_ages,
    expiry_data,
    review_history,
    visible_categories,
)
from .compliance_permits import (
    KIND_CHIP,
    PERMIT_PERMISSION,
    permit_table,
    requested_query,
    requested_sort,
    requested_state,
    sort_context,
)
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
    REVIEW_PERMISSION,
)


# «Qué atender primero» (LV-367): el ORDEN es una PROPUESTA y lo confirma la persona. Es la única lista que hay
# que tocar para cambiarlo; cada clave es una de las que arma `attention_first`. Hoy: faenas sin permiso
# vigente (la operación se detiene), después lo vencido, después las alertas con más de 30 días abiertas.
PRIORITY_ORDER = ("no_permit", "overdue", "old_alerts")
PRIORITY_LIMIT = 3


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
        "history": user.has_perm(REVIEW_PERMISSION),
        "permits": user.has_perm(PERMIT_PERMISSION),
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


def guide_steps(user, cost_center):
    """Los cinco pasos de «Cómo leer y revisar esta sección», cada uno con su enlace para corregir.

    El enlace sólo existe si la persona puede abrir esa pantalla (`url` queda `None` si no): la guía
    nunca manda a un 403. El paso se dice igual, porque saber que existe también orienta.
    """
    site = {"cost_center": cost_center.pk} if cost_center else {}
    permits = reverse("permission-list")
    if site:
        permits = f"{permits}?{urlencode(site)}"

    def link(permission, url):
        return url if user.has_perm(permission) else None

    return [
        {
            "n": 1,
            "label": _("Needs attention"),
            "text": _("Start with what the panel lists as needing attention."),
            "url": f"{reverse('dashboard')}#panel-attention",
        },
        {
            "n": 2,
            "label": _("Expiries"),
            "text": _("Open the alerts to correct what is overdue or about to expire."),
            "url": link(ALERT_PERMISSION, reverse("alert-list")),
        },
        {
            "n": 3,
            "label": _("Permits by site"),
            "text": _("Check which site has no permit in force and renew first."),
            "url": link("operations.view_flightpermission", permits),
        },
        {
            "n": 4,
            "label": _("Monthly close"),
            "text": _("Close last month: records on file for each site that flew."),
            "url": link(
                "compliance.view_monthlycompliancereview", reverse("monthly-review")
            ),
        },
        {
            "n": 5,
            "label": _("Report"),
            "text": _("Review the monthly DGAC report before approving it."),
            "url": link(REPORT_PERMISSION, reverse("monthly-report")),
        },
    ]


def guide_states(user):
    """La leyenda de estados de la guía (LV-376, fase 3): qué significa cada uno, qué hacer y, si se puede, a dónde ir.

    Los números (30 y 60 días) salen de las constantes de `kpis`, no de un texto tecleado, así que la guía no
    puede quedar atrás si se mueven. El enlace sólo existe si la persona puede abrir esa pantalla: la guía nunca
    manda a un 403 (`url` vacío si no).
    """
    permits = reverse("permission-list") if user.has_perm(PERMIT_PERMISSION) else ""
    create = (
        reverse("permission-create")
        if user.has_perm("operations.add_flightpermission")
        else ""
    )
    critical, warning = PERMIT_CRITICAL_DAYS, PERMIT_WARNING_DAYS
    rows = [
        (
            "none",
            _("No permit"),
            _("No permit in force: the site cannot fly."),
            _("Request a permit"),
            create,
        ),
        (
            "awaiting",
            _("Waiting for the DGAC"),
            _("Requested; there is no answer yet."),
            _("Follow up with the DGAC"),
            permits,
        ),
        (
            "not_started",
            _("Starts later"),
            _("Approved; it takes effect from its start date."),
            _("Nothing to do until that date"),
            "",
        ),
        (
            "renew_now",
            _("Renew now"),
            _("Expires in %(n)s days or less.") % {"n": critical},
            _("Prepare the renewal today"),
            permits,
        ),
        (
            "renew_soon",
            _("Renew soon"),
            _("Expires in %(a)s to %(b)s days.") % {"a": critical + 1, "b": warning},
            _("Plan the renewal"),
            "",
        ),
        (
            "ok",
            _("Up to date"),
            _("More than %(n)s days left.") % {"n": warning},
            _("Nothing to do"),
            "",
        ),
    ]
    return [
        {
            "kind": kind,
            "symbol": KIND_CHIP[kind][0],
            "tone": KIND_CHIP[kind][1],
            "label": label,
            "meaning": meaning,
            "todo": todo,
            "url": url,
        }
        for kind, label, meaning, todo, url in rows
    ]


def attention_first(rings, alerts, permits):
    """Hasta tres cosas que atender primero, en el orden de `PRIORITY_ORDER`; sólo las que hay (cifra > 0).

    Se arma con lo ya calculado para la sección (anillos, alertas y tabla de permisos): cero consultas y
    ninguna cifra nueva, así que coincide con el resto de la página. Cada una enlaza a donde se trabaja.
    """
    counts = {
        "no_permit": permits["without_permit"] if permits else 0,
        "overdue": sum(r["counts"]["overdue"] for r in rings or ()),
        "old_alerts": alerts["old"] if alerts else 0,
    }
    texts = {
        "no_permit": lambda n: ngettext(
            "%(count)s site without a permit in force",
            "%(count)s sites without a permit in force",
            n,
        ),
        "overdue": lambda n: ngettext(
            "%(count)s item overdue", "%(count)s items overdue", n
        ),
        "old_alerts": lambda n: ngettext(
            "%(count)s alert open for over 30 days",
            "%(count)s alerts open for over 30 days",
            n,
        ),
    }
    urls = {
        "no_permit": "#cx-permits",
        "overdue": "#cx-expiries",
        "old_alerts": reverse("alert-list"),
    }
    items = [
        {
            "key": key,
            "count": counts[key],
            "text": texts[key](counts[key]) % {"count": counts[key]},
            "url": urls[key],
        }
        for key in PRIORITY_ORDER
        if counts[key] > 0
    ]
    return items[:PRIORITY_LIMIT]


def _card(key, symbol, tone, n, url, name, sub, zero):
    return {
        "key": key,
        "symbol": symbol,
        "tone": tone,
        "n": n,
        "url": url,
        "name": name,
        "sub": sub,
        "zero": zero,
    }


def summary_cards(rings, permits):
    """Las cuatro tarjetas de arriba (LV-376, fase 2): ¿hay algo que no pueda esperar?

    Sale todo de lo ya calculado para la sección, cero consultas y ninguna cifra nueva: «sin permiso» es
    `without_permit` de la tabla; «vencido» y «vence en 30 días» son las del panel (`overdue_count` y
    `expiring_count`: SIN mantención, que el panel no cuenta y una prueba compara); «esperando a la DGAC»
    son las faenas con un permiso solicitado o aprobado que aún no empieza (el «esperando» del resumen de
    la tabla). Una tarjeta sólo existe si quien mira puede ver su fuente, y un cero se dice con palabras.
    """
    cards = []
    if permits:
        cards.append(
            _card(
                "no_permit",
                "✕",
                "none",
                permits["without_permit"],
                "#cx-permits",
                _("Sites without a permit"),
                _("They cannot fly today"),
                _("Every site that flies has a permit"),
            )
        )
    counted = [r for r in rings or () if r["key"] != "maintenance"]
    if counted:
        cards.append(
            _card(
                "overdue",
                "✕",
                "overdue",
                sum(r["counts"]["overdue"] for r in counted),
                "#cx-expiries",
                pgettext("compliance level", "Overdue"),
                _("Dates already past: documents, people, aircraft and permits"),
                _("Nothing overdue"),
            )
        )
        cards.append(
            _card(
                "expiring",
                "▲",
                "soon",
                sum(
                    r["counts"]["due_7"] + r["counts"]["due_15"] + r["counts"]["due_30"]
                    for r in counted
                ),
                "#cx-expiries",
                _("Expiring within 30 days"),
                _("Worth renewing now"),
                _("Nothing expires within 30 days"),
            )
        )
    if permits:
        waiting = next((t["n"] for t in permits["tally"] if t["key"] == "waiting"), 0)
        cards.append(
            _card(
                "waiting",
                "◐",
                "wait",
                waiting,
                "#cx-permits",
                _("Waiting for the DGAC"),
                _("Requested, or approved and not started yet"),
                _("Nothing is waiting"),
            )
        )
    return cards


def calm_line(rings, permits):
    """«✓ Al día: Personas, Mantenimiento · 8 de 11 faenas con permiso vigente», o `None` si no hay nada que decir."""
    names = ", ".join(str(r["label"]) for r in rings or () if not r["attend"])
    sites = ""
    if permits and permits["total"]:
        sites = _("%(n)s of %(m)s sites with a permit in force") % {
            "n": permits["total"] - permits["without_permit"],
            "m": permits["total"],
        }
    return {"names": names, "sites": sites} if names or sites else None


def open_flags(context):
    """Qué secciones plegables salen abiertas: sólo las que tienen algo. Se decide acá, no en la plantilla.

    El mapa de calor, el historial y la guía salen siempre cerrados. (Un `<details>` pierde su estado cada
    vez que htmx reemplaza el fragmento: la sección se pide una sola vez, no se refresca.)
    """
    rings = context.get("cx_rings") or ()
    alerts = context.get("cx_alerts")
    permits = context.get("cx_permits")
    return {
        "expiries": any(r["attend"] for r in rings),
        "alerts": bool(alerts and alerts["total"]),
        "maintenance": bool(context.get("cx_maintenance_to_define")),
        "permits": bool(permits and permits["problems"]),
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
        if blocks["permits"]:
            column, direction = requested_sort(request.GET)
            # LV-376: `?state=` (lista permitida) filtra en las dos vistas; `?q=` sólo en la página
            # completa, que es donde existe el cuadro de búsqueda (el fragmento del panel no lo dibuja).
            state = requested_state(request.GET)
            query = (
                requested_query(request.GET)
                if request.headers.get("HX-Request") != "true"
                else ""
            )
            context["cx_permits"] = permit_table(
                user,
                cost_center,
                today,
                tenant_ids,
                column,
                direction,
                state,
                query,
            )
            context["worktable_sort"] = sort_context(
                request, cost_center, state=state, query=query
            )
        if blocks["history"]:
            context["cx_history"] = review_history(user, cost_center, today, tenant_ids)
        context["cx_guide"] = guide_steps(user, cost_center)
        context["cx_guide_states"] = guide_states(user)
        rings = context.get("cx_rings") or []
        context["cx_attention"] = [r for r in rings if r["attend"]]
        context["cx_clear"] = [r for r in rings if not r["attend"]]
        context["cx_cards"] = summary_cards(rings, context.get("cx_permits"))
        context["cx_calm"] = calm_line(rings, context.get("cx_permits"))
        context["cx_priorities"] = attention_first(
            rings, context.get("cx_alerts"), context.get("cx_permits")
        )
        context["cx_open"] = open_flags(context)
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
