"""`LV-381` F1 · El menú lateral como **datos**, no como plantilla.

Hasta `LV-380` el menú eran ~300 líneas de `base.html`: veinticuatro `<a>` escritos
a mano, cada uno con su `{% if url_name == ... %}`, y **diecisiete sin condición de
permiso** aunque su vista exigía `view_*`. El resultado (V5 del diseño) eran
enlaces que terminaban en 403 para Operations, Maintenance y Compliance, y un
`admin:index` visible para quien no es del equipo técnico.

Acá cada entrada declara **a qué permiso responde**, y la plantilla sólo recorre el
resultado. F1 la dejó con el orden y los seis grupos de siempre; **F2 la
reagrupa** (bloque sin título arriba, cinco grupos, pie de Administración) sin
sumar ni quitar destinos: son los mismos veinticuatro.

## Reglas de la tabla

- `permissions`: **todos** los permisos que la vista exige (los mismos que su
  `ModelPermissionRequiredMixin`). Una entrada sin permiso es una entrada que la
  vista deja abierta a cualquier sesión (el panel, la bandeja de trabajo).
- `any_permissions`: basta uno. Lo usa sólo el centro de administración, que es
  la puerta a configuraciones de modelos distintos.
- `staff_only`: sólo `is_staff`. El administrador técnico de Django no admite
  a nadie más, y mostrar el enlace a quien rebota al inicio de sesión es el mismo
  defecto que un 403.
- `active_url_names`: los nombres de URL, además del propio, donde la entrada se
  marca actual (pantallas hijas de una lista: altas, ediciones, importadores).
- `detail_url_names` (`LV-381` F3): las **fichas** del destino. También lo marcan
  activo, y además son las únicas pantallas con migas de pan
  (`Grupo › Lista › ficha`, derivadas de este mismo registro): una lista y sus
  pantallas hijas no las necesitan, la ficha sí porque ahí es donde la persona se
  pierde (V8).

⚠️ **El guardián que importa no está acá, está en
`test_lv381_nav_registry.py`**: por cada rol de `bootstrap_roles`, cada enlace que
el menú dibuja responde distinto de 403. Si se agrega una entrada con un permiso
más flojo que el de su vista, ese test cae.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy


@dataclass(frozen=True)
class NavItem:
    url_name: str
    label: object  # str o lazy: el msgid está en inglés y lo traduce el catálogo
    icon: str  # id del símbolo en `static/img/icons.svg`, sin el prefijo `icon-`
    section: str  # sufijo de la clase `nav-<section>` (un color por sección, LV-207)
    permissions: tuple[str, ...] = ()
    any_permissions: tuple[str, ...] = ()
    staff_only: bool = False
    active_url_names: tuple[str, ...] = ()
    detail_url_names: tuple[str, ...] = ()
    badge: bool = False  # el contador de alertas sin resolver
    dynamic_url: str = ""  # `environment`: la URL depende de las pestañas del usuario

    def allowed_for(self, user) -> bool:
        if self.staff_only and not getattr(user, "is_staff", False):
            return False
        if not all(user.has_perm(perm) for perm in self.permissions):
            return False
        if self.any_permissions and not any(
            user.has_perm(perm) for perm in self.any_permissions
        ):
            return False
        return True

    @property
    def active_names(self) -> tuple[str, ...]:
        return (self.url_name, *self.active_url_names, *self.detail_url_names)


@dataclass(frozen=True)
class NavGroup:
    key: str  # `data-nav-group`: también lo lee `nav_module` para la cabecera
    label: object
    items: tuple[NavItem, ...] = field(default_factory=tuple)


# --- Arriba, sin título ------------------------------------------------------
#
# LV-381 F2: lo que se abre todos los días y no es de ningún módulo en particular
# —el panel, la bandeja de trabajo y las alertas— va junto, sin título y con el
# color de `overview`. La bandeja y las alertas salen de Cumplimiento: son la cola
# de pendientes de cualquiera, no sólo de quien gestiona cumplimiento.

DASHBOARD = NavItem("dashboard", _("Dashboard"), "dashboard", "overview")

# UX-13: la bandeja va **primera** y encima de las alertas: es con lo que se
# empieza el día. No pide permiso de modelo (cada fuente se gatea sola,
# `tray.SOURCES`).
WORK_TRAY = NavItem("work-tray", _("Work tray"), "work-tray", "overview")

ALERTS = NavItem(
    "alert-list",
    _("Alerts"),
    "alert-list",
    "overview",
    permissions=("compliance.view_alert",),
    active_url_names=("alert-create",),
    badge=True,
)

NAV_TOP: tuple[NavItem, ...] = (DASHBOARD, WORK_TRAY, ALERTS)

# LV-358: un solo ítem «Entorno» (tiempo, centelleo GNSS, espacio aéreo). Aparece
# sólo si la persona puede abrir alguna pestaña; quien tiene una sola entra directo.
# LV-381 F2: pasa a Vuelo, que es para lo que se consulta (¿se puede volar hoy?).
ENVIRONMENT = NavItem(
    "environment-hub",
    _("Environment"),
    "environment",
    "flight",
    active_url_names=("environment-weather", "environment-gnss", "airspace-map"),
    dynamic_url="environment",
)

# --- Grupos ------------------------------------------------------------------
#
# LV-381 F2: cinco grupos (D2 del diseño), con los mismos veinticuatro destinos.
# El flujo del permiso primero (LV-61), después lo que lo respalda, lo que se
# informa, y el padrón y las faenas, que se dan de alta una vez.

FLIGHT = NavGroup(
    "flight",
    _("Flight"),
    (
        NavItem(
            "permission-list",
            _("Permissions"),
            "permission-list",
            "flight",
            permissions=("operations.view_flightpermission",),
            active_url_names=("permission-create", "permission-update"),
            detail_url_names=("permission-detail",),
        ),
        NavItem(
            "geo-plan-list",
            _("Geospatial planning"),
            "geo-plan-list",
            "flight",
            permissions=("geo.view_geoplan",),
            active_url_names=("geo-plan-import",),
            detail_url_names=("geo-plan-detail",),
        ),
        # LV-291: «Vuelos» volvió al menú con el registro de operaciones DGAC.
        NavItem(
            "record-list",
            _("Flights"),
            "record-list",
            "flight",
            permissions=("operations.view_flightrecord",),
            active_url_names=(
                "permission-operations",
                "permission-operations-pick",
                "record-create",
            ),
            detail_url_names=("record-detail",),
        ),
        ENVIRONMENT,
    ),
)

COMPLIANCE = NavGroup(
    "compliance",
    _("Compliance"),
    (
        # LV-262: «Registros operacionales» y «Cumplimiento mensual» son una sola
        # entrada; la lista de registros se abre desde cada fila del cierre.
        NavItem(
            "monthly-review",
            _("Monthly close"),
            "monthly-review",
            "compliance",
            permissions=("compliance.view_monthlycompliancereview",),
            active_url_names=("operational-records",),
        ),
        NavItem(
            "nonconformity-list",
            _("Non-conformities"),
            "nonconformity-list",
            "compliance",
            permissions=("compliance.view_nonconformity",),
            active_url_names=("nonconformity-create", "nonconformity-update"),
            detail_url_names=("nonconformity-detail",),
        ),
        NavItem(
            "company-documents",
            _("Company documents"),
            "company-documents",
            "compliance",
            permissions=("compliance.view_document",),
        ),
    ),
)

# LV-170: Informes junta el catastro y el reporte de vigencias. El catastro
# lleva flota **y** personal, así que exige las dos lecturas, como su vista.
# LV-381 F2: el reporte de vigencias se llama así (antes «Reporte» a secas, que
# no decía de qué, y se confundía con el informe mensual RPA de al lado).
REPORTS = NavGroup(
    "reports",
    _("Reports"),
    (
        NavItem(
            "registry-roster",
            _("Roster report"),
            "registry-roster",
            "reports",
            permissions=("registry.view_aircraft", "registry.view_operator"),
        ),
        NavItem(
            "compliance-report",
            _("Validity report"),
            "compliance-report",
            "reports",
            permissions=("compliance.view_document",),
        ),
        NavItem(
            "monthly-report",
            _("Monthly RPA report"),
            "monthly-report",
            "reports",
            permissions=("reporting.view_reportrun",),
        ),
    ),
)

# LV-381 F2: «Mantenimiento» tenía una sola entrada; las mantenciones son del
# equipo, igual que las aeronaves y las baterías que se mantienen.
FLEET = NavGroup(
    "fleet",
    _("Fleet and personnel"),
    (
        NavItem(
            "aircraft-list",
            _("Aircraft"),
            "aircraft-list",
            "fleet",
            permissions=("registry.view_aircraft",),
            active_url_names=("aircraft-create", "aircraft-update", "aircraft-import"),
            detail_url_names=("aircraft-detail",),
        ),
        NavItem(
            "battery-list",
            _("Batteries"),
            "battery-list",
            "fleet",
            permissions=("registry.view_battery",),
        ),
        NavItem(
            "maintenance-list",
            _("Maintenance jobs"),
            "maintenance-list",
            "fleet",
            permissions=("maintenance.view_maintenancerecord",),
            active_url_names=("maintenance-create", "history-list"),
            detail_url_names=("maintenance-detail",),
        ),
        NavItem(
            "operator-list",
            _("Operators"),
            "operator-list",
            "fleet",
            permissions=("registry.view_operator",),
            active_url_names=("operator-create", "operator-update", "operator-import"),
            detail_url_names=("operator-detail",),
        ),
        # LV-158: la prueba de conocimientos, para quien la rinde (`add_`).
        NavItem(
            "assessment-take",
            _("Knowledge assessment"),
            "assessment-take",
            "fleet",
            permissions=("registry.add_knowledgeassessment",),
            active_url_names=("assessment-start",),
            detail_url_names=("assessment-detail",),
        ),
    ),
)

# La faena (centro de costo) y lo que se mueve en ella: quién y qué está
# asignado dónde, y la bitácora de esos movimientos.
SITES = NavGroup(
    "sites",
    _("Sites and movements"),
    (
        NavItem(
            "costcenter-list",
            _("Cost Centers"),
            "costcenter-list",
            "sites",
            permissions=("registry.view_costcenter",),
            active_url_names=(
                "costcenter-create",
                "costcenter-update",
                "costcenter-import",
            ),
            detail_url_names=("costcenter-detail",),
        ),
        NavItem(
            "operatorassignment-list",
            _("Operator assignments"),
            "operatorassignment-list",
            "sites",
            permissions=("registry.view_operatorassignment",),
            active_url_names=("operatorassignment-create", "operatorassignment-update"),
            detail_url_names=("operatorassignment-detail",),
        ),
        NavItem(
            "aircraftassignment-list",
            _("Aircraft assignments"),
            "aircraftassignment-list",
            "sites",
            permissions=("registry.view_aircraftassignment",),
            active_url_names=("aircraftassignment-create", "aircraftassignment-update"),
            detail_url_names=("aircraftassignment-detail",),
        ),
        NavItem(
            "resourcemovementlog-list",
            _("Resource movements"),
            "resourcemovementlog-list",
            "sites",
            permissions=("registry.view_resourcemovementlog",),
        ),
    ),
)

NAV_GROUPS: tuple[NavGroup, ...] = (FLIGHT, COMPLIANCE, REPORTS, FLEET, SITES)

# --- Pie fijo: Administración ------------------------------------------------

ADMIN_LABEL = pgettext_lazy("sidebar zone", "Administration")

# Los mismos permisos de lectura que la página del centro revisa fila por fila
# (no `is_staff`): quien gestiona cumplimiento con `view_documenttype` no tenía
# otra forma de llegar a la configuración de tipos de documento y reglas.
ADMIN_CENTER_PERMISSIONS = (
    "core.view_operationaltenant",
    "core.view_tenantmembership",
    "compliance.view_documenttype",
    "compliance.view_alertrule",
    "workboard.view_kanbanboard",
    "workboard.view_kanbanstage",
    "workboard.view_kanbanlabel",
    "core.view_backupconfig",
    "core.view_auditevent",
)

NAV_FOOTER: tuple[NavItem, ...] = (
    NavItem(
        "administration",
        _("Administration center"),
        "administration",
        "admin",
        any_permissions=ADMIN_CENTER_PERMISSIONS,
    ),
    NavItem(
        "admin:index",
        _("Technical administration"),
        "admin-index",
        "admin",
        staff_only=True,
    ),
)


@dataclass(frozen=True)
class RetiredItem:
    """Una entrada que salió del menú **sin borrar su vista**, y por qué.

    No se dibuja nunca. Vive acá, y no en comentarios de la plantilla, para que
    cada retiro tenga a la vista su condición de cierre (AGENTS.md: un paso 1
    sin condición de cierre es deuda con intereses) y para que el sprite de
    iconos siga sabiendo qué símbolos reserva. **Devolver una entrada al menú es
    pasarla de acá a su grupo**, con su permiso.
    """

    url_name: str
    label: str
    icon: str
    retired: str
    why: str
    closing: str


RETIRED: tuple[RetiredItem, ...] = (
    RetiredItem(
        "can-i-fly",
        "Can I fly?",
        "can-i-fly",
        "LV-284 paso 1 (2026-10-06, decisión del usuario)",
        "«ocultar el puedo volar y vuelos no son necesarios de momento»; sólo el "
        "enlace: la vista, la URL, sus permisos y sus tests siguen enteros.",
        "Si en un mes nadie lo echa de menos y no hay un solo uso en el registro "
        "de auditoría, se decide entre congelarlo y borrarlo; si lo piden de "
        "vuelta, vuelve al grupo de Vuelo.",
    ),
    RetiredItem(
        "flight-request-list",
        "SIGO requests",
        "flight-request-list",
        "LV-150 paso 1 (2026-08-26, decisión del usuario)",
        "Desde R10.1 los datos que SIGO pide se leen en la ficha del plan y con "
        "LV-149 se copian de ahí; la lista de solicitudes es una pantalla a la "
        "que se llega sin tener nada que hacer en ella. La ficha del plan lleva "
        "un enlace contextual «N solicitudes de este plan». Nada se borra.",
        "Si en un mes hay al menos una solicitud creada en producción, se "
        "revierte en vez de avanzar al paso 2.",
    ),
    RetiredItem(
        "calendar",
        "Calendar",
        "calendar",
        "LV-103 paso 1 (2026-08-14, decisión del usuario)",
        "«no lo utilizo, me estoy guiando de alertas»: cuatro de los ocho tipos de "
        "evento son vencimientos, o sea lo mismo que ya llega a la bandeja de "
        "alertas, donde además se resuelven. Las vistas calendar/calendar-events "
        "y sus tests siguen enteros.",
        "Si nadie lo echa de menos, se congela y al final se borra; devolverlo es "
        "pasarlo al grupo de Vuelo.",
    ),
    RetiredItem(
        "document-list",
        "Documents",
        "document-list",
        "LV-D8 (2026-08-03, decisión de producto)",
        "La carga ya está dividida por sección (ficha de cada entidad, Documentos "
        "de la empresa, Registros operacionales); una pestaña transversal encima "
        "se sentía redundante. La vista y la URL siguen vivas.",
        "Sin fecha: es la auditoría de todos los documentos juntos.",
    ),
    RetiredItem(
        "kanban",
        "Action plan",
        "kanban",
        "LV-69 (2026-08-11, decisión del usuario)",
        "No reconocía qué hacía y lo veía duplicado: desde R6.2/R6.3 la lista de "
        "alertas registra causa raíz y cierra sin pasar por el tablero. Sigue "
        "siendo el mecanismo de acción correctiva de ISO 10.2 y el cierre "
        "alerta-tarjeta de R6.1 lo usa; los enlaces «Ver tarea» funcionan.",
        "Si en un mes nadie lo extraña, se elimina; el reemplazo propuesto es "
        "NonConformity con verificación de eficacia (R7.6).",
    ),
    RetiredItem(
        "qualification-list",
        "Qualifications",
        "qualification-list",
        "R5.8 (2026-08-11, decisión del usuario)",
        "Redundante con la ficha del operador, que muestra las habilitaciones "
        "reales de cada uno. La vista y la URL siguen vivas.",
        "Sin fecha: es la auditoría de todas las habilitaciones juntas.",
    ),
)

# Los entregables también salieron (2026-08-20) y **no tienen ancla**: se
# borró, no se comentó. Para devolverlos hay que escribir la entrada con
# `compliance.view_deliverable` apuntando a `deliverable-list`. Condición de
# cierre: en cuanto se cree un entregable en producción el enlace vuelve; si no
# se crea ninguno se retira de verdad —vista, URL, plantillas y tests— salvo que
# `NonConformity` siga dependiendo del rechazo de entregables, que hoy es el caso.


# --- Resolución --------------------------------------------------------------


@dataclass(frozen=True)
class ResolvedItem:
    key: str
    url: str
    label: object
    icon: str
    section: str
    active: bool
    badge: bool
    ficha: bool = False  # la página actual es una ficha de este destino

    @property
    def aria_current(self) -> str:
        """`page` si es esta pantalla; `true` si es una ficha **de** este destino.

        La ficha ya lleva su propio `aria-current="page"` (el último elemento de
        las migas); dos «página actual» en una pantalla confunden a un lector de
        pantalla, así que el menú sólo dice que el destino contiene a la actual.
        """
        if not self.active:
            return ""
        return "true" if self.ficha else "page"


@dataclass(frozen=True)
class Crumb:
    label: object
    url: str = ""  # vacío: el grupo no es una página


@dataclass(frozen=True)
class ResolvedGroup:
    key: str
    label: object
    items: tuple[ResolvedItem, ...]


@dataclass(frozen=True)
class SidebarMenu:
    top: tuple[ResolvedItem, ...]
    groups: tuple[ResolvedGroup, ...]
    footer: tuple[ResolvedItem, ...]

    @property
    def breadcrumbs(self) -> tuple[Crumb, ...]:
        """`Grupo › Lista` de la ficha actual; vacío si la página no es una ficha.

        Salen del **mismo** registro que el menú: no hay una segunda tabla de
        migas que se desincronice. Falta el último eslabón (la ficha misma): lo
        pone la plantilla con el objeto que la vista ya tiene.
        """
        for group in self.groups:
            for item in group.items:
                if item.ficha:
                    return (Crumb(group.label), Crumb(item.label, item.url))
        for item in (*self.top, *self.footer):
            if item.ficha:
                return (Crumb(item.label, item.url),)
        return ()


def _environment_url(user) -> str:
    # Import local: `environment` importa de `core`, y esto corre en cada petición.
    from apps.environment.tabs import tabs_for

    tabs = tabs_for(user)
    return tabs[0]["url"] if tabs else ""


def _resolve(item: NavItem, user, url_name: str) -> ResolvedItem | None:
    if not item.allowed_for(user):
        return None
    if item.dynamic_url == "environment":
        url = _environment_url(user)
        if not url:
            return None
    else:
        url = reverse(item.url_name)
    return ResolvedItem(
        key=item.url_name,
        url=url,
        label=item.label,
        icon=item.icon,
        section=item.section,
        active=url_name in item.active_names,
        badge=item.badge,
        ficha=url_name in item.detail_url_names,
    )


def _resolve_all(items, user, url_name):
    resolved = (_resolve(item, user, url_name) for item in items)
    return tuple(entry for entry in resolved if entry is not None)


def build_sidebar(user, url_name: str = "") -> SidebarMenu:
    """El menú que `user` puede usar, con la entrada actual marcada.

    Un grupo sin ninguna entrada permitida **no se dibuja**: un título sin filas
    debajo es un callejón sin salida.
    """
    groups = []
    for group in NAV_GROUPS:
        items = _resolve_all(group.items, user, url_name)
        if items:
            groups.append(ResolvedGroup(group.key, group.label, items))
    return SidebarMenu(
        top=_resolve_all(NAV_TOP, user, url_name),
        groups=tuple(groups),
        footer=_resolve_all(NAV_FOOTER, user, url_name),
    )


def all_items() -> tuple[NavItem, ...]:
    """Todas las entradas vivas, en el orden en que se dibujan."""
    return (
        *NAV_TOP,
        *(item for group in NAV_GROUPS for item in group.items),
        *NAV_FOOTER,
    )
