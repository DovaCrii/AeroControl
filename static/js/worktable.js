/* `UX-10`: cada fila de tabla se apila como tarjeta bajo 768 px.
 *
 * Medido antes de escribir nada: la lista de aeronaves mide **900 px de tabla
 * dentro de un contenedor de 356** en una pantalla de 390. Leer una fila en
 * faena obliga a arrastrar de lado, con guantes, para volver a empezar en la
 * siguiente.
 *
 * **El rótulo de cada celda lo pone este archivo y no la plantilla**, y ésa es
 * la decisión que hace viable la fila: la alternativa era escribir
 * `data-label="…"` en cada `<td>` de **58 tablas**, un cambio que nadie puede
 * revisar y que además duplicaría cada encabezado —el del `<th>` y el del
 * atributo— para que se separen la primera vez que alguien renombre una
 * columna. Acá el rótulo **se lee del `<th>`**, así que no puede discrepar.
 *
 * Corre también después de cada intercambio de htmx: la paginación y los
 * filtros reemplazan `#table-body` sin recargar, y las filas nuevas llegarían
 * sin rótulo.
 */
(function () {
  "use strict";

  function label(table) {
    var headers = [].map.call(table.querySelectorAll("thead th"), function (th) {
      return th.textContent.trim();
    });
    if (!headers.length) return;

    [].forEach.call(table.querySelectorAll("tbody tr"), function (row) {
      [].forEach.call(row.children, function (cell, index) {
        // Una celda que abarca varias columnas no pertenece a un encabezado:
        // son las filas de agrupación y la de "sin resultados". Rotularlas con
        // el nombre de la primera columna diría algo falso.
        if (cell.colSpan > 1) return;
        var text = headers[index];
        if (!text) return;
        // La columna de acciones son botones: un rótulo delante no agrega nada
        // y le roba la mitad del ancho a la fila más angosta.
        if (cell.querySelector(".btn, button, form")) return;
        cell.setAttribute("data-label", text);
      });
    });
  }

  function run(root) {
    [].forEach.call((root || document).querySelectorAll("table"), label);
  }

  /* `UX-11`: selección explícita por casilla, y la barra que la resume.
   *
   * Las casillas las inyecta este archivo en vez de escribirlas en las
   * plantillas, por lo mismo que los rótulos: alcanza a las listas genéricas
   * sin tocar ninguna. **Sólo donde la fila declara su `data-pk`** — donde no
   * sabe quién es, no se ofrece seleccionar, que es mejor que una casilla que
   * no sabe qué manda.
   *
   * Sin JS no hay casillas ni barra, y la lista funciona como siempre: la
   * selección es una comodidad, no el único camino a exportar.
   */
  var BULK_CLASS = "bulk-cell";

  function bar() {
    return document.getElementById("bulk-bar");
  }

  function selectedIds(body) {
    return [].filter
      .call(body.querySelectorAll("tr[data-pk] ." + BULK_CLASS), function (box) {
        return box.checked;
      })
      .map(function (box) {
        return box.closest("tr").dataset.pk;
      });
  }

  function refresh(body) {
    var strip = bar();
    if (!strip) return;
    var ids = selectedIds(body);
    strip.hidden = ids.length === 0;
    var count = strip.querySelector(".bulk-count");
    // El rótulo lo escribe la plantilla con su plural traducido; acá sólo se
    // sustituye el número, para no armar frases en JS.
    if (count) count.textContent = count.dataset.template.replace("{n}", ids.length);
    var link = strip.querySelector("#bulk-export");
    if (link) {
      var url = new URL(window.location.href);
      url.searchParams.set("export", "csv");
      url.searchParams.delete("ids");
      ids.forEach(function (id) {
        url.searchParams.append("ids", id);
      });
      link.setAttribute("href", url.pathname + url.search);
    }
  }

  function box(checked) {
    var input = document.createElement("input");
    input.type = "checkbox";
    input.className = BULK_CLASS + " form-check-input";
    input.checked = !!checked;
    return input;
  }

  function selectable(table) {
    var body = table.querySelector("tbody");
    if (!body || !body.querySelector("tr[data-pk]")) return;
    if (table.dataset.bulkReady === "1") return;
    table.dataset.bulkReady = "1";

    var head = table.querySelector("thead tr");
    if (head && !head.querySelector("." + BULK_CLASS)) {
      var th = document.createElement("th");
      th.scope = "col";
      var all = box(false);
      all.setAttribute("aria-label", table.dataset.labelSelectAll || "Select all");
      th.appendChild(all);
      head.insertBefore(th, head.firstChild);
      all.addEventListener("change", function () {
        [].forEach.call(body.querySelectorAll("." + BULK_CLASS), function (one) {
          one.checked = all.checked;
        });
        refresh(body);
      });
    }

    [].forEach.call(body.querySelectorAll("tr[data-pk]"), function (row) {
      if (row.querySelector("." + BULK_CLASS)) return;
      var cell = document.createElement("td");
      cell.appendChild(box(false));
      row.insertBefore(cell, row.firstChild);
    });

    body.addEventListener("change", function (event) {
      if (event.target.classList.contains(BULK_CLASS)) refresh(body);
    });
    refresh(body);
  }

  function wire(root) {
    [].forEach.call((root || document).querySelectorAll("table"), selectable);
  }

  var clear = document.getElementById("bulk-clear");
  if (clear) {
    clear.addEventListener("click", function () {
      [].forEach.call(document.querySelectorAll("." + BULK_CLASS), function (one) {
        one.checked = false;
      });
      var body = document.getElementById("table-body");
      if (body) refresh(body);
    });
  }

  run(document);
  wire(document);
  // htmx reemplaza `#table-body` al paginar y al filtrar; sin esto las filas
  // nuevas llegarían sin rótulo y sin casilla.
  document.body.addEventListener("htmx:afterSwap", function (event) {
    var table = event.target.closest ? event.target.closest("table") : null;
    if (table) {
      label(table);
      // La tabla ya tiene su columna, pero las filas nuevas no: se rehace.
      table.dataset.bulkReady = "";
      selectable(table);
    } else {
      run(event.target);
      wire(event.target);
    }
  });
})();
