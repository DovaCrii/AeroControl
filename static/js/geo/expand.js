// LV-136: "Ampliar" -- la tarjeta del mapa ocupa la ventana entera para dibujar.
//
// Pedido del usuario mirando la ficha: *"evaluar una opción para darle más espacio
// al mapa o ver una opción de utilizar mejor el espacio para editar y trabajar con
// más espacio"*. El alto suelto ya creció con la ventana (CSS), y esto resuelve la
// otra mitad: cuando de verdad se está editando, la pantalla entera.
//
// **Es un estado de la misma tarjeta, no una ventana nueva.** Los controles de
// dibujo, el panel de capas y Deshacer/Rehacer/Guardar siguen siendo los mismos
// elementos del DOM, así que no hay un segundo editor que pueda desincronizarse
// del primero -- que es exactamente el error que cometería un modal con su propia
// copia del mapa.
//
// Lo único que Leaflet exige: `invalidateSize()` después de cambiar el tamaño del
// contenedor. Sin eso el lienzo queda del tamaño viejo, con las teselas cortadas
// y los clics desplazados respecto de lo que se ve.

const EXPANDED = "geo-expanded";
const BODY_OPEN = "geo-expanded-open";

export function installExpand(map, { card, button }) {
  if (!card || !button) {
    return;
  }

  const labels = {
    expand: button.dataset.labelExpand || button.textContent.trim(),
    collapse: button.dataset.labelCollapse || button.textContent.trim(),
  };

  const apply = (expanded) => {
    card.classList.toggle(EXPANDED, expanded);
    document.body.classList.toggle(BODY_OPEN, expanded);
    button.textContent = expanded ? labels.collapse : labels.expand;
    button.setAttribute("aria-pressed", expanded ? "true" : "false");
    // En el siguiente cuadro: la clase ya está aplicada y el contenedor tiene su
    // tamaño nuevo cuando Leaflet lo mide.
    requestAnimationFrame(() => map.invalidateSize());
  };

  button.addEventListener("click", () => {
    apply(!card.classList.contains(EXPANDED));
  });

  // Escape sale, que es lo que la tecla hace en todo lo demás que tapa la
  // pantalla. Sin esto, en modo ampliado no queda ningún elemento de la app a la
  // vista y la única salida visible es el propio botón.
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && card.classList.contains(EXPANDED)) {
      apply(false);
    }
  });
}
