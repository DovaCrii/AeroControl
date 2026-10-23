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

## Proveedor (LV-365, decisión de la persona del 2026-10-21)

Se dejó Open-Meteo: su API gratuita es de **uso no comercial**. El proveedor por omisión es **MET
Norway** (`locationforecast/2.0/complete`): licencias NLOD 2.0 y CC BY 4.0, uso comercial permitido,
sin llave. `WEATHER_PROVIDER` = `met_norway` (por omisión) | `open_meteo` (sólo con plan de pago o
servidor propio: `WEATHER_API_URL` y `WEATHER_API_KEY`, que viaja como `apikey` y solo por entorno).

Reglas de uso de MET que el código cumple (`apps/core/weather.py`, `_met_panel`):

- **User-Agent obligatorio** con la app y un contacto: `WEATHER_USER_AGENT`, SOLO por entorno (el repo
  es público). Si falta no se llama y la tarjeta dice «no disponible»; el log lo advierte una vez
  por hora (`weather_user_agent_missing`).
- Respeta `Expires` (el pronóstico se guarda lo mayor entre `WEATHER_PANEL_CACHE_SECONDS` y lo que
  falte) y usa `If-Modified-Since`: un 304 reutiliza la copia. Acepta 203 con aviso en el log.
- Coordenadas con 2 decimales (el máximo permitido es 4). Una sola llamada por ubicación: el panel,
  «Entorno» y la ficha del plan comparten el mismo pronóstico en caché. Muy por debajo de 20 req/s.
- 429: frena 15 minutos y mientras tanto sirve la copia vieja con su hora real de consulta.
- **Atribución**: «Based on data from MET Norway» y CC BY 4.0, en la tarjeta, en «Entorno» y en la
  ficha del plan (sale del proveedor que dio ESE pronóstico).
- El servidor (`p340`) debe poder salir a `api.met.no` (HTTPS). La CSP no cambia: la llamada es del
  servidor.

Medición real (2026-10-23, Santiago): la respuesta `complete` pesa ~61 KB sin comprimir, 88 pasos
(horarios las primeras ~60 h y cada 6 h hasta ~9 días). `MAX_BODY_BYTES` es 256 KB.

### Lo que MET no entrega (y la tarjeta dice «no disponible»)

Fuera de los países nórdicos **no hay ráfagas, probabilidad de precipitación ni visibilidad**: quedan
`None`, la tarjeta lo nombra («No disponible en esta fuente») y sin esos datos no se emiten los
eventos «Ráfagas» ni «Visibilidad baja» por medición (la niebla sí, porque viene del símbolo del
tiempo). Sin eventos se dice «Sin eventos … en los datos disponibles», nunca un «tranquilo» de más.
Tampoco se usa su UV (es el de cielo despejado, no el pronóstico).

El adaptador (`apps/core/weather_met.py`) devuelve la MISMA forma que Open-Meteo, así que el panel, el
centelleo y «Entorno» no cambian. Pérdidas documentadas: `symbol_code` → WMO es una tabla fija (la
llovizna no existe en MET; el aguanieve sale como lluvia helada; toda tormenta es 95; no hay granizo);
el día en curso resume lo que falta del día; la lluvia de un paso de 6 h se atribuye al día en que
empieza; el código diario es el más severo.

### Amanecer y atardecer

No vienen de ninguna API: `apps/core/solar.py` (NOAA/Meeus, ±1 min entre ±72°) es la fuente única de
la ventana de centelleo y de la escena del cielo (LV-364).

### Para volver a Open-Meteo de pago

`WEATHER_PROVIDER=open_meteo`, `WEATHER_API_KEY=<llave de pago>` y reiniciar. La geocodificación de
Open-Meteo sólo se usa con ese proveedor.
## Sin Internet en el servidor

El panel no se rompe ni bloquea el render: espera como máximo `WEATHER_TIMEOUT_SECONDS` (4 s),
muestra el estado de error con «Reintentar», cachea el fallo `WEATHER_PANEL_CACHE_SECONDS` y deja
UNA advertencia de log por ventana (`weather_unreachable`, sin URL ni datos). Si la petición htmx
misma falla, `static/js/weather-card.js` reemplaza el esqueleto por ese mismo estado.

## Por verificar en vivo (no lo cubren las pruebas, que no salen a la red)

- Salida de `p340` a `api.met.no` y que `WEATHER_USER_AGENT` esté fijado en `/etc/aerocontrol.env`.
- Con el proveedor de MET, la tarjeta de Santiago con datos reales (ráfagas y visibilidad en «no disponible»).
- Tras desplegar: `collectstatic` (lleva JS nuevo) y comprobar que el panel dibuja la tarjeta.
