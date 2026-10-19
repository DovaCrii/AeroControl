/* LV-330 (ola G): el menú «⋯» de cada fila (`generic/_row_menu.html`).
 *
 * El `<details>` ya abre y cierra sin JS; esto sólo le suma lo que un menú debe tener:
 * Esc cierra y devuelve el foco, las flechas se mueven entre entradas, un clic fuera
 * lo cierra, y abrir uno cierra el que estuviera abierto. Además lo saca del flujo con
 * `position: fixed`: dentro de `.table-responsive` y `.card` (overflow) un menú absoluto
 * se recortaría en las últimas filas. Sin JS queda absoluto y sigue siendo usable.
 */
(function () {
  "use strict";

  var SELECTOR = "details.id-rowmenu";

  function items(menu) {
    return [].slice.call(menu.querySelectorAll(".id-rowmenu-item"));
  }

  function place(menu) {
    var list = menu.querySelector(".id-rowmenu-list");
    var summary = menu.querySelector("summary");
    if (!list || !summary) return;
    var box = summary.getBoundingClientRect();
    list.classList.add("is-floating");
    var width = list.offsetWidth;
    var left = Math.max(8, Math.min(box.right - width, window.innerWidth - width - 8));
    var top = box.bottom + 4;
    if (top + list.offsetHeight > window.innerHeight - 8) {
      top = Math.max(8, box.top - list.offsetHeight - 4);
    }
    list.style.left = left + "px";
    list.style.top = top + "px";
  }

  function unplace(menu) {
    var list = menu.querySelector(".id-rowmenu-list");
    if (!list) return;
    list.classList.remove("is-floating");
    list.style.left = "";
    list.style.top = "";
  }

  function closeAll(except) {
    [].forEach.call(document.querySelectorAll(SELECTOR + "[open]"), function (menu) {
      if (menu !== except) menu.removeAttribute("open");
    });
  }

  document.addEventListener(
    "toggle",
    function (event) {
      var menu = event.target;
      if (!menu.matches || !menu.matches(SELECTOR)) return;
      if (menu.open) {
        closeAll(menu);
        place(menu);
      } else {
        unplace(menu);
      }
    },
    true
  );

  document.addEventListener("click", function (event) {
    if (!event.target.closest(SELECTOR)) closeAll(null);
  });

  document.addEventListener("keydown", function (event) {
    var menu = event.target.closest && event.target.closest(SELECTOR);
    if (!menu || !menu.open) return;
    var summary = menu.querySelector("summary");
    if (event.key === "Escape") {
      menu.removeAttribute("open");
      if (summary) summary.focus();
      event.preventDefault();
      return;
    }
    var all = items(menu);
    if (!all.length) return;
    var at = all.indexOf(document.activeElement);
    var next = null;
    if (event.key === "ArrowDown") next = all[(at + 1) % all.length];
    else if (event.key === "ArrowUp") next = all[(at <= 0 ? all.length : at) - 1];
    else if (event.key === "Home") next = all[0];
    else if (event.key === "End") next = all[all.length - 1];
    if (next) {
      next.focus();
      event.preventDefault();
    }
  });

  /* Un menú flotante no sigue a su fila: al desplazar o redimensionar se cierra. */
  function dismiss() {
    closeAll(null);
  }
  window.addEventListener("resize", dismiss);
  window.addEventListener("scroll", dismiss, true);
})();
