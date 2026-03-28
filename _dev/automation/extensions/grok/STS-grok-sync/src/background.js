// STS Grok Sync — Service Worker
// Owns the WebSocket connection (bypasses page CSP) and relays to content script.
// Content script holds a persistent port to keep the service worker alive (MV3).

let _ws = null;
let _wsConnected = false;
let _wsReconnectTimer = null;
let _wsReconnectAttempts = 0;
const _WS_PATH = "/ws/animator-grok-video-grabber";
const _PORT_MIN = 5050;
const _PORT_MAX = 5059; // 5060 is blocked by Chrome (SIP port — ERR_UNSAFE_PORT)

// ── Persistent Port (keeps service worker alive) ────

let _ports = [];

chrome.runtime.onConnect.addListener((port) => {
  if (port.name !== "sts-grok-alive") return;
  _ports.push(port);
  console.log("[STS BG] Port connected (" + _ports.length + " active)");

  port.postMessage({ type: "STS_WS_STATUS", connected: _wsConnected });

  port.onDisconnect.addListener(() => {
    _ports = _ports.filter(p => p !== port);
    console.log("[STS BG] Port disconnected (" + _ports.length + " active)");
  });

  port.onMessage.addListener((msg) => {
    if (msg.action === "STS_WS_SEND") {
      sendWS(msg.payload);
    } else if (msg.action === "STS_WS_GET_STATUS") {
      port.postMessage({ type: "STS_WS_STATUS", connected: _wsConnected });
    } else if (msg.action === "STS_WS_RECONNECT") {
      if (_ws) { try { _ws.close(); } catch(e) {} }
      _ws = null; _wsConnected = false; _wsReconnectAttempts = 0;
      connectWS(msg.manualWsUrl || null);
    }
  });
});

function _broadcastToAllPorts(msg) {
  for (let i = _ports.length - 1; i >= 0; i--) {
    try { _ports[i].postMessage(msg); }
    catch(e) { _ports.splice(i, 1); }
  }
}

function _broadcastStatus(port) {
  const msg = { type: "STS_WS_STATUS", connected: _wsConnected, port: port || 0 };
  _broadcastToAllPorts(msg);
  chrome.tabs.query({ url: "*://grok.com/*" }, (tabs) => {
    if (!tabs) return;
    for (const tab of tabs) {
      try { chrome.tabs.sendMessage(tab.id, { action: "STS_WS_STATUS", connected: _wsConnected, port: port || 0 }); } catch(e) {}
    }
  });
}

// ── WebSocket Management ────────────────────────────

function _tryPort(p) {
  return new Promise((resolve) => {
    const url = "ws://localhost:" + p + _WS_PATH;
    let ws;
    try { ws = new WebSocket(url); } catch(e) { resolve(null); return; }
    const timer = setTimeout(() => { try { ws.close(); } catch(e) {} resolve(null); }, 1500);
    ws.onopen = () => { clearTimeout(timer); resolve({ ws, url, port: p }); };
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
  _broadcastToAllPorts({ type: "STS_WS_MESSAGE", payload: msg });
  chrome.tabs.query({ url: "*://grok.com/*" }, (tabs) => {
    if (!tabs) return;
    for (const tab of tabs) {
      try { chrome.tabs.sendMessage(tab.id, { action: "STS_WS_MESSAGE", payload: msg }); } catch(e) {}
    }
  });
}

function _attachWS(ws, wsUrl, port) {
  _ws = ws;
  const _onOpen = () => {
    if (_ws !== ws) return;
    console.log("[STS BG] Connected to", wsUrl);
    _wsConnected = true;
    _wsReconnectAttempts = 0;
    try { ws.send(JSON.stringify({ type: "EXTENSION_READY", source: "sts-grok-sync" })); } catch(e) {}
    _broadcastStatus(port);
  };
  if (ws.readyState === WebSocket.OPEN) { _onOpen(); }
  ws.onopen = _onOpen;
  ws.onmessage = (evt) => {
    if (_ws !== ws) return;
    try {
      const msg = JSON.parse(evt.data);
      if (msg.type === "PING") { try { ws.send(JSON.stringify({ type: "PONG" })); } catch(e) {} return; }
      if (msg.type === "PONG") return;
      if (msg.type === "DIAGNOSE") { _handleDiagnose(_ws); return; }
      if (msg.type === "FORCE_DISCONNECT") {
        console.log("[STS BG] FORCE_DISCONNECT — closing WS");
        if (_ws) { try { _ws.close(); } catch(e) {} }
        return;
      }
      _relayToContent(msg);
    } catch(e) {
      console.warn("[STS BG] Bad message:", e);
    }
  };
  ws.onclose = () => {
    if (_ws === ws) { _ws = null; }
    console.log("[STS BG] Disconnected");
    _wsConnected = false;
    _broadcastStatus(0);
    _scheduleReconnect();
  };
  ws.onerror = () => {
    if (_ws === ws) _wsConnected = false;
  };
}

function connectWS(manualWsUrl) {
  if (_ws && (_ws.readyState === WebSocket.OPEN || _ws.readyState === WebSocket.CONNECTING)) return;

  if (manualWsUrl) {
    let ws;
    try { ws = new WebSocket(manualWsUrl); } catch(e) {
      _wsConnected = false; _scheduleReconnect(); return;
    }
    _attachWS(ws, manualWsUrl, 0);
    return;
  }

  _discoverPort().then((result) => {
    if (result) {
      console.log("[STS BG] Found server on port " + result.port);
      _attachWS(result.ws, result.url, result.port);
    } else {
      _wsConnected = false;
      _broadcastStatus(0);
      _scheduleReconnect();
    }
  });
}

function _scheduleReconnect() {
  if (_wsReconnectTimer) return;
  _wsReconnectAttempts++;
  const delay = Math.min(_wsReconnectAttempts * 2000, 10000);
  _wsReconnectTimer = setTimeout(() => { _wsReconnectTimer = null; connectWS(null); }, delay);
}

function sendWS(msg) {
  if (_ws && _ws.readyState === WebSocket.OPEN) {
    try {
      _ws.send(typeof msg === "string" ? msg : JSON.stringify(msg));
      return true;
    } catch(e) {}
  }
  return false;
}

connectWS(null);

// ── Diagnostics ─────────────────────────────────────

function _handleDiagnose(ws) {
  const report = {
    type: "DIAGNOSE_REPORT",
    ts: new Date().toISOString(),
    bg: {
      wsConnected: _wsConnected,
      wsReadyState: _ws ? _ws.readyState : -1,
      portsActive: _ports.length,
      reconnectAttempts: _wsReconnectAttempts,
    },
    contentStates: [],
  };

  chrome.tabs.query({ url: "*://grok.com/*" }, (tabs) => {
    if (!tabs || !tabs.length) {
      try { ws.send(JSON.stringify(report)); } catch(e) {}
      return;
    }
    let pending = tabs.length;
    for (const tab of tabs) {
      chrome.tabs.sendMessage(tab.id, { action: "STS_DIAGNOSE" }, (resp) => {
        if (chrome.runtime.lastError) {
          report.contentStates.push({ tabId: tab.id, error: chrome.runtime.lastError.message });
        } else if (resp) {
          report.contentStates.push({ tabId: tab.id, state: resp });
        }
        pending--;
        if (pending <= 0) {
          try { ws.send(JSON.stringify(report)); } catch(e) {}
        }
      });
    }
  });
}

// ── Legacy Message Handler ──────────────────────────

chrome.runtime.onInstalled.addListener(() => { console.log("[STS Grok Sync] Installed"); });

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === "PING") { sendResponse({ pong: true }); return false; }
  if (msg.type === "ACTIVATE_TAB") {
    if (sender.tab && sender.tab.id) {
      chrome.tabs.update(sender.tab.id, { active: true });
      chrome.windows.update(sender.tab.windowId, { focused: true });
    }
    sendResponse({ ok: true }); return false;
  }
  if (msg.action === "STS_WS_SEND") { sendWS(msg.payload); sendResponse({ ok: true }); return false; }
  if (msg.action === "STS_WS_GET_STATUS") { sendResponse({ connected: _wsConnected }); return false; }
  if (msg.action === "STS_WS_RECONNECT") {
    if (_ws) { try { _ws.close(); } catch(e) {} }
    _ws = null; _wsConnected = false; _wsReconnectAttempts = 0;
    connectWS(msg.manualWsUrl || null);
    sendResponse({ ok: true }); return false;
  }
  return false;
});
