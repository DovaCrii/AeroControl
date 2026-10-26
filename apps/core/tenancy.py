"""Tenant resolution helpers (ADR-0001 / T3.2).

Single-tenant today: every operational record belongs to one default
`OperationalTenant`. `get_default_tenant` is the field default on the scoped
FKs, so existing code and tests that do not pass a tenant keep working and new
rows are never NULL. When real multi-tenancy arrives, the request's tenant
(from `TenantMembership`) replaces this default at the view layer (ADR Fase 1).
"""

DEFAULT_TENANT_SLUG = "default"
DEFAULT_TENANT_NAME = "AeroControl"


def get_default_tenant():
    """Return the default tenant's pk, creating it once if needed.

    Returns the pk (not the instance) so it is usable directly as a model
    field ``default=``.
    """
    from apps.core.models import OperationalTenant

    tenant, _ = OperationalTenant.objects.get_or_create(
        slug=DEFAULT_TENANT_SLUG,
        defaults={"name": DEFAULT_TENANT_NAME},
    )
    return tenant.pk


def scope_queryset_to_tenant(queryset, user, tenant_path=None):
    """Restrict a queryset to the user's tenant(s) (F-03/F-06, object-level).

    The list views were scoped in T3.2 Fase 2, but a detail/edit/archive view
    resolved its object by pk alone, so `/aircraft/<other-tenant-pk>/` still
    opened. This closes that by tenant. A no-op for a superuser.

    `tenant_path` is the ORM path from the model to the tenant id:
    - ``None`` (default): the model's own ``tenant_id`` if it has a direct
      ``tenant`` FK (CostCenter/Aircraft/Operator/Document/AlertRule), else a
      no-op -- so passing an unrelated queryset never over-filters.
    - an explicit path for models that reach the tenant through a relation
      (e.g. ``"cost_center__tenant_id"``, ``"aircraft__tenant_id"``).

    Behaviour-preserving today (single tenant), correct once tenants diverge.
    """
    tenant_ids = visible_tenant_ids(user)
    if tenant_ids is None:
        return queryset
    if tenant_path is None:
        if not any(field.name == "tenant" for field in queryset.model._meta.fields):
            return queryset
        tenant_path = "tenant_id"
    return queryset.filter(**{f"{tenant_path}__in": tenant_ids})


def scope_queryset_to_visible_tenants(
    queryset, user, tenant_path=None, *, include_unowned=False
):
    """Lo mismo que `scope_queryset_to_tenant`, **sin consultas propias** (LV-372).

    `scope_queryset_to_tenant` resuelve primero los tenants de la persona con una consulta
    (dos si no tiene membresía: la de membresías y la del tenant por defecto) y filtra con esa
    lista. Eso cuesta una o dos consultas **por llamada**, y el panel y el contador de alertas
    de la barra lateral —que se arman en cada carga de página— tienen techo de consultas: acotar
    ocho querysets de ahí con la función eager habría sumado más de diez.

    Esta variante expresa la misma regla como subconsulta dentro del `WHERE`: la persona ve los
    tenants de los que es miembro activo y, si no es miembro de ninguno, el tenant por defecto
    (`DEFAULT_TENANT_SLUG`, el mismo respaldo de `visible_tenant_ids`). Un superusuario no se
    acota. `tenant_path` es el mismo camino ORM al id del tenant (`"cost_center__tenant_id"`,
    `"alert_rule__tenant_id"`...); sin él, el `tenant` propio del modelo, o ningún filtro si no
    lo tiene.

    `include_unowned=True` deja ver además las filas **sin empresa** (el camino llega a `NULL`,
    p. ej. una no conformidad sin centro de costo): no se pueden atribuir a ninguna, y ocultarlas
    a todos cambiaría lo que hoy se ve con una sola empresa. Es opt-in y se declara en la vista.

    La igualdad con `visible_tenant_ids` la fija `apps/core/test_tenancy.py`.
    """
    from django.db.models import Exists, Q

    if user.is_superuser:
        return queryset
    if tenant_path is None:
        if not any(field.name == "tenant" for field in queryset.model._meta.fields):
            return queryset
        tenant_path = "tenant_id"
    from apps.core.models import OperationalTenant

    member_of = OperationalTenant.objects.filter(members=user, is_active=True)
    slug_path = f"{tenant_path.removesuffix('_id')}__slug"
    visible = Q(**{f"{tenant_path}__in": member_of.values("pk")}) | (
        ~Exists(member_of) & Q(**{slug_path: DEFAULT_TENANT_SLUG})
    )
    if include_unowned:
        visible |= Q(**{f"{tenant_path}__isnull": True})
    return queryset.filter(visible)


# LV-372 (F-08): el camino al tenant de cada modelo operativo, para acotar los **desplegables** de
# un formulario. Sin esto, abrir «Nuevo permiso» ofrecía las faenas, aeronaves y operadores de todas
# las empresas (y un POST con el pk de una ajena se guardaba). La segunda entrada de cada fila dice
# si las filas **sin empresa** (el camino llega a NULL) siguen ofreciéndose a todos: sólo los
# tableros, etapas y etiquetas del Kanban, donde `tenant` es opcional y «sin empresa» es «común».
FORM_CHOICE_TENANT_PATHS = {
    "registry.costcenter": ("tenant_id", False),
    "registry.aircraft": ("tenant_id", False),
    "registry.operator": ("tenant_id", False),
    "registry.battery": ("tenant_id", False),
    "registry.assignment": ("cost_center__tenant_id", False),
    "registry.operatorassignment": ("cost_center__tenant_id", False),
    "registry.aircraftassignment": ("cost_center__tenant_id", False),
    "registry.qualification": ("operator__tenant_id", False),
    # LV-372 (fase 4): el motor de alertas vigila estos dos con el mismo camino.
    "registry.knowledgeassessment": ("operator__tenant_id", False),
    "compliance.monthlycompliancereview": ("cost_center__tenant_id", False),
    "compliance.document": ("tenant_id", False),
    "compliance.alertrule": ("tenant_id", False),
    "compliance.deliverable": ("cost_center__tenant_id", False),
    "compliance.nonconformity": ("cost_center__tenant_id", True),
    "operations.flightpermission": ("cost_center__tenant_id", False),
    "operations.flightrequest": ("cost_center__tenant_id", False),
    "operations.flightrecord": ("permission__cost_center__tenant_id", False),
    "maintenance.maintenancerecord": ("aircraft__tenant_id", False),
    "geo.geoplan": ("cost_center__tenant_id", False),
    "workboard.kanbanboard": ("tenant_id", True),
    "workboard.kanbanstage": ("board__tenant_id", True),
    "workboard.kanbanlabel": ("board__tenant_id", True),
    "workboard.kanbantask": ("board__tenant_id", True),
}


def scope_queryset_for_model(queryset, user):
    """Acota un queryset **de cualquier modelo operativo** a las empresas de `user` (LV-372).

    Para referencias genéricas (`ContentType` + `object_id`) donde no se sabe el modelo de antemano.
    Usa `FORM_CHOICE_TENANT_PATHS`; la propia empresa (`core.operationaltenant`, de donde cuelgan los
    documentos de la empresa) se acota por su identificador. Un modelo que no figura queda como está.
    Sin `user` o con un superusuario, no se acota.
    """
    if user is None or user.is_superuser:
        return queryset
    from django.db.models import Exists, Q

    model = queryset.model
    label = f"{model._meta.app_label}.{model._meta.model_name}"
    if label == "core.operationaltenant":
        member_of = model.objects.filter(members=user, is_active=True)
        return queryset.filter(
            Q(pk__in=member_of.values("pk"))
            | (~Exists(member_of) & Q(slug=DEFAULT_TENANT_SLUG))
        )
    entry = FORM_CHOICE_TENANT_PATHS.get(label)
    if entry is None:
        return queryset
    path, include_unowned = entry
    return scope_queryset_to_visible_tenants(
        queryset, user, path, include_unowned=include_unowned
    )


def scope_form_choices(form, user):
    """Acota los desplegables de un formulario a las empresas de `user` (LV-372, F-08).

    Recorre los campos que eligen filas (`ModelChoiceField` y `ModelMultipleChoiceField`) y, para
    los modelos de `FORM_CHOICE_TENANT_PATHS`, reemplaza el queryset por su versión acotada
    (subconsulta, sin consultas propias). Como la validación del campo usa ese mismo queryset, un
    pk de otra empresa en el POST da «Seleccione una opción válida» y no se guarda. Los modelos
    que no figuran (catálogos globales: tipos de documento, de habilitación, de trabajo) quedan
    como estaban. Un superusuario no se acota. Los querysets con `slice` se dejan: ya no admiten
    `filter`, y ninguno de este proyecto lo es.
    """
    from django import forms

    if user is None or user.is_superuser:
        return form
    # Un formulario con campos que no son `ModelChoiceField` (la referencia genérica de un
    # documento) se acota a sí mismo cuando se le dice quién mira.
    scope_itself = getattr(form, "scope_to_user", None)
    if scope_itself is not None:
        scope_itself(user)
    for field in form.fields.values():
        if not isinstance(field, forms.ModelChoiceField):
            continue
        queryset = field.queryset
        if queryset is None or queryset.query.is_sliced:
            continue
        label = f"{queryset.model._meta.app_label}.{queryset.model._meta.model_name}"
        entry = FORM_CHOICE_TENANT_PATHS.get(label)
        if entry is None:
            continue
        path, include_unowned = entry
        field.queryset = scope_queryset_to_visible_tenants(
            queryset, user, path, include_unowned=include_unowned
        )
    return form


def visible_tenant_ids(user):
    """Tenant ids a user may see, or ``None`` for "all tenants" (T3.2 Fase 1).

    Single source of truth for read scoping, replacing three inline copies of
    the same `OperationalTenant.objects.filter(members=...)` query (the calendar
    feed and the assignment list). A superuser sees everything (``None``). Any
    other user sees the tenants they are a member of; **when they have none they
    fall back to the default tenant** instead of seeing nothing -- today every
    record lives in that default tenant and there are no memberships yet, so
    without the fallback a non-superuser collaborator saw an empty calendar and
    empty lists (a latent bug this fixes). Real multi-tenant membership takes
    over automatically once memberships exist.
    """
    if user.is_superuser:
        return None
    from apps.core.models import OperationalTenant

    ids = list(
        OperationalTenant.objects.filter(members=user, is_active=True).values_list(
            "pk", flat=True
        )
    )
    return ids or [get_default_tenant()]
