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
export function wireLayer(layer, uid, state, onChange) {
  const sync = () => {
    const node = findPlacemark(state.doc, uid);
    if (!node) {
      return;
    }
    const geometry = geometryFromLayer(layer);
    if (geometry) {
      node.geometry = geometry;
      state.snapshot();
      onChange();
    }
  };
  // pm:update fires once an edit gesture completes; the drag events cover
  // whole-shape moves. Together they catch every geometry change without
  // snapshotting on every intermediate vertex move.
  layer.on("pm:update", sync);
  layer.on("pm:dragend", sync);
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
