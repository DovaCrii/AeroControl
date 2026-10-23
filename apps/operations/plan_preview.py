"""LV-368 (fase 4): «lo que trae el plan», la lectura que comparten el formulario y la ficha.

El formulario del permiso (vista previa al elegir un plan) y la ficha (sección
«Ubicación y área») muestran **la misma lectura**: la tabla de lo que el KMZ trae,
la modalidad, el aeródromo más cercano, la comuna y la región, y el mini-mapa. Se
arma acá, una sola vez, a partir de `plan_sections` (lectura pura, no toca la
base): una segunda derivación del centro o del AMC es cómo la ficha y el
formulario acaban diciendo cosas distintas (`LV-132`).

El plan es dueño de la **geometría**; el permiso guarda sólo lo declarado. Por eso
esta lectura nunca copia nada al permiso: rellenar es otro acto, y ocurre al
guardar (`fill_location_gaps`, que sólo llena huecos).
"""

from apps.geo.mini_map import mini_map_payload

from .flight_requests import kmz_contents, plan_sections


def plan_reading(plan):
    """El contexto de `operations/_plan_reading.html` para un plan.

    `area_count` dice cuántas áreas trae el archivo: con más de una no hay un
    centro que declarar (elegir uno sería inventar cuál manda), y la pantalla
    manda a separarlas en solicitudes en vez de elegir por la persona.
    """
    rows = plan_sections(plan)
    areas = []
    for row in rows:
        brings, missing = kmz_contents(row)
        areas.append(
            {
                "name": row["name"],
                "modality_label": row["modality_label"],
                "lat": row["lat_readable"],
                "lon": row["lon_readable"],
                "radius_m": row["radius_m"],
                "amc": row["amc"],
                "amc_distance_km": row["amc_distance_km"],
                "comuna": row["comuna"],
                "region": row["region"],
                "brings": brings,
                "missing": missing,
            }
        )
    return {
        "plan": plan,
        "areas": areas,
        "area_count": len(areas),
        "single": areas[0] if len(areas) == 1 else None,
        "mini_map": mini_map_payload(rows) if rows else None,
        "map_id": f"mini-map-{plan.pk}",
    }
