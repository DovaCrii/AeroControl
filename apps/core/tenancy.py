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
