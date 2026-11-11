"""Cortes de urgencia de un vencimiento: la unica definicion (LV-428).

Modulo hoja, sin imports de la app, para que `workboard`, `compliance.models`,
`digest` y `reports` lo usen sin ciclos. Mover un corte es cambiar esta tupla.

⚠️ No confundir con el semaforo de vencimientos de `registry.selectors`
(`expiry_band`, cortes 30/60 de `kpis.permit_band`): es otra escala, con otro
proposito, y no se mezcla con esta.

Los bordes son inclusivos: con `days_left == 7` todavia es `due_7`. Vencido es
estrictamente antes de hoy (`days_left < 0`).
"""

# Del tramo mas urgente al menos urgente: (clave del tramo, dias de corte).
URGENCY_BUCKETS = (
    ("due_7", 7),
    ("due_15", 15),
    ("due_30", 30),
)
URGENCY_CUTOFFS_DAYS = tuple(days for _key, days in URGENCY_BUCKETS)

# Lo que se mira hacia adelante: el ultimo corte.
HORIZON_DAYS = URGENCY_CUTOFFS_DAYS[-1]


def urgency_bucket(days_left):
    """Return the bucket key for `days_left` days to an expiry.

    `"overdue"` when negative, `None` beyond the horizon.
    """
    if days_left < 0:
        return "overdue"
    for key, cutoff in URGENCY_BUCKETS:
        if days_left <= cutoff:
            return key
    return None
