"""`LV-396`: enlaces a los sistemas oficiales de la DGAC (SIGO y SIPA).

Las URL viven acá, como constantes, y no en las plantillas: igual que `AIP_ENR_URL`
(`apps/airspace/payload.py`), así hay un solo lugar donde corregirlas si la DGAC las
mueve. El mismo registro alimenta las tarjetas del panel, el grupo «Enlaces oficiales»
del menú lateral y (después) la página de inicio, y por eso llega por context processor.

No llevan logos ni capturas de la DGAC: son marcas de terceros y el CSP sólo admite
imágenes propias. Los msgid van en inglés; el español vive en el catálogo.
"""

from django.utils.translation import gettext_lazy as _

# Sistema de Gestión de Seguridad Operacional: autorizaciones de operación RPA y permisos.
SIGO_URL = "https://servicios.dgac.gob.cl/sigo-web/#/"
# Sistema Informático de Personal Aeronáutico: licencias y habilitaciones del personal.
SIPA_URL = "https://sipa.dgac.gob.cl/"

OFFICIAL_LINKS = (
    {
        "key": "sigo",
        "acronym": "SIGO",
        "name": _("Operational Safety Management System (SIGO)"),
        "purpose": _(
            "Use it to validate RPA operating authorizations and manage DGAC flight permits."
        ),
        "url": SIGO_URL,
        "icon": "permission-list",
    },
    {
        "key": "sipa",
        "acronym": "SIPA",
        "name": _("Aeronautical Personnel Information System (SIPA)"),
        "purpose": _(
            "Use it for the licenses and ratings of aeronautical personnel, and to verify licenses."
        ),
        "url": SIPA_URL,
        "icon": "operator-list",
    },
)


def official_links(request):
    """Disponibles en toda página para quien inició sesión (el menú no se dibuja sin sesión)."""
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}
    return {"official_links": OFFICIAL_LINKS}
