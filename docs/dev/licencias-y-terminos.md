# Licencias y términos de las fuentes externas (LV-360)

> Estado: inventario (2026-10-21), nota interna no autoritativa. **No es asesoría legal.** Los términos de terceros cambian: lo marcado «verificar» se confirma en la página oficial del proveedor antes de decidir. Lo que requiere un contrato o una autorización lo decide la persona.

## 1. Qué usa hoy AeroControl y qué exige

| Fuente | Para qué se usa | Condición conocida | ¿Hace falta algo? | Estado |
|---|---|---|---|---|
| **Open-Meteo** (`api.open-meteo.com`, geocodificación) | Pronóstico, puesta de sol y eventos de la tarjeta del tiempo; lleva la hora de atardecer de la ventana de centelleo | La API gratuita es de **uso no comercial**; los datos se publican con licencia **CC BY 4.0** (atribución). Para uso comercial hay plan de pago con llave, o servidor propio | **Sí** para cumplir: plan de pago (`WEATHER_API_URL`/`WEATHER_API_KEY`) o servidor propio. Riesgo aceptado por la persona «de momento» (2026-10-20). Salida inmediata: `WEATHER_ENABLED=False` | Encendido, riesgo aceptado |
| **AIP-Chile / DGAC** (aipchile.dgac.gob.cl; API de aeródromos y, en estudio, ENR 5.1) | Aeródromos (copia versionada de la API), enlaces al IFIS y, a futuro, zonas P/R/D | Es publicación oficial; **verificar** el aviso de derechos y si permite reproducir o derivar para uso interno | **Verificar** y, si hay duda, pedir autorización escrita a la DGAC (AIS). Citar siempre la fuente y la vigencia (AIRAC) | En investigación (LV-360 b) |
| **Mapa «ZONAS SENSIBLES»** (Google My Maps, lo que entrega la DGAC) | Zonas, aeródromos, pistas y FIR de «Espacio aéreo» | Autoría y licencia **no confirmadas** (el visor dice «Un usuario creó este mapa»; la persona lo da por oficial). Es contenido de un tercero | Confirmar con la DGAC quién lo mantiene y bajo qué condiciones se puede copiar. Mientras tanto: datos **solo en la base, nunca en git**, atribución textual y «Referencial» | En producción, sin licencia confirmada |
| **GEOCOM / Trimble** (portal de perturbaciones ionosféricas) | Referencia estadística de la ventana de centelleo (texto, sin llamadas ni datos en vivo) | Contenido de un tercero; no se copia su mapa ni sus series, solo se cita el criterio | Pedir autorización a GEOCOM para citarlo y, si se quieren **datos en vivo**, un acuerdo (el interés es de la persona, que conoce el portal) | Citado; sin acuerdo |
| **OpenStreetMap** (fondo «Streets») | Mapa de fondo de Planificación geoespacial y de Espacio aéreo | Los teselas de `tile.openstreetmap.org` tienen **política de uso** (no uso intensivo, atribución, identificación válida); no garantizan servicio | Para uso interno de pocas personas suele bastar con atribuir; si crece el tráfico, un proveedor de teselas con contrato o servidor propio. **Verificar** la política vigente | Atribución en pantalla |
| **Esri World Imagery** (fondo «Satellite», por omisión) | Fondo satelital | Servicio de Esri con sus propios términos y atribución; el uso en producción suele pedir cuenta/llave de ArcGIS. **Verificar** los términos vigentes | **Probable sí**: cuenta de desarrolladores de Esri (plan gratuito con límites) o un proveedor alternativo, antes de depender de él | Atribución en pantalla |
| **BCN** (comunas y regiones, `apps/geo/data/comunas.txt`) | Ubicación administrativa (referencial) | Datos abiertos de la Biblioteca del Congreso Nacional; **citar la fuente**. Verificar la licencia exacta del conjunto | Mantener la atribución y la advertencia de «referencial» | Incluido en el repo con aviso |
| **NVIDIA NIM** (asistente) | Asistente de consulta (apagado en producción) | Términos de prueba: no producción; pueden usar prompts y respuestas | **Sí** antes de activarlo: licencia con uso en producción (ver `docs/dev/asistente-ia.md`, cinco puntos) o modelo propio | Apagado |
| **Librerías front-end** (Leaflet, Geoman free, Bootstrap, htmx, Chart.js, FullCalendar, SortableJS) | Interfaz | Licencias permisivas (BSD/MIT; **verificar** cada una al actualizar). Se sirven desde el propio origen (`static/vendor/README.md`) | No; conservar los avisos de licencia al actualizar | Al día |
| **Ilustraciones y tipografías** (AeroAcademy, Archivo) | Identidad visual | Propias de la organización / tipografía libre (**verificar** la licencia del archivo servido) | No | Al día |

## 2. Reglas que se mantienen

- Los datos importados de terceros viven en la base, no en git (repo público), con la atribución visible y la fecha de la foto.
- «Referencial. Confirme contra el AIP-Chile y los NOTAM antes de volar»: nunca se presenta un dato de terceros como decisión de vuelo.
- Una fuente nueva con llamadas salientes va detrás de un interruptor (`*_ENABLED`) y se documenta aquí **antes** de encenderla.

## 3. Decisiones que le tocan a la persona

1. **DGAC:** autorización escrita (o confirmación de los términos públicos) para reproducir el contenido del AIP-Chile y del mapa de zonas sensibles dentro de AeroControl.
2. **Open-Meteo:** plan comercial o servidor propio, o apagar la tarjeta del tiempo.
3. **Fondos de mapa:** cuenta de Esri para el satélite y política de uso de OSM; o un proveedor único con contrato.
4. **GEOCOM:** autorización para citar el criterio y, si se desea, acuerdo para datos en vivo.
5. **NVIDIA:** licencia con producción, o dejar el asistente apagado.
