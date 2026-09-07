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


#: `UX-21`. Nombres de campo que son un teléfono aunque su tipo sea `CharField`.
#: Se comprueba por subcadena porque en el proyecto conviven `phone`,
#: `contact_phone` y `emergency_phone`.
_TEL_FIELD_HINTS = ("phone", "telefono", "movil", "celular")


def _set_mobile_input_hints(name, field):
    """`UX-21`: `inputmode` y `autocomplete` según lo que el campo **es**.

    El criterio de la fila es literal: *"un campo numérico abre teclado numérico
    en móvil"*. Y pesa más acá que en una aplicación de escritorio, porque quien
    carga una bitácora lo hace en faena, en un teléfono: un teclado alfabético
    para escribir una altura de vuelo o una coordenada es fricción en cada dato,
    varias veces por jornada.

    Se deduce del **tipo del campo**, no de su nombre — un `DecimalField` es
    decimal en todos los modelos— con una sola excepción declarada: "teléfono"
    no tiene tipo propio en Django y sólo se sabe por cómo se llama.

    ⚠️ **`enterkeyhint` no se pone, y es deliberado.** Su valor correcto depende
    de si el campo es el último del formulario —ahí `done`, si no `next`— y eso
    el formulario no lo sabe: el orden final lo arma la plantilla, y varias
    reordenan u ocultan campos. Un `enterkeyhint="next"` en el último campo
    promete un salto que no ocurre, y una promesa falsa en el teclado es peor
    que ninguna pista.

    ⚠️ **Y `autocomplete` sólo se levanta donde el navegador acierta.** El
    defecto del proyecto es `off` y se conserva: en un formulario de cumplimiento
    casi todo campo describe un registro *ajeno* —la matrícula de una aeronave,
    el folio de un permiso, el correo del titular— así que ofrecer ahí lo que la
    persona escribió en otro formulario invita a guardar el dato de otro. Se abre
    sólo donde lo sugerido sería de quien escribe.
    """
    widget = field.widget
    # Sin caja de texto no hay teclado que dirigir; y `HiddenInput` no se toca
    # porque su valor no lo escribe nadie.
    if isinstance(
        widget,
        (forms.CheckboxInput, forms.Select, forms.Textarea, forms.FileInput),
    ):
        return
    # `getattr`: `input_type` lo declaran las subclases de `Input`, no `Widget`,
    # y un formulario puede traer un widget propio que no lo tenga.
    if getattr(widget, "input_type", "") in {
        "hidden",
        "date",
        "datetime-local",
        "time",
    }:
        # Las de fecha ya las fijó `AeroModelForm.__init__`, y el teclado de un
        # `<input type="date">` lo elige el sistema operativo: un `inputmode`
        # encima sólo puede empeorarlo.
        return

    attrs = widget.attrs
    if isinstance(field, (forms.DecimalField, forms.FloatField)):
        # `decimal` y no `numeric`: acá viajan coordenadas, radios y horas de
        # vuelo, y un teclado sin separador decimal los vuelve inescribibles.
        attrs.setdefault("inputmode", "decimal")
    elif isinstance(field, forms.IntegerField):
        attrs.setdefault("inputmode", "numeric")
    elif isinstance(field, forms.EmailField):
        attrs.setdefault("inputmode", "email")
    elif any(hint in name.lower() for hint in _TEL_FIELD_HINTS):
        attrs.setdefault("inputmode", "tel")


class AeroModelForm(forms.ModelForm):
    """Shared form behavior for translated, correctly typed operational fields."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # LV-142: la fila que ya ocupa el valor duplicado, cuando un `clean_*`
        # la encuentra. La deja acá para que la vista pueda ofrecer su ficha; el
        # mensaje de error se levanta igual, no depende de esto.
        self.duplicate_of = None
        for name, field in self.fields.items():
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
            _set_mobile_input_hints(name, field)

    def validate_constraints(self):
        """LV-142: una `UniqueConstraint` que menciona `tenant` no se validaba nunca.

        `tenant` no está en ningún formulario de escritura del proyecto — viene
        del `default` del campo, no de la pantalla— así que
        `_get_validation_exclusions()` lo excluye, y `UniqueConstraint.validate()`
        retorna sin mirar en cuanto alguno de sus campos está excluido. Resultado:
        el duplicado pasaba la validación y moría como `IntegrityError`, o sea un
        500 sin mensaje. Devolver `tenant` al alcance **sólo para esta
        comprobación** basta: `Model.__init__` ya puso su valor.

        Es la red, no el aviso. El mensaje de Django es genérico y aterriza en
        `__all__`; los `clean_*` de cada formulario dicen quién tiene el valor.
        Cuando uno de ellos dispara, el campo sale de `cleaned_data`,
        `construct_instance` no lo escribe y la exclusión lo cubre: no hay
        mensaje doble.
        """
        exclude = self._get_validation_exclusions()
        exclude.discard("tenant")
        try:
            self.instance.validate_constraints(exclude=exclude)
        except forms.ValidationError as exc:
            self._update_errors(exc)
