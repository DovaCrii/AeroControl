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
