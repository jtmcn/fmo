/* graph.js -- SVG rendering, pan/zoom, hover, drag.
 *
 * Owns the picture. Knows about positions (from layout) and which node is lit,
 * but decides nothing: it reports clicks and hovers through the callbacks passed
 * to init(), and paints whatever state it is handed.
 *
 * To add a visual layer, append a <g> in build() and draw it in paint().
 */
(function (FMO) {
  'use strict';

  var SVGNS = 'http://www.w3.org/2000/svg';
  var COLOR = { fm: 'var(--ink)', wx: 'var(--cold)', ksh: 'var(--warm)', bfo: 'var(--graphite)' };

  var svg, view, layers = {}, on = {};
  var nodes = [], edges = [];
  var cam = { x: 0, y: 0, k: 1 };
  var selected = null, hovered = null, lit = {};
  var drag = null, pan = null;
  var kindOn = { sub: true, rel: true };
  // Profile mode dims rather than hides: the export subgraph is only legible as a
  // shape if the ontology it is cut from stays on the page behind it.
  var profileOnly = false;

  function el(name, attrs) {
    var e = document.createElementNS(SVGNS, name);
    for (var k in attrs) e.setAttribute(k, attrs[k]);
    return e;
  }

  function radius(n) {
    return (n.minted ? 4.6 : 4) + Math.min(Math.sqrt(n.deg || 0) * 2.1, 7.5);
  }

  function color(n) { return COLOR[n.module] || COLOR.bfo; }

  /* In the profile view at all: a shape names this class, or an edge a shape walks
     lands on it. The panel draws the distinction; the picture only needs the union. */
  function inProfile(n) { return !!(n.profile || n.reached); }

  function build(root, data, handlers) {
    svg = root;
    on = handlers || {};
    nodes = data.nodes;
    edges = data.edges;

    view = el('g', {});
    svg.appendChild(view);

    ['grat', 'sub', 'rel', 'elab', 'dot', 'nlab'].forEach(function (name) {
      layers[name] = el('g', { class: name === 'grat' ? 'grat' : '' });
      view.appendChild(layers[name]);
    });

    graticule();

    edges.forEach(function (e) {
      e.el = el('path', { class: e.k === 'sub' ? 'e-sub' : 'e-rel' });
      if (e.k === 'rel') e.el.setAttribute('stroke', color(e.a || { module: 'fm' }));
      layers[e.k].appendChild(e.el);

      if (e.k === 'rel') {
        e.lab = el('text', { class: 'e-lab', fill: color(e.a || { module: 'fm' }) });
        e.lab.textContent = (e.p || '').split(':')[1] || '';
        layers.elab.appendChild(e.lab);
      }
    });

    nodes.forEach(function (n) {
      n.el = el('circle', {
        class: 'n-dot' + (n.minted ? '' : ' is-ext'),
        r: radius(n),
        fill: n.minted ? color(n) : 'var(--paper)',
        stroke: color(n)
      });
      n.el.setAttribute('data-id', n.id);
      layers.dot.appendChild(n.el);

      n.lab = el('text', { class: 'n-lab' });
      n.lab.textContent = n.label;
      layers.nlab.appendChild(n.lab);
    });

    wire();
  }

  /* A faint graticule, drawn once in world space so it pans and zooms with the
     map. Strokes are non-scaling, so it stays hairline at every zoom. */
  function graticule() {
    var S = 120, N = 26;
    for (var i = -N; i <= N; i++) {
      layers.grat.appendChild(el('line', { x1: i * S, y1: -N * S, x2: i * S, y2: N * S }));
      layers.grat.appendChild(el('line', { x1: -N * S, y1: i * S, x2: N * S, y2: i * S }));
    }
  }

  function paint() {
    view.setAttribute('transform',
      'translate(' + cam.x + ',' + cam.y + ') scale(' + cam.k + ')');

    var focus = hovered || selected;
    var showLabels = cam.k > 1.15;
    var placed = [];

    edges.forEach(function (e) {
      var a = e.a, b = e.b;
      if (!a || !b) return;
      var off = a.hidden || b.hidden || !kindOn[e.k];
      e.el.style.display = off ? 'none' : '';
      if (off) { if (e.lab) e.lab.style.display = 'none'; return; }

      e.el.setAttribute('d', path(a, b));
      // A relation is in the profile when the shapes walk that path; a subClassOf
      // is in it when both ends are, which is what makes the hierarchy still read.
      var inProf = !profileOnly ||
        (e.k === 'rel' ? !!e.profile : inProfile(a) && inProfile(b));
      var isLit = inProf && focus && (a.id === focus.id || b.id === focus.id);
      e.el.classList.toggle('is-lit', !!isLit);
      e.el.classList.toggle('is-dim', (!!focus && !isLit) || !inProf);

      // Relation names only on the edges you are interrogating. At rest they pile
      // up in the dense core and drown the map they are annotating. Sit them on
      // the curve's apex, not the chord, so relations sharing a node fan apart.
      if (e.lab) {
        var at = isLit && apex(a, b);
        var ok = at && reserve(at.x, at.y, e.lab.textContent.length * 5.2 + 6, 12, placed);
        e.lab.style.display = ok ? '' : 'none';
        if (ok) {
          e.lab.setAttribute('x', at.x);
          e.lab.setAttribute('y', at.y);
        }
      }
    });

    // Labels are placed most-connected first; anything that would collide with an
    // already-placed one is dropped. Zooming in frees the space and they return.
    // Lit relation names went into `placed` first: they answer the current action.
    var order = nodes.slice().sort(function (p, q) {
      return (q === focus) - (p === focus) || (q.flagged | 0) - (p.flagged | 0) ||
             q.deg - p.deg;
    });

    order.forEach(function (n) {
      if (n.hidden) { n.el.style.display = 'none'; n.lab.style.display = 'none'; return; }
      n.el.style.display = '';
      n.el.setAttribute('cx', n.x);
      n.el.setAttribute('cy', n.y);

      var isLit = (!focus || n.id === focus.id || lit[n.id]) &&
                  (!profileOnly || inProfile(n));
      n.el.classList.toggle('is-dim', !isLit);
      n.el.setAttribute('r', radius(n) * (n === focus ? 1.5 : 1));

      var ly = n.y - radius(n) - 5;
      var want = isLit && (showLabels || n.deg >= 4 || n === focus || n.flagged) &&
                 reserve(n.x, ly - 6, n.label.length * 5.6 + 8, 13, placed);

      n.lab.style.display = want ? '' : 'none';
      if (want) {
        n.lab.setAttribute('x', n.x);
        n.lab.setAttribute('y', ly);
        n.lab.classList.toggle('is-dim', !isLit);
      }
    });
  }

  /** Midpoint of the drawn curve, which is where a label looks attached. */
  function apex(a, b) {
    if (a === b) return { x: a.x + radius(a) + 14, y: a.y - radius(a) - 8 };
    var dx = b.x - a.x, dy = b.y - a.y;
    var d = Math.hypot(dx, dy) || 1;
    var bow = d * 0.12;
    var cx = (a.x + b.x) / 2 - (dy / d) * bow;
    var cy = (a.y + b.y) / 2 + (dx / d) * bow;
    return { x: (a.x + 2 * cx + b.x) / 4, y: (a.y + 2 * cy + b.y) / 4 - 4 };
  }

  /** Claim a label box, or refuse if it overlaps one already claimed. Sizes are
      screen px converted to world units, so the test loosens as you zoom in. */
  function reserve(cx, cy, wpx, hpx, placed) {
    var w = wpx / cam.k, h = hpx / cam.k;
    var x = cx - w / 2, y = cy - h / 2;
    for (var i = 0; i < placed.length; i++) {
      var p = placed[i];
      if (x < p.x + p.w && x + w > p.x && y < p.y + p.h && y + h > p.y) return false;
    }
    placed.push({ x: x, y: y, w: w, h: h });
    return true;
  }

  /* Relations bow, so a pair joined both by subClassOf and by a property does not
     draw one line on top of the other. Self-relations become a visible loop. */
  function path(a, b) {
    if (a === b) {
      var r = radius(a) + 9;
      return 'M' + a.x + ',' + (a.y - r * 0.5) +
             'a' + r + ',' + r + ' 0 1,1 ' + (r * 0.4) + ',0';
    }
    var dx = b.x - a.x, dy = b.y - a.y;
    var d = Math.hypot(dx, dy) || 1;
    var bow = d * 0.12;
    var mx = (a.x + b.x) / 2 - (dy / d) * bow;
    var my = (a.y + b.y) / 2 + (dx / d) * bow;
    return 'M' + a.x + ',' + a.y + 'Q' + mx + ',' + my + ' ' + b.x + ',' + b.y;
  }

  function setFocus(node) {
    selected = node;
    lit = {};
    if (node) {
      FMO.layout.neighbours(node.id).forEach(function (e) {
        lit[e.s] = lit[e.t] = true;
      });
    }
    paint();
  }

  function setHover(node) {
    if (hovered === node) return;
    hovered = node;
    if (node) {
      lit = {};
      FMO.layout.neighbours(node.id).forEach(function (e) { lit[e.s] = lit[e.t] = true; });
    } else {
      setFocus(selected);
      return;
    }
    paint();
  }

  /* ---- camera ---- */

  function toWorld(px, py) {
    var r = svg.getBoundingClientRect();
    return { x: (px - r.left - cam.x) / cam.k, y: (py - r.top - cam.y) / cam.k };
  }

  function zoomTo(k, cx, cy) {
    var r = svg.getBoundingClientRect();
    cx = cx === undefined ? r.width / 2 : cx;
    cy = cy === undefined ? r.height / 2 : cy;
    var w = { x: (cx - cam.x) / cam.k, y: (cy - cam.y) / cam.k };
    cam.k = Math.max(0.22, Math.min(4.5, k));
    cam.x = cx - w.x * cam.k;
    cam.y = cy - w.y * cam.k;
    paint();
  }

  function fit(pad) {
    var b = FMO.layout.extent();
    var r = svg.getBoundingClientRect();
    pad = pad || 78;
    var k = Math.min((r.width - pad * 2) / Math.max(b.x1 - b.x0, 1),
                     (r.height - pad * 2) / Math.max(b.y1 - b.y0, 1));
    cam.k = Math.max(0.22, Math.min(1.6, k));
    cam.x = r.width / 2 - ((b.x0 + b.x1) / 2) * cam.k;
    cam.y = r.height / 2 - ((b.y0 + b.y1) / 2) * cam.k;
    paint();
  }

  /** Centre one node without changing zoom -- how search results are revealed. */
  function centre(node, k) {
    var r = svg.getBoundingClientRect();
    if (k) cam.k = Math.max(0.22, Math.min(4.5, k));
    cam.x = r.width / 2 - node.x * cam.k;
    cam.y = r.height / 2 - node.y * cam.k;
    paint();
    if (on.moved) on.moved();
  }

  /* ---- input ---- */

  function hit(ev) {
    var t = ev.target;
    if (!t || !t.getAttribute) return null;
    var id = t.getAttribute('data-id');
    if (!id) return null;
    for (var i = 0; i < nodes.length; i++) if (nodes[i].id === id) return nodes[i];
    return null;
  }

  function wire() {
    svg.addEventListener('pointerdown', function (ev) {
      var n = hit(ev);
      svg.setPointerCapture(ev.pointerId);
      if (n) {
        drag = { node: n, moved: false };
        n.pinned = true;
      } else {
        pan = { x: ev.clientX - cam.x, y: ev.clientY - cam.y, moved: false };
        svg.classList.add('is-panning');
      }
    });

    svg.addEventListener('pointermove', function (ev) {
      if (drag) {
        var w = toWorld(ev.clientX, ev.clientY);
        drag.node.x = w.x; drag.node.y = w.y;
        drag.moved = true;
        paint();
        if (on.disturb) on.disturb();
      } else if (pan) {
        cam.x = ev.clientX - pan.x;
        cam.y = ev.clientY - pan.y;
        pan.moved = true;
        paint();
      } else {
        setHover(hit(ev));
      }
    });

    function release(ev) {
      if (drag) {
        drag.node.pinned = false;
        if (!drag.moved && on.select) on.select(drag.node);
        drag = null;
      } else if (pan) {
        if (!pan.moved && on.select) on.select(null);
        pan = null;
        svg.classList.remove('is-panning');
      }
      if (ev && ev.pointerId !== undefined && svg.hasPointerCapture(ev.pointerId)) {
        svg.releasePointerCapture(ev.pointerId);
      }
    }
    svg.addEventListener('pointerup', release);
    svg.addEventListener('pointercancel', release);
    svg.addEventListener('pointerleave', function () { setHover(null); });

    svg.addEventListener('wheel', function (ev) {
      ev.preventDefault();
      zoomTo(cam.k * Math.pow(0.999, ev.deltaY), ev.clientX - svg.getBoundingClientRect().left,
             ev.clientY - svg.getBoundingClientRect().top);
      if (on.moved) on.moved();
    }, { passive: false });
  }

  function setKind(kind, on) { kindOn[kind] = on; paint(); }

  function setProfile(on) { profileOnly = on; paint(); }

  FMO.graph = {
    build: build,
    paint: paint,
    fit: fit,
    centre: centre,
    zoomTo: zoomTo,
    setFocus: setFocus,
    setKind: setKind,
    setProfile: setProfile,
    camera: cam
  };
})(window.FMO);
