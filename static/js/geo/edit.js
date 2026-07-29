// Geoman editing wired to the canonical document (GEO-8). Geoman is loaded as a
// classic script before the module, so it augments the global `L`.
//
// Editing rules: points are CircleMarkers (KML Point), lines Polylines
// (LineString), polygons/rectangles Polygons. Circle/marker/text/cut/rotate are
// off — they have no faithful KML representation here. Every completed gesture
// mutates state.doc, records an undo snapshot, and flags the page dirty.

import { addPlacemark, removePlacemark, findPlacemark, geometryFromLayer, newUid } from "./doc.js";

const DRAW_CONTROLS = {
  position: "topleft",
  drawCircleMarker: true,
  drawPolyline: true,
  drawPolygon: true,
  drawRectangle: true,
  drawMarker: false,
  drawCircle: false,
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

export function installEditor({ map, state, render, onChange, getActiveFolder }) {
  map.pm.addControls(DRAW_CONTROLS);

  map.on("pm:create", (event) => {
    const geometry = geometryFromLayer(event.layer);
    // Drop Geoman's raw layer; render() re-adds it styled and wired from the
    // canonical node, so there is exactly one layer per placemark.
    map.removeLayer(event.layer);
    if (!geometry) {
      return;
    }
    const folderUid = getActiveFolder ? getActiveFolder() : null;
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
