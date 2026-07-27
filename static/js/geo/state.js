// In-memory editor state for the map island (GEO-8): the canonical document is
// the single source of truth; Leaflet layers are a view over it. Undo/redo is a
// capped stack of structuredClone snapshots — one entry per completed gesture.
// No business rules here; the server re-validates every commit.

const MAX_HISTORY = 50;

export class EditorState {
  constructor(doc) {
    this.doc = doc;
    this._baseline = JSON.stringify(doc); // to detect dirtiness cheaply
    this._undo = [];
    this._redo = [];
  }

  get dirty() {
    return JSON.stringify(this.doc) !== this._baseline;
  }

  // Call AFTER mutating this.doc, to record the new state for undo.
  snapshot() {
    this._undo.push(structuredClone(this.doc));
    if (this._undo.length > MAX_HISTORY) {
      this._undo.shift();
    }
    this._redo.length = 0;
  }

  // Mark the current document as the saved baseline (after a successful commit).
  markSaved() {
    this._baseline = JSON.stringify(this.doc);
  }

  canUndo() {
    return this._undo.length > 1;
  }

  canRedo() {
    return this._redo.length > 0;
  }

  undo() {
    if (!this.canUndo()) {
      return false;
    }
    this._redo.push(this._undo.pop());
    this.doc = structuredClone(this._undo[this._undo.length - 1]);
    return true;
  }

  redo() {
    if (!this.canRedo()) {
      return false;
    }
    const next = this._redo.pop();
    this._undo.push(next);
    this.doc = structuredClone(next);
    return true;
  }

  // Seed the undo stack with the initial state so the first snapshot() has a
  // predecessor to undo back to.
  seed() {
    this._undo = [structuredClone(this.doc)];
    this._redo = [];
  }
}
