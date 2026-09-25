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
from apps.reporting.forms import ActionFormSet, FindingFormSet, PeriodNoteForm
from apps.reporting.models import ReportRun
from apps.reporting.summary import executive_summary

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
        context.update(self._sheets(payload))
        # LV-260: la hoja ejecutiva, calculada del payload y no de la base.
        context["summary"] = executive_summary(payload)
        return context

    @staticmethod
    def _sheets(payload):
        """El reparto de las tablas en hojas, y la numeración del documento.

        ⚠️ **La numeración se asigna acá, en un solo lugar.** Antes cada plantilla
        de página traía su número escrito a mano (`page=3`) y el pie decía
        «de 5» literal — cierto para el informe emitido de agosto, y falso en
        cuanto la tabla necesita una hoja más. Dos sitios decidiendo la
        numeración es cómo un documento termina con dos hojas numeradas igual.

        Las hojas fijas son cuatro —portada, resumen, y las dos últimas— y en
        medio van tantas como pidan los permisos.
        """
        from .pagination import CLOSING_PX, ROW_BASE_PX, row_px, sheets_for

        permits = payload.get("permits") or []
        in_force = [row for row in permits if row.get("in_force")]
        awaiting = [row for row in permits if not row.get("in_force")]
        # El bloque de "en trámite" cierra la sección junto a la observación y la
        # leyenda, así que su alto se descuenta del techo de la última hoja: si
        # no, cinco solicitudes en trámite volverían a empujar el cierre fuera.
        # Se mide fila por fila como las otras, más su rótulo, que ocupa una
        # escasa.
        closing = CLOSING_PX + sum(row_px(row) for row in awaiting)
        if awaiting:
            closing += ROW_BASE_PX
        permit_sheets = sheets_for(in_force, closing_px=closing)

        first_permit_page = 3
        for offset, sheet in enumerate(permit_sheets):
            sheet["page"] = first_permit_page + offset
            # `index`/`of` son de la **sección**, no del documento: el rótulo de
            # la tabla dice "hoja 2 de 3 de la sección" mientras el pie dice
            # "Página 4 de 6". Son dos cuentas distintas y confundirlas es cómo
            # alguien cree que le falta media sección.
            sheet["index"] = offset + 1
            sheet["of"] = len(permit_sheets)
            # El total de la sección, repetido en cada hoja: es lo que vuelve
            # detectable un recorte (ver la advertencia de `pagination.py`).
            sheet["total"] = len(in_force)
            # Las solicitudes en trámite van en la última hoja de la sección,
            # que es donde el documento emitido las tenía.
            sheet["awaiting"] = awaiting if sheet["last"] else []
        after = first_permit_page + len(permit_sheets)
        # LV-260: el plan compacto comparte hoja con la cobertura cuando los dos
        # bloques caben, medidos (`pagination.plan_fits_with_coverage`). Si no,
        # el plan va a su hoja — igual de compacto.
        from .pagination import plan_fits_with_coverage

        plan = payload.get("plan") or {}
        matrix_rows = len((plan.get("matrix") or {}).get("rows") or []) or 4
        plan_joins = plan_fits_with_coverage(
            len(payload.get("cost_centres") or []), matrix_rows
        )
        coverage_page = after
        plan_page = None if plan_joins else after + 1
        last_fixed = coverage_page if plan_joins else plan_page

        # LV-248: el anexo con la nómina, que la tabla de permisos dejó de listar.
        # Vigentes y en trámite, en el mismo orden que la sección 2, para que un
        # folio se encuentre en las dos hojas en la misma posición. Sin ningún
        # nombre cargado no se emite: una hoja anexa de puros guiones le diría al
        # lector que falta algo que nunca existió.
        from .pagination import ROSTER_FIRST_ROW_TOP_PX, roster_row_px

        roster = in_force + awaiting
        roster_sheets = []
        if any(row.get("operators") for row in roster):
            roster_sheets = sheets_for(
                roster,
                closing_px=0,
                estimate=roster_row_px,
                first_top=ROSTER_FIRST_ROW_TOP_PX,
            )
            for offset, sheet in enumerate(roster_sheets):
                sheet["page"] = last_fixed + 1 + offset
                sheet["index"] = offset + 1
                sheet["of"] = len(roster_sheets)
                sheet["total"] = len(roster)
        return {
            "permit_sheets": permit_sheets,
            "coverage_page": coverage_page,
            "plan_page": plan_page,
            "plan_joins_coverage": plan_joins,
            "coverage_section": "coverage_plan" if plan_joins else "coverage",
            "roster_sheets": roster_sheets,
            "total_pages": last_fixed + len(roster_sheets),
        }


class ExecutiveBriefView(MonthlyReportView):
    """LV-235: el **Dato Ejecutivo**, la hoja de una página, generada.

    Pedido del usuario con la plantilla en papel a la vista: *"el otro lo genero
    de forma automática de manera diferente, yo lo voy llenando"*.

    **Hereda de `MonthlyReportView` a propósito y no repite su contexto.** Es una
    segunda salida del **mismo payload**: dos recolecciones separadas es cómo la
    hoja de una página y el informe de cinco empiezan a decir cifras distintas
    del mismo mes, que es lo que `LV-188` costó y lo que `collect_kpis` ya evita
    contando sobre las filas recolectadas.

    Lo único que agrega son las dos vistas del mismo dato que esta hoja pide y el
    informe largo no: cuántas faenas están habilitadas (la plantilla lo pide como
    indicador propio) y las solicitudes en trámite como lista.
    """

    template_name = "reporting/executive_brief.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        payload = context["payload"]
        centres = payload.get("cost_centres") or []
        context["habilitados"] = sum(
            1 for row in centres if row.get("permits_in_force")
        )
        # Las solicitudes en trámite, desde las mismas filas de permisos que la
        # página 3 dibuja. `status` es el reconstruido **al corte** (`LV-233`),
        # así que un permiso aprobado en septiembre sigue apareciendo como
        # trámite en el informe de agosto, que es lo que ese mes decía.
        context["awaiting"] = [
            row
            for row in (payload.get("permits") or [])
            if row.get("status") == "requested"
        ]
        # Las acciones viven en el `ReportRun`, no en el payload: son narrativa,
        # como los hallazgos. Sin informe congelado no hay dónde escribirlas, y
        # la hoja lo dice en vez de dibujar una tabla vacía.
        context["actions"] = context["run"].actions if context["run"] else []
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
        return self._render(
            request, run, self._note(run), self._findings(run), self._actions(run)
        )

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
        actions = self._actions(run, request.POST)
        if not (note.is_valid() and findings.is_valid() and actions.is_valid()):
            return self._render(request, run, note, findings, actions)

        run = note.save(commit=False)
        run.findings = findings.entries
        run.actions = actions.entries
        # `full_clean` y no sólo `save`: la comprobación de forma vive en el
        # modelo justamente para que ningún camino la esquive, y la vista es un
        # camino más.
        run.full_clean()
        run.save(update_fields=["period_note", "findings", "actions", "updated_at"])
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
    def _actions(run, data=None):
        """LV-235: las acciones del Dato Ejecutivo, en la misma pantalla.

        Se escriben acá y no en una vista propia porque son **la misma
        naturaleza** que los hallazgos —narrativa del informe, escrita por quien
        firma— y separarlas habría dado dos formularios que guardan sobre la
        misma fila, con dos oportunidades de pisarse.
        """
        return ActionFormSet(data, initial=run.actions, prefix="actions")

    @staticmethod
    def _render(request, run, note, findings, actions):
        return render(
            request,
            "reporting/narrative_form.html",
            {
                "run": run,
                "note_form": note,
                "finding_formset": findings,
                "action_formset": actions,
            },
        )


class ReportCompareView(ModelViewPermissionRequiredMixin, TemplateView):
    """LV-251: qué cambió entre este informe y el anterior.

    El pedido del 2026-09-08 que quedó pendiente: *"lo que se modifica y los cambios
    más claro"*. Dos comparaciones, elegibles con `?against=`: la **revisión
    anterior** del mismo mes (qué corrigió esta revisión) y el **mes anterior** (cómo
    se movió la operación). Sin parámetro, la revisión si existe —es la pregunta que
    lleva a alguien a abrir una revisión 1— y si no, el mes.

    Permiso de **lectura**: comparar no escribe nada, y quien puede ver el informe
    puede ver en qué cambió.
    """

    model = ReportRun
    template_name = "reporting/compare.html"

    def get_context_data(self, **kwargs):
        from .compare import (
            baselines_for,
            compare_kpis,
            compare_narrative,
            compare_permits,
        )

        context = super().get_context_data(**kwargs)
        run = get_object_or_404(ReportRun, pk=self.kwargs["pk"])
        baselines = baselines_for(run)
        against = self.request.GET.get("against")
        if against not in baselines or baselines[against] is None:
            against = "revision" if baselines["revision"] else "month"
        baseline = baselines[against]
        context.update(
            run=run,
            baselines=baselines,
            against=against,
            baseline=baseline,
        )
        if baseline is not None:
            kpis = compare_kpis(baseline.payload, run.payload)
            context.update(
                kpis=kpis,
                changed_count=sum(1 for row in kpis if row["changed"]),
                permits=compare_permits(baseline.payload, run.payload),
                narrative=compare_narrative(baseline, run),
            )
        return context


class ReportTemplateUpdate(ModelPermissionRequiredMixin, View):
    """LV-249: los bloques editables del informe — portada, fases y matriz.

    Pedido del usuario: *"tomar otras plantillas más fáciles de modificar"*. Lo que
    se edita acá es lo que hasta ahora exigía tocar el código: la portada
    (`collect_meta`), las fases del plan (`PLAN_PHASES`) y la matriz de exigibilidad,
    que tenía SEP–DIC escrito a mano en la plantilla.

    Mismo permiso que la narrativa (`change_reportrun`): quien puede redactar el
    informe puede ajustar sus textos fijos. No se inventa un permiso nuevo para
    cuatro filas.

    ⚠️ **Editar acá no cambia ningún informe congelado**: los bloques se copian al
    payload al congelar, y un informe congelado se dibuja desde su payload. Cambia
    la vista previa y los que se congelen de aquí en adelante. La pantalla lo dice,
    porque es exactamente lo que alguien se preguntaría antes de guardar.
    """

    model = ReportRun
    permission_action = "change"

    def get(self, request):
        template = self._template()
        return self._render(request, *self._forms(template))

    def post(self, request):
        template = self._template()
        cover, phases, rows = self._forms(template, request.POST)
        if not (cover.is_valid() and phases.is_valid() and rows.is_valid()):
            return self._render(request, cover, phases, rows)

        from django.db import transaction

        with transaction.atomic():
            cover.save()
            self._save_archiving(phases)
            self._save_archiving(rows)
        set_audit_context(request, template, action="update")
        messages.success(
            request,
            _(
                "Saved. The preview and the reports frozen from now on use these "
                "texts; reports already frozen keep theirs."
            ),
        )
        return redirect("monthly-report-template")

    @staticmethod
    def _template():
        """El bloque vigente, creándolo con los textos de fábrica si la base no lo
        tiene sembrado — una pantalla de edición que no abre por falta de datos no
        sirve para cargarlos."""
        from .builder import FACTORY_COVER
        from .models import ReportTemplate

        template = ReportTemplate.current()
        if template is None:
            template = ReportTemplate.objects.create(**FACTORY_COVER, plan_lede="")
        return template

    @staticmethod
    def _forms(template, data=None):
        from .forms import ExigibilityRowFormSet, PlanPhaseFormSet, ReportTemplateForm

        # Las columnas de la matriz son las fases **ya guardadas**: una fase que se
        # agrega en este mismo envío suma su columna al guardar, no antes.
        saved_phases = list(template.active_phases())
        return (
            ReportTemplateForm(data, instance=template, prefix="cover"),
            PlanPhaseFormSet(
                data,
                instance=template,
                queryset=template.active_phases(),
                prefix="phases",
            ),
            ExigibilityRowFormSet(
                data,
                instance=template,
                queryset=template.active_matrix_rows(),
                prefix="rows",
                form_kwargs={"phases": saved_phases},
            ),
        )

    @staticmethod
    def _save_archiving(formset):
        """Guarda el formset **archivando** lo marcado para borrar.

        `AGENTS.md`: nunca se borran filas, se archivan. Y acá importa más que en
        otro lado: una fase borrada de la base haría que un informe **no congelado**
        de un mes pasado cambiara su plan al regenerarse, sin rastro de que existió.
        """
        instances = formset.save(commit=False)
        for obj in formset.deleted_objects:
            obj.is_active = False
            obj.save(update_fields=["is_active", "updated_at"])
        for obj in instances:
            obj.full_clean()
            obj.save()

    @staticmethod
    def _render(request, cover, phases, rows):
        return render(
            request,
            "reporting/template_form.html",
            {"cover_form": cover, "phase_formset": phases, "row_formset": rows},
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
