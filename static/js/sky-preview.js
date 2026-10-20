/* LV-356: vista previa de 24 h de la escena del cielo (tarjeta del tiempo).
 *
 * Al pasar el puntero o enfocar la cabecera de la tarjeta se recorre el día entero en unos segundos
 * (fase, sol, luna) y al salir vuelve a la hora real. Sólo con movimiento permitido: con
 * `prefers-reduced-motion: reduce` no hace nada y la escena queda quieta y completa. Sin red y sin
 * dependencias; si falta este script la escena funciona igual. La tarjeta llega por htmx, así que
 * los eventos se escuchan en `document`. Las fases repiten las de `apps/weather/sky.py`
 * (amanecer -45 min a +60 min, mediodía ±90 min de la mitad del día, atardecer 60 min antes de la
 * puesta, crepúsculo 45 min después); aquí sólo son una aproximación para la vista previa.
 */
(function () {
  "use strict";

  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)");
  var DURATION = 7000; // ms que dura el recorrido de 24 h
  var active = null; // { head, frame, started, from, done }

  function allowed() {
    return !(reduce && reduce.matches) && "requestAnimationFrame" in window;
  }

  function phaseFor(t, sr, ss) {
    var noon = (sr + ss) / 2;
    if (t < sr - 0.75 || t >= ss + 0.75) return "night";
    if (t < sr + 1) return "dawn";
    if (t < noon - 1.5) return "morning";
    if (t < noon + 1.5) return "midday";
    if (t < ss - 1) return "afternoon";
    if (t < ss) return "sunset";
    return "twilight";
  }

  function arc(p) {
    p = Math.min(1, Math.max(0, p));
    return [40 + 560 * p, 120 - 90 * Math.sin(Math.PI * p)];
  }

  function place(node, p) {
    if (!node) return;
    var xy = arc(p);
    node.setAttribute("transform", "translate(" + xy[0].toFixed(1) + " " + xy[1].toFixed(1) + ")");
  }

  function paint(head, hour) {
    var sr = parseFloat(head.getAttribute("data-sr"));
    var ss = parseFloat(head.getAttribute("data-ss"));
    if (!isFinite(sr) || !isFinite(ss) || ss <= sr) return;
    var t = ((hour % 24) + 24) % 24;
    var scene = head.querySelector(".sky-scene");
    var phase = phaseFor(t, sr, ss);
    if (head.getAttribute("data-sky") !== phase) head.setAttribute("data-sky", phase);
    if (!scene) return;
    var sunUp = t >= sr && t < ss;
    scene.setAttribute("data-sun", sunUp ? "on" : "off");
    scene.setAttribute("data-moon", sunUp ? "off" : "on");
    place(scene.querySelector(".sky-sun-wrap"), (t - sr) / (ss - sr));
    var span = sr + 24 - ss;
    var sinceSunset = t >= ss ? t - ss : t + 24 - ss;
    place(scene.querySelector(".sky-moon-wrap"), sinceSunset / span);
  }

  function snapshot(head) {
    var scene = head.querySelector(".sky-scene");
    var sun = scene && scene.querySelector(".sky-sun-wrap");
    var moon = scene && scene.querySelector(".sky-moon-wrap");
    return {
      phase: head.getAttribute("data-sky"),
      sunOn: scene && scene.getAttribute("data-sun"),
      moonOn: scene && scene.getAttribute("data-moon"),
      sun: sun && sun.getAttribute("transform"),
      moon: moon && moon.getAttribute("transform"),
    };
  }

  function restore(head, saved) {
    var scene = head.querySelector(".sky-scene");
    if (saved.phase) head.setAttribute("data-sky", saved.phase);
    if (!scene) return;
    if (saved.sunOn) scene.setAttribute("data-sun", saved.sunOn);
    if (saved.moonOn) scene.setAttribute("data-moon", saved.moonOn);
    var sun = scene.querySelector(".sky-sun-wrap");
    var moon = scene.querySelector(".sky-moon-wrap");
    if (sun && saved.sun) sun.setAttribute("transform", saved.sun);
    if (moon && saved.moon) moon.setAttribute("transform", saved.moon);
  }

  function stop() {
    if (!active) return;
    window.cancelAnimationFrame(active.frame);
    active.head.classList.remove("is-previewing");
    if (active.head.isConnected) restore(active.head, active.saved);
    active = null;
  }

  function start(head) {
    if (!allowed() || (active && active.head === head)) return;
    stop();
    var from = parseFloat(head.getAttribute("data-hour"));
    if (!isFinite(from)) return;
    active = { head: head, saved: snapshot(head), frame: 0, started: null, from: from };
    head.classList.add("is-previewing");
    function step(now) {
      if (!active || active.head !== head || !head.isConnected) return;
      if (active.started === null) active.started = now;
      var progress = (now - active.started) / DURATION;
      if (progress >= 1) {
        stop(); // un recorrido completo y vuelve a la hora real
        return;
      }
      paint(head, active.from + progress * 24);
      active.frame = window.requestAnimationFrame(step);
    }
    active.frame = window.requestAnimationFrame(step);
  }

  function headOf(event) {
    var target = event.target;
    return target && target.closest ? target.closest(".wx-head--sky[data-sr]") : null;
  }

  document.addEventListener("mouseover", function (event) {
    var head = headOf(event);
    if (head) start(head);
  });
  document.addEventListener("mouseout", function (event) {
    var head = headOf(event);
    if (!head || (event.relatedTarget && head.contains(event.relatedTarget))) return;
    if (active && active.head === head) stop();
  });
  document.addEventListener("focusin", function (event) {
    var head = headOf(event);
    if (head) start(head);
  });
  document.addEventListener("focusout", function (event) {
    var head = headOf(event);
    if (!head || (event.relatedTarget && head.contains(event.relatedTarget))) return;
    if (active && active.head === head) stop();
  });
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") stop();
  });
  document.addEventListener("htmx:beforeSwap", stop);
})();
