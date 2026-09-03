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

  run(document);
  // htmx reemplaza `#table-body` al paginar y al filtrar; sin esto las filas
  // nuevas llegarían sin rótulo y la tarjeta se vería a medias.
  document.body.addEventListener("htmx:afterSwap", function (event) {
    var table = event.target.closest ? event.target.closest("table") : null;
    if (table) label(table);
    else run(event.target);
  });
})();
