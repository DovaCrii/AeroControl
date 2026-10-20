"""Datos de dibujo de la escena del cielo (LV-356): geometría fija, sin red ni plantilla.

`apps/weather/sky.py` dice QUÉ hay en el cielo (fase, posición del sol y la luna, nubes,
precipitación). Acá se convierte en lo que el SVG necesita: el trazo de la fase lunar, las estrellas,
las gotas o los copos como una sola trayectoria, y las horas de amanecer y puesta que usa la vista
previa de 24 h. Todo es determinista (sin azar): la misma entrada dibuja siempre lo mismo.
"""

MOON_R = 9
# (x, y, escala) de las nubes, en el orden en que aparecen según el nivel 0..3.
CLOUD_SLOTS = ((70, 30, 1.0), (300, 46, 0.8), (480, 22, 1.25))
# Gotas y copos van en filas cada 24 px; el patrón se repite cada dos filas (48 px) y por eso el
# movimiento desplaza 48 px: vuelve a dibujar lo mismo y el salto no se ve.
# Estrellas fijas (poca cantidad, siempre la misma): puntos chicos y grandes, y 4 que titilan.
STARS_SMALL = (
    (24, 18),
    (66, 52),
    (118, 26),
    (176, 60),
    (232, 16),
    (290, 44),
    (352, 22),
    (404, 58),
    (468, 14),
    (520, 40),
    (572, 20),
    (616, 54),
)
STARS_BIG = ((92, 38), (210, 34), (330, 12), (446, 36), (548, 62), (600, 12))
STARS_TWINKLE = ((150, 20), (262, 62), (388, 30), (500, 24))
RAIN_ROW_GAP = 24
# Ciudad abajo: (ancho, alto) de cada edificio, de izquierda a derecha, repartidos en los 640 px.
CITY = (
    (16, 10),
    (12, 18),
    (18, 12),
    (10, 24),
    (16, 14),
    (14, 9),
    (20, 20),
    (12, 12),
    (16, 26),
    (12, 15),
    (18, 10),
    (14, 22),
    (10, 12),
    (20, 16),
    (12, 24),
    (16, 11),
    (14, 18),
    (18, 13),
    (10, 20),
    (16, 9),
    (12, 17),
    (20, 23),
    (14, 12),
    (16, 15),
    (12, 21),
    (18, 10),
    (10, 14),
    (14, 19),
    (20, 12),
    (12, 25),
    (16, 13),
    (14, 10),
    (18, 17),
    (12, 22),
    (16, 11),
    (10, 15),
    (20, 18),
    (14, 9),
    (12, 20),
    (16, 14),
    (16, 12),
    (18, 16),
    (16, 10),
)


def moon_path(illumination, waxing, radius=MOON_R):
    """Trazo de la parte iluminada de la luna, centrado en (0, 0), sin `defs` ni máscaras.

    En el hemisferio sur la luna creciente se ilumina por la izquierda (y la menguante por la
    derecha), al revés que en el norte: así se ve la de Chile. Devuelve `""` si no hay nada que
    dibujar (luna nueva).
    """
    k = min(1.0, max(0.0, illumination))
    if k < 0.02:
        return ""
    r = radius
    if k > 0.98:
        return f"M0 {-r}A{r} {r} 0 1 0 0 {r}A{r} {r} 0 1 0 0 {-r}Z"
    rx = round(r * abs(1 - 2 * k), 2)
    sweep = 1 if k < 0.5 else 0
    return f"M0 {-r}A{r} {r} 0 0 0 0 {r}A{rx} {r} 0 0 {sweep} 0 {-r}Z"


def _dots(points):
    """Una sola trayectoria de puntos (segmentos de largo cero con terminación redonda)."""
    return "".join(f"M{x} {y}h0" for x, y in points)


def _rain_path():
    """Gotas inclinadas en filas; un desplazamiento de una fila vuelve a dibujar lo mismo."""
    parts = []
    for row, y in enumerate(range(-72, 160 + RAIN_ROW_GAP, RAIN_ROW_GAP)):
        shift = 20 if row % 2 else 0
        for x in range(shift, 660, 40):
            parts.append(f"M{x} {y}l-3 8")
    return "".join(parts)


def _snow_points():
    points = []
    for row, y in enumerate(range(-72, 160 + RAIN_ROW_GAP, RAIN_ROW_GAP)):
        shift = 22 if row % 2 else 0
        for x in range(shift, 660, 44):
            points.append((x + (row * 7) % 14, y))
    return points


def _city():
    """Siluetas de edificios (un solo trazo) y sus ventanas encendidas (puntos)."""
    body, windows, x = [], [], 0
    for index, (width, height) in enumerate(CITY):
        top = 160 - height
        body.append(f"M{x} 160V{top}h{width}V160Z")
        if index % 3 == 0 and height >= 14:
            windows.append((x + width // 2, top + 5))
        if index % 4 == 1 and height >= 18:
            windows.append((x + width // 2, top + 11))
        x += width
    return "".join(body), _dots(windows)


def scene_context(sky, local_now, scintillation=False):
    """Todo lo que `weather/_sky.html` dibuja además de lo que ya trae `sky`."""
    moon = sky["moon"]
    clouds = [
        {"x": x, "y": y, "scale": scale, "n": index + 1}
        for index, (x, y, scale) in enumerate(CLOUD_SLOTS[: sky["clouds"]])
    ]
    precip = sky["precip"]
    city, windows = _city()
    return {
        "city": city,
        "windows": windows,
        "moon_path": moon_path(moon["illumination"], moon["fraction"] < 0.5),
        "moon_flip": moon["fraction"] >= 0.5,
        "stars_small": _dots(STARS_SMALL),
        "stars_big": _dots(STARS_BIG),
        "stars_twinkle": STARS_TWINKLE if scintillation else (),
        "clouds": clouds,
        "heavy": precip == "rain",
        "rain": _rain_path() if precip == "rain" else "",
        "snow": _dots(_snow_points()) if precip == "snow" else "",
        "scintillation": bool(scintillation),
        # Horas locales decimales para la vista previa de 24 h (`static/js/sky-preview.js`).
        "sunrise_h": round(_decimal_hour(sky["sunrise"]), 2),
        "sunset_h": round(_decimal_hour(sky["sunset"]), 2),
        "hour_now": round(local_now.hour + local_now.minute / 60, 2),
    }


def _decimal_hour(moment):
    return moment.hour + moment.minute / 60
