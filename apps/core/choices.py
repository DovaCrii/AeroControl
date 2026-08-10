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
PURPOSE_CHOICES = [
    ("photogrammetry", _("Photogrammetry Procedure")),
    ("video", _("Video Procedure")),
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
}
