"""LV-251: qué cambió entre dos informes.

Pedido del usuario el 2026-09-08, junto con la forma de editar el informe: *"una
mejor forma de editar y revisar el informe completo, lo que se modifica y los
cambios más claro"*. La edición se entregó entonces (`LV-227`, la narrativa) y
**"ver los cambios" quedó pendiente** — la vista del informe prometía "comparar" y
no había ninguna. Se retomó en el plan de mejora del 2026-09-23.

**Compara payloads congelados, nunca recalcula.** Un informe es su payload: lo que
dijo cuando se emitió. Recalcular cualquiera de los dos para compararlos mediría la
base de hoy contra la de hoy, y "qué cambió" pasaría a ser siempre "nada". Es la
misma razón por la que `ReportRun` existe.

Dos preguntas distintas, y la vista ofrece las dos:

* **La revisión contra la anterior del mismo mes**: qué corrigió la revisión. Es lo
  que hay que poder mostrar cuando alguien pregunta por qué el informe de agosto
  tiene una revisión 1.
* **El mes contra el mes anterior**: cómo se movió la operación. Es lo que se lee en
  una reunión de gestión.
"""

from datetime import timedelta

from django.utils.translation import gettext_lazy as _

#: Los indicadores del payload, en el orden en que el informe los presenta.
#:
#: ⚠️ **Declarados, no descubiertos del payload.** Recorrer `payload["kpis"]` daría
#: las claves en un orden arbitrario y con su nombre técnico; y un indicador nuevo
#: que entre al builder sin su rótulo acá aparecería como `permits_expiring_45d` en
#: una pantalla en español. `test_every_kpi_has_a_label` cruza las dos listas.
KPI_LABELS = [
    ("cost_centres_with_operation", _("Sites with operation")),
    ("cost_centres_without_permit", _("Sites without a permit in force")),
    ("permits_in_force", _("Permits in force")),
    ("permits_awaiting", _("Permits awaiting the DGAC")),
    ("permits_lapsed", _("Permits lapsed and not closed")),
    ("permits_expiring_30d", _("Permits expiring within 30 days")),
    ("permits_expiring_60d", _("Permits expiring within 60 days")),
    ("incidents", _("Incidents in the period")),
    ("incidents_open", _("Incidents still open")),
    ("fleet_total", _("Aircraft on the register")),
    ("fleet_flyable", _("Aircraft available")),
    ("insurance_up_to_date", _("JAC insurance up to date")),
    ("insurance_missing", _("JAC insurance with no date on file")),
    ("insurance_lapsed", _("JAC insurance lapsed")),
    ("operators_total", _("Operators on the register")),
    ("operators_credentialed", _("DGAC credential in force")),
    ("credentials_missing", _("DGAC credential with no date on file")),
    ("credentials_lapsed", _("DGAC credential lapsed")),
]


def _value(payload, key):
    """El valor de un indicador, o `None` si ese payload no lo trae.

    `None` y no cero: un informe congelado antes de que un indicador existiera **no
    dice** que valía cero, no dice nada. Mostrar un cero ahí inventaría un dato en
    una comparación que va a leer quien firma.
    """
    leaf = (payload or {}).get("kpis", {}).get(key)
    if isinstance(leaf, dict):
        return leaf.get("value")
    return leaf


def compare_kpis(before, after):
    """Una fila por indicador: antes, después, diferencia y si cambió."""
    rows = []
    for key, label in KPI_LABELS:
        old, new = _value(before, key), _value(after, key)
        numeric = isinstance(old, (int, float)) and isinstance(new, (int, float))
        rows.append(
            {
                "key": key,
                "label": label,
                "before": old,
                "after": new,
                "delta": (new - old) if numeric else None,
                "changed": old != new,
            }
        )
    return rows


def _folios(payload, *, in_force):
    return {
        row.get("folio")
        for row in (payload or {}).get("permits") or []
        if bool(row.get("in_force")) is in_force and row.get("folio")
    }


def compare_permits(before, after):
    """Qué permisos entraron y salieron de cada bloque, por folio.

    Por folio y no por posición: la tabla se ordena por vencimiento, así que un
    permiso que sólo cambió de fecha se movería de fila sin haber entrado ni salido.
    """
    result = {}
    for block, in_force in (("in_force", True), ("awaiting", False)):
        old, new = _folios(before, in_force=in_force), _folios(after, in_force=in_force)
        result[block] = {
            "added": sorted(new - old),
            "removed": sorted(old - new),
        }
    return result


def compare_narrative(before_run, after_run):
    """Los bloques escritos a mano que cambiaron: hallazgos, observación, acciones.

    Se comparan **enteros** y se muestran lado a lado, en vez de un diff palabra por
    palabra: son textos cortos que se leen completos, y un diff de caracteres sobre
    un párrafo en español es más difícil de leer que los dos párrafos.
    """

    def findings(run):
        return [
            f"{item.get('title', '')} — {item.get('text', '')}".strip(" —")
            for item in (run.findings or [])
        ]

    def actions(run):
        return [
            " · ".join(
                part
                for part in (item.get("action"), item.get("owner"), item.get("due"))
                if part
            )
            for item in (run.actions or [])
        ]

    blocks = [
        ("findings", _("Findings"), findings(before_run), findings(after_run)),
        (
            "period_note",
            _("Note for the period"),
            [before_run.period_note] if before_run.period_note else [],
            [after_run.period_note] if after_run.period_note else [],
        ),
        (
            "actions",
            _("Actions required this month"),
            actions(before_run),
            actions(after_run),
        ),
    ]
    return [
        {"key": key, "label": label, "before": old, "after": new}
        for key, label, old, new in blocks
        if old != new
    ]


def baselines_for(run):
    """Los dos puntos de comparación posibles para `run`, o `None` si no existen.

    La revisión anterior es la **inmediatamente** anterior, no la cero: es la que
    esta revisión corrigió. El mes anterior es su revisión **más alta**, que es la
    que quedó vigente — comparar contra una reemplazada mediría contra un documento
    que ya no vale.
    """
    from apps.reporting.models import ReportRun

    previous_revision = (
        ReportRun.objects.filter(period=run.period, revision__lt=run.revision)
        .order_by("-revision")
        .first()
    )
    # `period` es siempre el día 1 del mes: el día anterior cae en el mes previo.
    previous_period = (run.period - timedelta(days=1)).replace(day=1)
    previous_month = (
        ReportRun.objects.filter(period=previous_period).order_by("-revision").first()
    )
    return {"revision": previous_revision, "month": previous_month}
