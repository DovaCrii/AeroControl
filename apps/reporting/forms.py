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
from django.forms import formset_factory, inlineformset_factory
from django.utils.translation import gettext_lazy as _

from apps.reporting.models import ExigibilityRow, PlanPhase, ReportRun, ReportTemplate

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


class ActionForm(forms.Form):
    """Una fila de "Acciones requeridas este mes", del Dato Ejecutivo.

    `due` es opcional y las otras dos no, y eso es la forma del documento: una
    acción sin responsable es una acción que nadie hace, mientras que una sin
    plazo todavía puede estar pendiente de acordarse. La plantilla en papel
    dejaba pasar las tres vacías; acá una fila escrita a medias no se guarda.
    """

    action = forms.CharField(label=_("Action"), max_length=200)
    owner = forms.CharField(label=_("Owner"), max_length=100)
    due = forms.CharField(label=_("Due"), max_length=40, required=False)


class BaseActionFormSet(forms.BaseFormSet):
    """Mismo trato que los hallazgos: sin huecos en medio.

    Una fila vacía entre dos llenas dibuja un renglón en blanco en una hoja que
    se lleva a la reunión. Se rechaza en vez de compactarla en silencio, porque
    compactar cambiaría el orden que eligió quien la escribe.
    """

    def clean(self):
        super().clean()
        if any(self.errors):
            return
        seen_blank = False
        for is_filled in (bool(form.cleaned_data) for form in self.forms):
            if not is_filled:
                seen_blank = True
            elif seen_blank:
                raise forms.ValidationError(
                    _("Leave no empty action between two written ones.")
                )

    @property
    def entries(self):
        return [
            {
                "action": form.cleaned_data["action"],
                "owner": form.cleaned_data["owner"],
                "due": form.cleaned_data.get("due", ""),
            }
            for form in self.forms
            if form.cleaned_data
        ]


# Tres es lo que la plantilla en papel numera, y el tope es deliberado: una lista
# de acciones que crece sin fin deja de ser un compromiso del mes y pasa a ser un
# inventario de pendientes, que ya tiene su lugar en el tablero de alertas.
MAX_ACTIONS = 6

ActionFormSet = formset_factory(
    ActionForm,
    formset=BaseActionFormSet,
    extra=1,
    max_num=MAX_ACTIONS,
    validate_max=True,
    can_delete=False,
)


# --- LV-249: los bloques editables del informe -------------------------------


def _bootstrap(form):
    """Las clases de Bootstrap que la plantilla no pone.

    La pantalla dibuja campo por campo, y sin esto los campos salían con el borde
    del navegador y 180 px de ancho — comprobado en pantalla, no supuesto.
    """
    for field in form.fields.values():
        widget = field.widget
        if isinstance(widget, forms.CheckboxInput):
            css = "form-check-input"
        elif isinstance(widget, forms.Select):
            css = "form-select form-select-sm"
        else:
            css = "form-control"
        widget.attrs["class"] = f"{widget.attrs.get('class', '')} {css}".strip()


class ReportTemplateForm(forms.ModelForm):
    """La portada y el texto de apertura del plan.

    Campos declarados uno a uno y no `"__all__"`: `AGENTS.md` lo prohíbe en
    formularios de escritura, y acá `is_active` y `notes` no son del informe.
    """

    class Meta:
        model = ReportTemplate
        fields = [
            "issued_by",
            "jointly_with",
            "standard",
            "addressed_to",
            "scope",
            "sources",
            "plan_lede",
        ]
        widgets = {"plan_lede": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrap(self)


class PlanPhaseForm(forms.ModelForm):
    """Una fase del plan. El mes se elige como mes, no como fecha: una fase es el
    mes entero, y pedir un día invitaría a creer que importa."""

    month = forms.DateField(
        label=_("Month"),
        input_formats=["%Y-%m", "%Y-%m-%d"],
        widget=forms.DateInput(attrs={"type": "month"}, format="%Y-%m"),
    )

    class Meta:
        model = PlanPhase
        fields = ["month", "title", "text", "close"]
        widgets = {"text": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrap(self)


PlanPhaseFormSet = inlineformset_factory(
    ReportTemplate,
    PlanPhase,
    form=PlanPhaseForm,
    extra=1,
    can_delete=True,
)


class ExigibilityRowForm(forms.ModelForm):
    """Una fila de la matriz, con un nivel **por cada fase guardada**.

    Las columnas no son campos fijos: se agregan al construir el formulario, una
    por fase, porque la matriz tiene tantas columnas como fases el plan. Es lo que
    evita el SEP–DIC escrito a mano que había en la plantilla.
    """

    class Meta:
        model = ExigibilityRow
        fields = ["order", "label", "emphasis"]

    def __init__(self, *args, phases=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.phases = list(phases)
        levels = self.instance.levels if self.instance.pk else {}
        for phase in self.phases:
            self.fields[self.level_field(phase)] = forms.ChoiceField(
                label=f"{phase.month:%Y-%m}",
                choices=ExigibilityRow.LEVEL_CHOICES,
                initial=levels.get(phase.key, ExigibilityRow.LEVEL_NA),
                required=False,
            )
        _bootstrap(self)

    @staticmethod
    def level_field(phase):
        return f"level_{phase.key}"

    def level_fields(self):
        """Los campos de nivel, en el orden de las fases, para la plantilla."""
        return [self[self.level_field(phase)] for phase in self.phases]

    def save(self, commit=True):
        row = super().save(commit=False)
        # Se conservan los niveles de meses que ya no son fase: si alguien borra una
        # fase y la vuelve a crear, la fila no pierde lo que decía de ese mes.
        levels = dict(row.levels or {})
        for phase in self.phases:
            levels[phase.key] = (
                self.cleaned_data.get(self.level_field(phase))
                or ExigibilityRow.LEVEL_NA
            )
        row.levels = levels
        if commit:
            row.full_clean()
            row.save()
        return row


ExigibilityRowFormSet = inlineformset_factory(
    ReportTemplate,
    ExigibilityRow,
    form=ExigibilityRowForm,
    extra=1,
    can_delete=True,
)
