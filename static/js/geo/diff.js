// GEO-12a: compare two canonical documents by uid. Placemark-level, since only
// placemarks render on the map. Pure — no DOM, no network. uids are stable
// across versions once committed (import keeps them, restore copies content
// verbatim), so identity by uid is meaningful.

import { collectFeatures } from "./doc.js";

function indexByUid(doc) {
  const map = new Map();
  collectFeatures(doc).forEach((item) => map.set(item.uid, item));
  return map;
}

function sameGeometry(a, b) {
  return JSON.stringify(a) === JSON.stringify(b);
}

// Returns { status: Map(uid -> "added"|"changed"|"moved"|"unchanged"),
//           removed: [uid], base: Map(uid->item), target: Map(uid->item),
//           counts: {added, removed, changed, unchanged} }.
export function diffDocuments(base, target) {
  const b = indexByUid(base);
  const t = indexByUid(target);
  const status = new Map();

  for (const [uid, tv] of t) {
    if (!b.has(uid)) {
      status.set(uid, "added");
      continue;
    }
    const bv = b.get(uid);
    const changed =
      !sameGeometry(bv.geometry, tv.geometry) ||
      bv.name !== tv.name ||
      bv.description !== tv.description;
    const moved = bv.folderPath.join("/") !== tv.folderPath.join("/");
    status.set(uid, changed ? "changed" : moved ? "moved" : "unchanged");
  }

  const removed = [];
  for (const uid of b.keys()) {
    if (!t.has(uid)) {
      removed.push(uid);
    }
  }

  let added = 0;
  let changed = 0;
  let unchanged = 0;
  for (const s of status.values()) {
    if (s === "added") added += 1;
    else if (s === "changed" || s === "moved") changed += 1;
    else unchanged += 1;
  }

  return {
    status,
    removed,
    base: b,
    target: t,
    counts: { added, removed: removed.length, changed, unchanged },
  };
}

// Map a per-uid diff status to a colour role used by the map and the legend.
export const DIFF_COLORS = {
  added: "#22a06b",
  removed: "#e5484d",
  changed: "#e08a00",
  moved: "#e08a00",
  unchanged: "#8a94a6",
};
