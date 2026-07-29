// Set the colour theme before first paint to avoid a flash of the wrong theme.
// Extracted from an inline <script> so the page needs no 'unsafe-inline' in the
// Content-Security-Policy (MASTER_PLAN V.10). Must stay render-blocking in the
// document <head>.
(function () {
  var t = localStorage.getItem('theme');
  if (!t) {
    t = window.matchMedia('(prefers-color-scheme:dark)').matches ? 'dark' : 'light';
  }
  var h = document.documentElement;
  h.setAttribute('data-theme', t);
  h.setAttribute('data-bs-theme', t);
})();
