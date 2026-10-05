# Lecciones operativas (trampas ya vividas)

Destiladas de `AGENTS.md` § "Lecciones operativas": cada una costó tiempo real. Aquí va la regla; el relato completo, con fechas y filas `LV-N`, sigue en `AGENTS.md`.

Contenido: Registro y plan · Pruebas · Traducciones · Migraciones y datos · Alertas y señales · Frontend/CSS/JS · Producción

## Registro y plan
- **Fila fantasma**: trabajo hecho sin fila en `MASTER_PLAN.md` ni entrada en `CHANGELOG.md` (pasó con `LV-186`). Al cerrar, commit y fila juntos; al retomar, `plan_query.py --ghosts`.
- **El tablero miente**: un `⬜` puede estar hecho y un `✅` puede tener premisa vencida. `grep` del código antes de implementar.
- **Retiros "de pantalla y no de base"**: cada uno lleva escrita, el mismo día, la **condición de cierre** del paso 2 (qué tiene que ser cierto para borrar). Seis retiros dejaron el paso 2 sin decidir. Ejemplo de formato: `max_altitude_ft` en `apps/operations/models.py`.
- Si se retira una regla en el tablero, retirarla también de `AGENTS.md` el mismo día (las migraciones no se squashean por el tiempo del gate: se midió, 158 migraciones tardan 4,3 s).
- Un pendiente anotado en un test: escribir qué se **observó** y qué **no** se comprobó.

## Pruebas
- **Test verde de primera sobre un bug recién arreglado**: romper el arreglo una vez (revertir, correr, restaurar) para saber que el test sirve.
- Comparar contra el objeto (`Clase.mensaje`, `gettext("literal")`, `BUCKET_BADGE_CSS["overdue"]`), no contra texto o clases CSS tecleadas. Acotar la búsqueda a la región que se afirma, no a toda la página.
- **Punto ciego compartido**: la fixture debe poblar las relaciones que usa la regla de negocio (el permiso con padrón vacío hizo pasar ocho tests de «¿Puedo volar?» que contestaba Sí a quien no estaba nombrado). Si la comprobación responde sobre una terna, variar cada pata por separado.
- **Dependencia del día**: si falla un test y el diff no toca lo que afirma, mirar la fecha antes que el diff. Fijar el reloj y la fecha del dato.
- **El gate verifica código, no cableado**: una función que notifica se comprueba en producción (`--dry-run`, `systemctl list-timers`), no solo con tests.
- Antes de agregar un método a una clase larga, listar los que ya tiene.

## Traducciones
- Ver `convenciones.md` §3. Casos clave: `fuzzy` de `makemessages` puso en pantalla lo contrario de lo que decía el código (`LV-183`); `{% translate %}` con `%(x)s` devuelve inglés (`LV-198`); sin voseo.

## Migraciones y datos
- Los sembrados son idempotentes **por nombre/código** (`seed_alert_rules` por `name`, `seed_document_types` por `code`): renombrar una regla sembrada crea otra y deja la vieja viva (duplicaba avisos). Extender sumando filas, sin tocar claves.
- Chequeos previos a una migración: `values_list`, nunca `.all()`.
- El demo (`scripts/run-demo.ps1`, login `demo`/`demo-review-only`) tiene casos límite que la copia de restauración no: un bug de orden de la migración `0028` fue silencioso contra la copia limpia y reventó contra el demo.

## Alertas y señales
- `post_save`, no `pre_save`, cuando el handler vuelve a guardar algo (`Alert.resolve()` re-guarda la tarjeta enlazada; con `pre_save` esa escritura se pierde).
- Una función que notifica no está terminada hasta comprobar el camino completo en producción: grupo destinatario con correos y trabajo programado registrado.

## Frontend, CSS y JS
- **Contraste**: se calcula (aritmética sobre dos colores), no se lee del navegador; medir contra el fondo correcto. **Medir y además mirar**: un número correcto puede describir solo la mitad de un defecto visual; una captura cierra la fila.
- `colspan` de la fila vacía = número exacto de `<col>` en tablas `.table-normalized`; `colspan="99"` destruye los anchos. `worktable.js` le suma uno, nunca lo reemplaza. Hay un guardián que cruza `*_list.html` con `_*_rows.html`.
- Custom property inline en un elemento puede anular una regla de estado: usar un token aparte para el valor del usuario (`--ac-sidebar-width-user`) escrito en `documentElement`.
- `localStorage` **lanza** (no devuelve `null`) en ventana privada o con almacenamiento bloqueado: todo acceso va envuelto, lectura incluida.
- Vistas de error: `render_to_string` **sin** `request` (con `render(request, …)` corren los context processors y apoyan la página de error en el orden de los middleware).
- Al verificar CSS/JS en el navegador integrado, forzar revalidación (`fetch(url, {cache: 'reload'})`) antes de creerle a la medición. `collectstatic` de prueba deja `staticfiles/` (no versionado; borrarlo).
- **Service worker**: es el único código que sobrevive a un `git revert`. (1) Guardar en caché es efecto secundario fuera del camino de la respuesta (`event.waitUntil`, con su `try/catch`). (2) `status === 200`, no `response.ok` (una 206 también es `ok` y `Cache.put` la rechaza; tampoco respuestas `redirected`). (3) **Nunca se despliega habilitado por defecto**: va tras `SERVICE_WORKER_ENABLED=False`, y `/sw.js` sigue existiendo apagado sirviendo un worker que se desinstala solo. Se enciende tras ejercitarlo como worker registrado de verdad.

## Producción
- Ver `despliegue-p340.md`. Tres ideas: el hash final de `git log -1` en la VM es la única prueba de que llegó; el despliegue incluye TODO lo que falta en la VM, no solo el último commit; `showmigrations` es el diagnóstico de treinta segundos ante un 500.
