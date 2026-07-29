# GEO V2 — plan de diseño (alcance aprobado 2026-07-29)

> Continúa [geo-editor-plan.md](geo-editor-plan.md) (MVP GEO-0..GEO-10). El
> tablero vive en `MASTER_PLAN.md` (BLOQUE GEO). **Alcance aprobado por el
> usuario:** GEO-11 (edición de capas) + GEO-12a (diff visual). Diferidos con su
> propia decisión: GEO-12b (editar ExtendedData), GEO-13 (StyleMap editable /
> XSD; los iconos embebidos quedan como posible add-on), GEO-14 (hooks DJI).

## Principio rector

El servidor ya es la autoridad: **el commit re-valida cualquier forma de árbol**
(`apps/geo/kml/canonical.py:validate_document`, `reparse_raw=True`) y hace
cumplir los caps (`MAX_FEATURES=2000`, `MAX_CONTENT_BYTES=8 MB`) y el orden de
hermanos (se preserva tal cual en el JSON). Por eso GEO-11 y GEO-12a son
**casi todo trabajo de cliente**: no cambian el modelo ni el endpoint de commit.

## Decisiones transversales registradas

1. **uid sin re-keying.** Los `uid` son estables entre versiones una vez
   commiteados (import los conserva; restore copia el `content` verbatim; una
   feature creada en el editor conserva su `uid` `e-…` para siempre). El diff por
   `uid` (GEO-12a) funciona sin normalizar. El desajuste de prefijo cliente
   (`e-…`, `doc.js`) vs servidor (`p-/f-/r-`, `canonical.new_uid`) es cosmético;
   **no se agrega paso de re-keying** en el commit.
2. **Sin framework de test JS.** Se mantiene el "sin build pipeline" del repo. Las
   invariantes críticas viven en el servidor (el commit re-valida), y GEO-11/12a
   se verifican **en el navegador** como GEO-7/8. Los mutadores de `doc.js` se
   escriben como funciones puras sobre el canónico para poder razonarlos y, si más
   adelante se agrega un runner, testearlos sin DOM.
3. **"Dividir" acotado.** El split de GEO-11 = **explotar** una `MultiGeometry`
   (`GeometryCollection` en el canónico) en placemarks separados. El split de un
   polígono/línea por vértice (operación GIS) queda fuera.

---

## GEO-11 — edición de capas

### `static/js/geo/doc.js` — mutadores puros nuevos

Hoy sólo existen `addPlacemark` (inserta en la raíz), `removePlacemark` y
`findPlacemark` (sólo placemarks). Se agregan, todos operando sobre el árbol
`doc.children` y devolviendo el `doc` mutado (o un clon, ver undo):

| Función | Semántica |
|---|---|
| `findNode(doc, uid)` | Devuelve cualquier nodo (folder/placemark/raw) por uid. |
| `findParent(doc, uid)` | Devuelve `{parent, index}` (parent = `doc` o un folder). |
| `moveNode(doc, uid, targetFolderUid, index)` | Saca el nodo de su padre y lo inserta en el folder destino (o raíz si `null`) en la posición `index`. Rechaza mover un folder dentro de sí mismo/su descendencia. |
| `reorderSibling(doc, uid, index)` | Reordena dentro del mismo padre. |
| `duplicateNode(doc, uid)` | Copia profunda del nodo; **uids nuevos** (`newUid`) para el nodo y toda su descendencia; se inserta justo después del original. |
| `explodeMultiGeometry(doc, uid)` | Si el placemark tiene `geometry.type === "GeometryCollection"`, lo reemplaza por N placemarks hermanos, uno por sub-geometría, cada uno con `uid` nuevo, heredando name/description/style_url; el name recibe sufijo ` (1)`, ` (2)`… |

Invariante: ninguna de estas funciones toca `shared_styles`, `kmz_resources` ni
`raw_xml`; sólo reordenan/copian nodos existentes. La duplicación cuenta contra
`MAX_FEATURES` — el servidor lo rechaza si se excede (no hace falta chequear en
cliente, pero el panel puede avisar).

### `static/js/geo/panel.js` — de lista plana a árbol

Hoy `panel.js` pinta una fila-checkbox por *grupo de folder* (aplana con
`doc.js:collectFeatures`/`groupByFolder`) que togglea la visibilidad de un
`layerGroup` de Leaflet. Se reescribe a un **árbol anidado** que refleja
`doc.children`:

- Una fila por nodo (folder y placemark), con indentación por profundidad.
- Folder: triángulo colapsar/expandir + checkbox de visibilidad (togglea la
  visibilidad de todos sus placemarks descendientes, preservando el
  comportamiento actual de `layerGroup`).
- Placemark: checkbox de visibilidad + botones **Duplicar** y (si es
  `GeometryCollection`) **Explotar**.
- **Drag & drop** con la API nativa de HTML5 (`draggable`, `dragstart`/`dragover`/
  `drop`) — sin librerías, CSP-safe, DOM puro (nada de `innerHTML`). Soltar sobre
  un folder → `moveNode` a ese folder; soltar entre hermanos → `reorderSibling`/
  `moveNode` con índice. Indicador visual de destino.
- Todo construido con `document.createElement`/`textContent` (regla XSS del MVP).

### `static/js/geo/edit.js` — inserción folder-aware

`pm:create` hoy llama `addPlacemark(doc, newUid(), geometry)` que inserta en raíz.
Se agrega la noción de **folder activo** (el seleccionado en el panel): las
features nuevas caen en ese folder, o en la raíz si no hay selección. `addPlacemark`
gana un parámetro `targetFolderUid` opcional.

### Undo / render

Cada gesto completo (un move, un duplicate, un explode, un drop) llama
`state.snapshot()` **una vez** (contrato de undo existente, `state.js`, pila
`structuredClone` capada a 50). Tras cada mutación estructural se llama
`render()` (`main.js`), que ya reconstruye todas las capas y ahora también
re-pinta el árbol del panel. `dirty`/`beforeunload` siguen funcionando porque
comparan `JSON.stringify(doc)` con el baseline.

### Servidor

**Sin cambios.** El commit (`api.py:GeoPlanVersionsView.post`) ya valida el árbol
resultante, recomputa `feature_count`/`bbox`/`size_bytes` en el servidor e
ignora lo que mande el cliente.

---

## GEO-12a — diff visual entre versiones

### Fuente de datos

Sin endpoint nuevo: se reusa `GET .../versions/<n>/content/`
(`api.py:GeoPlanVersionContentView`, con ETag/304) para traer el `content` de dos
versiones. El diff es **100% cliente**.

### `static/js/geo/diff.js` — algoritmo por uid

```
diffDocuments(base, target) -> { added:[uid], removed:[uid], moved:[uid], changed:[uid], unchanged:[uid] }
```

- Índice `uid -> {node, folderPath}` de cada documento (reusa el recorrido de
  `doc.js:collectFeatures`, extendido para incluir folders).
- `removed` = uid en base y no en target; `added` = a la inversa.
- Para uid en ambos: `changed` si difiere geometría/atributos (comparación de
  `canonical_json` del nodo, ignorando hijos para folders); `moved` si cambió su
  `folderPath` o índice; si no, `unchanged`. Un nodo puede ser `moved`+`changed`
  → se prioriza `changed` en el color, `moved` en el detalle.

### UI

- Un selector "Comparar versión A ↔ B" en el shell del detalle (server-rendered,
  las versiones ya se listan). Al elegir, la isla entra en **modo diff**
  (read-only): trae ambos `content`, corre `diffDocuments`, y pinta sobre el mapa
  el estado *target* con colores por estado: **verde=agregado, rojo=borrado,
  ámbar=cambiado/movido, gris=sin cambios**. Leyenda + conteos.
- El panel muestra el árbol *target* con un badge de estado por fila; los
  `removed` se listan aparte (no están en target).
- Salir del modo diff vuelve al editor/visor normal.

### Sin cambios de servidor ni de modelo

El diff no persiste nada; es una vista derivada. (Un endpoint de diff server-side
se podría agregar a futuro, pero no es necesario y mantendría el mismo resultado.)

---

## Verificación (por tarea)

- **Navegador (demo)**: importar un KMZ con carpetas → reordenar/mover entre
  carpetas → duplicar → explotar una MultiGeometry → commit → **reabrir en Google
  Earth** y confirmar estructura/geometrías. Diff: commitear un cambio, comparar
  v(n-1) ↔ v(n), verificar colores/conteos.
- **Gate**: `verify.ps1` verde. Las vistas server nuevas (si el selector de diff
  agrega alguna) llevan test 403 por permiso; los strings nuevos al catálogo `es`;
  cobertura ≥83. La lógica de cliente se cubre por la verificación en navegador
  (decisión transversal #2).

## Riesgos

1. **Corrección del drag&drop + undo** (un gesto = un snapshot; mover a un
   descendiente propio debe rechazarse). Mitigación: mutadores puros y probados a
   mano en navegador; el servidor re-valida el árbol igual.
2. **Estabilidad de uid para el diff** — resuelta por la decisión transversal #1
   (uids estables post-commit).
3. **Rendimiento del árbol con 500-2000 features** — render incremental si hace
   falta; hoy `render()` reconstruye todo y el MVP ya vive con ese costo.

## Tareas (tablero en MASTER_PLAN)

- **GEO-11** — `codex/geo-11`: mutadores en `doc.js`, árbol+DnD en `panel.js`,
  inserción folder-aware en `edit.js`. Un commit.
- **GEO-12a** — `codex/geo-12a`: `diff.js` + modo diff en el shell/isla. Un commit.
