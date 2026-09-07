// `UX-26` · El *service worker*: la última consulta, disponible sin señal.
//
// **Se sirve desde `/sw.js` y no desde `/static/js/`, y eso no es preferencia.**
// El alcance de un service worker es el directorio del que se descarga: desde
// `/static/js/sw.js` sólo podría interceptar peticiones bajo `/static/js/`, o
// sea nada de lo que importa. Por eso lo entrega una vista de Django en la raíz.
// Es también la razón de que este archivo sea una plantilla: `CACHE` lleva la
// versión del despliegue, y un nombre nuevo es lo que hace que el navegador tire
// la caché vieja en vez de servir la pantalla del mes pasado para siempre.
//
// ## Las tres reglas, en orden de importancia
//
// 1. ⚠️ **Nunca se escribe sin conexión.** Todo lo que no sea `GET` va a la red
//    y no se guarda ni se reintenta. Sin conexión falla, y falla a la vista.
//    Es la línea textual del plan: *"un registro de cumplimiento creado offline
//    y sincronizado tarde es peor que no tenerlo"* — llegaría con la fecha
//    equivocada, después de que alguien ya decidió creyendo que no existía.
// 2. **Primero la red, siempre.** La caché es el plan B, nunca el plan A: esta
//    aplicación muestra vencimientos, y una pantalla de ayer servida como si
//    fuera de hoy es exactamente el error que no puede cometer.
// 3. **Lo servido de la caché va fechado.** Lo hace `pwa.js` en la página; acá
//    se guarda el sello (`X-Aero-Cached-At`) del que sale la fecha.
//
// ## Y lo que deliberadamente no se guarda
//
// Nada de `/admin/`, `/accounts/` ni `/api/`: credenciales, formularios de
// sesión y datos crudos. Y **la caché se borra al cerrar sesión**, que es la
// contrapartida de guardar fichas de personas y aeronaves en el navegador: en un
// equipo compartido en faena, cerrar sesión tiene que llevarse lo que se vio.

const CACHE = "aerocontrol-{{ version }}";

// Las rutas que no se tocan, ni para leer ni para guardar. Prefijos y no
// expresiones: una lista que hay que leer de un vistazo antes de agregarle algo.
const NEVER_CACHE = ["/admin/", "/accounts/", "/api/", "/csp-report/", "/health/"];

function offLimits(url) {
  return NEVER_CACHE.some((prefix) => url.pathname.startsWith(prefix));
}

self.addEventListener("install", (event) => {
  // Sin precarga de nada: no hay un juego de páginas "de la aplicación" que
  // tenga sentido guardar por adelantado, porque lo que sirve sin señal es lo
  // que esta persona miró. `skipWaiting` para que una versión nueva del worker
  // mande de inmediato en vez de esperar a que se cierren todas las pestañas.
  event.waitUntil(self.skipWaiting());
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      // Cachés de despliegues anteriores. Sin esto, cada versión deja la suya y
      // el navegador acumula pantallas de meses que nadie va a mirar.
      const names = await caches.keys();
      await Promise.all(
        names
          .filter((name) => name.startsWith("aerocontrol-") && name !== CACHE)
          .map((name) => caches.delete(name)),
      );
      await self.clients.claim();
    })(),
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);

  // ⚠️ Regla 1. Un `POST` no se intercepta, no se guarda y no se reintenta.
  if (request.method !== "GET") return;
  // Otro origen: no es asunto de este worker.
  if (url.origin !== self.location.origin) return;
  if (offLimits(url)) return;

  // Cerrar sesión se lleva lo guardado. Va antes del `return` de arriba porque
  // `/accounts/` está en la lista: el worker no cachea esa ruta, pero sí tiene
  // que reaccionar a ella.
  event.respondWith(networkFirst(request));
});

self.addEventListener("message", (event) => {
  if (event.data === "aero-clear-cache") {
    event.waitUntil(caches.delete(CACHE));
  }
});

async function networkFirst(request) {
  try {
    const response = await fetch(request);
    // Sólo respuestas completas y correctas. Una 404 guardada se serviría como
    // "la última vez que miraste" cuando en realidad es la última vez que
    // fallaste, y una respuesta parcial (206) no es una página.
    if (response.ok && response.type === "basic") {
      const copy = await stamp(response.clone());
      const cache = await caches.open(CACHE);
      await cache.put(request, copy);
    }
    return response;
  } catch (error) {
    const cached = await caches.match(request);
    if (cached) return cached;
    throw error;
  }
}

async function stamp(response) {
  // El sello del momento en que se guardó, que es lo que la página lee para
  // decir "datos del <fecha>". Va en una cabecera propia y no se deduce de
  // `Date`: esa cabecera la escribe el servidor y sobrevive a una respuesta
  // servida desde el caché HTTP del navegador, así que podría mentir por horas.
  const headers = new Headers(response.headers);
  headers.set("X-Aero-Cached-At", new Date().toISOString());
  return new Response(await response.blob(), {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}
