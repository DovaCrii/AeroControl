// Map island entry point: read-only viewer (GEO-7) plus, when the config says
// the plan is editable and the user may change it, the Geoman editor (GEO-8).
//
// The shell stays server-rendered; this is the interactive map only. Config
// arrives via json_script; content and commits go through the server API, which
// re-validates everything. Deleting this file leaves the data intact.

import { fetchCanonical, commit } from "./api.js";
import {
  collectFeatures,
  groupByFolder,
  toGeoJSON,
  findPlacemark,
  findNode,
  moveNode,
  duplicateNode,
  explodeMultiGeometry,
} from "./doc.js";
import { createMap } from "./map.js";
import { buildPanel, buildTree } from "./panel.js";
import { buildPopup, buildEditablePopup } from "./inspector.js";
import { EditorState } from "./state.js";
import { installEditor, wireLayer } from "./edit.js";

const STROKE = "#0f9f95";
const pathStyle = () => ({ color: STROKE, weight: 2, fillOpacity: 0.2 });
const pointToLayer = (_feature, latlng) =>
  L.circleMarker(latlng, { radius: 5, color: STROKE, weight: 2, fillOpacity: 0.6 });

function readConfig() {
  const el = document.getElementById("geo-map-config");
  if (!el) {
    return null;
  }
  try {
    return JSON.parse(el.textContent);
  } catch (err) {
    return null;
  }
}

function setStatus(el, text) {
  if (el) {
    el.textContent = text || "";
  }
}

async function init() {
  const config = readConfig();
  const mapEl = document.getElementById("geo-map");
  if (!config || !mapEl) {
    return;
  }
  const labels = config.labels || {};
  const panelEl = document.getElementById("geo-panel");
  const statusEl = document.getElementById("geo-map-status");
  const editable = !!config.editable;

  if (config.iconBase) {
    L.Icon.Default.imagePath = config.iconBase;
  }
  const map = createMap(mapEl, config.tileProviders);

  if (!config.contentUrl) {
    setStatus(statusEl, labels.empty);
    return;
  }

  setStatus(statusEl, labels.loading);
  let doc;
  try {
    doc = await fetchCanonical(config.contentUrl);
  } catch (err) {
    setStatus(statusEl, labels.error);
    return;
  }

  const state = editable ? new EditorState(doc) : null;
  if (state) {
    state.seed();
  }
  const currentDoc = () => (state ? state.doc : doc);

  let renderedLayers = [];
  let uidLayers = new Map();
  const hidden = new Set();
  let activeFolderUid = null;
  let fittedOnce = false;

  function makeLayer(item) {
    const layer = L.geoJSON(toGeoJSON(item), { style: pathStyle, pointToLayer });
    layer._geoUid = item.uid;
    layer.eachLayer((leaf) => {
      leaf._geoUid = item.uid;
    });
    return layer;
  }

  function fitOnce(layers) {
    if (!fittedOnce && layers.length) {
      const bounds = L.featureGroup(layers).getBounds();
      if (bounds.isValid()) {
        map.fitBounds(bounds, { padding: [24, 24], maxZoom: 17 });
      }
      fittedOnce = true;
    }
  }

  // ── GEO-11 helpers (editable only) ───────────────────────────────────────
  function descendantPlacemarkUids(folderNode) {
    const uids = [];
    (function walk(nodes) {
      for (const n of nodes || []) {
        if (n.kind === "placemark") {
          uids.push(n.uid);
        } else if (n.kind === "folder") {
          walk(n.children);
        }
      }
    })(folderNode.children);
    return uids;
  }

  function setLayerVisible(uid, visible) {
    if (visible) {
      hidden.delete(uid);
    } else {
      hidden.add(uid);
    }
    const layer = uidLayers.get(uid);
    if (layer) {
      if (visible) {
        layer.addTo(map);
      } else {
        map.removeLayer(layer);
      }
    }
  }

  // Visibility is view state, not a document edit, so it never snapshots/dirties.
  function onToggle(uid, visible) {
    const node = findNode(currentDoc(), uid);
    if (node && node.kind === "folder") {
      for (const u of descendantPlacemarkUids(node)) {
        setLayerVisible(u, visible);
      }
    } else {
      setLayerVisible(uid, visible);
    }
  }

  // A structural mutation already ran; snapshot once and rebuild from the doc.
  function structural(mutated) {
    if (mutated) {
      state.snapshot();
      render();
      onChange();
    }
  }

  function render() {
    for (const layer of renderedLayers) {
      map.removeLayer(layer);
    }
    renderedLayers = [];
    uidLayers = new Map();

    const items = collectFeatures(currentDoc());

    if (!editable) {
      // Read-only viewer: group by folder path, one layerGroup per group.
      const groups = groupByFolder(items, labels.untitled || "—");
      const panelGroups = new Map();
      const allRO = [];
      for (const [name, groupItems] of groups) {
        const group = L.layerGroup();
        for (const item of groupItems) {
          const layer = makeLayer(item);
          layer.bindPopup(() => buildPopup(item, labels));
          layer.addTo(group);
          allRO.push(layer);
        }
        group.addTo(map);
        renderedLayers.push(group);
        panelGroups.set(name, { group, count: groupItems.length });
      }
      if (panelEl) {
        buildPanel(panelEl, panelGroups, map, labels);
      }
      fitOnce(allRO);
      setStatus(statusEl, allRO.length ? "" : labels.empty);
      return;
    }

    // Editable: one layer per placemark, addressable by uid for the tree.
    const allLayers = [];
    for (const item of items) {
      const layer = makeLayer(item);
      uidLayers.set(item.uid, layer);
      layer.bindPopup(() =>
        buildEditablePopup(findPlacemark(state.doc, item.uid), labels, (n, d) => {
          const node = findPlacemark(state.doc, item.uid);
          if (node) {
            node.name = n;
            node.description = d;
            state.snapshot();
            render();
            onChange();
            layer.closePopup();
          }
        }),
      );
      wireLayer(layer, item.uid, state, onChange);
      if (!hidden.has(item.uid)) {
        layer.addTo(map);
      }
      renderedLayers.push(layer);
      allLayers.push(layer);
    }

    if (panelEl) {
      buildTree(panelEl, currentDoc(), {
        map,
        uidLayers,
        labels,
        activeFolderUid,
        hidden,
        onMove: (uid, target, index) =>
          structural(moveNode(currentDoc(), uid, target, index)),
        onDuplicate: (uid) => structural(!!duplicateNode(currentDoc(), uid)),
        onExplode: (uid) => structural(explodeMultiGeometry(currentDoc(), uid) > 0),
        onSelectFolder: (uid) => {
          activeFolderUid = uid;
          render();
        },
        onToggle,
      });
    }
    fitOnce(allLayers);
    setStatus(statusEl, allLayers.length ? "" : labels.empty);
  }

  function onChange() {
    updateToolbar();
  }

  // ── Editor wiring (GEO-8) ────────────────────────────────────────────────
  const saveBtn = document.getElementById("geo-save");
  const undoBtn = document.getElementById("geo-undo");
  const redoBtn = document.getElementById("geo-redo");
  const dirtyEl = document.getElementById("geo-dirty");
  const banner = document.getElementById("geo-banner");
  const dialog = document.getElementById("geo-save-dialog");
  const summaryInput = document.getElementById("geo-summary");

  function updateToolbar() {
    if (!editable) {
      return;
    }
    if (undoBtn) {
      undoBtn.disabled = !state.canUndo();
    }
    if (redoBtn) {
      redoBtn.disabled = !state.canRedo();
    }
    if (dirtyEl) {
      dirtyEl.textContent = state.dirty ? labels.unsaved || "" : "";
    }
  }

  function showBanner(message, withRescue) {
    if (!banner) {
      return;
    }
    banner.replaceChildren();
    banner.hidden = false;
    const text = document.createElement("span");
    text.textContent = message;
    banner.appendChild(text);
    if (withRescue) {
      const link = document.createElement("a");
      link.className = "btn btn-sm btn-outline-light ms-2";
      link.textContent = labels.rescue || "Download local copy";
      const blob = new Blob([JSON.stringify(state.doc)], { type: "application/json" });
      link.href = URL.createObjectURL(blob);
      link.download = "geo-plan-local.json";
      banner.appendChild(link);
    }
  }

  async function doCommit(summary) {
    saveBtn.disabled = true;
    setStatus(statusEl, labels.saving);
    const result = await commit(config.commitUrl, config.csrfToken, {
      base_version: config.baseVersion,
      summary,
      content: state.doc,
    });
    setStatus(statusEl, "");
    saveBtn.disabled = false;
    if (result.status === 201 || result.status === 200) {
      // Reload so the versions table and the new base_version refresh from the
      // server (the authority), and the editor starts clean on the new version.
      state.markSaved();
      window.location.reload();
      return;
    }
    const code = result.body && result.body.code;
    if (result.status === 409 && code === "plan_locked") {
      showBanner(labels.locked || "This plan is locked.", false);
    } else if (result.status === 409) {
      showBanner(labels.conflict || "The plan changed on the server.", true);
    } else if (result.status === 400) {
      const detail = (result.body && result.body.detail) || "";
      showBanner(`${labels.invalid || "Rejected"} ${detail}`.trim(), true);
    } else if (result.status === 429) {
      showBanner(labels.throttled || "Too many saves; wait a moment.", false);
    } else if (result.status === 403) {
      showBanner(labels.locked || "Not allowed.", false);
    } else {
      showBanner(labels.error || "The map could not be saved.", true);
    }
  }

  if (editable) {
    installEditor({
      map,
      state,
      render,
      onChange,
      getActiveFolder: () => activeFolderUid,
    });
    if (saveBtn && dialog && summaryInput) {
      saveBtn.addEventListener("click", () => {
        summaryInput.value = "";
        dialog.showModal();
      });
      dialog.addEventListener("close", () => {
        if (dialog.returnValue === "confirm") {
          doCommit(summaryInput.value.trim());
        }
      });
    }
    if (undoBtn) {
      undoBtn.addEventListener("click", () => {
        if (state.undo()) {
          render();
          onChange();
        }
      });
    }
    if (redoBtn) {
      redoBtn.addEventListener("click", () => {
        if (state.redo()) {
          render();
          onChange();
        }
      });
    }
    window.addEventListener("beforeunload", (event) => {
      if (state.dirty) {
        event.preventDefault();
        event.returnValue = "";
      }
    });
  }

  render();
  updateToolbar();
}

init();
