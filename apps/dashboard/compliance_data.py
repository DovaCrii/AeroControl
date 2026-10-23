"""Los datos de los gráficos de «Cumplimiento» (LV-359, fase 2). Nada se recalcula: todo sale de lo que ya existe.

- Vencimientos: `upcoming_expirations(hoy, hoy + 90, faena, usuario)` —la misma función que la tarjeta de
  arriba del panel, con otro corte— y `digest.bucket_for`. **Vencido** y **hasta 30 días** coinciden con
  `overdue_count` y `expiring_count` del panel por construcción (los dos usan la misma función y la misma
  escala), y una prueba lo compara.
- Mantención: sólo con `view_maintenancerecord`; un registro sin completar con fecha ya pasada cuenta
  como vencido. Los «por definir» (sin fecha) se dicen aparte con `MaintenanceRecord.needing_planning`.
- Alertas abiertas por antigüedad: UNA agregación `Count(filter=Q)`, sólo con `view_alert`.

Cada categoría se dibuja sólo si la persona puede ver al menos una de sus fuentes: un anillo «0» de una
categoría que simplemente no puede ver diría «no vence nada», que es falso.
"""

from datetime import timedelta
from math import ceil

from django.db.models import Count, Q
from django.urls import reverse
from django.utils.http import urlencode
from django.utils.translation import gettext as _, ngettext, pgettext

from apps.compliance.digest import bucket_for
from apps.compliance.expirations import upcoming_expirations
from apps.compliance.models import Alert, MonthlyComplianceReview
from apps.compliance.monthly import previous_month_start
from apps.compliance.reports import alerts_for_cost_center
from apps.maintenance.models import MaintenanceRecord
from apps.registry.selectors import operating_cost_centers

HORIZON_DAYS = 90
WEEKS = 13  # 13 semanas de 7 días cubren los 90 días

LEVELS = ("overdue", "due_7", "due_15", "due_30", "later")
# Lo que se lee de cada tramo: símbolo + texto además del color (nunca sólo color). `tone` es la
# variante de `.id-chip--*` (identity.css): critical/warning/info/neutral.
LEVEL_SYMBOL = {
    "overdue": "✕",
    "due_7": "▲",
    "due_15": "◆",
    "due_30": "●",
    "later": "○",
}
LEVEL_TONE = {
    "overdue": "critical",
    "due_7": "warning",
    "due_15": "warning",
    "due_30": "info",
    "later": "neutral",
}

# Categoría -> permisos de sus fuentes. Con ninguno, la categoría no se dibuja.
CATEGORY_ORDER = ("papers", "people", "aircraft", "permits", "maintenance")
CATEGORY_PERMISSIONS = {
    "papers": ("compliance.view_document",),
    "people": (
        "registry.view_operator",
        "registry.view_qualification",
        "registry.view_knowledgeassessment",
    ),
    "aircraft": ("registry.view_aircraft",),
    "permits": ("operations.view_flightpermission",),
    "maintenance": ("maintenance.view_maintenancerecord",),
}
# Icono de cada categoría: símbolos del menú (`static/img/icons.svg`), sin dibujar nada nuevo.
CATEGORY_ICON = {
    "papers": "icon-document-list",
    "people": "icon-operator-list",
    "aircraft": "icon-aircraft-list",
    "permits": "icon-permission-list",
    "maintenance": "icon-maintenance-list",
}
# `item["subject_kind"]` (ver `expirations.add`) -> categoría.
SUBJECT_CATEGORY = {
    "document": "papers",
    "person": "people",
    "aircraft": "aircraft",
    "permit": "permits",
}


def category_label(key):
    return {
        "papers": _("Documents"),
        "people": _("People"),
        "aircraft": _("Aircraft"),
        "permits": _("Permits"),
        "maintenance": _("Maintenance"),
    }[key]


def level_label(level):
    """La etiqueta corta de cada tramo, para los chips y las descripciones."""
    return {
        "overdue": pgettext("compliance level", "Overdue"),
        "due_7": _("≤7 days"),
        "due_15": _("≤15 days"),
        "due_30": _("≤30 days"),
        "later": _("31–90 days"),
    }[level]


def visible_categories(user):
    return [
        key
        for key in CATEGORY_ORDER
        if any(user.has_perm(code) for code in CATEGORY_PERMISSIONS[key])
    ]


def level_of(expiry, today):
    return bucket_for(expiry, today) or "later"


def heat_step(count):
    """De la cifra al paso de color 0–4. La cifra es la información; el color sólo ayuda a ojear."""
    if count <= 0:
        return 0
    if count == 1:
        return 1
    if count <= 3:
        return 2
    if count <= 6:
        return 3
    return 4


def _week_of(days_left):
    """Semana 1 = hoy..7 días; semana 2 = 8..14; … semana 13 = 85..90."""
    return min(WEEKS, max(1, ceil(days_left / 7)))


def _narrow_of(days_left):
    return 0 if days_left <= 30 else (1 if days_left <= 60 else 2)


def _scoped(queryset, tenant_ids, path):
    """Acota por tenant con ids ya resueltos (`None` = todos): una consulta de membresía por pedido."""
    if tenant_ids is None:
        return queryset
    return queryset.filter(**{f"{path}__in": tenant_ids})


def _maintenance_dates(user, cost_center, today, tenant_ids):
    """(fechas con tramo, cantidad por definir) de las mantenciones sin completar."""
    queryset = MaintenanceRecord.objects.filter(is_active=True)
    if cost_center:
        queryset = queryset.filter(aircraft__cost_center=cost_center)
    queryset = _scoped(queryset, tenant_ids, "aircraft__tenant_id")
    cutoff = today + timedelta(days=HORIZON_DAYS)
    dates = list(
        queryset.exclude(status__in=MaintenanceRecord.TERMINAL_STATUSES)
        .filter(scheduled_date__isnull=False, scheduled_date__lte=cutoff)
        .values_list("scheduled_date", flat=True)
    )
    to_define = MaintenanceRecord.needing_planning(queryset).count()
    return dates, to_define


def _describe(label, counts):
    return _(
        "%(label)s: %(overdue)s overdue, %(d7)s within 7 days, %(d15)s within 15 days, "
        "%(d30)s within 30 days, %(later)s within 31 to 90 days."
    ) % {
        "label": label,
        "overdue": counts["overdue"],
        "d7": counts["due_7"],
        "d15": counts["due_15"],
        "d30": counts["due_30"],
        "later": counts["later"],
    }


def expiry_data(user, cost_center, today, tenant_ids):
    """Anillos y mapa de calor: {rings, heat_rows, heat_columns, maintenance_to_define, ...}.

    `tenant_ids` (`visible_tenant_ids(user)`, `None` = todos) es obligatorio y sin valor por defecto: un
    llamador que lo olvidara no acotaría por tenant y nadie lo notaría.
    """
    categories = visible_categories(user)
    if not categories:
        return None
    counts = {key: dict.fromkeys(LEVELS, 0) for key in categories}
    wide = {key: [0] * (1 + WEEKS) for key in categories}  # [vencido, S1..S13]
    narrow = {key: [0] * 4 for key in categories}  # [vencido, 0–30, 31–60, 61–90]

    def put(key, expiry):
        days_left = (expiry - today).days
        counts[key][level_of(expiry, today)] += 1
        if days_left < 0:
            wide[key][0] += 1
            narrow[key][0] += 1
        else:
            wide[key][_week_of(days_left)] += 1
            narrow[key][1 + _narrow_of(days_left)] += 1

    items = upcoming_expirations(
        today, today + timedelta(days=HORIZON_DAYS), cost_center, user
    )
    for item in items:
        key = SUBJECT_CATEGORY[item["subject_kind"]]
        if key in counts:
            put(key, item["date"])

    to_define = None
    if "maintenance" in counts:
        dates, to_define = _maintenance_dates(user, cost_center, today, tenant_ids)
        for expiry in dates:
            put("maintenance", expiry)

    rings = []
    for key in categories:
        c = counts[key]
        label = category_label(key)
        attend = c["overdue"] + c["due_7"] + c["due_15"] + c["due_30"]
        rings.append(
            {
                "key": key,
                "label": label,
                "icon": CATEGORY_ICON[key],
                "counts": c,
                "total": sum(c.values()),
                "attend": attend,
                "segments": [(f"id-cx-seg--{lv}", c[lv]) for lv in LEVELS],
                "levels": [
                    {
                        "key": lv,
                        "n": c[lv],
                        "symbol": LEVEL_SYMBOL[lv],
                        "tone": LEVEL_TONE[lv],
                        "label": level_label(lv),
                    }
                    for lv in LEVELS
                ],
                "title": _("%(label)s: %(attend)s to attend within 30 days")
                % {"label": label, "attend": attend},
                "desc": _describe(label, c),
            }
        )

    heat_rows = [
        {
            "key": key,
            "label": category_label(key),
            "wide": [{"n": n, "step": heat_step(n)} for n in wide[key]],
            "narrow": [{"n": n, "step": heat_step(n)} for n in narrow[key]],
        }
        for key in categories
    ]
    # Encabezados: símbolo + texto, sin depender del color. El símbolo de una semana es el del tramo
    # al que pertenece su PRIMER día (S3 empieza el día 15: ◆; S6 empieza el 36: ○).
    wide_columns = [
        {"symbol": LEVEL_SYMBOL["overdue"], "label": level_label("overdue"), "hint": ""}
    ]
    for week in range(1, WEEKS + 1):
        first = 0 if week == 1 else 7 * (week - 1) + 1
        last = min(HORIZON_DAYS, 7 * week)
        wide_columns.append(
            {
                "symbol": LEVEL_SYMBOL[level_of(today + timedelta(days=first), today)],
                "label": _("W%(n)s") % {"n": week},
                "hint": _("days %(first)s to %(last)s")
                % {"first": first, "last": last},
            }
        )
    narrow_columns = [
        {
            "symbol": LEVEL_SYMBOL["overdue"],
            "label": level_label("overdue"),
            "hint": "",
        },
        {"symbol": LEVEL_SYMBOL["due_30"], "label": _("0–30 days"), "hint": ""},
        {"symbol": LEVEL_SYMBOL["later"], "label": _("31–60 days"), "hint": ""},
        {"symbol": LEVEL_SYMBOL["later"], "label": _("61–90 days"), "hint": ""},
    ]
    return {
        "rings": rings,
        "heat_rows": heat_rows,
        "heat_wide_columns": wide_columns,
        "heat_narrow_columns": narrow_columns,
        "maintenance_to_define": to_define,
        "maintenance_url": _maintenance_url(cost_center),
    }


def _maintenance_url(cost_center):
    params = {"needs_planning": 1}
    if cost_center:
        params["cost_center"] = cost_center.pk
    return f"{reverse('maintenance-list')}?{urlencode(params)}"


def alert_ages(user, cost_center, today, tenant_ids):
    """Alertas abiertas por antigüedad con UNA agregación, o `None` sin `view_alert`.

    0–7 días = disparada hace 7 días o menos; 8–30; más de 30. «Sin responsable» es un conteo aparte,
    no una cuarta barra: es otra pregunta (¿quién la tiene?) y no suma a las edades.
    """
    if not user.has_perm("compliance.view_alert"):
        return None
    queryset = alerts_for_cost_center(
        Alert.objects.filter(is_active=True, is_resolved=False), cost_center
    )
    queryset = _scoped(queryset, tenant_ids, "alert_rule__tenant_id")
    week = today - timedelta(days=7)
    month = today - timedelta(days=30)
    agg = queryset.aggregate(
        total=Count("pk"),
        fresh=Count("pk", filter=Q(triggered_at__date__gte=week)),
        mid=Count(
            "pk", filter=Q(triggered_at__date__lt=week, triggered_at__date__gte=month)
        ),
        old=Count("pk", filter=Q(triggered_at__date__lt=month)),
        unassigned=Count("pk", filter=Q(assigned_to__isnull=True)),
    )
    bars = [
        (_("0–7 days"), agg["fresh"], "id-cx-bar--fresh"),
        (_("8–30 days"), agg["mid"], "id-cx-bar--mid"),
        (_("Over 30 days"), agg["old"], "id-cx-bar--old"),
    ]
    desc = _(
        "Open alerts by age: %(fresh)s from 0 to 7 days, %(mid)s from 8 to 30 days, "
        "%(old)s over 30 days; %(unassigned)s without an owner."
    ) % {
        "fresh": agg["fresh"],
        "mid": agg["mid"],
        "old": agg["old"],
        "unassigned": agg["unassigned"],
    }
    return {
        **agg,
        "bars": bars,
        "title": ngettext("%(count)s open alert", "%(count)s open alerts", agg["total"])
        % {"count": agg["total"]},
        "desc": desc,
        "url": reverse("alert-list"),
    }


HISTORY_MONTHS = 6
REVIEW_PERMISSION = "compliance.view_monthlycompliancereview"
# Estado del cierre -> símbolo y tono de `.id-chip--*`. Símbolo + texto además del color.
REVIEW_STATES = ("non_compliant", "pending", "completed", "unreviewed")
REVIEW_SYMBOL = {
    "non_compliant": "✕",
    "pending": "▲",
    "completed": "●",
    "unreviewed": "○",
}
REVIEW_TONE = {
    "non_compliant": "critical",
    "pending": "warning",
    "completed": "ok",
    "unreviewed": "neutral",
}


def review_status_label(key):
    return {
        "non_compliant": _("Non-compliant"),
        "pending": _("Pending review"),
        "completed": _("Compliant"),
        "unreviewed": _("Not reviewed"),
    }[key]


def closed_months(today, count=HISTORY_MONTHS):
    """Los `count` meses CERRADOS más recientes (primer día de cada uno), del más nuevo al más viejo.

    Un cierre describe un mes terminado, igual que `MonthlyReviewView._period`.
    """
    months = []
    day = today
    for _i in range(count):
        day = previous_month_start(day)
        months.append(day)
    return months


def review_history(user, cost_center, today, tenant_ids):
    """Seis meses × estado del cierre mensual (LV-262), o `None` sin `view_monthlycompliancereview`.

    Lee `MonthlyComplianceReview` tal como está (no recalcula nada): UNA agregación por (mes, estado)
    acotada por tenant y por las faenas que operan (las mismas que cuenta el cierre), y UNA cuenta de
    esas faenas para decir cuántas siguen «sin revisar». Cantidad de consultas constante: no crece con
    los datos.
    """
    if not user.has_perm(REVIEW_PERMISSION):
        return None
    sites = _scoped(operating_cost_centers(), tenant_ids, "tenant_id")
    if cost_center:
        sites = sites.filter(pk=cost_center.pk)
    operating = sites.count()
    months = closed_months(today)
    grouped = (
        MonthlyComplianceReview.objects.filter(
            is_active=True, period__in=months, cost_center__in=sites
        )
        .values("period", "status")
        .annotate(n=Count("pk"))
    )
    by_month = {month: {} for month in months}
    for row in grouped:
        by_month.setdefault(row["period"], {})[row["status"]] = row["n"]
    rows = []
    for month in months:
        counts = dict(by_month[month])
        counts["unreviewed"] = max(0, operating - sum(counts.values()))
        chips = [
            {
                "key": key,
                "n": counts[key],
                "symbol": REVIEW_SYMBOL[key],
                "tone": REVIEW_TONE[key],
                "label": review_status_label(key),
            }
            for key in REVIEW_STATES
            if counts.get(key)
        ]
        query = urlencode({"month": month.strftime("%Y-%m")})
        rows.append(
            {
                "month": month,
                "chips": chips,
                "url": f"{reverse('monthly-review')}?{query}",
            }
        )
    return {"rows": rows, "operating": operating}
