"""Shared choice constants used by more than one model/app.

Plain tuples, not TextChoices (T3.4 -- "migrate statuses to TextChoices" --
is deferred as churn without payoff, and there is no TextChoices anywhere
in this repo yet; introducing one here just for this field would be its
own inconsistency).
"""

from django.utils.translation import gettext_lazy as _

# R3.1: the closed vocabulary for `purpose` on FlightPermission, Assignment,
# OperatorAssignment and AircraftAssignment. Confirmed against real data
# (R3.1a, `report_purpose_mapping`) and against the user directly: the two
# SIGO procedures under DAN 137 Cap. J are "Fotogrametría" and "Videos" --
# not "Videografía", which the user explicitly rejected as not fitting this
# operation's usage. "Other" exists because the pre-existing free-text data
# is not clean enough to force into just these two (see PURPOSE_LEGACY_MAP
# below and R3.1a's report output: every real historical value found mixed
# more than one concept, e.g. "Fotogrametría - Fotos - Videos").
#
# LV-196: **"Patrullaje" entra**, pedido del usuario mirando el selector del
# permiso: *"sumar Patrullaje ya que se usará mucho"*. No corrige nada de R3.1 —
# es una decisión de negocio suya, y la razón es medible: hoy un patrullaje se
# registra como "Otro" con el texto en `purpose_detail`, así que no se puede
# contar ni filtrar, que es exactamente lo que el vocabulario cerrado vino a
# permitir. Un tercer procedimiento no rompe la premisa; que quedara fuera del
# catálogo sí la vaciaba.
#
# Va **último antes de "Otro"**: "Otro" tiene que quedar al final del
# desplegable, porque es el escape y no una opción más.
PURPOSE_CHOICES = [
    ("photogrammetry", _("Photogrammetry Procedure")),
    ("video", _("Video Procedure")),
    ("patrol", _("Patrol")),
    ("other", _("Other")),
]

# Exact, case-insensitive matches only -- used by both `report_purpose_mapping`
# (R3.1a) and the R3.1 backfill migrations. A value not in here becomes
# "other" with the original text preserved in `purpose_detail`, never a
# guess at which of the two procedures it meant.
PURPOSE_LEGACY_MAP: dict[str, str] = {
    "fotogrametría": "photogrammetry",
    "fotogrametria": "photogrammetry",
    "videos": "video",
    "video": "video",
    # LV-196: las dos formas exactas, con y sin tilde, igual que arriba. **No se
    # agrega "patrullaje aéreo" ni variantes**: la regla de este mapa es
    # coincidencia exacta y nunca adivinar, y su comentario explica por qué —
    # cada valor histórico real encontrado mezclaba más de un concepto.
    #
    # ⚠️ Esto **no reclasifica lo que ya está en la base**. El mapa lo usan
    # `report_purpose_mapping` y las migraciones de relleno de R3.1, que ya
    # corrieron; los permisos que hoy dicen "Otro" con un patrullaje en el
    # detalle se quedan así hasta que alguien decida moverlos, y esa decisión es
    # del usuario con el listado a la vista, no de una migración que adivine.
    "patrullaje": "patrol",
}
