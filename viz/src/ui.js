/* ui.js -- the chrome: search, module filters, legend, detail panel.
 *
 * Owns everything outside the SVG. Talks to the graph only through
 * FMO.graph.setFocus / centre, and to the data through FMO.nodes.
 *
 * To add a control: build it in index.html, wire it in one of the small
 * init* functions below, and leave the others alone.
 */
(function (FMO) {
  'use strict';

  var $ = function (id) { return document.getElementById(id); };

  var byId = {}, nodes = [], edges = [], props = {}, drawn = 0;
  // Datatype properties, grouped by the class that carries them: they end at a
  // literal, so they never reach the map and the panel is the only place they show.
  var lits = {};
  // Lenses from data.js, each with lookup sets built once; `lens` is the one lit.
  var lenses = [], lens = null;
  // Depth from BFO's entity, off the outline's rows: one computation, two views.
  var depth = {};
  var onSelect = function () {};
  var modules = { fm: true, wx: true, ksh: true, bfo: true };
  // Off by default: relations draw for the focused class and the active lens.
  var showRel = false;
  var matches = [], cursor = -1;
  // The search index: one entry per class, property and retired name.
  var entries = [], entryOf = {}, replaces = {};

  var MODULE_NAME = {
    fm: 'core · the pivot',
    wx: 'weather',
    ksh: 'kalshi',
    bfo: 'BFO (borrowed)'
  };

  /* A module swatch to set beside text. Anything not minted here is borrowed
     ground and keys as bfo, whatever namespace it came from. */
  function key(module) {
    var k = { fm: 1, wx: 1, ksh: 1 }[module] ? module : 'bfo';
    return '<i class="key key-' + k + '" aria-hidden="true"></i>';
  }

  // Borrowed terms name their own source; not all of them are BFO.
  var EXTERNAL_NAME = { bfo: 'Basic Formal Ontology', qudt: 'QUDT', owl: 'OWL' };

  function init(data, handlers) {
    nodes = data.nodes;
    edges = data.edges;
    props = data.properties;
    onSelect = handlers.select;
    nodes.forEach(function (n) { byId[n.id] = n; });

    var seen = {};
    data.edges.forEach(function (e) {
      if (e.k === 'rel' && !seen[e.p]) { seen[e.p] = 1; drawn++; }
    });

    Object.keys(data.datatypes || {}).forEach(function (pid) {
      var d = data.datatypes[pid];
      d.on.forEach(function (cid) {
        // A carrier off the map -- borrowed ground nothing else touches -- has no
        // panel to list it in. Skipping is what keeps it off, not an omission.
        if (byId[cid]) (lits[cid] || (lits[cid] = [])).push({ id: pid, meta: d });
      });
    });

    // data.js is gitignored, so it can predate the branch that reads it. A stale
    // one should cost the lens picker, not the whole map.
    lenses = (data.lenses || []).map(function (l) {
      var has = { named: {}, reached: {}, paths: {} };
      ['named', 'reached', 'paths'].forEach(function (k) {
        l[k].forEach(function (id) { has[k][id] = true; });
      });
      l.has = has;
      return l;
    });
    initLens();
    (data.tree || []).forEach(function (r) { if (!r.dup) depth[r.id] = r.d; });

    $('version').textContent = 'v' + data.version;
    buildIndex(data);
    initSearch();
    initChips();
    initViews();
    initPanel();
    legend();
    // On a phone the legend would cover the map; fold it rather than drop it,
    // or colour becomes the only thing saying which module a dot belongs to.
    if (window.matchMedia('(max-width: 900px)').matches) $('legend').open = false;
  }

  /* ---- filters ---- */

  /* Borrowed ground filters under the bfo chip whatever namespace it came from:
     a qudt endpoint has no chip of its own, so keying on the module alone would
     hide it with nothing left to bring it back. */
  function chipOf(n) { return n.minted ? n.module : 'bfo'; }

  function applyFilters() {
    nodes.forEach(function (n) { n.hidden = !modules[chipOf(n)]; });
    FMO.graph.setKind('rel', showRel);
    FMO.graph.setLens(lens);
    FMO.outline.paint({ lens: lens, bfo: modules.bfo });
    legend();
    // Results were filtered on visibility when they were built; rebuild them, or
    // Enter opens a term that is no longer on the map. Rebuilding must not pop the
    // list back open, so put its own state back.
    var open = !$('results').hidden;
    search($('search').value);
    if (!open) $('results').hidden = true;
  }

  /* Map or outline: one field, two readings of it. The panel, search and chips
     serve both, so switching changes nothing but what the field shows. */
  function initViews() {
    var chart = document.querySelector('.chart');
    [$('view-map'), $('view-outline')].forEach(function (btn) {
      btn.addEventListener('click', function () {
        var outline = btn.id === 'view-outline';
        chart.classList.toggle('is-outline', outline);
        $('view-map').setAttribute('aria-pressed', String(!outline));
        $('view-outline').setAttribute('aria-pressed', String(outline));
        $('view-map').classList.toggle('is-on', !outline);
        $('view-outline').classList.toggle('is-on', outline);
        FMO.outline.show(outline);
        // The SVG had no size while hidden; frame it again now it has one.
        if (!outline) FMO.graph.fit();
      });
    });
  }

  /* One lens at a time: two lit at once would leave no way to say which lit a dot. */
  function initLens() {
    var pick = $('lens');
    var groups = [], html = '<option value="">none</option>';
    lenses.forEach(function (l) { if (groups.indexOf(l.group) < 0) groups.push(l.group); });
    groups.forEach(function (g) {
      html += '<optgroup label="' + esc(g || 'Lenses') + '">' + lenses.map(function (l, i) {
        return l.group === g ? '<option value="' + i + '">' + esc(l.label) + '</option>' : '';
      }).join('') + '</optgroup>';
    });
    pick.innerHTML = html;
    $('lens-pick').hidden = !lenses.length;
    pick.addEventListener('change', function () {
      lens = pick.value === '' ? null : lenses[+pick.value];
      pick.classList.toggle('is-on', !!lens);
      applyFilters();
      // The panel's lens lines mark the active lens; redraw them.
      if (FMO.ui.current) FMO.ui.current();
    });
  }

  /* One line per way the term is in a lens group -- "used by CQ2, CQ5, CQ8" --
     with the active lens's line first. */
  function lensLines(id, kind) {
    var lines = [], at = {};
    lenses.filter(function (l) {
      return kind === 'path' ? l.has.paths[id] : l.has.named[id] || l.has.reached[id];
    }).sort(function (a, b) { return (b === lens) - (a === lens); }).forEach(function (l) {
      var w = l.words[kind === 'path' ? 'path' : l.has.named[id] ? 'named' : 'reached'];
      // A lens with nothing to attribute it to says its own line.
      if (l.line && l.has.named[id]) { lines.push({ line: l.line }); return; }
      var k = l.group + '|' + w;
      if (!(k in at)) { at[k] = lines.length; lines.push({ w: w, src: [] }); }
      lines[at[k]].src.push(l.source);
    });
    return lines.map(function (x) { return x.line || x.w + ' by ' + x.src.join(', '); });
  }

  function markLenses(id, kind) {
    var lines = lensLines(id, kind);
    $('panel-prof').hidden = !lines.length;
    $('panel-prof').innerHTML = lines.map(esc).join('<br>');
  }

  function initChips() {
    Array.prototype.forEach.call(document.querySelectorAll('.chip'), function (btn) {
      btn.addEventListener('click', function () {
        var on = !btn.classList.contains('is-on');
        btn.classList.toggle('is-on', on);
        btn.setAttribute('aria-pressed', String(on));
        if (btn.dataset.module) modules[btn.dataset.module] = on;
        else showRel = on;
        applyFilters();
      });
      btn.setAttribute('aria-pressed', String(btn.classList.contains('is-on')));
    });
  }

  function plural(n, word) { return n + ' ' + word + (n === 1 ? '' : 's'); }

  function legend() {
    var counts = {};
    nodes.forEach(function (n) {
      if (!n.hidden) counts[chipOf(n)] = (counts[chipOf(n)] || 0) + 1;
    });
    var rows = '';
    ['fm', 'wx', 'ksh', 'bfo'].forEach(function (m) {
      var c = 'var(--' + ({ fm: 'ink', wx: 'cold', ksh: 'warm', bfo: 'graphite' }[m]) + ')';
      rows += '<dt><span class="sw' + (m === 'bfo' ? ' ext' : '') +
              '" style="background:' + (m === 'bfo' ? 'none' : c) +
              ';border-color:' + c + '"></span></dt>' +
              '<dd>' + m + ':<span class="lg-name"> ' + MODULE_NAME[m] + '</span></dd>' +
              '<dd class="ct">' + (counts[m] || 0) + '</dd>';
    });
    // The two edge kinds and what their colour means; the counts are in the note.
    rows += '<dt><span class="sw-line"></span></dt><dd>is a<span class="lg-name">' +
            ' · rdfs:subClassOf</span></dd><dd class="ct"></dd>';
    rows += '<dt><span class="sw-line rel"></span></dt><dd>relation<span class="lg-name">' +
            ' · on selection, in its domain\'s colour</span></dd><dd class="ct"></dd>';
    $('legend-rows').innerHTML = rows;
    var shown = nodes.filter(function (n) { return !n.hidden; }).length;
    // Drawn, not declared: the properties left open-domain on purpose have no
    // edge, and the legend should not claim a line for them.
    // Every number counted off what is on the page right now. A build-time total
    // goes stale the moment a module chip hides half of what it counted.
    var named = 0, reached = 0, carriers = 0, seenLit = {}, litCount = 0;
    nodes.forEach(function (n) {
      if (n.hidden) return;
      if (lens && lens.has.named[n.id]) named++;
      else if (lens && lens.has.reached[n.id]) reached++;
      if (!lits[n.id]) return;
      carriers++;
      lits[n.id].forEach(function (d) {
        if (lens && lens.has.paths[d.id] && !seenLit[d.id]) { seenLit[d.id] = 1; litCount++; }
      });
    });
    var seenRel = {}, relCount = 0;
    if (lens) {
      edges.forEach(function (e) {
        if (e.k !== 'rel' || !lens.has.paths[e.p] || seenRel[e.p]) return;
        if (byId[e.s].hidden || byId[e.t].hidden) return;
        seenRel[e.p] = 1;
        relCount++;
      });
    }
    // A lens says what it shows -- for a question lens, the question; the counts
    // alone would not.
    $('legend-q').hidden = !(lens && lens.about);
    $('legend-q').textContent = lens && lens.about || '';
    // Listed, not lit, and folded: 45 names would bury the map under the legend.
    var unwalked = lens && lens.unwalked || [];
    $('legend-more').hidden = !unwalked.length;
    $('legend-more').querySelector('summary').textContent =
      unwalked.length + (unwalked.length === 1 ? ' property' : ' properties') + ' no question walks';
    $('legend-more').querySelector('p').textContent = unwalked.join(', ');
    // A lens that walks no paths reaches nothing; four zeros would only be noise.
    $('legend-note').textContent = lens
      ? lens.label + ' · ' + named + ' ' + lens.words.named + (lens.paths.length
        ? ' · ' + reached + ' ' + lens.words.reached + ' · ' + plural(relCount, 'relation') +
          ' · ' + plural(litCount, 'literal')
        : '')
      : shown + ' classes · ' + drawn + ' of ' + Object.keys(props).length +
        ' object properties drawn · ' + carriers + ' carry literal values';
  }

  /* ---- search ---- */

  /* Everything a reader might type: classes, both kinds of property, the API
     field names a property is read from, and retired names. A hit that is not a
     class opens its own panel, with the map focused on the class it hangs from. */
  function buildIndex(data) {
    function add(e) { entries.push(e); entryOf[e.id] = e; }
    nodes.forEach(function (n) {
      add({ id: n.id, label: n.label, def: n.def, kind: 'class', node: n });
    });
    // data.js is gitignored and can predate this branch; tolerate the missing keys.
    Object.keys(props).forEach(function (pid) {
      var p = props[pid];
      add({ id: pid, label: p.label, def: p.def, kind: 'relation', term: p,
            alias: p.fields || [], node: byId[(p.dom || [])[0]] || null });
    });
    var dts = data.datatypes || {};
    Object.keys(dts).forEach(function (pid) {
      var d = dts[pid];
      add({ id: pid, label: d.label || pid.split(':')[1], def: d.def, kind: 'literal', term: d,
            alias: d.fields || [], node: byId[d.on[0]] || null });
    });
    var retired = data.retired || {};
    Object.keys(retired).forEach(function (tid) {
      var r = retired[tid];
      add({ id: tid, label: r.label, def: r.note, kind: 'retired', to: r.to[0] });
      r.to.forEach(function (to) {
        (replaces[to] || (replaces[to] = [])).push({ id: tid, note: r.note });
      });
    });
  }

  /* A retired name stands in for its replacement everywhere but the result row. */
  function target(e) { return e.kind === 'retired' ? entryOf[e.to] || e : e; }

  function score(e, q) {
    var id = e.id.toLowerCase(), lab = e.label.toLowerCase();
    var alias = (e.alias || []).map(function (a) { return a.toLowerCase(); });
    if (id.split(':')[1] === q || lab === q || alias.indexOf(q) > -1) return 0;
    if (lab.indexOf(q) === 0 || id.indexOf(q) === 0 ||
        alias.some(function (a) { return a.indexOf(q) === 0; })) return 1;
    if (lab.indexOf(q) > -1 || id.indexOf(q) > -1) return 2;
    if ((e.def || '').toLowerCase().indexOf(q) > -1) return 3;
    return -1;
  }

  function open(e) {
    e = target(e);
    if (e.node) {
      onSelect(e.node);
      FMO.graph.centre(e.node, Math.max(FMO.graph.camera.k, 1.4));
    } else {
      onSelect(null);
    }
    if (e.kind !== 'class') showTerm(e);
  }

  function search(q) {
    q = q.trim().toLowerCase();
    var list = $('results');
    nodes.forEach(function (n) { n.flagged = false; });

    if (!q) {
      list.hidden = true;
      matches = [];
      cursor = -1;
      FMO.graph.paint();
      return;
    }

    matches = entries
      .map(function (e) { return { e: e, s: score(e, q) }; })
      .filter(function (m) {
        var n = target(m.e).node;
        return m.s >= 0 && !(n && n.hidden);
      })
      .sort(function (a, b) { return a.s - b.s || a.e.id.localeCompare(b.e.id); })
      .slice(0, 40)
      .map(function (m) { return m.e; });

    matches.forEach(function (e) { if (target(e).node) target(e).node.flagged = true; });
    cursor = matches.length ? 0 : -1;
    renderResults();
    FMO.graph.paint();
  }

  function renderResults() {
    var list = $('results');
    list.hidden = false;
    if (!matches.length) {
      list.innerHTML = '<li class="none">No term matches. Try a word from a definition.</li>';
      return;
    }
    var KIND = { relation: ' · relation', literal: ' · literal' };
    list.innerHTML = matches.map(function (e, i) {
      var desc = e.kind === 'retired' ? 'retired → ' + e.to : e.label + (KIND[e.kind] || '');
      return '<li role="option" data-i="' + i + '"' +
        (i === cursor ? ' aria-selected="true"' : '') +
        (e.kind === 'retired' ? ' class="is-retired"' : '') +
        '><b>' + key(e.node ? chipOf(e.node) : e.id.split(':')[0]) + esc(e.id) +
        '</b><span>' + esc(desc) + '</span></li>';
    }).join('');
  }

  function initSearch() {
    var input = $('search'), list = $('results');

    input.addEventListener('input', function () { search(input.value); });

    input.addEventListener('keydown', function (ev) {
      if (ev.key === 'ArrowDown' || ev.key === 'ArrowUp') {
        if (!matches.length) return;
        ev.preventDefault();
        cursor = (cursor + (ev.key === 'ArrowDown' ? 1 : -1) + matches.length) % matches.length;
        renderResults();
        var n = target(matches[cursor]).node;
        if (n) FMO.graph.centre(n);
      } else if (ev.key === 'Enter' && cursor > -1) {
        ev.preventDefault();
        open(matches[cursor]);
      } else if (ev.key === 'Escape') {
        input.value = '';
        search('');
        input.blur();
        // blur() lands before the event bubbles, so the document handler would
        // read this as an Escape from outside the field and close the panel too.
        ev.stopPropagation();
      }
    });

    list.addEventListener('mousedown', function (ev) {
      var li = ev.target.closest('li[data-i]');
      if (!li) return;
      ev.preventDefault();
      cursor = +li.dataset.i;
      open(matches[cursor]);
      renderResults();
    });

    input.addEventListener('blur', function () {
      setTimeout(function () { list.hidden = true; }, 120);
    });
    input.addEventListener('focus', function () {
      if (matches.length) list.hidden = false;
    });
  }

  /* ---- detail panel ---- */

  function initPanel() {
    $('panel-close').addEventListener('click', function () { onSelect(null); });
    $('jump').addEventListener('click', function () {
      var pivot = byId['fm:Proposition'];
      if (pivot) { onSelect(pivot); FMO.graph.centre(pivot, 1.5); }
    });
    $('panel-disj').addEventListener('click', function (ev) {
      var btn = ev.target.closest('button[data-to]');
      var n = btn && byId[btn.dataset.to];
      if (n) { onSelect(n); FMO.graph.centre(n, Math.max(FMO.graph.camera.k, 1.3)); }
    });
    $('panel-links').addEventListener('click', function (ev) {
      var btn = ev.target.closest('button[data-to]');
      if (!btn) return;
      var n = byId[btn.dataset.to];
      if (n) { onSelect(n); FMO.graph.centre(n, Math.max(FMO.graph.camera.k, 1.3)); }
    });
    $('panel-lits').addEventListener('click', function (ev) {
      var btn = ev.target.closest('button[data-term]');
      if (btn && entryOf[btn.dataset.term]) open(entryOf[btn.dataset.term]);
    });
  }

  function field(id, value) {
    var sec = $(id);
    sec.hidden = !value;
    return !!value;
  }

  function show(n) {
    $('panel-empty').hidden = !!n;
    $('panel-body').hidden = !n;
    if (!n) { current = null; return; }

    $('panel-kicker').innerHTML = key(chipOf(n)) + esc(n.minted
      ? MODULE_NAME[n.module].replace(' · the pivot', ' module')
      : (EXTERNAL_NAME[n.module] || n.module));

    $('panel-title').textContent = n.label;
    $('panel-curie').textContent = n.id + (n.id in depth ? ' · depth ' + depth[n.id] : '');

    // Named by a lens, or only landed on by a path it walks -- fm:hasSubject ranges
    // over fm:ObservationTarget while the export shape narrows it to the subclass,
    // so calling the range constrained would name the wrong class.
    markLenses(n.id, 'class');
    current = function () { show(n); };

    if (field('f-def', n.def)) $('panel-def').textContent = n.def;
    if (field('f-note', n.note)) $('panel-note').textContent = n.note;
    if (field('f-example', n.example)) $('panel-example').textContent = n.example;
    history(n.history, replaces[n.id]);
    coverage(n.coverage);
    disjoint(n.disjoint);
    field('f-api', false);

    literals(n);
    links(n);

    if (field('f-ttl', n.ttl)) $('panel-ttl').innerHTML = turtle(n.ttl);
  }

  /* The literal half of the surface. No edge to draw and nowhere to click
     through to, so a datatype property is listed with the type it lands in --
     that type is the whole of what it says beyond its definition. */
  function literals(n) {
    var out = (lits[n.id] || []).map(function (d) {
      return '<li' + (lens && lens.has.paths[d.id] ? ' class="in-prof"' : '') + '>' +
        '<p class="lit-head"><button type="button" class="lk-to" data-term="' + esc(d.id) +
        '">' + key(d.id.split(':')[0]) + esc(d.id) + '</button><span class="lit-range">' + esc(d.meta.range) + '</span></p>' +
        (d.meta.def ? '<p class="lit-def">' + esc(d.meta.def) + '</p>' : '') + '</li>';
    });
    field('f-lit', out.length);
    $('panel-lits').innerHTML = out.join('');
  }

  /* The panel for a property: what a class panel shows, plus the API fields it is
     read from, with its two ends (or its carriers) as the links. */
  function showTerm(e) {
    var t = e.term, mod = e.id.split(':')[0];
    $('panel-empty').hidden = true;
    $('panel-body').hidden = false;
    $('panel-kicker').innerHTML = key(mod) + esc(MODULE_NAME[mod].replace(' · the pivot', '') +
      (e.kind === 'relation' ? ' · object property' : ' · datatype property'));
    $('panel-title').textContent = t.label || e.label;
    $('panel-curie').textContent = e.id;
    markLenses(e.id, 'path');
    current = function () { showTerm(e); };

    if (field('f-def', t.def)) $('panel-def').textContent = t.def;
    if (field('f-note', t.note)) $('panel-note').textContent = t.note;
    field('f-example', false);
    history(t.history, replaces[e.id]);
    coverage(null);
    disjoint(null);
    if (field('f-api', (t.fields || []).length)) {
      $('panel-api').innerHTML = t.fields.map(function (f) {
        return '<code>' + esc(f) + '</code>';
      }).join(' ');
    }
    field('f-lit', false);

    var out = [];
    function end(via, cid) {
      var n = byId[cid];
      out.push(n
        ? '<li><button type="button" data-to="' + esc(cid) + '"><span class="lk-via">' + via +
          '</span><span class="lk-to">' + key(chipOf(n)) + esc(cid) + '</span></button></li>'
        : '<li><span class="lk-via">' + via + '</span> <span class="lk-to">' + esc(cid) + '</span></li>');
    }
    if (e.kind === 'relation') {
      (t.dom || []).forEach(function (c) { end('domain', c); });
      (t.rng || []).forEach(function (c) { end('range', c); });
    } else {
      t.on.forEach(function (c) { end('carried by', c); });
      out.push('<li><span class="lk-via">value</span> <span class="lk-to">' + esc(t.range) + '</span></li>');
    }
    // An open domain is a decision, not a gap; say so rather than show nothing.
    if (t.open) out.push('<li><span class="lk-via">domain left open on purpose</span></li>');
    field('f-links', out.length);
    $('panel-links').innerHTML = out.join('');

    if (field('f-ttl', t.ttl)) $('panel-ttl').innerHTML = turtle(t.ttl);
  }

  /* Where a class stands with the example data: exercised, or the reason its
     class-coverage-expectations.json entry gives for why no example reaches it. */
  var COVERAGE = {
    direct: 'exercised', subclass: 'exercised through a subclass',
    schema: 'enumerated in src/', unassertable: 'unassertable',
    unlisted: 'unlisted', unwritten: 'not yet written'
  };

  /* Disjointness draws nothing on the canvas -- the classes share no edge -- so
     the panel is where it shows. A partner off the map is named, not linked. */
  function disjoint(ids) {
    $('panel-disj').innerHTML = '';
    if (!field('f-disj', ids && ids.length)) return;
    $('panel-disj').innerHTML = ids.map(function (id) {
      var n = byId[id];
      return n
        ? '<li><button type="button" data-to="' + esc(id) + '"><span class="lk-to">' +
          key(chipOf(n)) + esc(id) + '</span></button></li>'
        : '<li><span class="lk-to">' + key('bfo') + esc(id) + '</span></li>';
    }).join('');
  }

  function coverage(c) {
    if (!field('f-cov', c && c.state)) return;
    $('panel-cov').innerHTML = '<span class="lk-via">' + esc(COVERAGE[c.state] || c.state) +
      (c.checked ? ' · checked ' + esc(c.checked) : '') + '</span> ' + esc(c.says || '');
  }

  /* Change and history notes, then any retired names this term replaced -- which
     is where a reader who searched for the old name wants the explanation. */
  function history(notes, replaced) {
    var out = (notes || []).map(function (h) {
      return '<li><span class="lk-via">' + esc(h.kind) + '</span><p>' + esc(h.text) + '</p></li>';
    }).concat((replaced || []).map(function (r) {
      return '<li><span class="lk-via">replaces</span> <span class="lk-to">' + key(r.id.split(':')[0]) +
        esc(r.id) + '</span>' + (r.note ? '<p>' + esc(r.note) + '</p>' : '') + '</li>';
    }));
    field('f-hist', out.length);
    $('panel-hist').innerHTML = out.join('');
  }

  function links(n) {
    var out = [];
    FMO.layout.neighbours(n.id).forEach(function (e) {
      var out_ = e.s === n.id;
      var other = byId[out_ ? e.t : e.s];
      if (!other) return;
      var via = e.k === 'sub'
        ? (out_ ? 'is a' : 'subsumes')
        : (out_ ? (e.p || '').split(':')[1] : '← ' + (e.p || '').split(':')[1]);
      out.push('<li><button type="button" data-to="' + esc(other.id) + '">' +
               '<span class="lk-via">' + esc(via) + '</span>' +
               '<span class="lk-to">' + key(chipOf(other)) + esc(other.id) +
               '</span></button></li>');
    });
    field('f-links', out.length);
    $('panel-links').innerHTML = out.join('');
  }

  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }

  /* The signature: the term shown in the syntax it is actually written in.
     One pass, strings and comments matched first so nothing inside them is
     re-coloured -- a definition reading "specifies a weather variable" must not
     have its "a" lit up as the rdf:type keyword. */
  var VOCAB = { rdfs: 1, rdf: 1, owl: 1, skos: 1, xsd: 1, dcterms: 1, qudt: 1 };
  var TOKEN = /("""[\s\S]*?"""|"(?:[^"\\]|\\.)*")|(#[^\n]*)|([A-Za-z][\w.-]*):([A-Za-z_][\w-]*)|(\s)a(?=\s)/g;

  function turtle(src) {
    var out = '', last = 0, m;
    TOKEN.lastIndex = 0;
    while ((m = TOKEN.exec(src)) !== null) {
      out += esc(src.slice(last, m.index));
      if (m[1]) out += '<span class="s">' + esc(m[1]) + '</span>';
      else if (m[2]) out += '<span class="c">' + esc(m[2]) + '</span>';
      // Terms take their module's colour, same as on the map; owl/rdfs/skos
      // scaffolding recedes, so what pops in the stanza is what the term touches.
      else if (m[3]) out += '<span class="' + (VOCAB[m[3]] ? 'k' : 'm-' + m[3]) + '">' +
                            esc(m[3] + ':' + m[4]) + '</span>';
      else out += m[5] + '<span class="k">a</span>';
      last = m.index + m[0].length;
    }
    return out + esc(src.slice(last));
  }

  // Redraws whatever the panel shows, when something it depends on changes.
  var current = null;

  FMO.ui = { init: init, show: show, applyFilters: applyFilters, search: search,
             current: function () { if (current) current(); } };
})(window.FMO);
