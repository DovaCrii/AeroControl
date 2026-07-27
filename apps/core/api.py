"""Shared DRF building blocks for the JSON API surface.

Kept in core so every app's API (workboard, geo, ...) enforces the same
read/write permission contract instead of each redefining it.
"""

from rest_framework.permissions import DjangoModelPermissions


class ViewModelPermissions(DjangoModelPermissions):
    """Require Django view permissions for read-only API methods too.

    DRF's ``DjangoModelPermissions`` leaves GET/HEAD/OPTIONS unguarded, which
    would let any authenticated user read any model's API. The read contract
    (AGENTS.md) demands an explicit ``view_*`` for every read surface.
    """

    perms_map = {
        **DjangoModelPermissions.perms_map,
        "GET": ["%(app_label)s.view_%(model_name)s"],
        "HEAD": ["%(app_label)s.view_%(model_name)s"],
        "OPTIONS": [],
    }
