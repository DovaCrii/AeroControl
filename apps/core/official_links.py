"""`LV-396`: enlaces a los sistemas oficiales de la DGAC (SIGO y SIPA).

Las URL viven acá, como constantes, y no en las plantillas: igual que `AIP_ENR_URL`
(`apps/airspace/payload.py`), así hay un solo lugar donde corregirlas si la DGAC las
mueve. El mismo registro alimenta las tarjetas del panel, el grupo «Enlaces oficiales»
del menú lateral y (después) la página de inicio, y por eso llega por context processor.

El repo no lleva logos ni capturas de la DGAC: son marcas de terceros y el repo es público.
Desde LV-399 quien administra puede cargar el banner de cada sistema (archivo o URL de
`dgac.gob.cl`), que se guarda en el almacenamiento privado y la app sirve con sesión, así que
el CSP sigue admitiendo sólo imágenes propias. Los msgid van en inglés; el español vive en el
catálogo.
"""

from django.utils.functional import SimpleLazyObject
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
    return {
        "official_links": OFFICIAL_LINKS,
        "official_link_cards": SimpleLazyObject(_cards),
    }


def _cards():
    """LV-399: los enlaces con la URL de su banner oficial, si alguien lo cargó.

    Perezoso a propósito: el menú lateral (en cada página) usa `official_links` y no toca la
    base; sólo la plantilla que dibuja las tarjetas (`dashboard/_official_links.html`) evalúa
    esto, con **una** consulta.
    """
    from django.urls import reverse

    from apps.core.models import OfficialLinkImage

    images = {
        image.link_key: image
        for image in OfficialLinkImage.objects.filter(is_active=True).only(
            "pk", "link_key", "updated_at"
        )
    }
    cards = []
    for link in OFFICIAL_LINKS:
        image = images.get(link["key"])
        url = ""
        if image is not None:
            url = "{}?v={}".format(
                reverse("official-link-image", args=[link["key"]]),
                int(image.updated_at.timestamp()),
            )
        cards.append({**link, "image_url": url})
    return cards
