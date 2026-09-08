# Post-mortem · 2026-09-08 · La aplicación dejó de cargar en producción

**Qué pasó:** después de desplegar `b4a7d9e`, `https://p340.tailccd107.ts.net`
devolvió `ERR_FAILED` en el navegador. El servidor estaba sano: `systemctl
is-active` decía `active`, gunicorn respondía en el puerto 8000 y la base no se
tocó. **Lo que no cargaba era la página, no el servicio.**

**Causa:** el *service worker* de `UX-26` (la copia sin conexión), escrito e
introducido ese mismo día.

**Duración:** minutos. Lo detectó el usuario probando la aplicación, y el arreglo
salió en la misma sesión.

**Alcance:** todo navegador que abrió la aplicación después del despliegue. No
hubo pérdida ni corrupción de datos: el worker sólo intercepta `GET`, y por
diseño no toca escrituras.

---

## El defecto, en una línea

`cache.put` estaba **dentro del camino de la respuesta**:

```js
// como estaba
try {
  const response = await fetch(request);
  if (response.ok && response.type === "basic") {
    await cache.put(request, await stamp(response.clone()));  // ⬅ aquí
  }
  return response;
} catch (error) {
  const cached = await caches.match(request);
  if (cached) return cached;
  throw error;                                                 // ⬅ y aquí
}
```

`Cache.put` **rechaza** en varios casos legítimos: una respuesta `206`, una
`redirected`, la cuota llena. Al rechazar, la ejecución caía al `catch`, que
buscaba una copia guardada, no encontraba ninguna —nunca se había guardado nada—
y **relanzaba**. Un `event.respondWith()` cuya promesa rechaza hace que el
navegador muestre un error de red: **no vuelve a la red por su cuenta.**

O sea: la petición al servidor salió bien, la respuesta llegó bien, y la página
murió al intentar guardarla.

Dos detalles agravantes, los dos míos:

- **`response.ok` incluye el 206.** Un `ok` cubre 200–299, y `Cache.put` rechaza
  explícitamente el 206. El guard parecía cubrir el caso y lo dejaba pasar.
- **`await` sobre el guardado.** Aun sin rechazar, esperar la escritura antes de
  devolver la respuesta pone el disco en el camino crítico de cada navegación.

## Por qué se propagó solo, y por qué eso es lo peor

Un service worker se instala en la primera visita y —con `clients.claim()`—
toma el control en la **siguiente** navegación. Así que:

- la pantalla en la que se probó **funcionó** (el worker recién se instalaba);
- la siguiente, no.

Y una vez instalado, **el navegador lo conserva**. Un `git revert` no lo arregla:
el navegador sigue ejecutando la copia que ya guardó. Es el único código de este
repositorio con esa propiedad, y es lo que separa este incidente de cualquier
otro defecto de esta magnitud.

## Por qué el gate no lo atrapó

Estaba verde: 3154 pruebas, 97,42 % de cobertura, `ruff`, `bandit`, `pip-audit`.
No falló nada porque **no había nada que pudiera fallar**: un service worker no
se puede ejercitar desde el cliente de pruebas de Django, y los tests que escribí
afirman sobre el **texto del archivo**, no sobre su comportamiento.

La verificación en navegador que sí hice fue con sondas de `caches` y `fetch`
desde la página — que comprueban que el archivo se sirve y que las funciones
existen, y **no** que el worker registrado no rompa una navegación. Ésa era la
única pregunta que importaba y no se hizo.

## Lo que se cambió

1. **Interruptor de apagado, y apagado por defecto.**
   `SERVICE_WORKER_ENABLED=False`. La ruta `/sw.js` **sigue existiendo** y sirve
   un worker que se desinstala solo (`registration.unregister()`), borra las
   cachés `aerocontrol-*` y **recarga las pestañas que estaba rompiendo**
   (`client.navigate`). Es el único camino que sana un navegador ya infectado sin
   pedirle a nadie que abra las herramientas del navegador.

   ⚠️ Un `404` en `/sw.js` **no** sirve: desregistra en Chrome, no en todos los
   navegadores, y deja la caché puesta.

2. **El guardado salió del camino de la respuesta**: sin `await` que la retenga,
   en `event.waitUntil`, con su propio `try/catch`. Si guardar falla, se pierde
   la copia sin conexión — que es exactamente lo que corresponde perder.

3. **`status === 200` en vez de `ok`**, más un descarte explícito de
   `response.redirected`.

4. **El interruptor se lee por petición**, en `ServiceWorkerView`, no con un
   `extra_context` en las URLs. Un `extra_context` congela el ajuste al importar
   el módulo: un interruptor de apagado que "no se aplica hasta reiniciar" sin
   decirlo es el peor tipo de interruptor, y de paso volvía imposible probar las
   dos ramas. Es la misma razón por la que `SignInView` existe.

## Guardianes que quedan puestos

| Test | Qué impide |
|---|---|
| `test_keeping_a_copy_can_never_fail_the_response` | Que el guardado vuelva al camino de la respuesta: exige `event.waitUntil(keep(` y **prohíbe** `await cache.put` en `networkFirst`. |
| `test_a_failed_response_is_not_kept` | Que vuelva `response.ok` en lugar de `status === 200`. |
| `test_it_is_off_unless_someone_turns_it_on` | Que se encienda por defecto otra vez. |
| `test_off_it_serves_a_worker_that_uninstalls_itself` | Que el camino de sanado desaparezca. |
| `test_the_route_stays_even_when_off` | Que alguien "limpie" la ruta apagada y con eso deje sin cura a los navegadores infectados. |
| `test_and_it_reloads_the_tabs_it_was_breaking` | Que el sanado deje la pestaña rota esperando un F5 manual. |

Y la regla en `AGENTS.md`, § *Lecciones operativas*: **nada que intercepte
navegaciones se despliega habilitado por defecto.**

## Cómo encender la copia sin conexión, cuando toque

1. `SERVICE_WORKER_ENABLED=True` en `/etc/aerocontrol.env` y reiniciar.
2. Abrir la aplicación, **navegar entre tres pantallas distintas** y confirmar
   que las tres cargan con el worker ya en control
   (`navigator.serviceWorker.controller` no nulo).
3. Cortar la red y confirmar que la última ficha vista se sirve **con el aviso
   de «datos del \<fecha\>»**.
4. Volver a conectar y confirmar que la pantalla siguiente llega fresca.

Si algo de eso falla: `SERVICE_WORKER_ENABLED=False` y reiniciar. Eso desinstala
los workers solos.

## Lo que este incidente no fue

**No fue una falla del despliegue.** El procedimiento corrió como está escrito:
respaldo tomado y verificado antes de migrar, una sola migración aplicada, roles
reconfigurados, estáticos copiados, y el commit de la VM coincidiendo con el de
`origin/main`. El defecto viajó **dentro** del código, con el gate verde.

Y **no fue el único defecto de esa tanda encontrado usando la aplicación**: el
mismo día, «¿Puedo volar?» (`UX-27`) contestaba *Sí* para una persona que el
permiso no nombra. Ese caso tiene su propia lección, anotada en `AGENTS.md`: la
fixture del test creaba el permiso con el padrón vacío, así que **el test
compartía el punto ciego del código que probaba**. Los dos defectos salieron de
la misma jornada y de la misma causa de fondo — verificación que confirma lo que
el código ya cree, en vez de ejercitar lo que un usuario hace.
