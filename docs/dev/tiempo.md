# Tarjeta del tiempo (LV-342, LV-343, LV-347, LV-353)

Nota interna, no autoritativa. Tarjeta SOLO informativa del panel: tiempo y eventos previstos en la
ciudad de la persona. No se cruza con permisos de vuelo, faenas ni aeronaves.

## Estado

Encendida por omisión desde LV-353 (decisión de la persona, 2026-10-20). Ciudad por omisión para
quien no eligió una: Santiago (`WEATHER_DEFAULT_*`). Cada persona puede elegir la suya en
`/weather/location/`.

## Cómo apagarla

`WEATHER_ENABLED=False` en el entorno (`.env` de la VM) y reiniciar. Apagada: no hay hueco en el
panel, ni script, ni petición; `/weather/panel/`, `/weather/location/` y `/weather/search/`
responden 404; el cliente no hace ninguna llamada saliente. Sin tocar código.

## RIESGO ACEPTADO: licencia de Open-Meteo

La API gratuita de Open-Meteo es de **uso no comercial**. La persona aceptó usarla «de momento»
desde el servidor de la empresa. Para cumplir la licencia comercial, cualquiera de estas salidas:

- plan de pago: `WEATHER_API_KEY` (sólo por entorno, nunca en el repo);
- servidor propio de Open-Meteo: `WEATHER_API_URL` (y `WEATHER_GEOCODING_URL`);
- o apagarla (`WEATHER_ENABLED=False`).

## Sin Internet en el servidor

El panel no se rompe ni bloquea el render: espera como máximo `WEATHER_TIMEOUT_SECONDS` (4 s),
muestra el estado de error con «Reintentar», cachea el fallo `WEATHER_PANEL_CACHE_SECONDS` y deja
UNA advertencia de log por ventana (`weather_unreachable`, sin URL ni datos). Si la petición htmx
misma falla, `static/js/weather-card.js` reemplaza el esqueleto por ese mismo estado.

## Por verificar en vivo (no lo cubren las pruebas, que no salen a la red)

- Respuesta real de Open-Meteo para Santiago (forma del JSON, unidades, `fetched_at`).
- Salida a Internet desde `p340` (DNS y HTTPS a `api.open-meteo.com` y `geocoding-api.open-meteo.com`).
- Tras desplegar: `collectstatic` (lleva JS nuevo) y comprobar que el panel dibuja la tarjeta.
