"""`LV-398`: los enlaces de la página «Cómo funciona» (`/inicio/`).

La página explica el proceso de la guía `JEJ-GRI-SS-INS-096` y no muestra datos de
dominio. Lo único que depende de quién mira son los enlaces a pantallas reales: cada
uno declara **todos** los permisos que su vista exige, igual que el registro del menú
(`apps/core/navigation.py`), y sólo se ofrece a quien los tiene. Un enlace que termina
en 403 enseña a desconfiar de la pantalla (`LV-130`); el guardián que cruza estos
permisos con los de cada vista está en `test_lv398_start_page.py`.

Los msgid van en inglés; el español vive en el catálogo.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.urls import reverse
from django.utils.translation import gettext_lazy as _


@dataclass(frozen=True)
class GuideLink:
    key: str
    url_name: str
    label: object
    icon: str  # símbolo de `static/img/icons.svg`, sin el prefijo `icon-`
    permissions: tuple[str, ...]
    description: object = ""

    def allowed_for(self, user) -> bool:
        return all(user.has_perm(perm) for perm in self.permissions)


PERMITS = GuideLink(
    "permits",
    "permission-list",
    _("Permissions"),
    "permission-list",
    ("operations.view_flightpermission",),
    _("DGAC permits by site, with their validity."),
)
GEO_PLANS = GuideLink(
    "geo-plans",
    "geo-plan-list",
    _("Geospatial planning"),
    "geo-plan-list",
    ("geo.view_geoplan",),
)
AIRCRAFT = GuideLink(
    "aircraft",
    "aircraft-list",
    _("Aircraft"),
    "aircraft-list",
    ("registry.view_aircraft",),
    _("The fleet, its documents and its status."),
)
OPERATORS = GuideLink(
    "operators",
    "operator-list",
    _("Operators"),
    "operator-list",
    ("registry.view_operator",),
    _("Pilots, credentials and ratings per model."),
)
DOCUMENTS = GuideLink(
    "documents",
    "company-documents",
    _("Company documents"),
    "company-documents",
    ("compliance.view_document",),
    _("Insurance, manuals and company certificates."),
)
MAINTENANCE = GuideLink(
    "maintenance",
    "maintenance-list",
    _("Maintenance jobs"),
    "maintenance-list",
    ("maintenance.view_maintenancerecord",),
    _("Services, repairs and technical reports."),
)
FLIGHTS = GuideLink(
    "flights",
    "record-list",
    _("Flights"),
    "record-list",
    ("operations.view_flightrecord",),
)
COMPLIANCE = GuideLink(
    "compliance",
    "dashboard-compliance",
    _("Compliance"),
    "compliance-report",
    ("compliance.view_alert",),
    _("What is in force, what is about to expire and what already did."),
)

# Los atajos del final de la página, en el orden en que se recorre el proceso.
SHORTCUTS: tuple[GuideLink, ...] = (
    PERMITS,
    AIRCRAFT,
    OPERATORS,
    DOCUMENTS,
    MAINTENANCE,
    COMPLIANCE,
)

# Cada requisito de «Qué se requiere» con la pantalla donde se lleva.
REQUIREMENT_LINKS: dict[str, GuideLink] = {
    "permit": PERMITS,
    "letter": GEO_PLANS,
    "credential": OPERATORS,
    "insurance": DOCUMENTS,
    "maintenance": MAINTENANCE,
    "logbook": FLIGHTS,
}


def all_links() -> tuple[GuideLink, ...]:
    return (*SHORTCUTS, *(link for link in REQUIREMENT_LINKS.values()))


def _resolved(link: GuideLink) -> dict:
    return {
        "key": link.key,
        "url": reverse(link.url_name),
        "label": link.label,
        "icon": link.icon,
        "description": link.description,
    }


def shortcuts_for(user) -> list[dict]:
    return [_resolved(link) for link in SHORTCUTS if link.allowed_for(user)]


def requirement_links_for(user) -> dict[str, dict]:
    return {
        key: _resolved(link)
        for key, link in REQUIREMENT_LINKS.items()
        if link.allowed_for(user)
    }
