from django.utils.translation import gettext_lazy as _

from apps.core.forms import AeroModelForm
from .models import MaintenanceHistory, MaintenanceRecord


class MaintenanceRecordForm(AeroModelForm):
    class Meta:
        model = MaintenanceRecord
        fields = [
            "aircraft",
            "maintenance_type",
            "description",
            "scheduled_date",
            "performed_by",
        ]
        labels = {
            # "Maintenance type" rendered untranslated (LV-8d): the derived
            # label was not in the catalog. Spelled out here so all labels are
            # controlled and translated.
            "aircraft": _("Aircraft"),
            "maintenance_type": _("Maintenance type"),
            "description": _("Description"),
            "scheduled_date": _("Scheduled date"),
            "performed_by": _("Performed by"),
        }
        help_texts = {
            "scheduled_date": _(
                "Leave blank for a 'to be defined' maintenance until it is planned."
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # R5.5: registration alone doesn't distinguish "which M300" in a
        # dropdown with several of the same model.
        self.fields["aircraft"].label_from_instance = lambda obj: obj.selector_label


class MaintenanceHistoryForm(AeroModelForm):
    class Meta:
        model = MaintenanceHistory
        fields = ["record", "previous_status", "new_status", "changed_by"]


class MaintenanceCompletionForm(AeroModelForm):
    class Meta:
        model = MaintenanceRecord
        fields = ["completed_date", "performed_by", "notes"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # performed_by is optional on the model (a "to be defined" record has
        # none yet, LV-8b) but completing a maintenance must record who did it
        # and when, so both are required in this context.
        self.fields["completed_date"].required = True
        self.fields["performed_by"].required = True
