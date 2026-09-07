"""R3: el informe mensual RPA, visible dentro de la aplicación.

Una sola pantalla que dibuja las cinco hojas A4 del documento emitido. Sirve dos
casos y **dice cuál está mirando**:

- **Un `ReportRun` congelado** del período: se dibuja su `payload` tal como
  quedó guardado. Es lo que hace posible que un informe de agosto siga diciendo
  en diciembre lo que decía en agosto.
- **Sin informe congelado**: se construye el payload al vuelo y se rotula como
  vista previa. Congelar y aprobar es `R5`; verlo no depende de eso.

⚠️ **La distinción se declara en la pantalla y no es cosmética.** Un borrador
que alguien imprima y firme creyéndolo emitido es el peor resultado posible de
esta vista, y la diferencia entre uno y otro no se ve en el papel: las mismas
cinco páginas, las mismas cifras. Por eso el aviso va arriba y fuera de la
impresión.
"""

import re
from datetime import date

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.generic import TemplateView, View

from apps.core.audit import set_audit_context
from apps.core.views import (
    ModelPermissionRequiredMixin,
    ModelViewPermissionRequiredMixin,
)
from apps.reporting.builder import build, month_bounds
from apps.reporting.forms import FindingFormSet, PeriodNoteForm
from apps.reporting.models import ReportRun

# Cuatro dígitos de año y dos de mes, exactos. Partir por el guion y confiar en
# `int()` acepta `26-8` y devuelve **el año 26**: un informe fechado dieciocho
# siglos atrás, con su portada y su código, y sin nada que avise. Un formato que
# se ensancha en silencio es peor que uno que rechaza.
PERIOD = re.compile(r"^(\d{4})-(\d{2})$")


def previous_month(today):
    """El mes cerrado anterior a `today`.

    Es el período por defecto porque un informe mensual describe un mes
    terminado: abrir la pantalla el 2 de septiembre y encontrar septiembre a
    medio correr invita a leer como cierre lo que todavía se está moviendo.
    """
    first, _last = month_bounds(today)
    return date.fromordinal(first.toordinal() - 1).replace(day=1)


def parse_period(raw, today):
    """`?period=YYYY-MM` → el primer día de ese mes.

    Una cadena que no es un mes cae al período por defecto en vez de reventar:
    el parámetro llega de un `<input type="month">` y de enlaces pegados a mano,
    y un 500 por un mes mal escrito no le dice nada a nadie.
    """
    match = PERIOD.match(raw or "")
    if not match:
        return previous_month(today)
    try:
        return date(int(match[1]), int(match[2]), 1)
    except ValueError:  # mes 00 o 13
        return previous_month(today)


class MonthlyReportView(ModelViewPermissionRequiredMixin, TemplateView):
    """Las cinco hojas del informe del período pedido.

    Lectura pura: ni congela, ni aprueba, ni escribe nada. El permiso es el de
    ver el informe (`reporting.view_reportrun`) y no un `LoginRequiredMixin` a
    secas, como manda el contrato de permisos de `AGENTS.md` para toda vista de
    lectura — y acá pesa más que en otras: la pantalla nombra faenas, cifras de
    cobertura y el estado de habilitación de cada una.
    """

    template_name = "reporting/monthly_report.html"
    model = ReportRun

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        period = parse_period(self.request.GET.get("period"), today)
        # La última revisión del período, que es la que vale: una corrección
        # nace como revisión siguiente y deja la anterior como `superseded`.
        run = ReportRun.objects.filter(period=period).order_by("-revision").first()
        if run:
            payload, missing = run.payload, run.missing_fields
        else:
            payload, missing = build(period)

        context.update(
            {
                "run": run,
                "payload": payload,
                "missing_fields": missing,
                "period_date": period,
                # Las fechas del payload vienen en ISO porque el payload es
                # JSON. Se convierten **desde el payload** y no desde la base:
                # un informe congelado tiene que fechar lo que congeló, no lo
                # que la consulta devolvería hoy.
                "cutoff_date": _iso(payload.get("meta", {}).get("cutoff")),
                "covers_from": _iso(
                    payload.get("meta", {}).get("covers", {}).get("from")
                ),
                "covers_to": _iso(payload.get("meta", {}).get("covers", {}).get("to")),
                "revision_label": (
                    _("Revision %(number)s") % {"number": run.revision}
                    if run
                    else _("Draft")
                ),
            }
        )
        return context


def _iso(value):
    """Una fecha ISO del payload como `date`, o `None` si no la trae.

    `None` y no "hoy": una plantilla que recibe la fecha de hoy donde faltaba la
    del corte imprime un informe fechado hoy sin que nada avise.
    """
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


class ReportDraftCreate(ModelPermissionRequiredMixin, View):
    """Congela el borrador del período, que es lo que habilita escribir en él.

    **La narrativa necesita dónde vivir.** Se guarda en el `ReportRun` porque es
    parte del documento —un informe aprobado tiene que seguir diciendo lo que
    decía, redacción incluida—, así que antes de escribir hay que crear la fila.

    **Es un paso explícito y no un efecto secundario de guardar el texto**, y
    ésa es la decisión: congelar el payload es el acto que separa "esto se mueve
    con la base" de "esto es el informe de agosto". Que ocurriera de refilón al
    escribir el primer hallazgo dejaría la cifra congelada en un instante que
    nadie eligió.

    Crea sólo el borrador de la revisión 0. Regenerar, comparar y aprobar es
    `R5`; esto es la mitad que `LV-227` necesita para existir.
    """

    model = ReportRun
    permission_action = "add"

    def post(self, request):
        period = parse_period(request.POST.get("period"), timezone.localdate())
        # **El mismo `freeze` que usa el trabajo programado** (`R5`), no una
        # copia: dos caminos que congelan por separado es cómo el informe que
        # genera el timer y el que genera una persona empiezan a diferir.
        try:
            run, created = ReportRun.freeze(period, request.user.get_username())
        except ValidationError as refused:
            # LV-233: el mes todavía no terminó. Se dice y se vuelve a la
            # pantalla, que sigue mostrando la vista previa en vivo -- mirar el
            # mes en curso está bien; lo que no se puede es convertirlo en
            # documento.
            messages.error(request, refused.messages[0])
            return redirect(f"{reverse('monthly-report')}?period={period:%Y-%m}")
        if not created:
            # La respuesta correcta a "ya existe" no es devolverlo callando:
            # quien apretó el botón dos veces tiene que saber cuál de las dos
            # cosas pasó.
            messages.info(
                request, _("This period already had a report; opening the latest one.")
            )
        else:
            set_audit_context(request, run, action="create")
            messages.success(
                request, _("Draft frozen. You can now write its narrative.")
            )
        return redirect(f"{reverse('monthly-report')}?period={period:%Y-%m}")


class ReportNarrativeUpdate(ModelPermissionRequiredMixin, View):
    """Los hallazgos y la observación del período, escritos a mano.

    **Un informe aprobado no se edita**: es el documento que se envió, y
    reescribirlo dejaría a la DGAC con una copia que ya no existe de este lado.
    Se comprueba con `is_editable`, la misma propiedad que el modelo ya definía
    — no con una condición nueva que pueda desviarse de ella.
    """

    model = ReportRun
    permission_action = "change"

    def get(self, request, pk):
        run = get_object_or_404(ReportRun, pk=pk)
        return self._render(request, run, self._note(run), self._findings(run))

    def post(self, request, pk):
        run = get_object_or_404(ReportRun, pk=pk)
        if not run.is_editable:
            messages.error(
                request,
                _("An approved report is not edited: issue a new revision instead."),
            )
            return redirect(f"{reverse('monthly-report')}?period={run.period:%Y-%m}")

        note = self._note(run, request.POST)
        findings = self._findings(run, request.POST)
        if not (note.is_valid() and findings.is_valid()):
            return self._render(request, run, note, findings)

        run = note.save(commit=False)
        run.findings = findings.entries
        # `full_clean` y no sólo `save`: la comprobación de forma vive en el
        # modelo justamente para que ningún camino la esquive, y la vista es un
        # camino más.
        run.full_clean()
        run.save(update_fields=["period_note", "findings", "updated_at"])
        set_audit_context(request, run, action="update")
        messages.success(request, _("Saved successfully."))
        return redirect(f"{reverse('monthly-report')}?period={run.period:%Y-%m}")

    @staticmethod
    def _note(run, data=None):
        return PeriodNoteForm(data, instance=run)

    @staticmethod
    def _findings(run, data=None):
        return FindingFormSet(data, initial=run.findings, prefix="findings")

    @staticmethod
    def _render(request, run, note, findings):
        return render(
            request,
            "reporting/narrative_form.html",
            {"run": run, "note_form": note, "finding_formset": findings},
        )


class ReportApprove(ModelPermissionRequiredMixin, View):
    """R5: aprobar es lo que convierte el borrador en el documento emitido.

    **Lo hace una persona y nunca el trabajo programado.** El informe va firmado
    ante la DGAC: un timer que aprobara en nombre de alguien estaría firmando, y
    la fecha y el nombre que quedan en la fila son evidencia de quién respondió
    por esas cifras.

    Aprobar **cierra** el informe: deja de ser editable y una corrección nace
    como revisión siguiente (`--force` del comando). Por eso no se re-aprueba —
    el guard vive en `ReportRun.approve` y no acá, para que el admin y el shell
    tropiecen con el mismo.

    ⚠️ **Hoy alcanza con `change_reportrun`**, o sea que quien redacta la
    narrativa puede además aprobarla. Para una evidencia ISO eso es una pregunta
    de segregación de funciones y **no la decide el código**: separarla exige un
    permiso propio y decidir a qué rol va, que es del usuario. Anotado en la
    fila; mientras tanto, la auditoría registra quién aprobó.
    """

    model = ReportRun
    permission_action = "change"

    def post(self, request, pk):
        run = get_object_or_404(ReportRun, pk=pk)
        try:
            run.approve(request.user.get_username())
        except ValidationError as error:
            messages.error(request, error.messages[0])
        else:
            set_audit_context(request, run, action="approve")
            messages.success(request, _("Report approved. It is now read-only."))
        return redirect(f"{reverse('monthly-report')}?period={run.period:%Y-%m}")
