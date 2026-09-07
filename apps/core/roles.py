"""`UX-31` · Vistas por rol: dónde aterriza cada quien y qué tiene a mano.

*Por qué está en el plan, textual:* **ocultar genera desconfianza; priorizar
genera velocidad.** De ahí sale la regla que gobierna todo este módulo — **nada
se esconde**. Los permisos siguen decidiendo qué se puede ver, el menú completo
sigue completo, y lo único que cambia por rol es **el orden en que aparecen las
cosas** y la pantalla en la que uno cae al entrar.

## Los roles son los que ya existen

No se inventa una taxonomía nueva: son los grupos que crea `bootstrap_roles`, y
eso importa porque son los que ya reparten permisos. Un segundo juego de roles
"para la interfaz" habría sido una lista paralela que se desincroniza — y
desincronizada querría decir aterrizar en una pantalla para la que no se tiene
permiso, o sea un 403 en el primer clic del día.

El plan nombra *"jefatura, cumplimiento y operador"*; la traducción a lo que hay
es directa, con `Maintenance` sumado porque existe y trabaja distinto:

| Grupo | Aterriza en | Por qué |
|---|---|---|
| `Operations` | «¿Puedo volar?» | Es literalmente su primera pregunta del día. |
| `Compliance` | La bandeja de trabajo | Su jornada **es** la cola de pendientes. |
| `Maintenance` | Mantenciones | Lo mismo, con otra cola. |
| `Administrator`, `Viewer`, y quien no tenga rol | El panel | Es la vista de conjunto, que es lo que mira quien no ejecuta una cola. |

⚠️ **El aterrizaje se aplica al iniciar sesión y en ningún otro momento.** No hay
redirección desde `/`: el panel sigue estando exactamente donde estaba y su
entrada de menú sigue llevando ahí. Redirigir la raíz habría vuelto el panel
inalcanzable para tres de los cinco roles — que es esconder, con otro nombre.

⚠️ **Y con permiso comprobado antes de mandar a nadie.** Un grupo puede quedar
sin el permiso de su propia pantalla (alguien lo edita en el administrador), y un
aterrizaje a un 403 es la peor forma posible de empezar el día. Sin permiso, el
panel; el panel no pide ninguno.
"""

#: Grupo → nombre de URL donde aterriza al iniciar sesión, y el permiso que esa
#: pantalla exige. El permiso se declara **acá y no se deduce**: la vista de la
#: bandeja no pide ninguno (cada fuente se gatea sola), así que preguntárselo a
#: la vista daría "ninguno" y mandaría gente a una bandeja vacía sin explicación.
ROLE_LANDING = {
    "Operations": ("can-i-fly", None),
    "Compliance": ("work-tray", None),
    "Maintenance": ("maintenance-list", "maintenance.view_maintenancerecord"),
}

#: Grupo → los accesos que se fijan arriba del menú, en orden.
#:
#: **Son atajos, no un menú recortado.** Cada uno de estos destinos sigue estando
#: en su grupo de siempre, más abajo: lo que hace esta lista es ponerlos primero
#: para quien los usa todos los días. Un operador no deja de ver «Documentos de
#: la empresa» — deja de tener que bajar hasta ellos.
ROLE_SHORTCUTS = {
    "Operations": ("can-i-fly", "permission-list", "record-list"),
    "Compliance": ("work-tray", "alert-list", "monthly-report"),
    "Maintenance": ("maintenance-list", "alert-list"),
}

#: El permiso que gatea cada atajo, para no ofrecer un enlace que termina en 403
#: (`LV-130`: un enlace que falla enseña a desconfiar de la pantalla). `None` es
#: "no pide ninguno", no "no se sabe".
SHORTCUT_PERMISSIONS = {
    "can-i-fly": None,
    "work-tray": None,
    "permission-list": "operations.view_flightpermission",
    "record-list": "operations.view_flightrecord",
    "alert-list": "compliance.view_alert",
    "monthly-report": "reporting.view_reportrun",
    "maintenance-list": "maintenance.view_maintenancerecord",
}

#: Cómo se rotula cada atajo. Se repiten los mismos textos que el menú usa más
#: abajo, a propósito: dos nombres para la misma pantalla es cómo alguien cree
#: que son dos pantallas.
SHORTCUT_LABELS = {
    "can-i-fly": "Can I fly?",
    "work-tray": "Work tray",
    "permission-list": "Permissions",
    "record-list": "Flights",
    "alert-list": "Alerts",
    "monthly-report": "Monthly RPA report",
    "maintenance-list": "Maintenance",
}


def role_of(user):
    """El primer grupo con vista propia al que pertenece, o `None`.

    ⚠️ **El primero por el orden de `ROLE_LANDING`, no el primero que devuelva la
    base.** Alguien puede estar en dos grupos —pasa: quien opera y además revisa
    cumplimiento— y el orden de `groups.all()` es el que quiera el motor. Una
    pantalla de inicio que cambia sola entre dos logins es de las cosas que nadie
    reporta como defecto y todos desconfían.
    """
    if not getattr(user, "is_authenticated", False):
        return None
    names = set(user.groups.values_list("name", flat=True))
    for role in ROLE_LANDING:
        if role in names:
            return role
    return None


def landing_url_name(user):
    """Dónde aterriza `user` al iniciar sesión. `None` = donde aterrizaba antes.

    Devolver `None` y no `"dashboard"` es deliberado: así quien llama conserva su
    propio destino por defecto —el `next=` de la URL, `LOGIN_REDIRECT_URL`— en
    vez de que este módulo lo pise. Sólo se opina cuando hay algo que decir.
    """
    role = role_of(user)
    if role is None:
        return None
    url_name, permission = ROLE_LANDING[role]
    if permission and not user.has_perm(permission):
        # Un grupo puede quedar sin el permiso de su propia pantalla; aterrizar
        # en un 403 es la peor forma de empezar el día.
        return None
    return url_name


def shortcuts_for(user):
    """Los atajos que este usuario puede usar de verdad, en orden.

    Se filtran por permiso acá y no en la plantilla por lo mismo que
    `EXPIRATION_PERMISSIONS` del panel: un `if` por atajo repartido en el HTML es
    un `if` que alguien olvida, y el olvido se ve como un enlace que devuelve 403.
    """
    role = role_of(user)
    if role is None:
        return []
    return [
        name
        for name in ROLE_SHORTCUTS.get(role, ())
        if SHORTCUT_PERMISSIONS[name] is None
        or user.has_perm(SHORTCUT_PERMISSIONS[name])
    ]
