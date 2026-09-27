/* main.js -- wiring only.
 *
 * data.js -> layout -> graph and outline -> ui. Nothing else reaches across those
 * seams, so a new feature usually lands in exactly one of them.
 */
(function (FMO) {
  'use strict';

  function select(node) {
    FMO.graph.setFocus(node);
    FMO.outline.setFocus(node);
    FMO.ui.show(node);
    document.getElementById('reset').hidden = !node;
  }

  function start() {
    // The tree arrives placed; there is nothing to settle, so no opening animation.
    FMO.layout.seed(FMO.nodes, FMO.edges);

    FMO.graph.build(document.getElementById('svg'), FMO, { select: select });

    FMO.outline.build(document.getElementById('outline'), FMO, { select: select });

    FMO.ui.init(FMO, { select: select });

    document.getElementById('reset').addEventListener('click', function () {
      select(null);
      FMO.graph.fit();
    });

    FMO.graph.fit();
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
})(window.FMO);
