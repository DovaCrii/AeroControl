from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.db.models import Count, Q
from django.db.models.functions import TruncMonth
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.compliance.digest import bucket_for
from apps.compliance.models import Alert, AlertRule, Document, DocumentType
from apps.compliance.watchables import terminal_statuses
from apps.maintenance.models import MaintenanceRecord
from apps.operations.models import FlightPermission, FlightRecord, FlightRequest
from apps.registry.models import Aircraft, CostCenter, Operator, Qualification


def resolved_alert_keys():
    """LV-122: (tipo, registro, valor) de todo lo que la bandeja ya cerró.

    Una consulta, no una por fila: el panel se abre en cada login y esto se
    cruza contra cinco listados. Devuelve la **misma clave con que
    `generate_alerts` deduplica** desde `LV-111` — y usarla textual es lo que
    garantiza que el panel esconda ni más ni menos de lo que la bandeja
    considera cerrado.
    """
    return set(
        Alert.objects.filter(is_resolved=True, is_active=True).values_list(
            "content_type_id", "object_id", "watched_value"
        )
    )


def upcoming_expirations(today, cutoff, cost_center=None):
    """Lo que expira **hasta** `cutoff`, incluido lo que ya expiró (T5.4/U4):
    habilitaciones, credenciales DGAC, seguros JAC, documentos y permisos. Cada
    ítem lleva su enlace para que el panel deje al usuario donde puede actuar.

    Las habilitaciones, credenciales, seguros y permisos respetan el filtro por
    centro de costo; los documentos cuelgan de una relación genérica sin centro
    de costo directo, así que van siempre (el motor de alertas y el reporte los
    miran igual).

    R1.1: el "bucket" de cada ítem reusa `digest.bucket_for` -- la misma escala
    overdue/due_7/due_15/due_30 que el reporte de cumplimiento, en vez de una
    cuarta escala propia.

    **LV-120: ya no hay piso en `today`.** Las cinco consultas filtraban
    `expiry >= today`, así que **nada vencido podía aparecer nunca** -- y el
    reporte del usuario (2026-08-20) es exacto: la tarjeta decía "5 faltantes o
    vencidos" y la lista de al lado sólo mostraba los dos del 2026-09-05,
    mientras `RPA-5534` (vencido el 08-08) y `RPA-2198` (el 05-20, tres meses)
    no salían en ninguna parte. La rama `overdue` de la plantilla estaba escrita
    completa —en rojo y en negrita— y **no podía dibujarse jamás**, que es la
    señal de que el hueco estaba en los datos y no en el diseño.

    El piso no fue un descuido: el comentario que lo puso dice que sin él la
    lista mostraba "todas las habilitaciones históricamente vencidas, en una
    página que se abre en cada login". Era un problema real y la solución se
    pasó de largo -- para sacar el ruido antiguo sacó también lo urgente.

    Lo que acota ahora es **la misma regla que el motor de alertas**: se excluyen
    los registros en estado terminal, leído de `TERMINAL_STATUSES` del propio
    modelo vía `terminal_statuses()` (`LV-90`, `LV-113`). Así el panel y la
    bandeja **no pueden discrepar por construcción**, que es justo lo que el
    usuario notó al ver una alerta sin su fila en el panel; y una aeronave dada
    de baja con el seguro vencido en 2024 deja de contar sin necesidad de una
    ventana hacia atrás elegida a dedo. Un permiso vencido tampoco reaparece: al
    caducar queda en `expired`, que es terminal (`LV-83`).

    **LV-122: y tampoco aparece lo que ya se revisó y se cerró.** `LV-120` alineó
    el panel con la bandeja en una sola dirección —mostrar lo que la bandeja
    muestra— y faltaba la otra: **esconder lo que la bandeja cerró**. El usuario
    lo vio el mismo día: la credencial de `Carlos Peñailillo`, vencida el
    2025-05-02 y resuelta con el motivo *"Fuera de CC con operación RPA"*, se
    instaló en el panel para siempre — porque esa fecha ya no va a cambiar
    nunca. Sus palabras: *"que sean las no resueltas nada más o si no se llenará
    completo"*, y es literal: cada vencimiento resuelto y no renovado se queda
    en la lista, así que el panel se llena de trabajo ya hecho hasta empujar
    fuera del corte de diez filas lo que sí importa.

    Se filtra con **la misma clave con que el motor deduplica** (`LV-111`):
    (registro, valor vigilado). Eso importa por lo que **no** esconde -- una
    renovación cambia el valor, así que el vencimiento siguiente es una fila
    nueva y vuelve a mostrarse, que es exactamente la mitad que `LV-111` decidió
    no suprimir. Y esconde sólo lo **resuelto**, no "lo que no tiene alerta
    abierta": un vencimiento que el motor todavía no miró (se genera a las
    06:00) no tiene alerta ninguna y tiene que verse igual.
    """
    triaged = resolved_alert_keys()
    items = []

    def add(model, record_pk, item):
        """Agrega el ítem salvo que su alerta ya esté resuelta.

        Se filtra acá y no al final para no construir la fila que se va a
        descartar, y con `get_for_model` —que Django cachea por modelo— para no
        pagar una consulta de `ContentType` por listado.
        """
        key = (
            ContentType.objects.get_for_model(model).id,
            record_pk,
            item["date"].isoformat(),
        )
        if key not in triaged:
            items.append(item)

    quals = Qualification.objects.filter(
        is_active=True, expiry_date__lte=cutoff
    ).select_related("operator", "qualification_type")
    if cost_center:
        quals = quals.filter(operator__cost_center=cost_center)
    for qual in quals:
        add(
            Qualification,
            qual.pk,
            {
                "kind": _("Qualification"),
                "label": f"{qual.operator} — {qual.qualification_type}",
                "date": qual.expiry_date,
                "bucket": bucket_for(qual.expiry_date, today),
                "url": reverse("operator-detail", args=[qual.operator_id]),
            },
        )

    # LV-29: the DGAC vigencias join the same window -- a lapsing credential or
    # JAC insurance is exactly what "upcoming expirations" is for.
    credentials = Operator.objects.filter(is_active=True, credential_expiry__lte=cutoff)
    if cost_center:
        credentials = credentials.filter(cost_center=cost_center)
    for operator in credentials:
        add(
            Operator,
            operator.pk,
            {
                "kind": _("DGAC credential"),
                "label": operator.full_name,
                "date": operator.credential_expiry,
                "bucket": bucket_for(operator.credential_expiry, today),
                "url": reverse("operator-detail", args=[operator.pk]),
            },
        )

    insured = Aircraft.objects.filter(
        is_active=True, insurance_expiry__lte=cutoff
    ).exclude(status__in=terminal_statuses(Aircraft))
    if cost_center:
        insured = insured.filter(cost_center=cost_center)
    for aircraft in insured:
        add(
            Aircraft,
            aircraft.pk,
            {
                "kind": _("JAC insurance"),
                "label": aircraft.registration,
                "date": aircraft.insurance_expiry,
                "bucket": bucket_for(aircraft.insurance_expiry, today),
                "url": reverse("aircraft-detail", args=[aircraft.pk]),
            },
        )

    documents = Document.objects.filter(
        is_active=True,
        is_current_version=True,
        expiry_date__isnull=False,
        expiry_date__lte=cutoff,
    ).select_related("doc_type")
    for document in documents:
        add(
            Document,
            document.pk,
            {
                "kind": _("Document"),
                "label": document.title,
                "date": document.expiry_date,
                "bucket": bucket_for(document.expiry_date, today),
                "url": reverse("document-detail", args=[document.pk]),
            },
        )

    permissions = FlightPermission.objects.filter(
        is_active=True, valid_until__lte=cutoff
    ).exclude(status__in=terminal_statuses(FlightPermission))
    if cost_center:
        permissions = permissions.filter(cost_center=cost_center)
    for permission in permissions:
        add(
            FlightPermission,
            permission.pk,
            {
                "kind": _("Flight permission"),
                # R1.2/R2.2/R2.3: used to be `permission_number or "Pending
                # DGAC folio"` -- permission_number is None until the DGAC
                # folio arrives (LV-39), and rendered as-is the row read
                # "Flight permission None" (verified live on the demo).
                # internal_folio is assigned at creation and never blank.
                "label": permission.internal_folio,
                "date": permission.valid_until,
                "bucket": bucket_for(permission.valid_until, today),
                "url": reverse("permission-detail", args=[permission.pk]),
            },
        )

    items.sort(key=lambda item: item["date"])
    return items


def panel_readiness(today, cost_center=None):
    """LV-89: can we operate today? -- as three counts, not two pie charts.

    Replaces "Aircraft by status" (two slices) and "Permissions by status" (one
    bar), which took a third of the screen to restate numbers the tiles above
    already showed. These three answer the question the panel is opened for, and
    each is a **fraction with its shortfall named**: a percentage alone tells you
    something is wrong without telling you how much work it is to fix.

    Nothing here is new data. Fleet availability reuses the target agreed with
    the user on 2026-08-12 (`FLEET_AVAILABILITY_TARGET`, 90%), and the other two
    read the same fields the alert engine watches -- so a number on the panel and
    an alert in the inbox can never disagree.

    `retired` is excluded from the fleet denominator for the same reason
    `kpis.fleet_availability` excludes it: a decommissioned aircraft is not
    unavailable, it left the fleet, and counting it would make the figure sag
    permanently for a good decision.
    """
    from apps.compliance.kpis import FLEET_AVAILABILITY_TARGET

    horizon = today + timedelta(days=30)

    fleet = Aircraft.objects.filter(is_active=True).exclude(status="retired")
    operators = Operator.objects.filter(is_active=True)
    if cost_center:
        fleet = fleet.filter(cost_center=cost_center)
        operators = operators.filter(cost_center=cost_center)

    fleet_total = fleet.count()
    flyable = fleet.filter(status="active").count()
    # "Up to date" means the policy is on file *and* still valid. An aircraft
    # whose insurance lapsed yesterday is not covered, whatever its status says.
    insured = fleet.filter(
        insurance_status=Aircraft.INSURANCE_STATUS_ACTIVE,
        insurance_expiry__gte=today,
    ).count()
    operators_total = operators.count()
    credentialed = operators.filter(credential_expiry__gte=today).count()

    return {
        "readiness": [
            {
                "label": _("Fleet available"),
                "count": flyable,
                "total": fleet_total,
                "pct": round(flyable * 100 / fleet_total, 1) if fleet_total else None,
                "target": FLEET_AVAILABILITY_TARGET,
                "shortfall": fleet_total - flyable,
                "shortfall_label": _("not flyable"),
                "url": reverse("aircraft-list"),
            },
            {
                "label": _("Insurance up to date"),
                "count": insured,
                "total": fleet_total,
                "pct": round(insured * 100 / fleet_total, 1) if fleet_total else None,
                "target": None,
                "shortfall": fleet_total - insured,
                "shortfall_label": _("missing or lapsed"),
                "soon": fleet.filter(
                    insurance_expiry__gte=today, insurance_expiry__lte=horizon
                ).count(),
                "url": reverse("aircraft-list"),
            },
            {
                "label": _("Credentials up to date"),
                "count": credentialed,
                "total": operators_total,
                "pct": (
                    round(credentialed * 100 / operators_total, 1)
                    if operators_total
                    else None
                ),
                "target": None,
                "shortfall": operators_total - credentialed,
                "shortfall_label": _("missing or lapsed"),
                "soon": operators.filter(
                    credential_expiry__gte=today, credential_expiry__lte=horizon
                ).count(),
                "url": reverse("operator-list"),
            },
        ]
    }


def panel_forecast(today, cost_center=None, user=None):
    """R8.4: the weather for the operation's next flight, for the panel.

    Until now the forecast only existed on a geo plan's page, and only when that
    plan had an area *and* a linked permit with a date -- buried, for something
    that gets consulted before every flight. What makes it reachable here is
    OPS-4: the permit carries its own `latitude`/`longitude`, so no geo plan is
    needed.

    **One call, never N.** The panel is opened by everyone, every day, so this
    resolves a single location and asks for a single (coordinate, day) -- the
    same cached entry the whole office shares. Showing every upcoming permit
    would be one outgoing request per permit per page load, which is the shape
    this project already paid for twice (V.18/V.19).

    Where the location comes from, in order:

    1. the next permit that is not finished or denied and does carry
       coordinates -- the actual next flight, and the day is clamped to today so
       a permit whose window is already open forecasts today rather than a start
       date in the past;
    2. failing that, the selected cost center's own site coordinates (R8.4
       option (c)) -- which is what makes the panel's cost-center filter double
       as the location selector.

    Returns a dict with `weather` set to None whenever the feature is off, no
    location is on file, or the provider did not answer; the card then does not
    render at all. Never raises: this feeds the page every login lands on.

    Each source is gated on the `view_*` of the model it reads (AGENTS.md's
    read contract): the card names a permit folio, its site and its aircraft, so
    it must not become a way around `view_flightpermission`.
    """
    from apps.core.weather import forecast_for

    def may_see(permission_codename):
        return user is None or user.has_perm(permission_codename)

    permissions = FlightPermission.objects.filter(
        is_active=True,
        latitude__isnull=False,
        longitude__isnull=False,
        valid_until__gte=today,
    ).exclude(
        # None of these has a flight left to plan for: one already happened,
        # one is not going to, and one ran out of time (LV-83). The date filter
        # above already rules the expired ones out; listing the status keeps the
        # intent readable rather than relying on that coincidence.
        status__in=[
            FlightPermission.STATUS_COMPLETED,
            FlightPermission.STATUS_DENIED,
            FlightPermission.STATUS_EXPIRED,
        ]
    )
    if cost_center:
        permissions = permissions.filter(cost_center=cost_center)
    permission = (
        permissions.select_related("cost_center").order_by("valid_from").first()
        if may_see("operations.view_flightpermission")
        else None
    )

    if permission is not None:
        # Bounded on purpose (one query, three values): the card names what is
        # flying, but a permit with a large fleet must not turn into a wall.
        fleet = list(
            permission.aircraft_fleet.filter(is_active=True).values_list(
                "registration", flat=True
            )[:3]
        )
        return {
            "weather": forecast_for(
                permission.latitude,
                permission.longitude,
                max(permission.valid_from, today),
            ),
            "weather_date": max(permission.valid_from, today),
            "weather_source": "permission",
            "weather_place": permission.area_name or permission.location,
            "weather_folio": permission.internal_folio,
            "weather_fleet": ", ".join(fleet),
            "weather_url": reverse("permission-detail", args=[permission.pk]),
        }

    coordinates = (
        cost_center.coordinates
        if cost_center and may_see("registry.view_costcenter")
        else None
    )
    if coordinates is None:
        # No upcoming located flight and no site on file. Deliberately not a
        # guessed location: a forecast for the wrong place, next to a real date,
        # is worse than no card.
        return {"weather": None}
    latitude, longitude = coordinates
    return {
        "weather": forecast_for(latitude, longitude, today),
        "weather_date": today,
        "weather_source": "cost_center",
        "weather_place": str(cost_center),
        "weather_url": reverse("costcenter-detail", args=[cost_center.pk]),
    }


@login_required
def dashboard(request):
    # OPS-8: an optional global filter by cost center. Silently ignored if it
    # does not resolve to a real, active cost center -- same "malformed filter
    # is a no-op, not an error" convention SearchMixin already uses.
    selected_cost_center = None
    cost_center_id = request.GET.get("cost_center")
    if cost_center_id:
        selected_cost_center = CostCenter.objects.filter(
            pk=cost_center_id, is_active=True
        ).first()
    cost_centers = CostCenter.objects.filter(is_active=True).order_by("code")

    # --- Summary counts ---
    aircraft_qs = Aircraft.objects.filter(is_active=True)
    operator_qs = Operator.objects.filter(is_active=True)
    if selected_cost_center:
        aircraft_qs = aircraft_qs.filter(cost_center=selected_cost_center)
        operator_qs = operator_qs.filter(cost_center=selected_cost_center)
    aircraft_count = aircraft_qs.filter(status="active").count()
    operator_count = operator_qs.count()
    alert_count = Alert.objects.filter(is_active=True, is_resolved=False).count()

    # --- Compliance module setup state ---
    # The old onboarding card required *everything* to be empty, so with the
    # registry loaded it could never fire again - while compliance sat at zero
    # and the tiles read "0 alerts" as if all was well. These three steps are
    # what turns the digest, the alerts and the report from built to working.
    compliance_setup = {
        "doc_types": DocumentType.objects.filter(is_active=True).exists(),
        "documents": Document.objects.filter(is_active=True).exists(),
        "rules": AlertRule.objects.filter(is_active=True).exists(),
    }
    compliance_incomplete = not all(compliance_setup.values())

    # --- Expirations ---
    # LV-120: acotado por arriba (30 días) y, por abajo, por el **estado
    # terminal** del registro en vez de por la fecha de hoy -- ver
    # `upcoming_expirations`. El piso en `today` es lo que hacía que un seguro
    # vencido no apareciera nunca en el panel aunque su alerta sí estuviera en
    # la bandeja. Sólo la lista visible se recorta; los contadores son reales.
    today = timezone.localdate()
    cutoff = today + timedelta(days=30)
    all_expirations = upcoming_expirations(today, cutoff, selected_cost_center)
    # Dos contadores y no uno: la tarjeta dice "Vence en 30 días", y meter ahí
    # lo ya vencido la volvería falsa -- la misma forma de defecto que `LV-118`
    # y `LV-119` corrigieron en la bandeja y en los correos. Lo vencido tiene
    # tarjeta propia, y sólo aparece cuando hay algo que mostrar.
    overdue_count = sum(1 for item in all_expirations if item["bucket"] == "overdue")
    expiring_count = len(all_expirations) - overdue_count
    expirations = all_expirations[:10]

    # --- LV-30: monthly compliance snapshot (latest period on record) ---
    # Compliant / total cost centers for the most recent reviewed month, with a
    # link into the monthly-review page. Absent (card hidden) until the first
    # month closes and check_monthly_records creates reviews.
    from django.db.models import Max

    from apps.compliance.models import MonthlyComplianceReview

    monthly_records = None
    review_qs = MonthlyComplianceReview.objects.filter(is_active=True)
    if selected_cost_center:
        review_qs = review_qs.filter(cost_center=selected_cost_center)
    latest_period = review_qs.aggregate(latest=Max("period"))["latest"]
    if latest_period:
        period_reviews = review_qs.filter(period=latest_period)
        monthly_records = {
            "period": latest_period.strftime("%Y-%m"),
            "total": period_reviews.count(),
            "compliant": period_reviews.filter(
                status=MonthlyComplianceReview.STATUS_COMPLETED
            ).count(),
            "pending": period_reviews.filter(
                status=MonthlyComplianceReview.STATUS_PENDING
            ).count(),
        }

    # LV-78/LV-89: the two Kanban charts are gone. The board was decommissioned
    # on 2026-08-12 and taken out of the menu, yet the panel kept drawing its
    # stages ("Recopilando antecedentes", "Enviado a DGAC") every day -- a chart
    # of a board nobody can reach, which reads as a live part of the operation.
    # This is step 1 of the retirement: the board loses its last surface without
    # a single row being deleted.

    # Charts label their slices with the human-readable choice, not the raw
    # database value (the legend used to read "active"/"in_progress"), and the
    # aggregations exclude archived rows like the rest of the app.
    def labelled(rows, field, choices):
        labels = dict(choices)
        return [
            {field: str(labels.get(row[field], row[field])), "count": row["count"]}
            for row in rows
        ]

    # --- Chart: Aircraft by status ---
    aircraft_by_status = labelled(
        aircraft_qs.values("status").annotate(count=Count("id")).order_by("status"),
        "status",
        Aircraft.STATUS_CHOICES,
    )

    # --- Chart: Permissions by status ---
    permissions_qs = FlightPermission.objects.filter(is_active=True)
    if selected_cost_center:
        permissions_qs = permissions_qs.filter(cost_center=selected_cost_center)
    perms_by_status = labelled(
        permissions_qs.values("status").annotate(count=Count("id")).order_by("status"),
        "status",
        FlightPermission.STATUS_CHOICES,
    )

    # --- Chart: Maintenance by type ---
    maintenance_qs = MaintenanceRecord.objects.filter(is_active=True)
    if selected_cost_center:
        maintenance_qs = maintenance_qs.filter(
            aircraft__cost_center=selected_cost_center
        )
    maint_by_type = labelled(
        maintenance_qs.values("maintenance_type")
        .annotate(count=Count("id"))
        .order_by("maintenance_type"),
        "maintenance_type",
        MaintenanceRecord.TYPES,
    )

    # --- LV-8e: maintenance that still needs planning ---
    # "To be defined" or missing a scheduled date, and not yet completed. The
    # alert engine only watches date *expiry*, so this absence is surfaced here
    # (and in the compliance report) instead of as an Alert object.
    incomplete_maintenance_count = (
        maintenance_qs.filter(status__in=["pending", "in_progress"])
        .filter(Q(maintenance_type="to_be_defined") | Q(scheduled_date__isnull=True))
        .count()
    )

    # --- R9.6: solicitudes SIGO presentadas y sin respuesta ---
    # Trabajo detenido en manos de un tercero: se presentó y nadie contestó. No
    # es una alerta —el motor vigila **vencimientos**, y acá no vence nada— sino
    # el mismo hueco que `LV-8e` resuelve para la mantención sin planificar: una
    # ausencia que ninguna regla de fecha puede ver.
    #
    # **Sin umbral inventado.** Se cuentan todas las presentadas y se muestra la
    # más antigua; poner "atrasada a los N días" exigiría un plazo de respuesta
    # de la DGAC que nadie confirmó, y un umbral inventado que resulta corto
    # enseña a ignorar la tarjeta.
    request_qs = FlightRequest.objects.filter(
        is_active=True, status=FlightRequest.STATUS_FILED
    )
    if selected_cost_center:
        request_qs = request_qs.filter(cost_center=selected_cost_center)
    awaiting_requests = list(request_qs.order_by("filed_on")[:5])
    awaiting_count = request_qs.count()
    longest_wait = next(
        (
            request.days_waiting()
            for request in awaiting_requests
            if request.days_waiting() is not None
        ),
        None,
    )

    # --- Chart: Monthly flight records (last 6 months) ---
    six_months_ago = timezone.localdate() - timedelta(days=180)
    flight_records_qs = FlightRecord.objects.filter(
        is_active=True, actual_date__gte=six_months_ago
    )
    if selected_cost_center:
        flight_records_qs = flight_records_qs.filter(
            aircraft__cost_center=selected_cost_center
        )
    monthly_flights = list(
        flight_records_qs.annotate(month=TruncMonth("actual_date"))
        .values("month")
        .annotate(count=Count("id"))
        .order_by("month")
    )

    chart_data = {
        "permissions_by_status": perms_by_status,
        "maintenance_by_type": maint_by_type,
        "aircraft_by_status": aircraft_by_status,
        "monthly_flights": monthly_flights,
    }

    context = {
        "aircraft_count": aircraft_count,
        "operator_count": operator_count,
        "alert_count": alert_count,
        "incomplete_maintenance_count": incomplete_maintenance_count,
        "awaiting_requests": awaiting_requests,
        "awaiting_count": awaiting_count,
        "longest_wait": longest_wait,
        "expirations": expirations,
        "expiring_count": expiring_count,
        "overdue_count": overdue_count,
        "chart_data": chart_data,
        "compliance_setup": compliance_setup,
        "compliance_incomplete": compliance_incomplete,
        "cost_centers": cost_centers,
        "selected_cost_center": selected_cost_center,
        "monthly_records": monthly_records,
    }
    context.update(panel_readiness(today, selected_cost_center))
    # R8.4: after the rest of the context, so a provider hiccup cannot get in
    # the way of anything the panel already showed.
    context.update(panel_forecast(today, selected_cost_center, request.user))
    return render(request, "dashboard/index.html", context)
