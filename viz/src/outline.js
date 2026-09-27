/* outline.js -- the map as an indented list: every class under its parent, with
 * its depth from bfo:entity. The keyboard path to every term, and the view where
 * a branch much deeper than its neighbours shows.
 *
 * Rows come precomputed as data.tree (generate_diagram.outline), so what this draws
 * is what diagram-check tested. Like graph, it decides nothing: a chosen row is
 * reported through handlers.select, and it paints whatever state it is handed.
 */
(function (FMO) {
  'use strict';

  var root, body, rows = [], byId = {}, labels = {}, on = {};
  var selected = null, state = { profile: false, bfo: true };

  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }

  function keyOf(n) { return n && n.minted ? n.module : 'bfo'; }

  function build(el, data, handlers) {
    root = el;
    on = handlers || {};
    data.nodes.forEach(function (n) { byId[n.id] = n; });

    var rel = {}, lit = {};
    data.edges.forEach(function (e) {
      if (e.k !== 'rel') return;
      rel[e.s] = (rel[e.s] || 0) + 1;
      if (e.t !== e.s) rel[e.t] = (rel[e.t] || 0) + 1;
    });
    Object.keys(data.datatypes || {}).forEach(function (pid) {
      data.datatypes[pid].on.forEach(function (c) { lit[c] = (lit[c] || 0) + 1; });
    });

    // data.js is gitignored and can predate this branch; no rows, no outline.
    rows = (data.tree || []).map(function (r) {
      return { id: r.id, d: r.d, via: r.via, dup: r.dup, node: byId[r.id] || null,
               label: r.label, rel: rel[r.id] || 0, lit: lit[r.id] || 0 };
    });

    root.innerHTML = '<p class="ol-sum">' + summary() + '</p>' +
      '<table class="ol"><thead><tr><th scope="col">Class</th>' +
      '<th scope="col" class="n">Depth</th><th scope="col" class="n opt">Relations</th>' +
      '<th scope="col" class="n opt">Literals</th></tr></thead><tbody></tbody></table>';
    body = root.querySelector('tbody');
    rows.forEach(function (r) { labels[r.id] = r.node ? r.node.label : r.label; });
    body.innerHTML = rows.map(row).join('');
    rows.forEach(function (r, i) { r.el = body.children[i]; });
    wire();
    paint();
  }

  /* Depth range per module: the book's mixed-granularity check, as a number. */
  function summary() {
    var span = {};
    rows.forEach(function (r) {
      if (r.dup || !r.node || !r.node.minted) return;
      var s = span[r.node.module] || (span[r.node.module] = { lo: r.d, hi: r.d });
      s.lo = Math.min(s.lo, r.d);
      s.hi = Math.max(s.hi, r.d);
    });
    return 'Depth counted from bfo:entity · ' + ['fm', 'wx', 'ksh'].filter(function (m) {
      return span[m];
    }).map(function (m) {
      return m + ' ' + span[m].lo + '–' + span[m].hi;
    }).join(' · ');
  }

  function row(r, i) {
    var n = r.node, label = n ? n.label : r.label;
    var key = '<i class="key key-' + keyOf(n) + '" aria-hidden="true"></i>';
    var name = '<span class="ol-label">' + esc(label) + '</span><span class="ol-curie">' +
               esc(r.id) + '</span>';
    var term = n
      ? '<button type="button" data-i="' + i + '">' + key + name + '</button>'
      : '<span class="ol-plain">' + key + name + '</span>';
    var note = r.dup ? 'also under ' + labels[r.via] + '; listed in full above'
             : n ? '' : 'not on the map';
    return '<tr class="' + (r.dup ? 'is-dup' : '') + (n ? '' : ' is-off') + '">' +
      '<td class="ol-term" style="--d:' + r.d + '">' + term +
      (note ? '<span class="ol-note">' + esc(note) + '</span>' : '') + '</td>' +
      '<td class="n">' + r.d + '</td>' +
      '<td class="n opt">' + (n ? r.rel : '') + '</td>' +
      '<td class="n opt">' + (n ? r.lit : '') + '</td></tr>';
  }

  function buttons() {
    return Array.prototype.filter.call(body.querySelectorAll('button[data-i]'), function (b) {
      return !b.closest('tr').hidden;
    });
  }

  function wire() {
    body.addEventListener('click', function (ev) {
      var b = ev.target.closest('button[data-i]');
      if (b && on.select) on.select(rows[+b.dataset.i].node);
    });
    // One tab stop per row is 100-odd; the list is one stop, and arrows walk it.
    body.addEventListener('focusin', function (ev) {
      if (ev.target.matches('button[data-i]')) rove(ev.target);
    });
    body.addEventListener('keydown', function (ev) {
      var list = buttons(), at = list.indexOf(document.activeElement), to = -1;
      if (at < 0) return;
      if (ev.key === 'ArrowDown') to = Math.min(at + 1, list.length - 1);
      else if (ev.key === 'ArrowUp') to = Math.max(at - 1, 0);
      else if (ev.key === 'Home') to = 0;
      else if (ev.key === 'End') to = list.length - 1;
      if (to < 0) return;
      ev.preventDefault();
      list[to].focus();
    });
  }

  function rove(to) {
    buttons().forEach(function (b) { b.tabIndex = b === to ? 0 : -1; });
  }

  function inProfile(n) { return !!(n && (n.profile || n.reached)); }

  /* Hidden follows the module chips, as on the map; the profile dims rather than
     hides, for the same reason it does there. */
  function paint(next) {
    if (next) state = next;
    rows.forEach(function (r) {
      r.el.hidden = r.node ? !!r.node.hidden : !state.bfo;
      r.el.classList.toggle('is-dim', state.profile && !inProfile(r.node));
      r.el.classList.toggle('is-sel', !!selected && r.node === selected);
    });
    // The tab stop sits on the selected class, or the first visible row.
    var list = buttons(), sel = list.filter(function (b) {
      return rows[+b.dataset.i].node === selected && !rows[+b.dataset.i].dup;
    })[0];
    if (list.length) rove(sel || list[0]);
  }

  function setFocus(node) {
    selected = node;
    paint();
    if (!node || root.hidden) return;
    var first = rows.filter(function (r) { return r.node === node && !r.dup; })[0];
    if (first) first.el.scrollIntoView({ block: 'nearest' });
  }

  function show(visible) {
    root.hidden = !visible;
    if (visible) setFocus(selected);
  }

  FMO.outline = { build: build, paint: paint, setFocus: setFocus, show: show };
})(window.FMO);
