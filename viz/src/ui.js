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

  var byId = {}, nodes = [], props = {};
  var onSelect = function () {};
  var modules = { fm: true, wx: true, ksh: true, bfo: true };
  var showRel = true;
  var matches = [], cursor = -1;

  var MODULE_NAME = {
    fm: 'core · the pivot',
    wx: 'weather',
    ksh: 'kalshi',
    bfo: 'BFO (borrowed)'
  };

  function init(data, handlers) {
    nodes = data.nodes;
    props = data.properties;
    onSelect = handlers.select;
    nodes.forEach(function (n) { byId[n.id] = n; });

    $('version').textContent = 'v' + data.version;
    initSearch();
    initChips();
    initPanel();
    legend();
  }

  /* ---- filters ---- */

  function applyFilters() {
    nodes.forEach(function (n) { n.hidden = !modules[n.module]; });
    FMO.graph.setKind('rel', showRel);
    legend();
    FMO.graph.paint();
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
      btn.setAttribute('aria-pressed', 'true');
    });
  }

  function legend() {
    var counts = {};
    nodes.forEach(function (n) {
      if (!n.hidden) counts[n.module] = (counts[n.module] || 0) + 1;
    });
    var rows = '';
    ['fm', 'wx', 'ksh', 'bfo'].forEach(function (m) {
      var c = 'var(--' + ({ fm: 'ink', wx: 'cold', ksh: 'warm', bfo: 'graphite' }[m]) + ')';
      rows += '<dt><span class="sw' + (m === 'bfo' ? ' ext' : '') +
              '" style="background:' + (m === 'bfo' ? 'none' : c) +
              ';border-color:' + c + '"></span></dt>' +
              '<dd>' + m + ':<span style="color:var(--graphite)"> ' + MODULE_NAME[m] + '</span></dd>' +
              '<dd class="ct">' + (counts[m] || 0) + '</dd>';
    });
    $('legend-rows').innerHTML = rows;
    var shown = nodes.filter(function (n) { return !n.hidden; }).length;
    $('legend-note').textContent = shown + ' classes · ' +
      Object.keys(props).length + ' object properties';
  }

  /* ---- search ---- */

  function score(n, q) {
    var id = n.id.toLowerCase(), lab = n.label.toLowerCase();
    if (id.split(':')[1] === q || lab === q) return 0;
    if (lab.indexOf(q) === 0 || id.indexOf(q) === 0) return 1;
    if (lab.indexOf(q) > -1 || id.indexOf(q) > -1) return 2;
    if ((n.def || '').toLowerCase().indexOf(q) > -1) return 3;
    return -1;
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

    matches = nodes
      .map(function (n) { return { n: n, s: score(n, q) }; })
      .filter(function (m) { return m.s >= 0 && !m.n.hidden; })
      .sort(function (a, b) { return a.s - b.s || a.n.id.localeCompare(b.n.id); })
      .slice(0, 40)
      .map(function (m) { return m.n; });

    matches.forEach(function (n) { n.flagged = true; });
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
    list.innerHTML = matches.map(function (n, i) {
      return '<li role="option" data-i="' + i + '"' +
        (i === cursor ? ' aria-selected="true"' : '') +
        '><b style="color:var(--' +
        ({ fm: 'ink', wx: 'cold', ksh: 'warm', bfo: 'graphite' }[n.module]) + ')">' +
        esc(n.id) + '</b><span>' + esc(n.label) + '</span></li>';
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
        FMO.graph.centre(matches[cursor]);
      } else if (ev.key === 'Enter' && cursor > -1) {
        ev.preventDefault();
        onSelect(matches[cursor]);
        FMO.graph.centre(matches[cursor], Math.max(FMO.graph.camera.k, 1.4));
      } else if (ev.key === 'Escape') {
        input.value = '';
        search('');
        input.blur();
      }
    });

    list.addEventListener('mousedown', function (ev) {
      var li = ev.target.closest('li[data-i]');
      if (!li) return;
      ev.preventDefault();
      cursor = +li.dataset.i;
      onSelect(matches[cursor]);
      FMO.graph.centre(matches[cursor], Math.max(FMO.graph.camera.k, 1.4));
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
    $('panel-links').addEventListener('click', function (ev) {
      var btn = ev.target.closest('button[data-to]');
      if (!btn) return;
      var n = byId[btn.dataset.to];
      if (n) { onSelect(n); FMO.graph.centre(n, Math.max(FMO.graph.camera.k, 1.3)); }
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
    if (!n) return;

    var tone = { fm: 'var(--ink)', wx: 'var(--cold)', ksh: 'var(--warm)' }[n.module]
             || 'var(--graphite)';

    var kicker = $('panel-kicker');
    kicker.textContent = n.minted
      ? MODULE_NAME[n.module].replace(' · the pivot', ' module')
      : 'Basic Formal Ontology';
    kicker.style.color = tone;

    $('panel-title').textContent = n.label;
    $('panel-curie').textContent = n.id;

    if (field('f-def', n.def)) $('panel-def').textContent = n.def;
    if (field('f-note', n.note)) $('panel-note').textContent = n.note;
    if (field('f-example', n.example)) $('panel-example').textContent = n.example;

    links(n);

    if (field('f-ttl', n.ttl)) $('panel-ttl').innerHTML = turtle(n.ttl);
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
               '<span class="lk-to" style="color:var(--' +
               ({ fm: 'ink', wx: 'cold', ksh: 'warm', bfo: 'graphite' }[other.module]) +
               ')">' + esc(other.id) + '</span></button></li>');
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

  FMO.ui = { init: init, show: show, applyFilters: applyFilters, search: search };
})(window.FMO);
