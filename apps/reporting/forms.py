"""`LV-227`: la narrativa del informe, escrita dentro de la aplicación.

Pedido del usuario: *"ver una opción del template subido dentro de la app, poder
modificarlo y que respete cambios, hacerlo directamente ahí sería interesante"*,
y confirmado después al preguntar por herramientas de edición.

**No es un editor de plantillas, y la distinción es la fila entera.** Lo que se
edita son los dos bloques que el informe emitido trae redactados a mano y que
cambian todos los meses: los hallazgos del período y la observación sobre los
permisos. El resto del documento —su estructura, sus cifras, su portada— no se
edita: las cifras salen de la base, y corregir una cifra es corregir el dato.

Un hallazgo es **un juicio sobre** las cifras, no una consulta: *"la renovación
exige una nueva carta del mandante, cuya gestión debía haber comenzado ya"* no
se deriva de ninguna columna. Por eso se escribe y se guarda.
"""

from django import forms
from django.forms import formset_factory
from django.utils.translation import gettext_lazy as _

from apps.reporting.models import ReportRun

# Cuatro hallazgos trae el informe emitido. El tope deja aire sin volver la
# página 2 una lista interminable: el resumen ejecutivo se lee de un vistazo o
# no se lee, y ocho párrafos en una hoja A4 ya no caben con las tarjetas encima.
MAX_FINDINGS = 8


class FindingForm(forms.Form):
    """Un hallazgo: su gravedad, su encabezado y lo que dice.

    El encabezado va aparte del texto porque el informe emitido lo dibuja en
    negrita seguido de un guion —*"Cobertura parcial —"*— y esa separación es
    del diseño, no del redactor. Pedirla como una sola cadena obligaría a quien
    escribe a acordarse de poner el guion, y el día que no lo ponga la página
    sale distinta.
    """

    severity = forms.ChoiceField(
        label=_("Severity"),
        choices=[
            (ReportRun.FINDING_CRITICAL, _("Critical")),
            (ReportRun.FINDING_WARNING, _("Warning")),
        ],
    )
    title = forms.CharField(label=_("Heading"), max_length=80)
    text = forms.CharField(label=_("Finding"), widget=forms.Textarea(attrs={"rows": 3}))


class BaseFindingFormSet(forms.BaseFormSet):
    def clean(self):
        """Los hallazgos van sin huecos en medio.

        Un formulario vacío entre dos llenos es fácil de dejar al borrar el del
        medio, y guardado tal cual dibujaría un recuadro en blanco en la página
        2 de un documento que va a la autoridad. Se rechaza en vez de
        compactarlo en silencio: compactar cambiaría el orden que el redactor
        ve, y el orden de los hallazgos es suyo.
        """
        super().clean()
        if any(self.errors):
            return
        seen_blank = False
        for is_filled in (bool(form.cleaned_data) for form in self.forms):
            if not is_filled:
                seen_blank = True
            elif seen_blank:
                raise forms.ValidationError(
                    _("Leave no empty finding between two written ones.")
                )

    @property
    def entries(self):
        """Los hallazgos escritos, listos para guardar en el `JSONField`.

        Se leen de `cleaned_data` y no de los datos crudos: así lo que se guarda
        es exactamente lo que el formulario validó.
        """
        return [
            {
                "severity": form.cleaned_data["severity"],
                "title": form.cleaned_data["title"],
                "text": form.cleaned_data["text"],
            }
            for form in self.forms
            if form.cleaned_data
        ]


FindingFormSet = formset_factory(
    FindingForm,
    formset=BaseFindingFormSet,
    extra=1,
    max_num=MAX_FINDINGS,
    validate_max=True,
    can_delete=False,
)


class PeriodNoteForm(forms.ModelForm):
    """La observación del período — un párrafo, el de la página 3.

    `fields` explícito y no `"__all__"`: esta pantalla edita la **narrativa** y
    nada más. Con `"__all__"` un POST podría llegar a `status`, `approved_by` o
    al propio `payload`, y ahí se pierde la garantía de que las cifras del
    informe salieron de la base.
    """

    class Meta:
        model = ReportRun
        fields = ["period_note"]
        widgets = {"period_note": forms.Textarea(attrs={"rows": 4})}
        labels = {"period_note": _("Note for the period")}
        help_texts = {
            "period_note": _(
                "Shown on the permits page. Leave it empty and the report says "
                "the note is pending, never that there is nothing to say."
            )
        }
