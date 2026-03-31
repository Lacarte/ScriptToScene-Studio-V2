(function() {
  if (window.__sarActive) return;
  window.__sarActive = true;

  // ── State ──────────────────────────────────────────
  var state = {
    picking: false,
    recording: false,
    target: null,
    intervalId: null,
    snapshots: [],       // { time, html, changes[] }
    startTime: 0,
    initialHTML: '',
    prevHTML: '',
    counts: { add: 0, rem: 0, attr: 0, text: 0, snapshots: 0 },
  };

  // ── Utilities ──────────────────────────────────────
  function getSelector(el) {
    if (!el || el.nodeType !== 1) return '';
    var parts = [];
    var cur = el;
    while (cur && cur !== document.body && cur !== document.documentElement) {
      var tag = cur.tagName.toLowerCase();
      if (cur.id) { parts.unshift(tag + '#' + cur.id); break; }
      var cls = Array.from(cur.classList || [])
        .filter(function(c) { return !c.startsWith('sar-') && !c.startsWith('ng-'); })
        .slice(0, 2).join('.');
      var sel = cls ? tag + '.' + cls : tag;
      var parent = cur.parentElement;
      if (parent) {
        var siblings = parent.querySelectorAll(':scope > ' + tag);
        if (siblings.length > 1) {
          var idx = Array.from(siblings).indexOf(cur);
          sel += ':nth-child(' + (idx + 1) + ')';
        }
      }
      parts.unshift(sel);
      cur = cur.parentElement;
    }
    return parts.join(' > ');
  }

  function truncate(str, max) {
    max = max || 200;
    if (!str) return '';
    str = str.replace(/\s+/g, ' ').trim();
    return str.length > max ? str.substring(0, max) + '...' : str;
  }

  function relTime(ts) {
    var diff = ts - state.startTime;
    var s = Math.floor(diff / 1000);
    var ms = diff % 1000;
    var m = Math.floor(s / 60);
    s = s % 60;
    return (m > 0 ? m + 'm' : '') + s + '.' + String(ms).padStart(3, '0') + 's';
  }

  function escHtml(s) {
    var d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
  }

  // Build full XPath for an element (within a container context)
  function getXPath(el, root) {
    if (!el || el.nodeType !== 1) return '';
    var parts = [];
    var cur = el;
    while (cur && cur !== root && cur !== document.documentElement) {
      var tag = cur.tagName.toLowerCase();
      var parent = cur.parentElement;
      if (parent) {
        var siblings = Array.from(parent.children).filter(function(c) { return c.tagName === cur.tagName; });
        var idx = siblings.indexOf(cur) + 1;
        parts.unshift(tag + '[' + idx + ']');
      } else {
        parts.unshift(tag);
      }
      cur = cur.parentElement;
    }
    return '/' + parts.join('/');
  }

  // Infer a human-readable reason for the change
  function inferReason(change) {
    if (change.type === 'add') {
      if (change.tag === 'script') return 'Script injected — likely dynamic code loading';
      if (change.tag === 'style' || change.tag === 'link') return 'Stylesheet added — visual update';
      if (change.tag === 'img' || change.tag === 'svg' || change.tag === 'canvas') return 'Media element inserted — new visual content';
      if (change.tag === 'iframe') return 'Iframe embedded — external content loaded';
      if (change.tag === 'input' || change.tag === 'textarea' || change.tag === 'select') return 'Form element added — UI interaction point created';
      if (change.tag === 'div' || change.tag === 'span' || change.tag === 'p') return 'Content container added — new content block rendered';
      if (change.tag === 'li' || change.tag === 'tr' || change.tag === 'td') return 'List/table item added — data row appended';
      if (change.tag === 'a' || change.tag === 'button') return 'Interactive element added — new action available';
      return 'Element inserted into DOM — dynamic content update';
    }
    if (change.type === 'rem') {
      if (change.tag === 'script') return 'Script removed — cleanup or replacement';
      if (change.tag === 'div' || change.tag === 'span' || change.tag === 'p') return 'Content container removed — content cleared or replaced';
      if (change.tag === 'li' || change.tag === 'tr' || change.tag === 'td') return 'List/table item removed — data row deleted';
      return 'Element removed from DOM — content cleanup or replacement';
    }
    if (change.type === 'attr') {
      var attr = change.attribute;
      if (attr === 'class') {
        var oldCls = (change.oldValue || '').split(/\s+/);
        var newCls = (change.newValue || '').split(/\s+/);
        var added = newCls.filter(function(c) { return c && oldCls.indexOf(c) === -1; });
        var removed = oldCls.filter(function(c) { return c && newCls.indexOf(c) === -1; });
        if (added.some(function(c) { return /hidden|hide|collapse|invisible|d-none|display-none/.test(c); })) return 'Element hidden via class — visibility toggled off';
        if (removed.some(function(c) { return /hidden|hide|collapse|invisible|d-none|display-none/.test(c); })) return 'Element shown via class — visibility toggled on';
        if (added.some(function(c) { return /active|selected|current|focus|open|expanded/.test(c); })) return 'State class added — element activated or selected';
        if (removed.some(function(c) { return /active|selected|current|focus|open|expanded/.test(c); })) return 'State class removed — element deactivated or deselected';
        if (added.some(function(c) { return /loading|spinner|pending|processing/.test(c); })) return 'Loading state applied — async operation in progress';
        if (removed.some(function(c) { return /loading|spinner|pending|processing/.test(c); })) return 'Loading state cleared — async operation completed';
        if (added.some(function(c) { return /error|invalid|danger|warning/.test(c); })) return 'Error/warning class added — validation or error state';
        if (added.some(function(c) { return /success|valid|complete/.test(c); })) return 'Success class added — positive state';
        if (added.length > 0 || removed.length > 0) return 'CSS classes changed — visual state updated (' + (added.length ? '+' + added.join(', +') : '') + (removed.length ? ' -' + removed.join(', -') : '') + ')';
        return 'CSS classes modified — styling change';
      }
      if (attr === 'style') return 'Inline style changed — direct visual modification';
      if (attr === 'disabled') return change.newValue === '(removed)' ? 'Element enabled — interaction allowed' : 'Element disabled — interaction blocked';
      if (attr === 'href' || attr === 'src') return 'Resource URL changed — content source updated';
      if (attr === 'value') return 'Input value changed — form data updated';
      if (attr === 'aria-hidden' || attr === 'aria-expanded' || attr === 'aria-selected') return 'ARIA attribute changed — accessibility state updated';
      if (attr === 'data-' || attr.startsWith('data-')) return 'Data attribute changed — application state updated';
      if (attr === 'title' || attr === 'alt' || attr === 'placeholder') return 'Descriptive attribute changed — label/hint updated';
      return 'Attribute "' + attr + '" modified — element property updated';
    }
    if (change.type === 'text') {
      var oldLen = (change.oldValue || '').length;
      var newLen = (change.newValue || '').length;
      if (oldLen === 0 && newLen > 0) return 'Text content populated — empty element now has content';
      if (oldLen > 0 && newLen === 0) return 'Text content cleared — element emptied';
      if (Math.abs(newLen - oldLen) < 5) return 'Text content tweaked — minor text edit';
      return 'Text content replaced — dynamic text update';
    }
    return 'DOM mutation detected';
  }

  // Build a human-readable description of what changed
  function describeChange(change) {
    if (change.type === 'add') {
      var desc = 'Added <' + change.tag + '>';
      if (change.id) desc += '#' + change.id;
      if (change.classes) desc += '.' + change.classes.split(' ').slice(0, 3).join('.');
      desc += ' as child of parent node';
      return desc;
    }
    if (change.type === 'rem') {
      var desc = 'Removed <' + change.tag + '>';
      if (change.id) desc += '#' + change.id;
      if (change.classes) desc += '.' + change.classes.split(' ').slice(0, 3).join('.');
      desc += ' from parent node';
      return desc;
    }
    if (change.type === 'attr') {
      return 'Changed attribute "' + change.attribute + '" on <' + change.tag + '> from "' + truncate(change.oldValue, 60) + '" to "' + truncate(change.newValue, 60) + '"';
    }
    if (change.type === 'text') {
      return 'Text in <' + change.tag + '> changed from "' + truncate(change.oldValue, 60) + '" to "' + truncate(change.newValue, 60) + '"';
    }
    return 'Unknown change';
  }

  // ── Snapshot Diff Engine ─────────────────────────────
  // Compare two snapshots by building maps keyed on selector/position
  function diffSnapshots(prevContainer, currContainer) {
    var changes = [];

    // Get all elements from both
    var prevEls = prevContainer.querySelectorAll('*');
    var currEls = currContainer.querySelectorAll('*');

    // Build maps by selector
    var prevMap = {};
    var currMap = {};

    Array.from(prevEls).forEach(function(el) {
      if (el.id === 'sar-panel' || el.classList.contains('sar-pick-highlight')) return;
      var sel = getSelector(el);
      if (sel) prevMap[sel] = el;
    });

    Array.from(currEls).forEach(function(el) {
      if (el.id === 'sar-panel' || el.classList.contains('sar-pick-highlight')) return;
      var sel = getSelector(el);
      if (sel) currMap[sel] = el;
    });

    // Added elements
    Object.keys(currMap).forEach(function(sel) {
      if (!prevMap[sel]) {
        var el = currMap[sel];
        var entry = {
          type: 'add',
          tag: el.tagName.toLowerCase(),
          id: el.id || '',
          classes: Array.from(el.classList || []).filter(function(c) { return !c.startsWith('sar-'); }).join(' '),
          selector: sel,
          xpath: getXPath(el, currContainer),
          html: truncate(el.outerHTML),
        };
        entry.description = describeChange(entry);
        entry.reason = inferReason(entry);
        changes.push(entry);
      }
    });

    // Removed elements
    Object.keys(prevMap).forEach(function(sel) {
      if (!currMap[sel]) {
        var el = prevMap[sel];
        var entry = {
          type: 'rem',
          tag: el.tagName.toLowerCase(),
          id: el.id || '',
          classes: Array.from(el.classList || []).filter(function(c) { return !c.startsWith('sar-'); }).join(' '),
          selector: sel,
          xpath: getXPath(el, prevContainer),
          html: truncate(el.outerHTML),
        };
        entry.description = describeChange(entry);
        entry.reason = inferReason(entry);
        changes.push(entry);
      }
    });

    // Attribute changes on elements that exist in both
    Object.keys(currMap).forEach(function(sel) {
      if (!prevMap[sel]) return;
      var prev = prevMap[sel];
      var curr = currMap[sel];

      // Check all attributes
      var allAttrs = new Set();
      Array.from(prev.attributes).forEach(function(a) { allAttrs.add(a.name); });
      Array.from(curr.attributes).forEach(function(a) { allAttrs.add(a.name); });

      allAttrs.forEach(function(attr) {
        if (attr.startsWith('sar-')) return;
        var oldVal = prev.getAttribute(attr) || '';
        var newVal = curr.getAttribute(attr) || '';
        // Filter sar- classes
        if (attr === 'class') {
          oldVal = oldVal.split(/\s+/).filter(function(c) { return !c.startsWith('sar-'); }).join(' ').trim();
          newVal = newVal.split(/\s+/).filter(function(c) { return !c.startsWith('sar-'); }).join(' ').trim();
        }
        if (oldVal !== newVal) {
          var entry = {
            type: 'attr',
            tag: curr.tagName.toLowerCase(),
            id: curr.id || '',
            classes: Array.from(curr.classList || []).filter(function(c) { return !c.startsWith('sar-'); }).join(' '),
            selector: sel,
            xpath: getXPath(curr, currContainer),
            attribute: attr,
            oldValue: truncate(oldVal || '(none)'),
            newValue: truncate(newVal || '(removed)'),
          };
          entry.description = describeChange(entry);
          entry.reason = inferReason(entry);
          changes.push(entry);
        }
      });

      // Check text content (direct text only, not children)
      var prevText = Array.from(prev.childNodes).filter(function(n) { return n.nodeType === 3; }).map(function(n) { return n.textContent; }).join('');
      var currText = Array.from(curr.childNodes).filter(function(n) { return n.nodeType === 3; }).map(function(n) { return n.textContent; }).join('');
      if (prevText.trim() !== currText.trim() && (prevText.trim() || currText.trim())) {
        var entry = {
          type: 'text',
          tag: curr.tagName.toLowerCase(),
          selector: sel,
          xpath: getXPath(curr, currContainer),
          oldValue: truncate(prevText.trim()),
          newValue: truncate(currText.trim()),
        };
        entry.description = describeChange(entry);
        entry.reason = inferReason(entry);
        changes.push(entry);
      }
    });

    return changes;
  }

  // ── Pick Mode ──────────────────────────────────────
  var lastHovered = null;

  function onPickMove(e) {
    if (lastHovered) lastHovered.classList.remove('sar-pick-highlight');
    var el = e.target;
    if (el.id === 'sar-panel' || el.closest('#sar-panel')) return;
    el.classList.add('sar-pick-highlight');
    lastHovered = el;
  }

  function onPickClick(e) {
    e.preventDefault();
    e.stopPropagation();
    if (lastHovered) lastHovered.classList.remove('sar-pick-highlight');
    document.removeEventListener('mousemove', onPickMove, true);
    document.removeEventListener('click', onPickClick, true);
    document.removeEventListener('keydown', onPickEsc, true);
    state.picking = false;

    var el = e.target;
    if (el.id === 'sar-panel' || el.closest('#sar-panel')) return;

    selectTarget(el);
  }

  function onPickEsc(e) {
    if (e.key === 'Escape') {
      if (lastHovered) lastHovered.classList.remove('sar-pick-highlight');
      document.removeEventListener('mousemove', onPickMove, true);
      document.removeEventListener('click', onPickClick, true);
      document.removeEventListener('keydown', onPickEsc, true);
      state.picking = false;
    }
  }

  function startPicking() {
    state.picking = true;
    document.addEventListener('mousemove', onPickMove, true);
    document.addEventListener('click', onPickClick, true);
    document.addEventListener('keydown', onPickEsc, true);
  }

  // ── Target Selection & Recording ───────────────────
  function selectTarget(el) {
    if (state.target) state.target.classList.remove('sar-monitored');
    if (state.intervalId) { clearInterval(state.intervalId); state.intervalId = null; }

    state.target = el;
    state.snapshots = [];
    state.counts = { add: 0, rem: 0, attr: 0, text: 0, snapshots: 0 };
    el.classList.add('sar-monitored');

    showPanel();
    startRecording();
  }

  function captureSnapshot() {
    if (!state.target || !state.recording) return;

    var now = Date.now();
    var currentHTML = state.target.outerHTML;

    // Skip if nothing changed since last snapshot
    if (currentHTML === state.prevHTML) return;

    // Parse prev and current into temp containers for diffing
    var prevContainer = document.createElement('div');
    prevContainer.innerHTML = state.prevHTML;
    var currContainer = document.createElement('div');
    currContainer.innerHTML = currentHTML;

    var changes = diffSnapshots(prevContainer, currContainer);

    if (changes.length > 0) {
      var snapshot = {
        time: now,
        html: currentHTML,
        changes: changes,
      };
      state.snapshots.push(snapshot);
      state.counts.snapshots++;

      // Update mutation counts
      changes.forEach(function(c) {
        if (c.type === 'add') state.counts.add++;
        else if (c.type === 'rem') state.counts.rem++;
        else if (c.type === 'attr') state.counts.attr++;
        else if (c.type === 'text') state.counts.text++;
      });

      state.prevHTML = currentHTML;
      renderPanel();
    }
  }

  function startRecording() {
    if (!state.target) return;
    state.recording = true;
    state.startTime = Date.now();
    state.initialHTML = state.target.outerHTML;
    state.prevHTML = state.initialHTML;

    // Capture snapshot every 1 second
    state.intervalId = setInterval(captureSnapshot, 1000);

    renderPanel();
  }

  function stopRecording() {
    if (state.intervalId) { clearInterval(state.intervalId); state.intervalId = null; }
    // Capture one final snapshot
    captureSnapshot();
    state.recording = false;
    renderPanel();
  }

  function clearData() {
    stopRecording();
    state.snapshots = [];
    state.counts = { add: 0, rem: 0, attr: 0, text: 0, snapshots: 0 };
    if (state.target) state.target.classList.remove('sar-monitored');
    state.target = null;
    state.initialHTML = '';
    state.prevHTML = '';
    var panel = document.getElementById('sar-panel');
    if (panel) panel.remove();
  }

  // ── Panel UI ───────────────────────────────────────
  function showPanel() {
    if (document.getElementById('sar-panel')) return;
    var panel = document.createElement('div');
    panel.id = 'sar-panel';
    panel.innerHTML =
      '<div class="sar-header">' +
        '<span class="sar-title">Section Activity Recorder</span>' +
        '<span id="sar-status" style="color:#8b949e;font-size:10px;">recording (1s interval)</span>' +
        '<button class="sar-header-btn" id="sar-minimize" title="Minimize">&#x2015;</button>' +
        '<button class="sar-header-btn" id="sar-close" title="Close">&times;</button>' +
      '</div>' +
      '<div class="sar-stats">' +
        '<div class="sar-stat sar-stat-snap"><div class="sar-stat-num" id="sar-c-snap">0</div><div class="sar-stat-label">Snaps</div></div>' +
        '<div class="sar-stat sar-stat-add"><div class="sar-stat-num" id="sar-c-add">0</div><div class="sar-stat-label">Added</div></div>' +
        '<div class="sar-stat sar-stat-rem"><div class="sar-stat-num" id="sar-c-rem">0</div><div class="sar-stat-label">Removed</div></div>' +
        '<div class="sar-stat sar-stat-attr"><div class="sar-stat-num" id="sar-c-attr">0</div><div class="sar-stat-label">Attrs</div></div>' +
        '<div class="sar-stat sar-stat-text"><div class="sar-stat-num" id="sar-c-text">0</div><div class="sar-stat-label">Text</div></div>' +
      '</div>' +
      '<div class="sar-log" id="sar-log"></div>' +
      '<div class="sar-controls">' +
        '<button class="sar-btn sar-btn-stop" id="sar-toggle">Stop</button>' +
        '<button class="sar-btn sar-btn-export" id="sar-export">Export</button>' +
        '<button class="sar-btn sar-btn-clear" id="sar-clear">Clear</button>' +
      '</div>';
    document.body.appendChild(panel);

    document.getElementById('sar-toggle').addEventListener('click', function() {
      if (state.recording) { stopRecording(); }
      else { startRecording(); }
    });
    document.getElementById('sar-export').addEventListener('click', exportReport);
    document.getElementById('sar-clear').addEventListener('click', clearData);
    document.getElementById('sar-minimize').addEventListener('click', function() {
      panel.classList.toggle('sar-minimized');
    });
    document.getElementById('sar-close').addEventListener('click', function() {
      panel.style.display = 'none';
    });

    // Draggable
    var header = panel.querySelector('.sar-header');
    var dragging = false, ox, oy;
    header.addEventListener('mousedown', function(e) {
      dragging = true;
      ox = e.clientX - panel.offsetLeft;
      oy = e.clientY - panel.offsetTop;
    });
    document.addEventListener('mousemove', function(e) {
      if (!dragging) return;
      panel.style.left = (e.clientX - ox) + 'px';
      panel.style.top = (e.clientY - oy) + 'px';
      panel.style.right = 'auto';
      panel.style.bottom = 'auto';
    });
    document.addEventListener('mouseup', function() { dragging = false; });
  }

  function renderPanel() {
    var snapEl = document.getElementById('sar-c-snap');
    var addEl = document.getElementById('sar-c-add');
    var remEl = document.getElementById('sar-c-rem');
    var attrEl = document.getElementById('sar-c-attr');
    var textEl = document.getElementById('sar-c-text');
    var statusEl = document.getElementById('sar-status');
    var toggleEl = document.getElementById('sar-toggle');

    if (snapEl) snapEl.textContent = state.counts.snapshots;
    if (addEl) addEl.textContent = state.counts.add;
    if (remEl) remEl.textContent = state.counts.rem;
    if (attrEl) attrEl.textContent = state.counts.attr;
    if (textEl) textEl.textContent = state.counts.text;
    if (statusEl) statusEl.textContent = state.recording ? 'recording (1s interval)' : 'stopped';
    if (toggleEl) {
      toggleEl.textContent = state.recording ? 'Stop' : 'Start';
      toggleEl.className = 'sar-btn ' + (state.recording ? 'sar-btn-stop' : 'sar-btn-start');
    }

    // Render last 50 snapshots' changes
    var log = document.getElementById('sar-log');
    if (!log) return;

    var recent = state.snapshots.slice(-50);
    var html = '';
    recent.forEach(function(snap) {
      var time = relTime(snap.time);
      html += '<div class="sar-snap-header">' + time + ' (' + snap.changes.length + ' changes)</div>';
      snap.changes.forEach(function(e) {
        var typeClass = 'sar-type-' + e.type;
        var typeLabel = { add: '+ADD', rem: '-REM', attr: '~ATTR', text: '~TEXT' }[e.type];
        var detail = '';
        if (e.type === 'add' || e.type === 'rem') {
          detail = '&lt;' + e.tag + '&gt;' + (e.id ? '#' + e.id : '') + (e.classes ? '.' + e.classes.split(' ')[0] : '');
        } else if (e.type === 'attr') {
          detail = e.attribute + ': ' + escHtml(truncate(e.oldValue, 30)) + ' &rarr; ' + escHtml(truncate(e.newValue, 30));
        } else {
          detail = escHtml(truncate(e.oldValue, 30)) + ' &rarr; ' + escHtml(truncate(e.newValue, 30));
        }
        html += '<div class="sar-entry">' +
          '<span class="' + typeClass + '">' + typeLabel + '</span> ' +
          detail +
          '<span class="sar-xpath">' + escHtml(e.xpath || '') + '</span>' +
          '<span class="sar-reason">' + escHtml(e.reason || '') + '</span>' +
        '</div>';
      });
    });
    log.innerHTML = html;
    log.scrollTop = log.scrollHeight;
  }

  // ── Export Report ──────────────────────────────────
  function exportReport() {
    var finalHTML = state.target ? state.target.outerHTML : '';
    var totalChanges = 0;
    state.snapshots.forEach(function(s) { totalChanges += s.changes.length; });
    var targetSelector = getSelector(state.target);
    var duration = state.snapshots.length > 0
      ? relTime(state.snapshots[state.snapshots.length - 1].time)
      : '0s';

    var html = '<!DOCTYPE html><html><head><meta charset="utf-8"><title>Section Activity Report</title><style>' +
      'body{background:#0d1117;color:#e6edf3;font-family:"SF Mono",Consolas,monospace;font-size:12px;padding:20px;margin:0;}' +
      'h1{color:#00d4aa;font-size:18px;margin:0 0 4px;}' +
      'h2{color:#58a6ff;font-size:14px;margin:20px 0 8px;border-bottom:1px solid #30363d;padding-bottom:4px;}' +
      '.meta{color:#8b949e;font-size:11px;margin-bottom:16px;}' +
      '.stats{display:flex;gap:16px;margin:12px 0 20px;}' +
      '.stat{background:#161b22;border:1px solid #30363d;border-radius:6px;padding:12px 16px;text-align:center;flex:1;}' +
      '.stat-num{font-size:24px;font-weight:700;}' +
      '.stat-label{font-size:10px;color:#8b949e;text-transform:uppercase;margin-top:4px;}' +
      '.stat-add .stat-num{color:#3fb950;} .stat-rem .stat-num{color:#f85149;}' +
      '.stat-attr .stat-num{color:#58a6ff;} .stat-text .stat-num{color:#d29922;}' +
      '.stat-snap .stat-num{color:#bc8cff;}' +
      '.timeline{border:1px solid #30363d;border-radius:6px;overflow:hidden;}' +
      '.snap-header{padding:8px 12px;background:#161b22;border-bottom:1px solid #30363d;color:#bc8cff;font-weight:700;font-size:11px;}' +
      '.entry{padding:6px 12px;border-bottom:1px solid #21262d;display:flex;gap:8px;align-items:flex-start;}' +
      '.entry:hover{background:#161b22;}' +
      '.entry:last-child{border-bottom:none;}' +
      '.type{min-width:50px;font-weight:700;flex-shrink:0;}' +
      '.type-add{color:#3fb950;} .type-rem{color:#f85149;} .type-attr{color:#58a6ff;} .type-text{color:#d29922;}' +
      '.detail{flex:1;word-break:break-all;}' +
      '.selector{color:#8b949e;font-size:10px;display:block;margin-top:2px;}' +
      '.old-new{margin-top:2px;font-size:10px;}' +
      '.old{color:#f85149;text-decoration:line-through;} .new{color:#3fb950;}' +
      '.xpath{color:#bc8cff;font-size:10px;display:block;margin-top:3px;font-family:monospace;word-break:break-all;}' +
      '.description{color:#e6edf3;font-size:11px;display:block;margin-top:2px;}' +
      '.reason{color:#8b949e;font-size:10px;font-style:italic;display:block;margin-top:1px;}' +
      'details{margin:12px 0;} summary{cursor:pointer;color:#58a6ff;padding:4px 0;}' +
      'pre{background:#161b22;border:1px solid #30363d;border-radius:4px;padding:12px;overflow-x:auto;font-size:10px;max-height:400px;overflow-y:auto;}' +
    '</style></head><body>';

    html += '<h1>Section Activity Report</h1>';
    html += '<div class="meta">Target: <code>' + escHtml(targetSelector) + '</code> | Duration: ' + duration +
      ' | Snapshots: ' + state.snapshots.length + ' | Total changes: ' + totalChanges + ' | Interval: 1s</div>';

    // Stats
    html += '<div class="stats">' +
      '<div class="stat stat-snap"><div class="stat-num">' + state.counts.snapshots + '</div><div class="stat-label">Snapshots</div></div>' +
      '<div class="stat stat-add"><div class="stat-num">' + state.counts.add + '</div><div class="stat-label">Added</div></div>' +
      '<div class="stat stat-rem"><div class="stat-num">' + state.counts.rem + '</div><div class="stat-label">Removed</div></div>' +
      '<div class="stat stat-attr"><div class="stat-num">' + state.counts.attr + '</div><div class="stat-label">Attributes</div></div>' +
      '<div class="stat stat-text"><div class="stat-num">' + state.counts.text + '</div><div class="stat-label">Text</div></div>' +
    '</div>';

    // Timeline grouped by snapshot
    html += '<h2>Snapshot Timeline (' + state.snapshots.length + ' snapshots, ' + totalChanges + ' changes)</h2>';
    html += '<div class="timeline">';

    state.snapshots.forEach(function(snap, si) {
      var time = relTime(snap.time);
      html += '<div class="snap-header">Snapshot #' + (si + 1) + ' @ ' + time + ' (' + snap.changes.length + ' changes)</div>';

      snap.changes.forEach(function(e) {
        var typeLabel = { add: '+ADD', rem: '-REM', attr: '~ATTR', text: '~TEXT' }[e.type];
        var typeCls = 'type-' + e.type;
        var detail = '';

        if (e.type === 'add') {
          detail = '<strong>&lt;' + e.tag + '&gt;</strong>' + (e.id ? ' #' + e.id : '') + (e.classes ? ' .' + e.classes.split(' ').join('.') : '');
          detail += '<div class="old-new"><span class="new">' + escHtml(e.html) + '</span></div>';
        } else if (e.type === 'rem') {
          detail = '<strong>&lt;' + e.tag + '&gt;</strong>' + (e.id ? ' #' + e.id : '') + (e.classes ? ' .' + e.classes.split(' ').join('.') : '');
          detail += '<div class="old-new"><span class="old">' + escHtml(e.html) + '</span></div>';
        } else if (e.type === 'attr') {
          detail = '<strong>' + e.attribute + '</strong> on &lt;' + e.tag + '&gt;';
          detail += '<div class="old-new"><span class="old">' + escHtml(e.oldValue) + '</span> &rarr; <span class="new">' + escHtml(e.newValue) + '</span></div>';
        } else {
          detail += '<div class="old-new"><span class="old">' + escHtml(e.oldValue) + '</span> &rarr; <span class="new">' + escHtml(e.newValue) + '</span></div>';
        }

        html += '<div class="entry">' +
          '<span class="type ' + typeCls + '">' + typeLabel + '</span>' +
          '<div class="detail">' +
            '<span class="description">' + escHtml(e.description || '') + '</span>' +
            detail +
            '<span class="xpath">XPath: ' + escHtml(e.xpath || '') + '</span>' +
            '<span class="selector">CSS: ' + escHtml(e.selector) + '</span>' +
            '<span class="reason">Why: ' + escHtml(e.reason || '') + '</span>' +
          '</div>' +
        '</div>';
      });
    });
    html += '</div>';

    // Snapshots
    html += '<h2>Initial HTML Snapshot</h2>';
    html += '<details><summary>Show initial HTML (' + state.initialHTML.length + ' chars)</summary>';
    html += '<pre>' + escHtml(formatHtml(state.initialHTML)) + '</pre></details>';

    html += '<h2>Final HTML Snapshot</h2>';
    html += '<details><summary>Show final HTML (' + finalHTML.length + ' chars)</summary>';
    html += '<pre>' + escHtml(formatHtml(finalHTML)) + '</pre></details>';

    // Per-snapshot HTML (collapsible)
    if (state.snapshots.length > 0) {
      html += '<h2>Per-Snapshot HTML</h2>';
      state.snapshots.forEach(function(snap, si) {
        var time = relTime(snap.time);
        html += '<details><summary>Snapshot #' + (si + 1) + ' @ ' + time + ' (' + snap.html.length + ' chars)</summary>';
        html += '<pre>' + escHtml(formatHtml(snap.html)) + '</pre></details>';
      });
    }

    html += '</body></html>';

    // Download
    var blob = new Blob([html], { type: 'text/html' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = 'section-activity-report-' + new Date().toISOString().replace(/[:.]/g, '-').substring(0, 19) + '.html';
    a.click();
    URL.revokeObjectURL(url);
  }

  function formatHtml(html) {
    var result = '';
    var indent = 0;
    html.replace(/(<\/?[^>]+>)/g, function(match) {
      if (match.startsWith('</')) indent = Math.max(0, indent - 1);
      result += '  '.repeat(indent) + match + '\n';
      if (match.startsWith('<') && !match.startsWith('</') && !match.endsWith('/>') && !match.includes('<!')) indent++;
    });
    return result || html;
  }

  // ── XPath / CSS Selector Resolution ─────────────────
  function resolveByPath(path) {
    var el = null;
    var isXPath = path.startsWith('/') || path.startsWith('(');

    if (isXPath) {
      try {
        var result = document.evaluate(path, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);
        el = result.singleNodeValue;
      } catch (e) {
        return { error: 'Invalid XPath: ' + e.message };
      }
    } else {
      try {
        el = document.querySelector(path);
      } catch (e) {
        return { error: 'Invalid CSS selector: ' + e.message };
      }
    }

    if (!el) {
      return { error: 'No element found for: ' + path };
    }
    if (el.nodeType !== 1) {
      return { error: 'Path resolved to non-element node (type ' + el.nodeType + ')' };
    }
    return { element: el };
  }

  function selectByPath(path) {
    var result = resolveByPath(path);
    if (result.error) return result;

    var el = result.element;
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    el.style.transition = 'outline 0.3s';
    el.style.outline = '4px solid #00d4aa';
    setTimeout(function() {
      el.style.outline = '';
      el.style.transition = '';
      selectTarget(el);
    }, 600);

    var tag = el.tagName.toLowerCase();
    var id = el.id ? '#' + el.id : '';
    var cls = el.classList.length ? '.' + Array.from(el.classList).slice(0, 2).join('.') : '';
    return { ok: true, message: 'Selected <' + tag + id + cls + '> — recording started (1s interval)' };
  }

  // ── Message Listener ───────────────────────────────
  chrome.runtime.onMessage.addListener(function(msg, sender, sendResponse) {
    if (msg.action === '__PING__') {
      sendResponse({ ok: true });
    } else if (msg.action === 'PICK_ELEMENT') {
      startPicking();
      sendResponse({ ok: true });
    } else if (msg.action === 'SELECT_BY_PATH') {
      var result = selectByPath(msg.path);
      sendResponse(result);
    } else if (msg.action === 'STOP_RECORDING') {
      stopRecording();
      sendResponse({ ok: true, message: 'Recording stopped' });
    } else if (msg.action === 'CLEAR_DATA') {
      clearData();
      sendResponse({ ok: true, message: 'Data cleared' });
    }
    return true;
  });

  // ── Public API (for cross-extension use) ───────────
  // Other extensions on the same page can call:
  //   window.__sarAPI.monitor(xpathOrCss)  — start monitoring
  //   window.__sarAPI.stop()               — stop recording
  //   window.__sarAPI.clear()              — clear data
  window.__sarAPI = {
    monitor: function(path) { return selectByPath(path); },
    stop: function() { stopRecording(); return { ok: true }; },
    clear: function() { clearData(); return { ok: true }; },
    isRecording: function() { return state.recording; }
  };

})();
