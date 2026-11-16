"""LV-450: how a detail sheet groups a model's fields into cards.

Presentation only, no business rules. A model listed in `LAYOUTS` gets the card
sheet (`templates/generic/_sheet.html`); any other model keeps the plain table.
Fields not named by any group fall into a trailing "Other data" card, so a new
model field is never silently hidden.
"""

from django.utils.translation import gettext_lazy as _

# Each group: (key, label, field names). Order is the reading order.
LAYOUTS = {
    "registry.operator": (
        (
            "identification",
            _("Identification"),
            (
                "full_name",
                "given_names",
                "surnames",
                "employee_id",
                "rut",
                "operator_type",
            ),
        ),
        ("contact", _("Contact"), ("email", "phone", "address")),
        ("credential", _("DGAC credential"), ("dgac_credential", "credential_expiry")),
        ("qualifications", _("Qualifications"), ("authorizations",)),
        ("assignment", _("Assignment"), ("cost_center", "user")),
        ("notes", _("Notes"), ("notes",)),
    ),
}

# Fields shown even when empty ("Not registered"): what a person needs to operate.
ALWAYS_SHOWN = {
    "registry.operator": frozenset({"dgac_credential", "credential_expiry"}),
}

# Identifiers set in monospace.
CODE_FIELDS = frozenset(
    {"rut", "employee_id", "dgac_credential", "registration", "serial_number", "code"}
)

OTHER_GROUP = ("other", _("Other data"))
