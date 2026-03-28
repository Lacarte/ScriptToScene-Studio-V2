// STS Gemini — Background Service Worker
// Owns the WebSocket connection (bypasses page CSP) and relays messages to content script.
// Also fetches images from Google CDN (has host_permissions) and handles tab activation.

var _ws = null;
var _wsConnected = false;
var _wsReconnectTimer = null;
var _wsReconnectAttempts = 0;
var _WS_PATH = '/ws/image-gemini';
var _PORT_MIN = 5050;
var _PORT_MAX = 5060;
var _contentTabId = null;

// ── WebSocket Management ────────────────────────────

function _tryPort(port) {
  return new Promise(function(resolve) {
    var url = 'ws://localhost:' + port + _WS_PATH;
    var ws;
    try { ws = new WebSocket(url); } catch(e) { resolve(null); return; }
    var timer = setTimeout(function() { try { ws.close(); } catch(e) {} resolve(null); }, 1500);
    ws.onopen = function() { clearTimeout(timer); resolve({ ws: ws, url: url, port: port }); };
    ws.onerror = function() { clearTimeout(timer); resolve(null); };
  });
}

function _discoverPort() {
  var promises = [];
  for (var p = _PORT_MIN; p <= _PORT_MAX; p++) promises.push(_tryPort(p));
  return Promise.all(promises).then(function(results) {
    var winner = null;
    for (var i = 0; i < results.length; i++) {
      if (results[i]) {
        if (!winner) { winner = results[i]; }
        else { try { results[i].ws.close(); } catch(e) {} }
      }
    }
    return winner;
  });
}

function _relayToContent(msg) {
  // Send to all Gemini tabs
  chrome.tabs.query({ url: 'https://gemini.google.com/*' }, function(tabs) {
    for (var i = 0; i < tabs.length; i++) {
      try {
        chrome.tabs.sendMessage(tabs[i].id, { action: 'STS_WS_MESSAGE', payload: msg });
      } catch(e) {}
    }
  });
}

function _notifyContentStatus(connected, wsUrl) {
  chrome.tabs.query({ url: 'https://gemini.google.com/*' }, function(tabs) {
    for (var i = 0; i < tabs.length; i++) {
      try {
        chrome.tabs.sendMessage(tabs[i].id, {
          action: 'STS_WS_STATUS',
          connected: connected,
          wsUrl: wsUrl || ''
        });
      } catch(e) {}
    }
  });
}

function _attachWS(ws, wsUrl) {
  _ws = ws;
  ws.onopen = function() {
    if (_ws !== ws) return;
    console.log('[STS BG WS] Connected to', wsUrl);
    _wsConnected = true;
    _wsReconnectAttempts = 0;
    try { ws.send(JSON.stringify({ type: 'EXTENSION_READY', source: 'sts-gemini-ext' })); } catch(e) {}
    _notifyContentStatus(true, wsUrl);
  };
  ws.onmessage = function(evt) {
    if (_ws !== ws) return;
    try {
      var msg = JSON.parse(evt.data);
      // Handle PING internally
      if (msg.type === 'PING') {
        try { ws.send(JSON.stringify({ type: 'PONG' })); } catch(e) {}
        return;
      }
      // Relay all other messages to content script
      _relayToContent(msg);
    } catch(e) {
      console.warn('[STS BG WS] Bad message:', e);
    }
  };
  ws.onclose = function() {
    if (_ws === ws) { _ws = null; }
    console.log('[STS BG WS] Disconnected');
    _wsConnected = false;
    _notifyContentStatus(false, '');
    _scheduleReconnect();
  };
  ws.onerror = function() {
    _wsConnected = false;
  };
}

function connectWS(manualUrl) {
  if (_ws && (_ws.readyState === WebSocket.OPEN || _ws.readyState === WebSocket.CONNECTING)) return;

  if (manualUrl) {
    console.log('[STS BG WS] Connecting to manual URL:', manualUrl);
    var ws;
    try { ws = new WebSocket(manualUrl); } catch(e) {
      console.warn('[STS BG WS] Connection failed:', e.message);
      _wsConnected = false; _scheduleReconnect(); return;
    }
    _attachWS(ws, manualUrl);
    return;
  }

  console.log('[STS BG WS] Scanning ports ' + _PORT_MIN + '-' + _PORT_MAX + '...');
  _discoverPort().then(function(result) {
    if (result) {
      console.log('[STS BG WS] Discovered server on port ' + result.port);
      _attachWS(result.ws, result.url);
    } else {
      console.warn('[STS BG WS] No server found');
      _wsConnected = false;
      _notifyContentStatus(false, '');
      _scheduleReconnect();
    }
  });
}

function _scheduleReconnect() {
  if (_wsReconnectTimer) return;
  _wsReconnectAttempts++;
  var delay = _wsReconnectAttempts <= 10 ? 2000 : 5000;
  _wsReconnectTimer = setTimeout(function() { _wsReconnectTimer = null; connectWS(null); }, delay);
}

function sendWS(msg) {
  if (_ws && _ws.readyState === WebSocket.OPEN) {
    try { _ws.send(JSON.stringify(msg)); } catch(e) { console.warn('[STS BG WS] Send failed:', e.message); }
  }
}

// Auto-connect on service worker start
connectWS(null);

// ── Message Handler ─────────────────────────────────

chrome.runtime.onMessage.addListener(function(request, sender, sendResponse) {
  // Tab activation
  if (request.type === 'ACTIVATE_TAB') {
    if (sender.tab && sender.tab.id) {
      chrome.tabs.update(sender.tab.id, { active: true });
      chrome.windows.update(sender.tab.windowId, { focused: true });
      console.log('[STS Gemini] Tab activated:', sender.tab.id);
    }
    sendResponse({ ok: true });
    return false;
  }

  // Content script wants to send a message over WS
  if (request.action === 'STS_WS_SEND') {
    sendWS(request.payload);
    sendResponse({ ok: true });
    return false;
  }

  // Content script asks for current WS status
  if (request.action === 'STS_WS_GET_STATUS') {
    sendResponse({ connected: _wsConnected });
    return false;
  }

  // Content script wants to reconnect WS (e.g. after URL change)
  if (request.action === 'STS_WS_RECONNECT') {
    if (_ws) { try { _ws.close(); } catch(e) {} }
    _ws = null; _wsConnected = false;
    connectWS(request.manualUrl || null);
    sendResponse({ ok: true });
    return false;
  }

  // Image fetch via background (existing functionality)
  if (request.action === 'FETCH_IMAGE_BASE64') {
    var url = request.url;
    console.log('[STS BG] Fetching image:', url.substring(0, 80) + '...');

    var strategies = [
      { credentials: 'omit', mode: 'cors', redirect: 'follow' },
      { credentials: 'omit', redirect: 'follow' },
      { credentials: 'include', redirect: 'follow' },
      {},
    ];

    var attempt = 0;
    function tryNext() {
      if (attempt >= strategies.length) {
        console.error('[STS BG] All strategies failed for', url.substring(0, 60));
        sendResponse({ success: false, error: 'All fetch strategies failed' });
        return;
      }
      var opts = strategies[attempt];
      attempt++;
      console.log('[STS BG] Strategy', attempt, ':', JSON.stringify(opts));

      fetch(url, opts)
        .then(function(r) {
          console.log('[STS BG] Strategy', attempt, 'status:', r.status, 'type:', r.type);
          if (!r.ok) throw new Error('HTTP ' + r.status);
          return r.blob();
        })
        .then(function(blob) {
          console.log('[STS BG] Got blob:', blob.size, 'bytes, type:', blob.type);
          var reader = new FileReader();
          reader.onload = function() {
            var sizeKB = Math.round(blob.size / 1024);
            console.log('[STS BG] Success (' + sizeKB + ' KB) via strategy', attempt);
            sendResponse({ success: true, data: reader.result });
          };
          reader.onerror = function() {
            console.error('[STS BG] FileReader failed');
            tryNext();
          };
          reader.readAsDataURL(blob);
        })
        .catch(function(err) {
          console.warn('[STS BG] Strategy', attempt, 'failed:', err.message);
          tryNext();
        });
    }

    tryNext();
    return true; // Keep channel open
  }
});
