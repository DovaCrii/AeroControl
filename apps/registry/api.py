"""Read-only padrón API for AeroLink (X.3).

Contract in docs/dev/adr-0002-coexistencia-aerolink.md: **AeroControl is the
master of the padrón** (aircraft, operators, cost centers) and AeroLink reads
it, never writes. This is the Fase 1 surface of that contract.

Why aircraft, and why keyed on serial: AeroLink receives telemetry from DJI
Pilot 2, which reports the airframe's **serial number** and knows nothing about
this app's UUIDs or registrations. `Aircraft.serial_number` is the only key
present in all three worlds (DJI, the Z: folder names, the DGAC registry) --
X.1 normalized it and made it unique precisely so it could serve as this
join key.

Deliberately narrow:

- **Read-only.** No POST/PATCH/DELETE at all -- not "permission-gated writes",
  no write routes exist. The ADR prohibits AeroLink writing into this domain,
  and the cheapest way to guarantee that is to not build the door.
- **Only the fields needed to resolve and label an airframe.** Insurance
  dates, weights, VLOS and the rest of the ficha are AeroControl's compliance
  business; a telemetry gateway has no use for them, and every field exposed
  is a field that has to keep working for an external consumer.
- **Tenant-scoped like every other read** (AGENTS.md read contract), plus
  `view_aircraft` -- a token does not bypass either.
"""

from rest_framework import serializers
from rest_framework.pagination import PageNumberPagination
from rest_framework.throttling import ScopedRateThrottle, UserRateThrottle
from rest_framework.viewsets import ReadOnlyModelViewSet

from apps.core.api import ViewModelPermissions
from apps.core.tenancy import scope_queryset_to_tenant

from .models import Aircraft, normalize_serial


class PadronPagination(PageNumberPagination):
    """The whole fleet is 16 aircraft today, so one page covers it -- but an
    unpaginated list endpoint is a footgun that only shows up once the data
    grows, so the ceiling is set now."""

    page_size = 100
    page_size_query_param = "page_size"
    max_page_size = 500


class AircraftPadronSerializer(serializers.ModelSerializer):
    cost_center_code = serializers.CharField(
        source="cost_center.code", read_only=True, default=None
    )
    cost_center_name = serializers.CharField(
        source="cost_center.name", read_only=True, default=None
    )

    class Meta:
        model = Aircraft
        fields = [
            "id",
            "registration",
            "serial_number",
            "manufacturer",
            "model",
            "type",
            "status",
            "cost_center_code",
            "cost_center_name",
            "updated_at",
        ]
        read_only_fields = fields


class AircraftPadronViewSet(ReadOnlyModelViewSet):
    """`GET /api/v1/registry/aircraft/` and `.../<uuid>/`.

    `?serial=<serial>` is the lookup AeroLink actually uses: it holds a serial
    from DJI and needs the matching airframe. Matched exactly (not `icontains`)
    -- a partial match on a serial would resolve telemetry to the wrong
    aircraft, which is worse than not resolving it. Stored serials are
    normalized by `normalize_serial` (X.1 whitespace, plus the upper-casing
    ADR-0002 §2 always required and X.4c finally implemented), so the incoming
    value goes through the same function instead of trusting the caller to have
    done it.
    """

    serializer_class = AircraftPadronSerializer
    permission_classes = (ViewModelPermissions,)
    pagination_class = PadronPagination
    # ScopedRateThrottle has to be listed explicitly: declaring throttle_scope
    # alone does nothing, because DEFAULT_THROTTLE_CLASSES does not include it
    # (same reason geo/api.py spells both out).
    throttle_classes = (UserRateThrottle, ScopedRateThrottle)
    throttle_scope = "padron"
    queryset = Aircraft.objects.none()  # DjangoModelPermissions reads the model

    def get_queryset(self):
        queryset = (
            Aircraft.objects.filter(is_active=True)
            .select_related("cost_center")
            .order_by("registration")
        )
        queryset = scope_queryset_to_tenant(queryset, self.request.user)
        serial = self.request.query_params.get("serial")
        if serial:
            queryset = queryset.filter(serial_number=normalize_serial(serial))
        return queryset
