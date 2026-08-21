/* main.js -- wiring only.
 *
 * data.js -> layout -> graph -> ui. Nothing else reaches across those seams, so a
 * new feature usually lands in exactly one of them.
 */
(function (FMO) {
  'use strict';

  var calm = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var alpha = 1, running = true, fitted = false;

  function select(node) {
    FMO.graph.setFocus(node);
    FMO.ui.show(node);
    document.getElementById('reset').hidden = !node;
  }

  function start() {
    FMO.layout.seed(FMO.nodes, FMO.edges);

    FMO.graph.build(document.getElementById('svg'), FMO, {
      select: select,
      // graph reports every camera move it makes on the user's behalf -- zoom, and
      // the centring that search and the panel links ask for.
      moved: function () { fitted = true; },
      disturb: function () {
        alpha = Math.max(alpha, 0.28);
        if (!running) { running = true; requestAnimationFrame(loop); }
      }
    });

    FMO.ui.init(FMO, { select: select });

    // Any deliberate camera move ends the opening fit; it must not fight the user.
    ['pointerdown', 'wheel'].forEach(function (ev) {
      document.getElementById('svg')
        .addEventListener(ev, function () { fitted = true; }, { capture: true, passive: true });
    });

    document.getElementById('reset').addEventListener('click', function () {
      select(null);
      FMO.graph.fit();
    });

    if (calm) {
      // No settling animation: run the simulation cold, then paint the result.
      FMO.layout.settle(320);
      FMO.graph.fit();
      return;
    }

    // The opening move: the map spreads from its seed spiral while the camera
    // tracks it, so the whole graph stays in frame as it finds its shape.
    FMO.graph.fit();
    requestAnimationFrame(loop);
  }

  function loop() {
    FMO.layout.tick(alpha);
    if (!fitted) FMO.graph.fit();
    else FMO.graph.paint();
    alpha *= 0.986;
    // Stop rather than re-arm: an idle tab should not wake every frame. disturb
    // starts it again.
    if (alpha < 0.012) { running = false; alpha = 0.012; return; }
    requestAnimationFrame(loop);
  }

  window.addEventListener('resize', function () {
    if (!document.getElementById('reset').hidden) return;
    FMO.graph.fit();
  });

  document.addEventListener('keydown', function (ev) {
    if (ev.key === '/' && document.activeElement.id !== 'search') {
      ev.preventDefault();
      document.getElementById('search').focus();
    }
    if (ev.key === 'Escape' && document.activeElement.id !== 'search') select(null);
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }

  // Hand the camera back to the user once the layout has stopped moving much.
  // One last fit to frame the settled shape -- unless they have already moved it.
  if (!calm) {
    setTimeout(function () {
      if (!fitted) { FMO.graph.fit(); fitted = true; }
    }, 2200);
  }
})(window.FMO);
