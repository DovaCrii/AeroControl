"""R0 del informe mensual RPA: el informe congelado como dato.

JEJ tiene que emitir cada mes un informe de reportabilidad RPA ante la DGAC
(estándar `JEJ-GRI-SS-INS-096`). Hasta ahora se armaba a mano; el de agosto de
2026 ya se envió y está en `OneDrive/DGAC/INFORMES/Agosto2026/`. La
especificación de la automatización y el mapeo campo→modelo real están en
`SPEC_REPORTE_MENSUAL_RPA.md` y en `apps/reporting/MAPPING.md`.

**Esta app sólo lee el dominio.** No define reglas de negocio ni toca permisos,
aeronaves ni operadores: recolecta lo que ya existe y lo congela.
"""

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _, pgettext_lazy

from apps.core.models import BaseModel


class ReportRun(BaseModel):
    """Un informe mensual, congelado como **dato** y no como PDF.

    Es la pieza que hace posible automatizar: el `payload` guarda el JSON del
    período, y el documento se re-renderiza desde ahí. Así un cambio de diseño no
    obliga a recalcular meses pasados, y comparar mes contra mes es una consulta
    sobre JSON en vez de un diff de documentos.

    **Por qué no se extendió `ComplianceSnapshot`**, que era la primera pregunta
    que `MAPPING.md` dejó planteada: ese modelo guarda seis contadores
    documentales en **columnas fijas** (`total`, `valid`, `expired`, `due_7/15/30`)
    por (fecha, faena), y existe para dar **tendencia diaria**. El informe es otra
    cosa: un payload heterogéneo —KPIs de flota, dotación, cobertura por faena,
    brechas, narrativa— emitido una vez al mes y sujeto a aprobación. Meterlo en
    ese modelo obligaría a un JSON colgando de una tabla de contadores, y
    convertiría un registro diario en uno mensual. Lo que sí hará `ReportRun` es
    **leer** snapshots cuando necesite la tendencia: son fuentes, no rivales.

    ⚠️ **El período no es único, y eso corrige una contradicción del SPEC.** Su
    §1.1 pide `unique_together = [("periodo",)]` y su §5.1 dice que `--force`
    *"crea una versión nueva, no sobrescribe"* — las dos cosas no pueden ser
    ciertas. Se resuelve con `(period, revision)`: el informe es un documento
    controlado (la portada del de agosto dice "Revisión 0"), así que las
    revisiones son parte de su naturaleza y no un accidente. Un informe aprobado
    queda inmutable y una corrección nace como revisión siguiente.
    """

    STATUS_DRAFT = "draft"
    STATUS_APPROVED = "approved"
    STATUS_SUPERSEDED = "superseded"
    STATUS_CHOICES = [
        (STATUS_DRAFT, _("Draft")),
        (STATUS_APPROVED, _("Approved")),
        # Una revisión posterior la reemplazó. No se borra: el informe emitido en
        # su momento es evidencia, y en un sistema de cumplimiento lo que se
        # envió tiene que seguir consultable.
        (STATUS_SUPERSEDED, _("Superseded")),
    ]
    # Los estados desde los que ya no se avanza, leído por el mismo criterio que
    # `LV-90` fijó en el resto del proyecto: la lista vive junto a las choices.
    TERMINAL_STATUSES = frozenset({STATUS_SUPERSEDED})

    # La severidad de un hallazgo, en el vocabulario del informe emitido: sus
    # cuatro llevan un cuadrado rojo o ámbar. No se reutilizan los tokens
    # `--sev-*` de la aplicación (`UX-01`) porque el informe tiene su propia
    # paleta de papel: sale firmado hacia la DGAC y no puede depender del tema
    # de quien lo abrió. Ver la cabecera de `report-a4.css`.
    FINDING_CRITICAL = "critical"
    FINDING_WARNING = "warning"
    FINDING_SEVERITIES = frozenset({FINDING_CRITICAL, FINDING_WARNING})
    FINDING_FIELDS = frozenset({"severity", "title", "text"})
    # LV-235: qué lleva una fila de "Acciones requeridas este mes". `due` puede
    # ir vacío —hay acciones sin fecha comprometida todavía— pero la llave tiene
    # que estar, para que una fila incompleta se distinga de una fila con otra
    # forma.
    ACTION_FIELDS = frozenset({"action", "owner", "due"})

    COMPLETENESS_OK = "ok"
    COMPLETENESS_PARTIAL = "partial"
    # ⚠️ **Con contexto, y no por prolijidad.** `_("Complete")` a secas comparte
    # msgid con el **botón** de completar una mantención y un permiso, así que el
    # catálogo lo traduce como *"Completar"* — un verbo. Acá es un **estado**, y
    # el comando imprimía "0 campos sin dato al corte (Completar)", que se lee
    # como una instrucción sobre un informe que ya está entero. Encontrado
    # corriendo el comando, no leyendo el código.
    COMPLETENESS_CHOICES = [
        (COMPLETENESS_OK, pgettext_lazy("report completeness", "Complete")),
        (COMPLETENESS_PARTIAL, pgettext_lazy("report completeness", "Partial")),
    ]

    # Primer día del mes reportado. `DateField` y no dos enteros: así el orden y
    # los rangos son los del motor de base de datos y no aritmética a mano.
    period = models.DateField(db_index=True, verbose_name=_("Period"))
    revision = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Revision"),
        help_text=_("0 is the first issue of the period; a correction raises it."),
    )
    generated_by = models.CharField(
        max_length=64,
        verbose_name=_("Generated by"),
        help_text=_('"cron" for the scheduled job, or the username.'),
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT
    )
    # El JSON del período. Inmutable por convención una vez aprobado: quien
    # corrige emite una revisión nueva.
    payload = models.JSONField(default=dict, blank=True)
    # **Las rutas del payload que quedaron sin dato, guardadas y no recalculadas.**
    # Es la misma lección que `LV-118` dejó en las alertas: el informe tiene que
    # seguir diciendo qué faltaba **cuando se emitió**, no qué falta hoy. Si se
    # recalculara, un informe de agosto mejoraría solo al cargarse los datos en
    # septiembre, y con él desaparecería la evidencia de la brecha que reportó.
    missing_fields = models.JSONField(default=list, blank=True)
    completeness = models.CharField(
        max_length=20, choices=COMPLETENESS_CHOICES, default=COMPLETENESS_PARTIAL
    )
    # **La narrativa: lo único del informe que no sale de la base y no podría.**
    #
    # `LV-227`. Un hallazgo es un **juicio sobre** las cifras —"la renovación
    # debía haber comenzado ya"—, no una consulta; el informe va firmado y quien
    # firma es quien lo escribe. Por eso se guarda y no se genera.
    #
    # Va en el `ReportRun` y no en una tabla aparte porque **es parte del
    # documento**: un informe aprobado tiene que seguir diciendo lo que decía,
    # narrativa incluida, y con la redacción colgando de otro lado se editaría
    # por detrás de un documento ya emitido.
    findings = models.JSONField(default=list, blank=True)
    # La observación del período (página 3 del informe emitido). Un párrafo, no
    # una lista: en el informe de agosto es uno solo, sobre la vigencia otorgada.
    period_note = models.TextField(blank=True, default="")
    # LV-235: **"Acciones requeridas este mes"**, del Dato Ejecutivo — la única
    # sección de ese documento que no se puede calcular.
    #
    # Todo el resto de esa hoja sale del payload: los seis indicadores, la tabla
    # por faena, los vencimientos a 60 días, las solicitudes en trámite y hasta
    # el detalle de los incidentes, que `NonConformity` ya guarda con su reporte
    # a la DGAC. Lo que ninguna consulta puede producir es **qué se decide hacer
    # este mes, quién lo hace y para cuándo**: eso es una asignación, y la toma
    # quien firma.
    #
    # Cada fila es `{"action", "owner", "due"}`. Lista y no tres campos sueltos
    # porque la plantilla pide tres y podrían ser dos o cuatro; y JSON y no tabla
    # aparte por lo mismo que `findings`: **es parte del documento**, y colgando
    # de otro lado se editaría por detrás de un informe ya aprobado.
    actions = models.JSONField(default=list, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        verbose_name = _("report run")
        verbose_name_plural = _("report runs")
        ordering = ["-period", "-revision"]
        constraints = [
            models.UniqueConstraint(
                fields=["period", "revision"],
                name="reporting_run_period_revision_uniq",
            ),
        ]
        indexes = [
            # La consulta habitual es "el último informe de este período".
            models.Index(fields=["period", "-revision"], name="reporting_run_last_idx"),
        ]

    def __str__(self):
        return f"{self.code} rev. {self.revision}"

    @property
    def code(self):
        """El código del documento, tal como lo lleva el informe emitido.

        El de agosto dice `JEJ-GTE-CT-INF-RPA-2026-08`. Se compone y no se guarda:
        es una función del período, y una columna con lo mismo sería una columna
        que puede discrepar de su propia fecha.
        """
        return f"JEJ-GTE-CT-INF-RPA-{self.period:%Y-%m}"

    @classmethod
    def freeze(cls, period, generated_by, *, force=False):
        """Congela el informe del período. Devuelve `(run, creado)`.

        **Es idempotente a propósito, y de eso depende que pueda correr desde un
        trabajo programado.** Sin `force`, un período que ya tiene informe
        devuelve el que hay y no escribe nada: el timer mensual corre el último
        día del mes, y un reintento —o dos timers solapados— no puede convertir
        un informe en dos.

        **`force` emite la revisión siguiente; nunca sobrescribe.** Es la
        contradicción del SPEC ya resuelta: su §1.1 pedía que el período fuera
        único y su §5.1 que `--force` creara una versión nueva. Un informe es un
        documento controlado, así que la corrección **nace como revisión** y las
        anteriores quedan `superseded` — no se borran, porque lo que se envió en
        su momento es evidencia y tiene que seguir consultable. `approved_at` y
        `approved_by` sobreviven al reemplazo: quién aprobó la revisión 0 sigue
        siendo un hecho después de que exista la 1.

        ⚠️ **La narrativa viaja a la revisión nueva.** Es una decisión, no un
        descuido: si las cifras se corrigen, los hallazgos escritos pueden
        quedar desactualizados — pero borrarlos es peor, porque obliga a
        reescribir de cero y ahí nadie nota que un hallazgo dejó de ser cierto.
        Copiados, quedan a la vista para corregirlos.

        Vive en el modelo y no en la vista ni en el comando porque **los dos lo
        llaman**: el botón de la pantalla y el trabajo programado. Dos copias de
        esta lógica es cómo el informe que genera el timer y el que genera una
        persona empiezan a diferir.
        """
        from apps.reporting.builder import build, month_bounds

        # ⚠️ **LV-233: un mes que no terminó no se congela.** Hasta acá nada lo
        # impedía, así que un `ReportRun` de septiembre con datos de tres días
        # podía nacer, aprobarse y firmarse — y un `ReportRun` aprobado es el
        # documento controlado que se emite a la DGAC. La vista previa en vivo
        # sigue disponible para mirar el mes en curso; lo que no se puede es
        # convertirla en documento.
        #
        # **Estrictamente futuro**, y ese borde importa: el mes termina el mismo
        # día que es su último día, así que el 31 de agosto agosto **sí** se
        # congela. Con `>=` el trabajo programado —que corre el último día del
        # mes— habría quedado bloqueado justo el día que tiene que correr.
        _start, end = month_bounds(period)
        if end > timezone.localdate():
            raise ValidationError(
                _(
                    "The period %(period)s has not finished yet: a monthly report "
                    "cannot be frozen before its month closes."
                )
                % {"period": f"{period:%Y-%m}"}
            )

        latest = cls.objects.filter(period=period).order_by("-revision").first()
        if latest and not force:
            return latest, False

        payload, missing = build(period)
        run = cls.objects.create(
            period=period,
            revision=(latest.revision + 1) if latest else 0,
            generated_by=generated_by,
            payload=payload,
            missing_fields=missing,
            completeness=(cls.COMPLETENESS_PARTIAL if missing else cls.COMPLETENESS_OK),
            findings=latest.findings if latest else [],
            period_note=latest.period_note if latest else "",
            # LV-247: **las acciones también viajan**, y no viajaban. El docstring
            # de arriba lo afirmaba para "la narrativa" entera, y la narrativa son
            # tres bloques: se copiaban dos. `actions` llegó después (`LV-235`, las
            # acciones del Dato Ejecutivo) y esta línea no se enteró, así que
            # emitir una revisión para corregir una cifra **borraba en silencio**
            # las acciones escritas — justo cuando alguien está corrigiendo el
            # documento y menos lo va a notar.
            actions=latest.actions if latest else [],
        )
        if latest:
            cls.objects.filter(period=period).exclude(pk=run.pk).update(
                status=cls.STATUS_SUPERSEDED
            )
        return run, True

    def approve(self, approved_by):
        """Marca el informe como el documento emitido.

        Aprobar es lo que lo vuelve inmutable, así que **no se re-aprueba**: un
        segundo intento movería `approved_at` y `approved_by` de un documento
        que ya se envió, y con ellos la evidencia de quién y cuándo lo firmó.
        """
        from django.utils import timezone

        if self.status != self.STATUS_DRAFT:
            raise ValidationError(
                _("Only a draft can be approved; issue a new revision instead.")
            )
        self.status = self.STATUS_APPROVED
        self.approved_at = timezone.now()
        self.approved_by = approved_by
        self.save(update_fields=["status", "approved_at", "approved_by", "updated_at"])

    def clean(self):
        """`findings` tiene forma, y se comprueba también acá.

        El formulario no es el único camino a esta columna: el admin, un
        `loaddata` y una corrida de datos escriben igual, y un `JSONField` acepta
        cualquier cosa. Una lista mal formada no revienta al guardar — revienta
        al **renderizar el informe**, que es el peor momento posible. Es la regla
        de `AGENTS.md`: validar en el formulario *y* en el modelo.
        """
        super().clean()
        if not isinstance(self.findings, list):
            raise ValidationError({"findings": _("Findings must be a list.")})
        for entry in self.findings:
            if not isinstance(entry, dict) or set(entry) != self.FINDING_FIELDS:
                raise ValidationError(
                    {"findings": _("Each finding needs a severity, title and text.")}
                )
            if entry["severity"] not in self.FINDING_SEVERITIES:
                raise ValidationError({"findings": _("Unknown finding severity.")})

        # LV-235: `actions` con la misma vara, y por la misma razón. Una fila mal
        # formada no revienta al guardar sino **al dibujar el Dato Ejecutivo**,
        # que es la hoja que se lleva a la reunión.
        if not isinstance(self.actions, list):
            raise ValidationError({"actions": _("Actions must be a list.")})
        for entry in self.actions:
            if not isinstance(entry, dict) or set(entry) != self.ACTION_FIELDS:
                raise ValidationError(
                    {
                        "actions": _(
                            "Each action needs a description, an owner and a date."
                        )
                    }
                )
            # Una acción sin responsable es una acción que nadie hace, y sin
            # plazo es una que se hace algún día. El texto solo no alcanza: es
            # exactamente lo que la plantilla en papel dejaba pasar.
            if not str(entry["action"]).strip() or not str(entry["owner"]).strip():
                raise ValidationError(
                    {"actions": _("An action needs both a description and an owner.")}
                )

    @property
    def is_editable(self):
        """Un informe aprobado no se toca: se emite una revisión.

        La aprobación es lo que lo convierte en el documento que se envió, y
        reescribirlo dejaría a la DGAC con una copia que ya no existe de este
        lado.
        """
        return self.status == self.STATUS_DRAFT


class ReportTemplate(BaseModel):
    """LV-249: los bloques del informe que se editan desde la aplicación.

    Pedido del usuario: *"tomar otras plantillas más fáciles de modificar"*. Hasta
    acá la portada vivía en `builder.collect_meta`, las fases del plan en la
    constante `PLAN_PHASES` —con los meses de 2026 escritos— y la matriz de
    exigibilidad en la plantilla, con **SEP–DIC a mano**: en enero iba a imprimirse
    un plan vencido como vigente, y cambiar una coma exigía un despliegue.

    ⚠️ **Esto revierte a propósito una decisión escrita en `builder.py`**: *"una
    tabla de configuración para cuatro filas que nadie edita es una tabla que nadie
    mantiene"*. Era cierto mientras nadie las editaba; el usuario pidió
    explícitamente poder hacerlo, y eligió esta forma —bloques editables en la app—
    por sobre exportar a Word.

    **No es un editor de plantillas**, y esa es la otra mitad de la decisión: el
    diseño y las cifras siguen en el repositorio y en la base. `LV-227` descartó
    editar plantillas desde la web porque una plantilla es código con acceso al
    contexto; acá se editan **textos**, que el informe dibuja como textos.

    ⚠️ **Regla que no se negocia: se lee al congelar.** `build()` copia estos bloques
    al payload, y un informe congelado se dibuja desde su payload. Editar la
    portada hoy cambia la vista previa y los informes que se congelen desde ahora;
    un informe ya emitido sigue diciendo lo que dijo — que es la razón de existir de
    `ReportRun`.

    Hay **uno** activo (`current`); una migración lo siembra con los textos que el
    código tenía, así que el primer informe después del cambio sale idéntico.
    """

    issued_by = models.CharField(_("Issued by"), max_length=200)
    jointly_with = models.CharField(_("Jointly with"), max_length=200)
    standard = models.CharField(_("Standard"), max_length=120)
    addressed_to = models.CharField(_("Addressed to"), max_length=300)
    scope = models.CharField(_("Scope"), max_length=200)
    sources = models.CharField(_("Sources"), max_length=200)
    plan_lede = models.TextField(_("Plan introduction"))

    class Meta:
        verbose_name = _("report template")
        verbose_name_plural = _("report templates")

    def __str__(self):
        return self.standard

    @classmethod
    def current(cls):
        """El bloque vigente, o `None` en una base sin sembrar.

        `None` y no un error: `build()` cae a los textos de siempre, y un informe
        que no se puede generar por falta de configuración es peor que uno que sale
        con la portada de fábrica.
        """
        return cls.objects.filter(is_active=True).order_by("created_at").first()

    def active_phases(self):
        return self.phases.filter(is_active=True).order_by("month")

    def active_matrix_rows(self):
        return self.matrix_rows.filter(is_active=True).order_by("order", "created_at")


class PlanPhase(BaseModel):
    """LV-249: una fase del plan de normalización, con su mes.

    Reemplaza a `builder.PLAN_PHASES`. El **estado** de cada fase —cumplida, en
    curso, por venir— se sigue calculando contra el período del informe
    (`collect_plan`), así que editar una fase no la marca como vigente: lo decide el
    calendario.
    """

    template = models.ForeignKey(
        ReportTemplate, on_delete=models.PROTECT, related_name="phases"
    )
    month = models.DateField(
        _("month"),
        help_text=_("The phase is the whole month; the day is ignored."),
    )
    title = models.CharField(_("Title"), max_length=200)
    text = models.TextField(_("Description"))
    close = models.CharField(_("Closing criterion"), max_length=300)

    class Meta:
        ordering = ["month"]
        verbose_name = _("plan phase")
        verbose_name_plural = _("plan phases")

    def __str__(self):
        return f"{self.month:%Y-%m} · {self.title}"

    def save(self, *args, **kwargs):
        # Una fase es un mes entero: se guarda el día 1 para que dos fases del
        # mismo mes se reconozcan como tales y la clave de la matriz sea estable.
        if self.month:
            self.month = self.month.replace(day=1)
        super().save(*args, **kwargs)

    @property
    def key(self):
        """La clave con que la matriz de exigibilidad se refiere a este mes."""
        return f"{self.month:%Y-%m}"


class ExigibilityRow(BaseModel):
    """LV-249: una fila de la matriz de exigibilidad progresiva.

    **Las columnas no se guardan: son las fases.** La matriz de la plantilla tenía
    SEP–DIC escrito a mano, y en enero habría seguido diciéndolo. Acá cada fila
    guarda un nivel **por mes de fase** (`levels`, `{"2026-09": "due", …}`), y las
    columnas del informe salen de las fases vigentes: agregar una fase agrega una
    columna, y un mes sin nivel se dibuja como «No aplica».
    """

    LEVEL_DUE = "due"
    LEVEL_INFO = "info"
    LEVEL_NA = "na"
    LEVEL_CHOICES = [
        # Con contexto: "Required" ya está en el catálogo como «Requerido» —lo usan
        # los formularios—, y en el informe este nivel se llama «Exigible».
        (LEVEL_DUE, pgettext_lazy("requirement level", "Required")),
        (LEVEL_INFO, _("Informative")),
        (LEVEL_NA, _("Not applicable")),
    ]

    template = models.ForeignKey(
        ReportTemplate, on_delete=models.PROTECT, related_name="matrix_rows"
    )
    order = models.PositiveSmallIntegerField(_("Order"), default=0)
    label = models.CharField(_("What is reported"), max_length=200)
    emphasis = models.BooleanField(_("Emphasised"), default=False)
    levels = models.JSONField(_("Levels"), default=dict, blank=True)

    class Meta:
        ordering = ["order", "created_at"]
        verbose_name = _("requirement row")
        verbose_name_plural = _("requirement rows")

    def __str__(self):
        return self.label

    def clean(self):
        """Los niveles son uno de tres. En el modelo y no sólo en el formulario,
        porque el admin y una migración de datos también escriben acá, y un nivel
        mal escrito no falla al guardar: se dibuja como una celda sin color."""
        super().clean()
        valid = {code for code, _label in self.LEVEL_CHOICES}
        if not isinstance(self.levels, dict) or any(
            value not in valid for value in self.levels.values()
        ):
            raise ValidationError(
                {
                    "levels": _(
                        "Each level must be required, informative or not applicable."
                    )
                }
            )

    def level_for(self, phase_key):
        return self.levels.get(phase_key, self.LEVEL_NA)
