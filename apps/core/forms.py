from django import forms
from django.utils.translation import gettext_lazy as _


def translate_field_label(label):
    """Normalize Django's generated labels before looking them up in gettext."""
    words = str(label).replace("_", " ").split()
    if not words:
        return ""
    return " ".join([words[0].capitalize(), *[word.lower() for word in words[1:]]])


class AeroModelForm(forms.ModelForm):
    """Shared form behavior for translated, correctly typed operational fields."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if field.label:
                field.label = _(translate_field_label(field.label))
            if isinstance(field.widget, forms.DateTimeInput):
                field.widget.input_type = "datetime-local"
            elif isinstance(field.widget, forms.DateInput):
                field.widget.input_type = "date"
            elif isinstance(field.widget, forms.TimeInput):
                field.widget.input_type = "time"
            field.widget.attrs.setdefault("autocomplete", "off")
