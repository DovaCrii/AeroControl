"""Shared DRF building blocks for the JSON API surface.

Kept in core so every app's API (workboard, geo, ...) enforces the same
read/write permission contract instead of each redefining it.

**LV-78, step 1:** the API index and the token endpoint moved here from
`apps.workboard`. They were never Kanban features -- they are the entrance to
the whole JSON API, including the padrón AeroLink reads (`X.3`) and the battery
sync (`X.4b`). Leaving them inside the app being retired meant the integration
with another system hung off a module marked for removal, which nobody had
written down. This move is worth doing **even if the board stays**.
"""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views import View
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.permissions import DjangoModelPermissions
from rest_framework.throttling import AnonRateThrottle


class ThrottledObtainAuthToken(ObtainAuthToken):
    """Token endpoint with the anon throttle it silently opted out of.

    DRF's ``ObtainAuthToken`` sets ``throttle_classes = ()`` on the class, so the
    project-wide DEFAULT_THROTTLE_CLASSES never applied to the one endpoint that
    accepts unauthenticated credential guesses.
    """

    throttle_classes = (AnonRateThrottle,)


class ApiIndexView(LoginRequiredMixin, View):
    """What `/api/v1/` offers.

    Rewritten with the move (LV-78): it listed **only** the Kanban endpoints and
    said nothing about the padrón, which is the one another system actually
    consumes -- an index that omits the supported API and advertises the retiring
    one is worse than no index. The task endpoints stay listed while they still
    answer, marked deprecated, because silently dropping a live route from its
    own index is the other way to mislead.
    """

    def get(self, request):
        return JsonResponse(
            {
                "version": "v1",
                "authentication": "Django session or configured API gateway",
                "endpoints": {
                    "aircraft_list": {
                        "method": "GET",
                        "path": "/api/v1/registry/aircraft/",
                        "permission": "registry.view_aircraft",
                        "filters": ["serial"],
                        "notes": (
                            "Read-only aircraft roster (ADR-0002 §4). `serial` "
                            "matches exactly, never by prefix."
                        ),
                    },
                    "aircraft_detail": {
                        "method": "GET",
                        "path": "/api/v1/registry/aircraft/<uuid>/",
                        "permission": "registry.view_aircraft",
                    },
                    "tasks_list": {
                        "method": "GET",
                        "path": "/api/v1/workboard/tasks/",
                        "permission": "workboard.view_kanbantask",
                        "deprecated": True,
                        "notes": "The Kanban board is being retired (LV-78).",
                        "filters": [
                            "board",
                            "operator",
                            "priority",
                            "state",
                            "label",
                            "q",
                            "page",
                            "page_size",
                        ],
                    },
                    "task_update": {
                        "method": "PATCH",
                        "path": "/api/v1/workboard/tasks/<uuid>/",
                        "permission": "workboard.change_kanbantask",
                        "deprecated": True,
                        "fields": [
                            "title",
                            "description",
                            "priority",
                            "stage_id",
                            "due_date",
                        ],
                    },
                },
            }
        )


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
