from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.db.models.functions import TruncMonth
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.compliance.reports import alerts_for_cost_center
from apps.compliance.models import Alert, AlertRule, Document, DocumentType

# LV-240: `upcoming_expirations` y su tabla de permisos **se mudaron al dominio**
# (`apps.compliance.expirations`). Vivían acá, y por eso el correo diario recorría
# dos de las seis fuentes que esta pantalla recorre: `compliance.digest` no podía
# importar de una vista que a su vez lo importa a él. Se siguen usando igual.
from apps.compliance.expirations import upcoming_expirations
from apps.maintenance.models import MaintenanceRecord
from apps.operations.models import FlightRecord, FlightRequest
from apps.registry.models import Aircraft, CostCenter, Operator
from apps.registry.selectors import operational_fleet, operational_roster


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
    from apps.compliance.kpis import FLEET_AVAILABILITY_TARGET, permit_counts

    horizon = today + timedelta(days=30)

    # LV-242: las exclusiones se leen de `registry.selectors`, que es de donde las
    # lee también el filtro `?insurance=` de la lista. Vivían escritas acá, y la
    # tarjeta llevaba al padrón sin filtrar — en cuanto el clic empezó a filtrar de
    # verdad, dos copias del criterio habrían hecho que el número de la tarjeta y
    # las filas del listado dejaran de coincidir. El porqué de cada exclusión está
    # en el docstring de `operational_fleet`.
    # LV-229 (el porqué de excluir las faenas que no vuelan, con el caso de
    # `RPA-2019` en `CC110` que lo motivó) vive ahora en ese docstring, junto al
    # criterio que aplica.
    fleet = operational_fleet()
    operators = operational_roster()

    # **El padrón que se cuenta es el que existía en `today`, no el de hoy.**
    #
    # `today` ya mandaba sobre las comparaciones de vencimiento —una credencial
    # vence *respecto de* esa fecha— pero no sobre la población: los dos
    # `filter(is_active=True)` de arriba traían el padrón **actual**. Con la
    # fecha de hoy da igual; con la de un mes cerrado, no. Medido en producción:
    # el payload de agosto devolvía **42 operadores** y el informe emitido a la
    # DGAC decía **41**. Un informe de agosto generado en diciembre habría dado
    # otra cifra todavía, que es justo lo que congelar el dato viene a evitar.
    #
    # Va sin parámetro y siempre: `created_at__date <= today` es verdadero para
    # toda fila cuando `today` es hoy, así que **el panel no cambia** — y una
    # segunda función "igual pero con corte" es cómo el panel y el informe
    # empiezan a discrepar, la lección que `LV-188` y `LV-201` ya dejaron.
    #
    # ⚠️ **Lo que este corte NO hace, y hay que decirlo porque el informe va
    # firmado**: no reconstruye el padrón de esa fecha, sólo **deja de contar lo
    # que todavía no existía**. Sin historial de `is_active` no se sabe quién
    # estaba archivado entonces, y si una ficha se cargó a destiempo su
    # `created_at` es la fecha de carga y no la del hecho. Es una cota superior
    # honesta, no una foto.
    fleet = fleet.filter(created_at__date__lte=today)
    operators = operators.filter(created_at__date__lte=today)

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

    # LV-201: los permisos vuelven a la fila, y vuelven porque el usuario los
    # pidió: *"es importante mencionar tanto en los reportes como en el dashboard
    # la cantidad de permisos vigentes, atrasados, o el indicador en general"*. La
    # fila mostraba flota, seguros y credenciales — y ninguna cifra del objeto que
    # esta aplicación existe para tramitar.
    #
    # No es una tarjeta nueva suelta: el docstring de arriba cuenta que `LV-89`
    # **retiró** un gráfico "Permissions by status" porque restataba números sin
    # decir qué hacer. Vuelven con la forma que esa fila fijó, una fracción con su
    # faltante nombrado.
    #
    # **El cálculo vive en `kpis.permit_counts` y no acá**, aunque acá sea el único
    # lugar donde hoy se dibuja: el pedido nombraba el panel **y** los informes, y
    # dos cálculos separados de la misma cifra es exactamente cómo el panel y el
    # informe terminan diciendo números distintos. `LV-188` acabó de mostrar el
    # costo de esa separación en otra función.
    permits = permit_counts(today, cost_center)

    return {
        "readiness": [
            {
                # LV-129: clave estable para direccionar la tarjeta sin pasar
                # por su etiqueta, que es traducible -- un test que compare
                # contra el texto pasa o falla según el idioma activo, que es lo
                # que `LV-95` dejó escrito y este archivo volvió a pagar.
                "key": "fleet",
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
                "key": "insurance",
                "label": _("Insurance up to date"),
                "count": insured,
                "total": fleet_total,
                "pct": round(insured * 100 / fleet_total, 1) if fleet_total else None,
                "target": None,
                "shortfall": fleet_total - insured,
                # LV-129: "faltantes o vencidos" era una sola cifra para dos
                # cosas que se arreglan distinto -- cargar una fecha que nadie
                # ingresó, o renovar una póliza que caducó. Sumadas, además, no
                # cuadraban con ninguna otra tarjeta del panel: los "faltantes"
                # no generan alerta (`LV-29`: un nulo es "nunca se ingresó") ni
                # aparecen en la lista de vencimientos, así que el 5 de acá no
                # tenía cómo conversar con el 3 de más arriba.
                "missing": fleet.filter(insurance_expiry__isnull=True).count(),
                "lapsed": fleet.filter(insurance_expiry__lt=today).count(),
                # LV-241: el faltante que **no** es ni vencido ni sin fecha: la
                # póliza tiene fecha por delante y su estado no es `active`. Sin
                # rótulo la tarjeta escribía el número solo —el mismo defecto que el
                # usuario reportó en permisos, que estas tres filas compartían— y
                # ese caso no es raro: es una póliza en trámite o dada de baja.
                "shortfall_label": _("without valid cover"),
                "soon": fleet.filter(
                    insurance_expiry__gte=today, insurance_expiry__lte=horizon
                ).count(),
                # LV-242: el clic lleva a **lo que falta**, no al padrón entero.
                # La tarjeta dice cuántos no están al día; su destino natural es
                # esa lista y no las dieciséis aeronaves para buscarlas a ojo.
                # Cuando no falta ninguno el enlace se queda en la lista completa:
                # un filtro que no recorta nada es un filtro que confunde.
                "url": (
                    f"{reverse('aircraft-list')}?insurance=attention"
                    if fleet_total - insured
                    else reverse("aircraft-list")
                ),
            },
            {
                "key": "credentials",
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
                "missing": operators.filter(credential_expiry__isnull=True).count(),
                "lapsed": operators.filter(credential_expiry__lt=today).count(),
                # LV-241: ver la fila de seguros. Acá el resto son las credenciales
                # que vencen hoy mismo, que no caen en `lapsed` (`__lt`) ni en
                # `missing` — un borde de un día, pero el que deja el número mudo.
                "shortfall_label": _("not up to date"),
                "soon": operators.filter(
                    credential_expiry__gte=today, credential_expiry__lte=horizon
                ).count(),
                # LV-242: ver la fila de seguros. Acá pesaba más, porque el padrón
                # es de cuarenta y cinco personas y la tarjeta llegó a decir
                # "7 sin fecha cargada".
                "url": (
                    f"{reverse('operator-list')}?credential=attention"
                    if operators_total - credentialed
                    else reverse("operator-list")
                ),
            },
            {
                "key": "permits",
                "label": _("Permits in force"),
                "count": permits["in_force"],
                "total": permits["total"],
                "pct": permits["pct"],
                "target": None,
                "shortfall": permits["total"] - permits["in_force"],
                # LV-241: **esta fila no tenía rótulo para su faltante**, y con
                # `lapsed` y `awaiting` en cero la plantilla caía a la rama
                # `{{ shortfall }} {{ shortfall_label }}` y escribía el número
                # solo. El usuario lo vio en pantalla: *"13/14 · 1 · 2 vencen en
                # 30 días"* — un 1 sin decir de qué.
                "shortfall_label": _("not in force today"),
                # LV-241: el aprobado que nadie cerró **más** el caducado del mes en
                # curso. Se suman para la tarjeta porque para quien la mira son el
                # mismo trabajo —un permiso sin vigencia que hay que renovar— y
                # siguen separados en `permit_counts` porque se diagnostican
                # distinto: uno delata que el trabajo nocturno no corrió.
                "lapsed": permits["lapsed"] + permits["expired_this_month"],
                # LV-241: el permiso **aprobado que todavía no empieza**. Se
                # calculaba desde `LV-233` y no se dibujaba en ninguna parte, así
                # que era la explicación del número huérfano de arriba y estaba a
                # una línea. El comentario de `permit_counts` ya defendía
                # mostrarlo: *"un número en la casilla equivocada es peor que un
                # número menos"* — y no dibujarlo es la tercera opción, que es
                # peor que las dos.
                "not_started": permits["not_started"],
                # `awaiting` es propio de esta fila: las otras tres no tienen a
                # quién esperar. La plantilla lo dibuja junto a `lapsed` en vez de
                # en su lugar, porque son dos trabajos distintos y sumarlos sería
                # el defecto que `LV-129` corrigió en la tarjeta de seguros.
                "awaiting": permits["awaiting"],
                "soon": permits["soon"],
                "url": reverse("permission-list"),
            },
        ]
    }


# LV-237: acá vivían `panel_forecast` y sus tres ayudantes (`R8.4`, `LV-147`).
#
# `LV-216` retiró la tarjeta del clima de la plantilla a pedido del usuario —*"no es
# necesario que muestre el clima, ya el dashboard lo veo innecesario"*— y **borró sólo
# la mitad**: la vista siguió llamando `panel_forecast` en cada carga durante un mes,
# resolviendo candidatos de permisos, sitios con coordenadas y el plan geo ligado para
# un contexto que ninguna plantilla volvía a leer. Nueve consultas por carga de la
# primera pantalla de la aplicación, más la posible salida a Open-Meteo cuando la
# caché estaba fría.
#
# Es la razón por la que `test_lv237_panel_query_budget.py` existe: retirar una
# sección de la pantalla y dejar viva su consulta no se nota mirando la pantalla.
#
# **Lo que NO se fue**: `apps/core/weather.forecast_for` y la revisión meteorológica
# de la ficha del plan geo (`R8.1`/`R8.2`, `WeatherReview`), que es donde el pronóstico
# **queda registrado como evidencia** y era el único camino real desde `LV-216`. Un
# pronóstico no es reproducible después: preguntarle al proveedor por una fecha pasada
# devuelve otra corrida del modelo, o nada.
#
# Reponer la tarjeta es recuperar este bloque y el de la plantilla de git, en el commit
# anterior a esta fila.
@login_required
def dashboard(request):
    # OPS-8: an optional global filter by cost center. Silently ignored if it
    # does not resolve to a real, active cost center -- same "malformed filter
    # is a no-op, not an error" convention SearchMixin already uses.
    selected_cost_center = None
    cost_center_id = request.GET.get("cost_center")
    if cost_center_id:
        # LV-146: el `try/except` arregla un 500 vigente. "No-op silencioso"
        # cubría el UUID válido que no existe, el archivado y el de otro tenant —
        # pero no `?cost_center=abc`: un valor que no es UUID hace que
        # `filter(pk=...)` sobre una pk `UUIDField` levante `ValidationError`
        # **dentro** de la consulta, y eso no lo atrapa el `.first()`. Una URL
        # guardada, un autocompletado del navegador o un bot probando query
        # strings tiraban la primera pantalla de la app.
        try:
            selected_cost_center = CostCenter.objects.filter(
                pk=cost_center_id, is_active=True
            ).first()
        except (ValueError, ValidationError):
            selected_cost_center = None

    # `UX-17`: la faena elegida se recuerda. Quien trabaja una faena la vuelve a
    # elegir en cada login, y el panel es la primera pantalla del día.
    #
    # **En la sesión y no en una columna del usuario**: es una comodidad de
    # navegación, no una preferencia del negocio, y una columna la convertiría en
    # dato que alguien tiene que administrar.
    #
    # ⚠️ **La rama se elige por si el parámetro *viene*, no por si trae valor**, y
    # ésa es la distinción que hace que el recuerdo se pueda apagar: llegar sin
    # `cost_center` es abrir el panel de nuevo —y ahí se restaura—, mientras que
    # llegar con `?cost_center=` vacío es haber pedido "todas" a propósito, y eso
    # tiene que **borrar** el recuerdo. Sin separarlas, la única forma de volver a
    # verlo todo sería cerrar sesión.
    if "cost_center" in request.GET:
        # Se guarda la que resolvió de verdad y no la cadena cruda, así una faena
        # archivada deja de recordarse sola en vez de fijar un filtro que ya no
        # existe.
        if selected_cost_center is not None:
            request.session["dashboard_cost_center"] = str(selected_cost_center.pk)
        else:
            request.session.pop("dashboard_cost_center", None)
    else:
        remembered = request.session.get("dashboard_cost_center")
        if remembered:
            try:
                selected_cost_center = CostCenter.objects.filter(
                    pk=remembered, is_active=True
                ).first()
            except (ValueError, ValidationError):
                selected_cost_center = None
            if selected_cost_center is None:
                request.session.pop("dashboard_cost_center", None)
    cost_centers = CostCenter.objects.filter(is_active=True).order_by("code")

    # --- Summary counts ---
    aircraft_qs = Aircraft.objects.filter(is_active=True)
    operator_qs = Operator.objects.filter(is_active=True)
    if selected_cost_center:
        aircraft_qs = aircraft_qs.filter(cost_center=selected_cost_center)
        operator_qs = operator_qs.filter(cost_center=selected_cost_center)
    aircraft_count = aircraft_qs.filter(status="active").count()
    operator_count = operator_qs.count()
    # LV-129: respeta el filtro por centro de costo, como el resto de la fila.
    # Antes contaba las alertas de toda la operación, así que elegir una faena
    # cambiaba todas las tarjetas menos ésta — un número ajeno al filtro puesto
    # al lado de otros que sí lo obedecen.
    alert_count = alerts_for_cost_center(
        Alert.objects.filter(is_active=True, is_resolved=False), selected_cost_center
    ).count()

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
    # LV-206: el estado por faena sale de `kpis`, la misma casa que
    # `permit_counts` — un solo lugar donde vive "qué es un permiso vigente".
    from apps.compliance.kpis import permit_status_by_cost_center

    today = timezone.localdate()
    cutoff = today + timedelta(days=30)
    # LV-191: `request.user`, o la lista nombra permisos, matrículas, personas y
    # documentos que los permisos del usuario no le dan. Lo tapaba por accidente
    # el guard del onboarding, que escondía la sección entera cuando la base
    # estaba vacía — un control de acceso que no era uno, y que `LV-187` retiró.
    all_expirations = upcoming_expirations(
        today, cutoff, selected_cost_center, request.user
    )
    # Dos contadores y no uno: la tarjeta dice "Vence en 30 días", y meter ahí
    # lo ya vencido la volvería falsa -- la misma forma de defecto que `LV-118`
    # y `LV-119` corrigieron en la bandeja y en los correos. Lo vencido tiene
    # tarjeta propia, y sólo aparece cuando hay algo que mostrar.
    overdue_count = sum(1 for item in all_expirations if item["bucket"] == "overdue")
    expiring_count = len(all_expirations) - overdue_count
    expirations = all_expirations[:10]

    # LV-187: si se dibuja la tarjeta "Comienza tu operación" en vez del panel.
    #
    # Se calcula acá y no en la plantilla porque son cinco términos y ya iba mal
    # con cuatro: la condición vivía como `{% if not aircraft_count and not
    # operator_count and not alert_count and not stages %}`, y **`stages` nunca
    # existió en este contexto** — un cuarto término que parecía proteger algo y
    # era condición muerta desde algún refactor. Un `{% if %}` que nadie puede
    # leer de un vistazo es donde se esconde eso.
    #
    # **Los vencimientos entran en la condición.** No entraban, y el guard es
    # una decisión sobre si mostrar el panel: sin ellos, una operación con
    # documentos cargados y sin flota todavía —el orden real en que se carga,
    # porque los documentos de empresa no esperan a las aeronaves— veía el
    # onboarding con vencimientos reales detrás. La familia de `LV-120`.
    #
    # **Y sólo sin filtro por faena.** Los tres contadores lo respetan, así que
    # elegir una faena sin flota ni padrón cumplía la condición y escondía el
    # panel entero: "Comienza tu operación" y "1. Crear un centro de costo" a una
    # operación con 16 aeronaves, mientras la lista de al lado tenía vencimientos
    # de esa faena que no se dibujaban. Con una faena elegida lo que corresponde
    # es el panel con sus vacíos propios —"Nada expirado ni por vencer"—, que
    # dice la verdad: esta faena no tiene registros, no "no tienes operación".
    show_onboarding = not (
        selected_cost_center
        or aircraft_count
        or operator_count
        or alert_count
        or overdue_count
        or expiring_count
    )

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

    # LV-237: acá se agregaban "Aeronaves por estado" y "Permisos por estado".
    #
    # `LV-89` retiró los dos gráficos de la plantilla —restataban números que las
    # tarjetas de arriba ya mostraban— y las dos agregaciones se quedaron: se
    # calculaban, se serializaban al HTML en `#chart-data` y **ningún gráfico las
    # leía**. El propio `static/js/dashboard.js` lo dejó escrito: seguían ahí *"porque
    # un test lee `permissions_by_status` como evidencia del filtro por faena"*.
    #
    # Un test no debería fijar la forma del contexto de producción, y menos cobrando
    # dos agregaciones por inicio de sesión. La evidencia del filtro se lee ahora de
    # `readiness` —su fila `permits` respeta `selected_cost_center`—, que es un dato
    # que la pantalla **sí** dibuja: si mañana deja de filtrar, el test cae *y* se ve.
    #
    # De paso dejan de viajar al navegador dos distribuciones de estado que la página
    # no usa para nada.

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
        "maintenance_by_type": maint_by_type,
        "monthly_flights": monthly_flights,
    }

    # `UX-15`: **qué está pasando hoy**, no sólo qué vence.
    #
    # Es lo que distingue un panel de cumplimiento de un centro de operaciones:
    # todo lo demás de esta pantalla contesta por vigencias y trabajo pendiente,
    # y ninguna tarjeta decía si hoy voló alguien. Criterio de la fila: *"sale de
    # datos existentes, sin modelo nuevo"* — y así es: `FlightRecord` ya guarda
    # la fecha real del vuelo.
    #
    # Por `actual_date` y no por `created_at`: la bitácora se escribe **después**
    # del vuelo, a veces al día siguiente, así que contar por fecha de carga
    # diría "0 operaciones hoy" en una jornada que sí voló. Es la misma
    # distinción que `LV-234` acaba de dejar cara: contar por cuándo se registró
    # en vez de por cuándo ocurrió.
    # LV-237: **una sola vuelta de `permit_counts` por carga.** El número de
    # permisos vigentes se dibuja dos veces —en el encabezado y en la tarjeta de
    # la tira, a cien píxeles— y hasta acá se calculaba dos veces para eso: una
    # dentro de `panel_readiness` y otra en esta función. Son la misma cifra con
    # los mismos argumentos, así que la tira se arma primero y el encabezado lee
    # de ella. Dos llamadas separadas además podían llegar a discrepar, que es
    # justo lo que `LV-201` centralizó `permit_counts` para evitar.
    readiness = panel_readiness(today, selected_cost_center)
    permits_in_force = next(
        row["count"] for row in readiness["readiness"] if row["key"] == "permits"
    )

    flights_today = FlightRecord.objects.filter(is_active=True, actual_date=today)
    if selected_cost_center:
        flights_today = flights_today.filter(
            permission__cost_center=selected_cost_center
        )

    context = {
        "flights_today": flights_today.count(),
        # El acompañante que la fila pide en la misma frase ("N operaciones hoy ·
        # M permisos vigentes"), y sale de `permit_counts` — la misma función que
        # el informe, para que el panel y el PDF no digan cifras distintas.
        "permits_in_force": permits_in_force,
        "aircraft_count": aircraft_count,
        "operator_count": operator_count,
        "alert_count": alert_count,
        "incomplete_maintenance_count": incomplete_maintenance_count,
        "awaiting_requests": awaiting_requests,
        "awaiting_count": awaiting_count,
        "longest_wait": longest_wait,
        "expirations": expirations,
        # LV-242: cuántos hay en total, para poder decir lo que el corte esconde.
        # No cuesta consulta: `all_expirations` ya está en memoria, y es la misma
        # lista de la que salen los dos contadores de la tarjeta.
        "expirations_total": len(all_expirations),
        "expiring_count": expiring_count,
        "overdue_count": overdue_count,
        "show_onboarding": show_onboarding,
        # LV-206: el estado de los permisos faena por faena, incluidas las que no
        # tienen ninguno — que son las que el usuario quiere ver. Sólo las que
        # vuelan: ver `operates_flights` en `CostCenter`.
        "permit_status_rows": permit_status_by_cost_center(today),
        "chart_data": chart_data,
        "compliance_setup": compliance_setup,
        "compliance_incomplete": compliance_incomplete,
        "cost_centers": cost_centers,
        "selected_cost_center": selected_cost_center,
        "monthly_records": monthly_records,
    }
    context.update(readiness)
    return render(request, "dashboard/index.html", context)
