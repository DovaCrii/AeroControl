// Geoman editing wired to the canonical document (GEO-8). Geoman is loaded as a
// classic script before the module, so it augments the global `L`.
//
// Editing rules: points are CircleMarkers (KML Point), lines Polylines
// (LineString), polygons/rectangles Polygons. Marker/text/cut/rotate are off —
// they have no faithful KML representation here. Every completed gesture
// mutates state.doc, records an undo snapshot, and flags the page dirty.
//
// LV-202: **el círculo se enciende.** Estaba apagado junto a los otros cuatro y
// por la misma razón escrita arriba —"no faithful KML representation"—, y eso era
// cierto a medias: KML no tiene un círculo, pero sí lo tiene poligonalizado, que
// es exactamente cómo llegan los reales (los KMZ de Trimble de CC 738, que
// `R10.4` aprendió a leer). El usuario lo reportó como crítico y el síntoma se
// entiende con esto a la vista: al no haber círculo, el botón redondo de la barra
// es el de **punto** (`drawCircleMarker`, que es como se dibuja un KML Point), así
// que apretarlo "sólo genera un marker" — no era un fallo, era la única
// herramienta redonda que había.
//
// `L.Circle.toGeoJSON()` devuelve un `Point` y **pierde el radio**, así que
// encender el botón no habría bastado: la conversión a anillo es la fila.

import {
  addPlacemark,
  circleRing,
  removePlacemark,
  findPlacemark,
  geometryFromLayer,
  newUid,
} from "./doc.js";
import { closedRingOf, pairCircleCenters, ringCentroid } from "./circles.js";

const DRAW_CONTROLS = {
  position: "topleft",
  drawCircleMarker: true,
  drawPolyline: true,
  drawPolygon: true,
  drawRectangle: true,
  drawCircle: true,
  drawMarker: false,
  drawText: false,
  editMode: true,
  dragMode: true,
  removalMode: true,
  cutPolygon: false,
  rotateMode: false,
};

// Attach edit-sync listeners to one rendered layer so vertex/drag edits flow
// back into its placemark node. Called by the renderer for every layer.
//
// LV-277: `layer` llega como el grupo de `L.geoJSON`, y `toGeoJSON()` de un grupo
// es una `FeatureCollection` **sin `geometry`**: `geometryFromLayer` devolvía
// `null` y la sincronización no escribía nada. Se escucha y se lee la **hoja** (la
// figura que Geoman realmente edita), no el grupo que la envuelve.
//
// `getLayers()` devuelve el `Map(uid -> capa)` vigente: `main.js` lo reconstruye en
// cada `render()`, así que se pasa una función y no el mapa, que quedaría viejo.
export function wireLayer(layer, uid, state, onChange, getLayers) {
  layer = leafOf(layer);
  if (!layer) {
    return;
  }
  // Mientras se arrastra un círculo: el pin que lo acompaña y de dónde partió.
  let follower = null;

  const persist = () => {
    const node = findPlacemark(state.doc, uid);
    if (!node) {
      return;
    }
    const geometry = geometryFromLayer(layer);
    if (!geometry) {
      return;
    }
    node.geometry = geometry;
    if (follower) {
      const pinNode = findPlacemark(state.doc, follower.uid);
      if (pinNode) {
        pinNode.geometry = {
          type: "Point",
          coordinates: [follower.lng, follower.lat],
        };
      }
    }
    // Un solo snapshot para el anillo y su centro: un Deshacer los devuelve juntos.
    state.snapshot();
    onChange();
  };

  // LV-277: el centro es el punto que `pairCircleCenters` empareja con este
  // anillo —el mismo criterio con que el servidor decide cuál copia la hoja de
  // SIGO—. Sin anillo-círculo o sin punto dentro, no hay nada que acompañar.
  layer.on("pm:dragstart", () => {
    follower = null;
    const node = findPlacemark(state.doc, uid);
    const ring = node && closedRingOf(node.geometry);
    const layers = getLayers ? getLayers() : null;
    if (!ring || !layers) {
      return;
    }
    const pinUid = pairCircleCenters(state.doc).get(uid);
    const pinNode = pinUid && findPlacemark(state.doc, pinUid);
    const pinLeaf = pinNode && leafOf(layers.get(pinUid));
    if (!pinLeaf || typeof pinLeaf.setLatLng !== "function") {
      return;
    }
    const [lng, lat] = pinNode.geometry.coordinates;
    follower = {
      uid: pinUid,
      leaf: pinLeaf,
      start: ringCentroid(ring),
      lng,
      lat,
      startLng: lng,
      startLat: lat,
    };
  });
  // En vivo: el pin se mueve con la misma distancia que el anillo. Se mide el
  // centroide del anillo **ahora** contra el de la salida, en vez de acumular
  // deltas de los eventos, que pierden pasos si el navegador los junta.
  layer.on("pm:drag", () => {
    if (!follower) {
      return;
    }
    const ring = closedRingOf(geometryFromLayer(layer));
    if (!ring) {
      return;
    }
    const now = ringCentroid(ring);
    follower.lng = follower.startLng + (now.lng - follower.start.lng);
    follower.lat = follower.startLat + (now.lat - follower.start.lat);
    follower.leaf.setLatLng([follower.lat, follower.lng]);
  });
  // pm:update fires once an edit gesture completes; the drag events cover
  // whole-shape moves. Together they catch every geometry change without
  // snapshotting on every intermediate vertex move.
  layer.on("pm:update", persist);
  layer.on("pm:dragend", () => {
    persist();
    follower = null;
  });
}

function leafOf(layer) {
  if (layer && typeof layer.getLayers === "function") {
    return layer.getLayers()[0] || null;
  }
  return layer;
}

// Install the Geoman toolbar and the create/remove handlers. `render` rebuilds
// all layers from state.doc (used after create/remove/undo so there is a single
// representation of each feature). `getActiveFolder` returns the uid of the
// folder new features should land in (GEO-11), or null for the document root.
// Show/hide the Geoman draw toolbar. Used to suspend editing while the diff
// overlay (GEO-12a) is active so a stray draw cannot mutate the document.
export function setDrawControls(map, on) {
  if (on) {
    map.pm.addControls(DRAW_CONTROLS);
  } else {
    map.pm.removeControls();
  }
}

export function installEditor({
  map,
  state,
  render,
  onChange,
  getActiveFolder,
  labels,
}) {
  map.pm.addControls(DRAW_CONTROLS);

  map.on("pm:create", (event) => {
    const folderUid = getActiveFolder ? getActiveFolder() : null;
    // LV-202: una circunferencia terminada deja **dos** cosas: el anillo y su
    // punto central. El centro es el pedido literal del usuario ("cuando se
    // termine de editar y finalizar me cree un pin central"), y no es un adorno:
    // el backend empareja el punto declarado con el anillo y mide el radio contra
    // **ese** centro (`sections.py`); sin él estima el centroide, que en un
    // círculo de 64 lados es casi el mismo punto pero deja de ser un dato
    // declarado y pasa a ser uno inferido. La hoja de SIGO copia el centro.
    if (event.shape === "Circle" && typeof event.layer.getRadius === "function") {
      const center = event.layer.getLatLng();
      const ring = circleRing(center, event.layer.getRadius());
      map.removeLayer(event.layer);
      addPlacemark(
        state.doc,
        newUid(),
        { type: "Polygon", coordinates: [ring] },
        folderUid
      );
      const pin = addPlacemark(
        state.doc,
        newUid(),
        { type: "Point", coordinates: [center.lng, center.lat] },
        folderUid
      );
      // El único de los dos con nombre, y por eso: en el panel de capas hay que
      // poder decir cuál de los dos elementos nuevos es el centro. El texto viene
      // traducido del servidor, como el resto (`config.labels`) — en estos
      // módulos no se escriben cadenas visibles.
      if (labels && labels.circleCenter) {
        pin.name = labels.circleCenter;
      }
      state.snapshot();
      render();
      onChange();
      return;
    }
    const geometry = geometryFromLayer(event.layer);
    // Drop Geoman's raw layer; render() re-adds it styled and wired from the
    // canonical node, so there is exactly one layer per placemark.
    map.removeLayer(event.layer);
    if (!geometry) {
      return;
    }
    addPlacemark(state.doc, newUid(), geometry, folderUid);
    state.snapshot();
    render();
    onChange();
  });

  map.on("pm:remove", (event) => {
    const uid = event.layer && event.layer._geoUid;
    if (!uid) {
      return;
    }
    removePlacemark(state.doc, uid);
    state.snapshot();
    // Rebuild layers + the layer tree so the panel reflects the removal.
    render();
    onChange();
  });
}
