"""LV-431: relleno de `cost_center` y `aircraft` en los análisis anteriores a la sección propia."""

from __future__ import annotations

from django.db.models import Q


def backfill(apps) -> int:
    """`cost_center` = el del permiso; `aircraft` sólo si el vuelo enlazado la da y es de ese centro.

    Recibe el registro de apps (el histórico de la migración o el real) para poder probarse.
    Devuelve cuántas filas cambió. Es idempotente: sólo toca lo que está vacío. Una aeronave
    que no es del centro del permiso queda nula: es ambigua y no se supone nada.
    """
    Analysis = apps.get_model("operations", "FlightLogAnalysis")
    rows = Analysis.objects.filter(
        Q(cost_center__isnull=True)
        | Q(aircraft__isnull=True, flight_record__isnull=False)
    ).select_related("permission", "flight_record__aircraft")
    changed = 0
    for analysis in rows:
        update = []
        if analysis.cost_center_id is None and analysis.permission_id:
            analysis.cost_center_id = analysis.permission.cost_center_id
            update.append("cost_center")
        record = analysis.flight_record
        aircraft = record.aircraft if record is not None else None
        if (
            analysis.aircraft_id is None
            and aircraft is not None
            and analysis.cost_center_id is not None
            and aircraft.cost_center_id == analysis.cost_center_id
        ):
            analysis.aircraft_id = aircraft.pk
            update.append("aircraft")
        if update:
            analysis.save(update_fields=update)
            changed += 1
    return changed
