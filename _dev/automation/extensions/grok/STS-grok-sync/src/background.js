// STS Grok Sync — Service Worker
// Owns the WebSocket connection (bypasses page CSP) and relays messages to content script.
// Also handles tab activation.

let _ws = null;
let _wsConnected = false;
let _wsReconnectTimer = null;
let _wsReconnectAttempts = 0;
const _WS_PATH = "/ws/animator-grok-video-grabber";
const _PORT_MIN = 5050;
const _PORT_MAX = 5060;

// ── WebSocket Management ────────────────────────────

function _tryPort(port) {
  return new Promise((resolve) => {
    const url = "ws://localhost:" + port + _WS_PATH;
    let ws;
    try { ws = new WebSocket(url); } catch(e) { resolve(null); return; }
    const timer = setTimeout(() => { try { ws.close(); } catch(e) {} resolve(null); }, 1500);
    ws.onopen = () => { clearTimeout(timer); resolve({ ws, url, port }); };
    ws.onerror = () => { clearTimeout(timer); resolve(null); };
  });
}

function _discoverPort() {
  const promises = [];
  for (let p = _PORT_MIN; p <= _PORT_MAX; p++) promises.push(_tryPort(p));
  return Promise.all(promises).then((results) => {
    let winner = null;
    for (const r of results) {
      if (r) {
        if (!winner) { winner = r; }
        else { try { r.ws.close(); } catch(e) {} }
      }
    }
    return winner;
  });
}

function _relayToContent(msg) {
  chrome.tabs.query({ url: "*://grok.com/*" }, (tabs) => {
    for (const tab of tabs) {
      try {
        chrome.tabs.sendMessage(tab.id, { action: "STS_WS_MESSAGE", payload: msg });
      } catch(e) {}
    }
  });
}

function _notifyContentStatus(connected, port) {
  chrome.tabs.query({ url: "*://grok.com/*" }, (tabs) => {
    for (const tab of tabs) {
      try {
        chrome.tabs.sendMessage(tab.id, {
          action: "STS_WS_STATUS",
          connected: connected,
          port: port || 0
        });
      } catch(e) {}
    }
  });
}

function _attachWS(ws, wsUrl, port) {
  _ws = ws;
  ws.onopen = () => {
    if (_ws !== ws) return;
    console.log("[STS BG WS] Connected to", wsUrl);
    _wsConnected = true;
    _wsReconnectAttempts = 0;
    try { ws.send(JSON.stringify({ type: "EXTENSION_READY", source: "sts-grok-sync" })); } catch(e) {}
    _notifyContentStatus(true, port);
  };
  ws.onmessage = (evt) => {
    if (_ws !== ws) return;
    try {
      const msg = JSON.parse(evt.data);
      if (msg.type === "PING") {
        try { ws.send(JSON.stringify({ type: "PONG" })); } catch(e) {}
        return;
      }
      _relayToContent(msg);
    } catch(e) {
      console.warn("[STS BG WS] Bad message:", e);
    }
  };
  ws.onclose = () => {
    if (_ws === ws) { _ws = null; }
    console.log("[STS BG WS] Disconnected");
    _wsConnected = false;
    _notifyContentStatus(false, 0);
    _scheduleReconnect();
  };
  ws.onerror = () => {
    _wsConnected = false;
  };
}

function connectWS(manualWsUrl) {
  if (_ws && (_ws.readyState === WebSocket.OPEN || _ws.readyState === WebSocket.CONNECTING)) return;

  if (manualWsUrl) {
    console.log("[STS BG WS] Connecting to manual URL:", manualWsUrl);
    let ws;
    try { ws = new WebSocket(manualWsUrl); } catch(e) {
      console.warn("[STS BG WS] Connection failed:", e.message);
      _wsConnected = false; _scheduleReconnect(); return;
    }
    _attachWS(ws, manualWsUrl, 0);
    return;
  }

  console.log("[STS BG WS] Scanning ports " + _PORT_MIN + "-" + _PORT_MAX + "...");
  _discoverPort().then((result) => {
    if (result) {
      console.log("[STS BG WS] Discovered server on port " + result.port);
      _attachWS(result.ws, result.url, result.port);
    } else {
      console.warn("[STS BG WS] No server found");
      _wsConnected = false;
      _notifyContentStatus(false, 0);
      _scheduleReconnect();
    }
  });
}

function _scheduleReconnect() {
  if (_wsReconnectTimer) return;
  _wsReconnectAttempts++;
  const delay = _wsReconnectAttempts <= 10 ? 2000 : 5000;
  _wsReconnectTimer = setTimeout(() => { _wsReconnectTimer = null; connectWS(null); }, delay);
}

function sendWS(msg) {
  if (_ws && _ws.readyState === WebSocket.OPEN) {
    try { _ws.send(JSON.stringify(msg)); } catch(e) { console.warn("[STS BG WS] Send failed:", e.message); }
  }
}

// Auto-connect on service worker start
connectWS(null);

// ── Message Handler ─────────────────────────────────

chrome.runtime.onInstalled.addListener(() => {
  console.log("[STS Grok Sync] Installed");
});

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === "PING") {
    sendResponse({ pong: true, from: "background" });
    return false;
  }
  if (msg.type === "ACTIVATE_TAB") {
    if (sender.tab && sender.tab.id) {
      chrome.tabs.update(sender.tab.id, { active: true });
      chrome.windows.update(sender.tab.windowId, { focused: true });
      console.log("[STS Grok Sync] Tab activated:", sender.tab.id);
    }
    sendResponse({ ok: true });
    return false;
  }
  // Content script wants to send a message over WS
  if (msg.action === "STS_WS_SEND") {
    sendWS(msg.payload);
    sendResponse({ ok: true });
    return false;
  }
  // Content script asks for current WS status
  if (msg.action === "STS_WS_GET_STATUS") {
    sendResponse({ connected: _wsConnected });
    return false;
  }
  // Content script wants to reconnect WS
  if (msg.action === "STS_WS_RECONNECT") {
    if (_ws) { try { _ws.close(); } catch(e) {} }
    _ws = null; _wsConnected = false;
    connectWS(msg.manualWsUrl || null);
    sendResponse({ ok: true });
    return false;
  }
  return false;
});
