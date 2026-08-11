from django import forms
from django.utils.translation import gettext_lazy as _


def translate_field_label(label):
    """Normalize Django's generated labels before looking them up in gettext.

    Acronyms are preserved: lowercasing them produced lookups like
    "Dgac credential" that never matched the catalog's "DGAC credential",
    so those labels silently fell back to English.
    """

    def normalize(word, first=False):
        if len(word) > 1 and word.isupper():
            return word
        return word.capitalize() if first else word.lower()

    words = str(label).replace("_", " ").split()
    if not words:
        return ""
    return " ".join(
        [normalize(words[0], first=True), *[normalize(word) for word in words[1:]]]
    )


class AeroModelForm(forms.ModelForm):
    """Shared form behavior for translated, correctly typed operational fields."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if field.label:
                field.label = _(translate_field_label(field.label))
            # LV-73 [bug de pérdida de datos]: cambiar `input_type` sin fijar
            # también el `format` hacía que el navegador **descartara el valor**.
            # Django renderizaba la fecha en el formato del locale
            # (`value="21/08/2026"` con LANGUAGE_CODE="es") y un
            # `<input type="date">` sólo acepta ISO `AAAA-MM-DD`, así que el
            # campo se mostraba **vacío** aunque la base tuviera el dato — y
            # guardar el formulario lo borraba en silencio. Se descubrió en el
            # demo abriendo la ficha de RPA-2002, cuyo seguro JAC vencía el
            # 2026-08-21 y aparecía en blanco.
            # El lado del guardado ya estaba bien: `DATE_INPUT_FORMATS` del
            # locale `es` incluye `%Y-%m-%d`, así que sólo faltaba emitirlo así.
            if isinstance(field.widget, forms.DateTimeInput):
                field.widget.input_type = "datetime-local"
                field.widget.format = "%Y-%m-%dT%H:%M"
            elif isinstance(field.widget, forms.DateInput):
                field.widget.input_type = "date"
                field.widget.format = "%Y-%m-%d"
            elif isinstance(field.widget, forms.TimeInput):
                field.widget.input_type = "time"
                field.widget.format = "%H:%M"
            elif isinstance(field.widget, forms.Textarea):
                # LV-35: textareas (Notas, dirección, servicios…) start at a
                # medium height instead of the oversized default block; the user
                # can still drag to grow them.
                field.widget.attrs.setdefault("rows", 3)
            field.widget.attrs.setdefault("autocomplete", "off")
