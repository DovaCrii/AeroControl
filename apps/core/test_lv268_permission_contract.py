"""LV-268: toda vista exige un permiso de modelo, o está declarada como excepción.

`AGENTS.md` pide que **toda vista de lectura exija `view_*`**, y el contrato nació
de los hallazgos F-05/F-06: documentos y calendario legibles con sólo iniciar
sesión. Hasta hoy el contrato se cumplía **vista por vista**, con una prueba de
403 que cada autor escribe o se olvida de escribir. Una vista nueva con
`LoginRequiredMixin` a secas pasa el gate sin que nada lo note.

Este archivo recorre **las rutas reales** (no el código) y exige, para cada una
fuera de `admin/` —que gestiona sus propios permisos—, una de dos cosas:

1. un permiso de modelo (`PermissionRequiredMixin` de Django, o un permiso de
   modelo de DRF), o
2. figurar en `EXEMPT` **con su motivo escrito**.

La lista no es un cajón: cada entrada dice por qué esa vista no tiene un modelo
del cual pedir permiso, y el test falla si una entrada **sobra** (la vista ya
tiene permiso, o desapareció) para que la lista no se vuelva una colección de
excusas viejas. Y ninguna excepción puede estar abierta: salvo las declaradas
públicas, toda excepción tiene que exigir al menos sesión.

Es el espejo de `test_templates_reference_real_urls`: aquel lee las plantillas
para que un `{% url %}` roto no espere a producción; éste lee el enrutador para
que una vista sin permiso no espere a una auditoría.
"""

import inspect

from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.urls import URLPattern, URLResolver, get_resolver
from rest_framework.permissions import DjangoModelPermissions, IsAuthenticated

# Rutas del panel de administración de Django: `ModelAdmin` aplica `has_*_permission`
# por su cuenta, y no hay una vista nuestra que vigilar ahí.
SKIP_PREFIX = "admin/"

# Públicas **a propósito**: no exigen ni sesión. Quien agregue una a esta lista está
# diciendo que cualquiera, sin cuenta, puede llamarla.
PUBLIC = {
    "apps.core.views.SignInView": "la pantalla de acceso: tiene que verse sin sesión.",
    "django.contrib.auth.views.LogoutView": "cerrar sesión no expone datos.",
    "apps.core.views.HealthCheckView": (
        "los monitores y el proxy inverso la consultan sin sesión; devuelve sólo "
        "ok/error de la base y de la carpeta de documentos."
    ),
    "apps.core.views.CspReportView": (
        "el navegador envía el informe de la política de seguridad solo, sin "
        "sesión ni token; sólo registra, acota el cuerpo y nunca confía en él."
    ),
    "apps.core.views.ServiceWorkerView": (
        "el navegador lo pide al registrar el worker; servido apagado desinstala "
        "el worker roto (`UX-26`), y eso tiene que ocurrir sin sesión."
    ),
    "apps.core.api.ThrottledObtainAuthToken": (
        "entrega un token a quien presenta usuario y contraseña, con el límite de "
        "peticiones anónimas que antes no tenía."
    ),
    "django.views.i18n.set_language": "elegir idioma no toca datos del negocio.",
    "apps.workboard.api.api_openapi_schema": (
        "el contrato OpenAPI público y estable de la API v1: describe, no consulta."
    ),
}

# Piden sesión y **no** un permiso de modelo. Cada una dice dónde está el control.
LOGIN_ONLY = {
    "django.contrib.auth.views.PasswordChangeView": (
        "cambiar la propia contraseña no necesita permiso de modelo."
    ),
    "django.contrib.auth.views.PasswordChangeDoneView": (
        "la confirmación de ese cambio: sólo muestra un mensaje."
    ),
    "apps.core.views.WorkTrayView": (
        "la bandeja cruza cuatro modelos y no tiene uno propio; **cada fuente se "
        "lee sólo si quien mira puede verla** (`tray.SOURCES`). No resuelve nada."
    ),
    "apps.operations.views.CanIFlyView": (
        "cruza cuatro padrones y no tiene modelo propio; cada desplegable se llena "
        "sólo con lo que el usuario puede ver (`ROSTER_PERMISSIONS`). Todo por GET."
    ),
    "apps.core.views.ListColumnsSave": (
        "guarda cómo esta persona mira su propia pantalla; pedir `change_*` "
        "convertiría una preferencia personal en un privilegio."
    ),
    "apps.core.views.ListViewSave": "preferencia personal: la vista guardada es suya.",
    "apps.core.views.ListViewDelete": (
        "borra sólo una vista propia: el filtro por `user` está en la consulta."
    ),
    "apps.core.views.AlertCountPartial": (
        "el contador de la barra lateral; sin `compliance.view_alert` se dibuja "
        "vacío en vez de dar 403, porque se refresca solo cada 60 s."
    ),
    "apps.core.views.UnifiedCalendarEventsView": (
        "el calendario agrega siete modelos; cada fuente se filtra por el permiso "
        "de su propio modelo (`CALENDAR_EVENT_PERMISSIONS`)."
    ),
    "apps.operations.views.CalendarView": (
        "`CalendarAccessMixin` da 403 a quien no puede ver **ninguna** fuente de "
        "eventos; el resto se filtra por fuente."
    ),
    "apps.core.views.GlobalSearchView": (
        "busca en varios modelos y filtra cada fuente por su permiso `view_*`."
    ),
    "apps.core.views.AdministrationCenterView": (
        "el índice de configuración: cada acceso se muestra según el permiso que "
        "pide su destino, que sigue protegido por su propia vista."
    ),
    "apps.core.api.ApiIndexView": (
        "documenta los endpoints y el permiso que pide cada uno; no consulta datos."
    ),
    "apps.registry.assessment_views.KnowledgeAssessmentStart": (
        "redirige: manda a rendir si tiene `add_knowledgeassessment` y explica por "
        "qué no en caso contrario, en vez de un 403 sin contexto."
    ),
    "apps.dashboard.views.dashboard": (
        "el panel de inicio; cada tarjeta se arma sólo con lo que el usuario puede "
        "ver (`EXPIRATION_PERMISSIONS`, `panel_readiness`)."
    ),
    # DRF: piden `IsAuthenticated` y hacen la comprobación de modelo adentro,
    # porque el permiso depende del método (GET lista, POST escribe).
    "apps.geo.api.GeoPlanVersionsView": (
        "GET exige `view_geoplan` y POST `change_geoplan`, según el método."
    ),
    "apps.geo.api.GeoPlanRestoreView": "comprueba `change_geoplan` adentro.",
    "apps.geo.api.GeoPlanExportView": "comprueba `view_geoplan` adentro.",
}

EXEMPT = {**PUBLIC, **LOGIN_ONLY}


def _walk(patterns):
    for pattern in patterns:
        if isinstance(pattern, URLResolver):
            yield from _walk(pattern.url_patterns)
        elif isinstance(pattern, URLPattern):
            yield pattern


def _routes():
    """{llave estable: la vista real}, sin `admin/` y sin repetir clases.

    Una clase puede colgar de varias rutas (el calendario, el API de tareas): se
    cuenta una vez, por la llave `módulo.Clase` o `módulo.función`.
    """
    # `str(pattern.pattern)` sólo da el tramo propio; el prefijo se recompone
    # recorriendo los resolvers para poder saltar `admin/` entero.
    found = {}

    def visit(patterns, prefix):
        for pattern in patterns:
            route = prefix + str(pattern.pattern)
            if isinstance(pattern, URLResolver):
                if route.startswith(SKIP_PREFIX):
                    continue
                visit(pattern.url_patterns, route)
            elif isinstance(pattern, URLPattern) and not route.startswith(SKIP_PREFIX):
                callback = pattern.callback
                real = (
                    getattr(callback, "view_class", None)
                    or getattr(callback, "cls", None)
                    or callback
                )
                found.setdefault(f"{real.__module__}.{real.__name__}", real)

    visit(get_resolver().url_patterns, "")
    return found


def _has_model_permission(view):
    if inspect.isclass(view) and issubclass(view, PermissionRequiredMixin):
        return True
    classes = getattr(view, "permission_classes", None) or []
    return any(
        issubclass(c, DjangoModelPermissions) or "ModelPermissions" in c.__name__
        for c in classes
    )


def _asks_for_login(view):
    if inspect.isclass(view) and issubclass(view, LoginRequiredMixin):
        return True
    classes = getattr(view, "permission_classes", None) or []
    if any(issubclass(c, IsAuthenticated) for c in classes):
        return True
    try:
        return "login_required" in inspect.getsource(view)
    except (OSError, TypeError):
        return False


def test_the_discovery_sees_the_real_routes():
    """El guardián del guardián: si el recorrido se rompe devolviendo pocas rutas,
    el resto del archivo pasaría en verde sin haber mirado nada."""
    routes = _routes()
    assert len(routes) > 150
    assert sum(_has_model_permission(view) for view in routes.values()) > 130


def test_every_view_requires_a_model_permission_or_is_declared_an_exception():
    undeclared = sorted(
        key
        for key, view in _routes().items()
        if not _has_model_permission(view) and key not in EXEMPT
    )
    assert not undeclared, (
        "Vistas sin permiso de modelo que no están declaradas como excepción. "
        "Agrega `ModelViewPermissionRequiredMixin` (o `ModelPermissionRequiredMixin`"
        " con su `permission_action`) y su prueba de 403; si de verdad no hay un "
        "modelo del cual pedir permiso, añádela a `LOGIN_ONLY` con el motivo y "
        "dónde está el control:\n  " + "\n  ".join(undeclared)
    )


def test_the_exemption_list_has_no_stale_entries():
    routes = _routes()
    gone = sorted(key for key in EXEMPT if key not in routes)
    now_protected = sorted(
        key for key in EXEMPT if key in routes and _has_model_permission(routes[key])
    )
    assert not gone, f"Excepciones de vistas que ya no existen: {gone}"
    assert not now_protected, (
        f"Excepciones de vistas que ya exigen permiso de modelo: {now_protected}. "
        "Quita la entrada: la lista no guarda excusas viejas."
    )


def test_no_exception_is_open_unless_it_is_declared_public():
    routes = _routes()
    open_views = sorted(
        key for key in LOGIN_ONLY if key in routes and not _asks_for_login(routes[key])
    )
    assert not open_views, (
        f"Excepciones que no exigen ni sesión y no están en `PUBLIC`: {open_views}"
    )


def test_every_exception_says_why():
    short = sorted(key for key, why in EXEMPT.items() if len(why.strip()) < 20)
    assert not short, f"Excepciones sin motivo escrito: {short}"
    assert not set(PUBLIC) & set(LOGIN_ONLY)
