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
import { diffDocuments, DIFF_COLORS } from "./diff.js";
import { buildPopup, buildEditablePopup } from "./inspector.js";
import { EditorState } from "./state.js";
import { installEditor, wireLayer, setDrawControls } from "./edit.js";

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
  let diffState = null; // GEO-12a: {status, removed, base, target, counts} or null

  // GEO-13: render a point that carries an embedded icon as a real marker
  // (icon served same-origin from the source KMZ); everything else stays a
  // circle. In diff mode colour wins over the icon so the status reads clearly.
  function pointLayer(feature, latlng) {
    const res =
      feature && feature.properties && feature.properties.iconResource;
    if (res && config.resourceUrlBase) {
      const url = `${config.resourceUrlBase}?name=${encodeURIComponent(res)}`;
      return L.marker(latlng, {
        icon: L.icon({
          iconUrl: url,
          iconSize: [28, 28],
          iconAnchor: [14, 14],
          popupAnchor: [0, -12],
        }),
      });
    }
    return pointToLayer(feature, latlng);
  }

  function makeLayer(item, color) {
    const style = color
      ? () => ({ color, weight: 3, fillOpacity: 0.15 })
      : pathStyle;
    const pt = color
      ? (_f, latlng) =>
          L.circleMarker(latlng, { radius: 5, color, weight: 2, fillOpacity: 0.6 })
      : pointLayer;
    const layer = L.geoJSON(toGeoJSON(item), { style, pointToLayer: pt });
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

    if (diffState) {
      renderDiff();
      return;
    }

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

  // ── GEO-12a version diff ─────────────────────────────────────────────────
  const diffEl = document.getElementById("geo-diff");

  function renderDiff() {
    const layers = [];
    for (const item of diffState.target.values()) {
      const st = diffState.status.get(item.uid) || "unchanged";
      const layer = makeLayer(item, DIFF_COLORS[st]);
      layer.bindPopup(() => buildPopup(item, labels));
      layer.addTo(map);
      renderedLayers.push(layer);
      layers.push(layer);
    }
    for (const uid of diffState.removed) {
      const item = diffState.base.get(uid);
      if (!item) {
        continue;
      }
      const layer = makeLayer(item, DIFF_COLORS.removed);
      layer.bindPopup(() => buildPopup(item, labels));
      layer.addTo(map);
      renderedLayers.push(layer);
      layers.push(layer);
    }
    if (panelEl) {
      buildDiffLegend(panelEl);
    }
    fitOnce(layers);
    setStatus(statusEl, "");
  }

  function buildDiffLegend(container) {
    container.replaceChildren();
    const head = document.createElement("div");
    head.className = "geo-panel-head";
    head.textContent = labels.compare || "Compare";
    container.appendChild(head);
    const rows = [
      ["added", labels.diffAdded || "Added", diffState.counts.added],
      ["changed", labels.diffChanged || "Changed", diffState.counts.changed],
      ["removed", labels.diffRemoved || "Removed", diffState.counts.removed],
    ];
    for (const [key, text, count] of rows) {
      const row = document.createElement("div");
      row.className = "geo-panel-row";
      const dot = document.createElement("span");
      dot.className = "geo-diff-dot";
      dot.style.background = DIFF_COLORS[key];
      const label = document.createElement("span");
      label.className = "geo-panel-label";
      label.textContent = text;
      const num = document.createElement("span");
      num.className = "geo-panel-count";
      num.textContent = String(count);
      row.append(dot, label, num);
      container.appendChild(row);
    }
  }

  function versionSelect(defaultIndex) {
    const select = document.createElement("select");
    select.className = "form-select form-select-sm geo-diff-select";
    config.versions.forEach((v, i) => {
      const opt = document.createElement("option");
      opt.value = v.url;
      opt.textContent = `v${v.number}`;
      if (i === defaultIndex) {
        opt.selected = true;
      }
      select.appendChild(opt);
    });
    return select;
  }

  async function enterDiff(aUrl, bUrl) {
    if (aUrl === bUrl) {
      return;
    }
    setStatus(statusEl, labels.loading);
    let aDoc;
    let bDoc;
    try {
      [aDoc, bDoc] = await Promise.all([fetchCanonical(aUrl), fetchCanonical(bUrl)]);
    } catch (err) {
      setStatus(statusEl, labels.error);
      return;
    }
    diffState = diffDocuments(aDoc, bDoc);
    if (editable) {
      setDrawControls(map, false);
    }
    fittedOnce = false;
    render();
    buildDiffBar();
  }

  function exitDiff() {
    diffState = null;
    if (editable) {
      setDrawControls(map, true);
    }
    fittedOnce = false;
    render();
    buildDiffBar();
  }

  function buildDiffBar() {
    if (!diffEl || !config.versions || config.versions.length < 2) {
      return;
    }
    diffEl.replaceChildren();
    if (diffState) {
      const exit = document.createElement("button");
      exit.type = "button";
      exit.className = "btn btn-sm btn-outline-secondary";
      exit.textContent = labels.diffExit || "Exit comparison";
      exit.addEventListener("click", exitDiff);
      diffEl.appendChild(exit);
      return;
    }
    // Default: compare the second-newest (index 1) against the newest (index 0).
    const selA = versionSelect(1);
    const selB = versionSelect(0);
    const arrow = document.createElement("span");
    arrow.textContent = "↔";
    const cmp = document.createElement("button");
    cmp.type = "button";
    cmp.className = "btn btn-sm btn-outline-secondary";
    cmp.textContent = labels.compare || "Compare";
    cmp.addEventListener("click", () => enterDiff(selA.value, selB.value));
    diffEl.append(selA, arrow, selB, cmp);
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
  buildDiffBar();
}

init();
