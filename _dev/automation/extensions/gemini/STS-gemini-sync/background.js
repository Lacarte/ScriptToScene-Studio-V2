// STS Gemini — Background Service Worker
// Owns the WebSocket connection (bypasses page CSP) and relays to content script.
// Uses chrome.alarms to survive MV3 service worker idle timeout (30s).

var _ws = null;
var _wsConnected = false;
var _wsUrl = '';
var _wsReconnectTimer = null;
var _wsReconnectAttempts = 0;
var _WS_PATH = '/ws/image-gemini';
var _PORT_MIN = 5050;
var _PORT_MAX = 5060;

// ── MV3 Service Worker Keepalive ────────────────────
// chrome.alarms fires even when the service worker is idle,
// waking it up and giving us a chance to check/reconnect WS.

var _ALARM_NAME = 'sts-gemini-keepalive';

function _startKeepAliveAlarm() {
  chrome.alarms.create(_ALARM_NAME, { periodInMinutes: 0.4 }); // ~24s
}

chrome.alarms.onAlarm.addListener(function(alarm) {
  if (alarm.name !== _ALARM_NAME) return;

  // Check if WS is still alive
  if (_ws && _ws.readyState === WebSocket.OPEN) {
    try { _ws.send(JSON.stringify({ type: 'PONG' })); } catch(e) {}
  } else {
    // WS died or was never connected — reconnect
    if (_wsConnected) {
      _wsConnected = false;
      _broadcastStatus();
    }
    if (!_wsReconnectTimer) {
      connectWS(null);
    }
  }
});

_startKeepAliveAlarm();

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
  chrome.tabs.query({ url: 'https://gemini.google.com/*' }, function(tabs) {
    if (!tabs || !tabs.length) return;
    for (var i = 0; i < tabs.length; i++) {
      try {
        chrome.tabs.sendMessage(tabs[i].id, { action: 'STS_WS_MESSAGE', payload: msg });
      } catch(e) {}
    }
  });
}

function _broadcastStatus() {
  chrome.tabs.query({ url: 'https://gemini.google.com/*' }, function(tabs) {
    if (!tabs) return;
    var msg = { action: 'STS_WS_STATUS', connected: _wsConnected, wsUrl: _wsUrl };
    for (var i = 0; i < tabs.length; i++) {
      try { chrome.tabs.sendMessage(tabs[i].id, msg); } catch(e) {}
    }
  });
}

function _attachWS(ws, wsUrl) {
  _ws = ws;
  _wsUrl = wsUrl;

  ws.onopen = function() {
    if (_ws !== ws) return;
    console.log('[STS BG] Connected to', wsUrl);
    _wsConnected = true;
    _wsReconnectAttempts = 0;
    try { ws.send(JSON.stringify({ type: 'EXTENSION_READY', source: 'sts-gemini-ext' })); } catch(e) {}
    _broadcastStatus();
  };

  ws.onmessage = function(evt) {
    if (_ws !== ws) return;
    try {
      var msg = JSON.parse(evt.data);
      if (msg.type === 'PING') {
        try { ws.send(JSON.stringify({ type: 'PONG' })); } catch(e) {}
        return;
      }
      if (msg.type === 'PONG') return;
      _relayToContent(msg);
    } catch(e) {
      console.warn('[STS BG] Bad message:', e);
    }
  };

  ws.onclose = function() {
    if (_ws === ws) { _ws = null; }
    console.log('[STS BG] Disconnected');
    _wsConnected = false;
    _broadcastStatus();
    _scheduleReconnect();
  };

  ws.onerror = function() {
    if (_ws === ws) _wsConnected = false;
  };
}

function connectWS(manualUrl) {
  if (_ws && (_ws.readyState === WebSocket.OPEN || _ws.readyState === WebSocket.CONNECTING)) return;

  if (manualUrl) {
    console.log('[STS BG] Connecting to manual URL:', manualUrl);
    var ws;
    try { ws = new WebSocket(manualUrl); } catch(e) {
      console.warn('[STS BG] Connection failed:', e.message);
      _wsConnected = false; _scheduleReconnect(); return;
    }
    _attachWS(ws, manualUrl);
    return;
  }

  console.log('[STS BG] Scanning ports ' + _PORT_MIN + '-' + _PORT_MAX + '...');
  _discoverPort().then(function(result) {
    if (result) {
      console.log('[STS BG] Found server on port ' + result.port);
      _attachWS(result.ws, result.url);
    } else {
      _wsConnected = false;
      _broadcastStatus();
      _scheduleReconnect();
    }
  });
}

function _scheduleReconnect() {
  if (_wsReconnectTimer) return;
  _wsReconnectAttempts++;
  var delay = Math.min(_wsReconnectAttempts * 2000, 10000);
  _wsReconnectTimer = setTimeout(function() {
    _wsReconnectTimer = null;
    connectWS(null);
  }, delay);
}

function sendWS(msg) {
  if (_ws && _ws.readyState === WebSocket.OPEN) {
    try {
      _ws.send(typeof msg === 'string' ? msg : JSON.stringify(msg));
      return true;
    } catch(e) {
      console.warn('[STS BG] Send failed:', e.message);
    }
  }
  return false;
}

// Auto-connect on service worker start
connectWS(null);

// ── Message Handler ─────────────────────────────────

chrome.runtime.onMessage.addListener(function(request, sender, sendResponse) {
  if (request.type === 'ACTIVATE_TAB') {
    if (sender.tab && sender.tab.id) {
      chrome.tabs.update(sender.tab.id, { active: true });
      chrome.windows.update(sender.tab.windowId, { focused: true });
    }
    sendResponse({ ok: true });
    return false;
  }

  if (request.action === 'STS_WS_SEND') {
    var ok = sendWS(request.payload);
    sendResponse({ ok: ok, connected: _wsConnected });
    return false;
  }

  if (request.action === 'STS_WS_GET_STATUS') {
    sendResponse({ connected: _wsConnected, wsUrl: _wsUrl });
    return false;
  }

  if (request.action === 'STS_WS_RECONNECT') {
    if (_ws) { try { _ws.close(); } catch(e) {} }
    _ws = null; _wsConnected = false;
    _wsReconnectAttempts = 0;
    connectWS(request.manualUrl || null);
    sendResponse({ ok: true });
    return false;
  }

  if (request.action === 'FETCH_IMAGE_BASE64') {
    var url = request.url;
    var strategies = [
      { credentials: 'omit', mode: 'cors', redirect: 'follow' },
      { credentials: 'omit', redirect: 'follow' },
      { credentials: 'include', redirect: 'follow' },
      {},
    ];

    var attempt = 0;
    function tryNext() {
      if (attempt >= strategies.length) {
        sendResponse({ success: false, error: 'All fetch strategies failed' });
        return;
      }
      var opts = strategies[attempt];
      attempt++;

      fetch(url, opts)
        .then(function(r) {
          if (!r.ok) throw new Error('HTTP ' + r.status);
          return r.blob();
        })
        .then(function(blob) {
          var reader = new FileReader();
          reader.onload = function() {
            sendResponse({ success: true, data: reader.result });
          };
          reader.onerror = function() { tryNext(); };
          reader.readAsDataURL(blob);
        })
        .catch(function() { tryNext(); });
    }

    tryNext();
    return true; // Keep channel open for async response
  }
});
