/* layout.js -- force-directed placement.
 *
 * Owns node positions and nothing else: no DOM, no colour, no selection. Give it
 * nodes and edges, call tick() until it cools, read x/y.
 *
 * ponytail: repulsion is a naive O(n^2) sweep. At 109 nodes that is ~6k pairs a
 * frame, which is free. Swap in Barnes-Hut only if this ever passes ~1000 nodes.
 */
(function (FMO) {
  'use strict';

  var CFG = {
    repel: 4200,      // node-node inverse-square push
    repelCut: 300,    // ...ignored past this, so clusters form instead of one blob
    springSub: 58,    // rest length: subClassOf pulls tight, it is the skeleton
    springRel: 150,   // rest length: relations hold further apart
    stiffSub: 0.08,
    stiffRel: 0.02,
    gravity: 0.019,   // pull toward origin so leaves do not stream off the edge
    damp: 0.85,
    maxV: 20,
    minDist: 12
  };

  var nodes = [], edges = [], adjacency = {};

  function seed(ns, es) {
    nodes = ns;
    edges = es;

    // Seed on a golden-angle spiral: deterministic (so the map is the same every
    // load) and already roughly evenly spread, which shortens the settle.
    var golden = Math.PI * (3 - Math.sqrt(5));
    nodes.forEach(function (n, i) {
      var r = 26 * Math.sqrt(i + 1);
      n.x = Math.cos(i * golden) * r;
      n.y = Math.sin(i * golden) * r;
      n.vx = n.vy = 0;
      n.pinned = false;
    });

    adjacency = {};
    edges.forEach(function (e) {
      (adjacency[e.s] || (adjacency[e.s] = [])).push(e);
      // A symmetric relation is one edge, not two: pushing both ends of a
      // self-loop would list it twice in the panel.
      if (e.t !== e.s) (adjacency[e.t] || (adjacency[e.t] = [])).push(e);
    });

    var byId = {};
    nodes.forEach(function (n) { byId[n.id] = n; });
    edges.forEach(function (e) { e.a = byId[e.s]; e.b = byId[e.t]; });
  }

  function tick(alpha) {
    var i, j, a, b, dx, dy, d2, d, f;

    var cut2 = CFG.repelCut * CFG.repelCut;
    for (i = 0; i < nodes.length; i++) {
      a = nodes[i];
      for (j = i + 1; j < nodes.length; j++) {
        b = nodes[j];
        dx = b.x - a.x;
        dy = b.y - a.y;
        d2 = dx * dx + dy * dy;
        if (d2 > cut2) continue;
        if (d2 < 1) { dx = (i % 7) - 3; dy = (j % 7) - 3; d2 = dx * dx + dy * dy + 1; }
        d = Math.sqrt(d2);
        f = (CFG.repel / d2) * alpha;
        dx /= d; dy /= d;
        a.vx -= dx * f; a.vy -= dy * f;
        b.vx += dx * f; b.vy += dy * f;
      }
    }

    for (i = 0; i < edges.length; i++) {
      var e = edges[i];
      if (!e.a || !e.b || e.a === e.b) continue;
      var rest = e.k === 'sub' ? CFG.springSub : CFG.springRel;
      var stiff = e.k === 'sub' ? CFG.stiffSub : CFG.stiffRel;
      dx = e.b.x - e.a.x;
      dy = e.b.y - e.a.y;
      d = Math.sqrt(dx * dx + dy * dy) || CFG.minDist;
      f = (d - rest) * stiff * alpha;
      dx = (dx / d) * f; dy = (dy / d) * f;
      e.a.vx += dx; e.a.vy += dy;
      e.b.vx -= dx; e.b.vy -= dy;
    }

    for (i = 0; i < nodes.length; i++) {
      a = nodes[i];
      if (a.pinned) { a.vx = a.vy = 0; continue; }
      a.vx -= a.x * CFG.gravity * alpha;
      a.vy -= a.y * CFG.gravity * alpha;
      a.vx *= CFG.damp;
      a.vy *= CFG.damp;
      var v = Math.hypot(a.vx, a.vy);
      if (v > CFG.maxV) { a.vx = (a.vx / v) * CFG.maxV; a.vy = (a.vy / v) * CFG.maxV; }
      a.x += a.vx;
      a.y += a.vy;
    }
  }

  /** Run the simulation to rest without painting -- used for reduced motion. */
  function settle(steps) {
    for (var i = 0; i < steps; i++) tick(1 - i / steps);
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

  FMO.layout = {
    config: CFG,
    seed: seed,
    tick: tick,
    settle: settle,
    neighbours: neighbours,
    extent: extent
  };
})(window.FMO);
