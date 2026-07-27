// GEO-7 read-only map island entry point.
//
// The page shell (header, versions, source file) is server-rendered; this
// module is the interactive map only. Config arrives via json_script; the
// canonical document is fetched from the read API. No business rules here --
// deleting this file would leave the data and its guarantees intact.

import { fetchCanonical } from "./api.js";
import { collectFeatures, groupByFolder, toGeoJSON } from "./doc.js";
import { createMap } from "./map.js";
import { buildPanel } from "./panel.js";
import { buildPopup } from "./inspector.js";

const STROKE = "#0f9f95";
const pathStyle = () => ({ color: STROKE, weight: 2, fillOpacity: 0.2 });
const pointToLayer = (_feature, latlng) =>
  L.circleMarker(latlng, {
    radius: 5,
    color: STROKE,
    weight: 2,
    fillOpacity: 0.6,
  });

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

  const items = collectFeatures(doc);
  const groups = groupByFolder(items, labels.untitled || "—");
  const panelGroups = new Map();
  const allLayers = [];

  for (const [name, groupItems] of groups) {
    const group = L.layerGroup();
    for (const item of groupItems) {
      const layer = L.geoJSON(toGeoJSON(item), {
        style: pathStyle,
        pointToLayer,
      });
      layer.bindPopup(() => buildPopup(item, labels));
      layer.addTo(group);
      allLayers.push(layer);
    }
    group.addTo(map);
    panelGroups.set(name, { group, count: groupItems.length });
  }

  if (allLayers.length) {
    const bounds = L.featureGroup(allLayers).getBounds();
    if (bounds.isValid()) {
      map.fitBounds(bounds, { padding: [24, 24], maxZoom: 17 });
    }
  }

  if (panelEl) {
    buildPanel(panelEl, panelGroups, map, labels);
  }
  setStatus(statusEl, items.length ? "" : labels.empty);
}

init();
