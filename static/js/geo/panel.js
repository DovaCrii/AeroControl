// Layer panel (GEO-7 viewer + GEO-11 editor tree).
//
// Read-only: a flat, per-folder-group visibility list (unchanged behaviour).
// Editable: a nested tree that mirrors doc.children, with per-node visibility,
// drag-and-drop to reorder / move between folders, and Duplicate / Explode
// actions. Built entirely with DOM APIs (createElement + textContent, no
// innerHTML, no inline handlers) so it stays CSP-safe and cannot inject markup
// from feature names.

export function buildPanel(container, groups, map, labels) {
  container.replaceChildren();

  const heading = document.createElement("div");
  heading.className = "geo-panel-head";
  heading.textContent = `${labels.layers} · ${labels.features}`;
  container.appendChild(heading);

  for (const [name, layer] of groups) {
    const row = document.createElement("label");
    row.className = "geo-panel-row";

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = true;
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) {
        layer.group.addTo(map);
      } else {
        map.removeLayer(layer.group);
      }
    });

    const text = document.createElement("span");
    text.className = "geo-panel-label";
    text.textContent = name;

    const count = document.createElement("span");
    count.className = "geo-panel-count";
    count.textContent = String(layer.count);

    row.append(checkbox, text, count);
    container.appendChild(row);
  }
}

// ── GEO-11 editable layer tree ─────────────────────────────────────────────
// opts: {
//   map, uidLayers: Map(uid -> leaflet layer|null for folders/empty),
//   labels, activeFolderUid, hidden: Set(uid),
//   onMove(uid, targetFolderUid, index), onDuplicate(uid), onExplode(uid),
//   onSelectFolder(uid|null), onToggle(uid, visible)
// }
export function buildTree(container, doc, opts) {
  container.replaceChildren();

  // Which node is being dragged (shared by every row's drop handler).
  let dragUid = null;

  function wireDrag(rowEl, uid) {
    rowEl.draggable = true;
    rowEl.addEventListener("dragstart", (e) => {
      dragUid = uid;
      e.dataTransfer.effectAllowed = "move";
      rowEl.classList.add("is-dragging");
    });
    rowEl.addEventListener("dragend", () => {
      dragUid = null;
      rowEl.classList.remove("is-dragging");
    });
  }

  // `doMove(dragUid)` runs on a valid drop; the element highlights while a drag
  // hovers it.
  function wireDropTarget(el, doMove) {
    el.addEventListener("dragover", (e) => {
      if (dragUid) {
        e.preventDefault();
        el.classList.add("is-drop");
      }
    });
    el.addEventListener("dragleave", () => el.classList.remove("is-drop"));
    el.addEventListener("drop", (e) => {
      e.preventDefault();
      el.classList.remove("is-drop");
      if (dragUid) {
        doMove(dragUid);
      }
    });
  }

  const head = document.createElement("div");
  head.className = "geo-panel-head";
  head.textContent = opts.labels.layers || "Layers";
  container.appendChild(head);

  // Root drop target: dropping here moves a node to the document root (end),
  // and clicking selects the root as the active folder for new features.
  const rootDrop = document.createElement("div");
  rootDrop.className = "geo-tree-root";
  rootDrop.textContent = opts.labels.rootDrop || "▸ /";
  if (opts.activeFolderUid == null) {
    rootDrop.classList.add("is-active");
  }
  rootDrop.addEventListener("click", () => opts.onSelectFolder(null));
  wireDropTarget(rootDrop, (uid) => opts.onMove(uid, null, null));
  container.appendChild(rootDrop);

  const tree = document.createElement("div");
  tree.className = "geo-tree";
  tree._folderUid = null;
  container.appendChild(tree);

  function renderNodes(nodes, parentEl, depth) {
    for (let i = 0; i < (nodes || []).length; i += 1) {
      const node = nodes[i];
      const index = i;
      const parentUid = parentEl._folderUid || null;
      const row = document.createElement("div");
      row.className = `geo-tree-row geo-tree-${node.kind}`;
      row.style.paddingLeft = `${depth * 14 + 4}px`;
      wireDrag(row, node.uid);

      // Drop onto a folder = move into it (append); onto a placemark = insert
      // before it within its parent.
      if (node.kind === "folder") {
        wireDropTarget(row, (uid) => {
          if (uid !== node.uid) {
            opts.onMove(uid, node.uid, null);
          }
        });
      } else {
        wireDropTarget(row, (uid) => {
          if (uid !== node.uid) {
            opts.onMove(uid, parentUid, index);
          }
        });
      }

      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.checked = !opts.hidden.has(node.uid);
      checkbox.title = opts.labels.visible || "Visible";
      checkbox.addEventListener("change", () =>
        opts.onToggle(node.uid, checkbox.checked),
      );

      const text = document.createElement("span");
      text.className = "geo-tree-label";
      const kindMark = node.kind === "folder" ? "📁 " : "";
      text.textContent = kindMark + (node.name || opts.labels.untitled || "—");
      if (node.kind === "folder") {
        text.addEventListener("click", () => opts.onSelectFolder(node.uid));
        if (opts.activeFolderUid === node.uid) {
          row.classList.add("is-active");
        }
      }

      const actions = document.createElement("span");
      actions.className = "geo-tree-actions";
      actions.appendChild(
        actionButton("⧉", opts.labels.duplicate || "Duplicate", () =>
          opts.onDuplicate(node.uid),
        ),
      );
      if (isExplodable(node)) {
        actions.appendChild(
          actionButton("⋔", opts.labels.explode || "Split", () =>
            opts.onExplode(node.uid),
          ),
        );
      }

      row.append(checkbox, text, actions);
      parentEl.appendChild(row);

      if (node.kind === "folder") {
        const childBox = document.createElement("div");
        childBox._folderUid = node.uid;
        parentEl.appendChild(childBox);
        renderNodes(node.children, childBox, depth + 1);
      }
    }
  }

  renderNodes(doc.children, tree, 0);
}

function actionButton(symbol, title, handler) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "geo-tree-btn";
  btn.textContent = symbol;
  btn.title = title;
  btn.setAttribute("aria-label", title);
  btn.addEventListener("click", (e) => {
    e.stopPropagation();
    handler();
  });
  return btn;
}

function isExplodable(node) {
  return (
    node.kind === "placemark" &&
    node.geometry &&
    node.geometry.type === "GeometryCollection" &&
    Array.isArray(node.geometry.geometries) &&
    node.geometry.geometries.length > 1
  );
}
