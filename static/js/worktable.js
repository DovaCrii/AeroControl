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

  /* `UX-09`: el selector de columnas, y aplicarlas.
   *
   * **La identidad de la columna viaja del `<th data-col>` a cada celda por
   * posición**, igual que el rótulo de `UX-10`. Es lo que permite esconder una
   * columna sin tocar ninguno de los dieciséis parciales de filas: la
   * alternativa era escribir `data-col` en cada `<td>`, con el mismo problema de
   * duplicación que ya se descartó ahí.
   *
   * El menú se llena **leyendo el encabezado**, no una segunda lista declarada
   * en la plantilla. Dos listas es cómo el selector y la tabla terminan
   * discrepando.
   */
  var COL_ATTR = "data-col";

  function columnsOf(table) {
    return [].map.call(table.querySelectorAll("thead th"), function (th) {
      return th.getAttribute(COL_ATTR) || "";
    });
  }

  function stampColumns(table) {
    var keys = columnsOf(table);
    if (!keys.length) return;
    [].forEach.call(table.querySelectorAll("tbody tr"), function (row) {
      [].forEach.call(row.children, function (cell, index) {
        // Igual que con el rótulo: una celda que abarca varias columnas no
        // pertenece a ninguna, y marcarla con la primera la escondería entera
        // -- justo la fila de "sin resultados", que es la que hay que ver.
        if (cell.colSpan > 1) return;
        if (keys[index]) cell.setAttribute(COL_ATTR, keys[index]);
      });
    });
  }

  function applyHidden(table, hidden) {
    // El estado vivo se devuelve al atributo, y no es cosmético: htmx reemplaza
    // `#table-body` al paginar, y si el atributo siguiera con el valor que trajo
    // el servidor, la columna que alguien acaba de esconder reaparecería en la
    // página 2 -- y quien la escondió no entendería por qué.
    table.dataset.hiddenColumns = hidden.join(",");
    stampColumns(table);
    [].forEach.call(table.querySelectorAll("[" + COL_ATTR + "]"), function (cell) {
      cell.hidden = hidden.indexOf(cell.getAttribute(COL_ATTR)) !== -1;
    });
    // El cuerpo esperaba escondido para no mostrar un salto; ya se puede ver.
    table.classList.remove("wt-pending");
  }

  function hiddenOf(table) {
    return (table.dataset.hiddenColumns || "")
      .split(",")
      .filter(function (key) {
        return key;
      });
  }

  function persist(key, hidden) {
    var token = document.querySelector("[name=csrfmiddlewaretoken]");
    if (!token) return;
    var body = new FormData();
    body.append("csrfmiddlewaretoken", token.value);
    body.append("list_key", key);
    hidden.forEach(function (one) {
      body.append("hidden", one);
    });
    // Sin `catch` visible: esconder una columna es una comodidad, y una alerta
    // de red por ella interrumpiría el trabajo para avisar de nada importante.
    // Lo que se pierde es que la preferencia no sobreviva a la recarga.
    fetch("/listas/columnas/", { method: "POST", body: body }).catch(function () {});
  }

  function columnPicker() {
    var bar = document.querySelector(".worktable-toolbar");
    var table = document.querySelector("#table-wrapper table");
    if (!bar || !table) return;
    var picker = bar.querySelector(".worktable-columns");
    var menu = bar.querySelector(".worktable-columns-menu");
    if (!picker || !menu) return;

    var hidden = hiddenOf(table);
    applyHidden(table, hidden);

    var any = false;
    [].forEach.call(table.querySelectorAll("thead th[" + COL_ATTR + "]"), function (th) {
      var key = th.getAttribute(COL_ATTR);
      var row = document.createElement("label");
      row.className = "form-check worktable-column-option";
      var input = document.createElement("input");
      input.type = "checkbox";
      input.className = "form-check-input";
      input.checked = hidden.indexOf(key) === -1;
      input.addEventListener("change", function () {
        var at = hidden.indexOf(key);
        if (input.checked && at !== -1) hidden.splice(at, 1);
        if (!input.checked && at === -1) hidden.push(key);
        applyHidden(table, hidden);
        persist(bar.dataset.listKey, hidden);
      });
      row.appendChild(input);
      // El rótulo sale del propio encabezado, así que no puede discrepar con lo
      // que la columna dice. `textContent` y no `innerHTML`: el `<th>` lleva la
      // flechita de orden, y copiarla acá pondría una flecha en cada casilla.
      row.appendChild(document.createTextNode(" " + th.textContent.trim()));
      menu.appendChild(row);
      any = true;
    });
    // Sin ninguna columna con nombre no hay nada que ofrecer, y un menú vacío es
    // peor que ningún menú.
    picker.hidden = !any;

    // `UX-12`: el formulario de guardar vista lleva el filtro que la persona
    // está mirando **y** sus columnas, para que volver a la vista devuelva lo
    // que guardó y no la mitad.
    var form = bar.querySelector(".worktable-save-menu");
    if (form) {
      form.addEventListener("submit", function () {
        var field = form.querySelector("[data-worktable-query]");
        if (field) field.value = window.location.search;
        [].forEach.call(form.querySelectorAll("[data-worktable-hidden]"), function (old) {
          old.remove();
        });
        hidden.forEach(function (one) {
          var input = document.createElement("input");
          input.type = "hidden";
          input.name = "hidden";
          input.value = one;
          input.setAttribute("data-worktable-hidden", "1");
          form.appendChild(input);
        });
      });
    }
  }

  run(document);
  wire(document);
  columnPicker();
  // htmx reemplaza `#table-body` al paginar y al filtrar; sin esto las filas
  // nuevas llegarían sin rótulo y sin casilla.
  document.body.addEventListener("htmx:afterSwap", function (event) {
    var table = event.target.closest ? event.target.closest("table") : null;
    if (table) {
      label(table);
      // Las filas nuevas llegan sin `data-col`, así que una columna escondida
      // reaparecería al paginar -- y quien la escondió no entendería por qué.
      applyHidden(table, hiddenOf(table));
      // La tabla ya tiene su columna, pero las filas nuevas no: se rehace.
      table.dataset.bulkReady = "";
      selectable(table);
    } else {
      run(event.target);
      wire(event.target);
    }
  });
})();
