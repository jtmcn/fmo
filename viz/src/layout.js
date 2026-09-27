/* layout.js -- node positions, and the adjacency the panel reads.
 *
 * Positions are the is-a tree generate_diagram.place() computed: one row per
 * depth from bfo:entity, leaves in reading order, each parent over its children.
 * Computed there rather than simulated here, so diagram-check counts the crossings
 * the page draws. This module only copies them in; no DOM, no colour, no selection.
 */
(function (FMO) {
  'use strict';

  var nodes = [], adjacency = {};

  function seed(ns, es) {
    nodes = ns;
    nodes.forEach(function (n) {
      n.x = n.px || 0;
      n.y = n.py || 0;
    });

    adjacency = {};
    es.forEach(function (e) {
      (adjacency[e.s] || (adjacency[e.s] = [])).push(e);
      // A symmetric relation is one edge, not two: pushing both ends of a
      // self-loop would list it twice in the panel.
      if (e.t !== e.s) (adjacency[e.t] || (adjacency[e.t] = [])).push(e);
    });

    var byId = {};
    nodes.forEach(function (n) { byId[n.id] = n; });
    es.forEach(function (e) { e.a = byId[e.s]; e.b = byId[e.t]; });
  }

  function neighbours(id) { return adjacency[id] || []; }

  function extent() {
    var b = { x0: Infinity, y0: Infinity, x1: -Infinity, y1: -Infinity };
    nodes.forEach(function (n) {
      if (n.hidden) return;
      if (n.x < b.x0) b.x0 = n.x;
      if (n.y < b.y0) b.y0 = n.y;
      if (n.x > b.x1) b.x1 = n.x;
      if (n.y > b.y1) b.y1 = n.y;
    });
    return isFinite(b.x0) ? b : { x0: -300, y0: -300, x1: 300, y1: 300 };
  }

  FMO.layout = { seed: seed, neighbours: neighbours, extent: extent };
})(window.FMO);
