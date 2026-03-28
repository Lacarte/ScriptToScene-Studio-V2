// STS Grok Sync — Service Worker
// Owns the WebSocket connection (bypasses page CSP) and relays to content script.
// Uses chrome.alarms to survive MV3 service worker idle timeout (30s).

let _ws = null;
let _wsConnected = false;
let _wsReconnectTimer = null;
let _wsReconnectAttempts = 0;
const _WS_PATH = "/ws/animator-grok-video-grabber";
const _PORT_MIN = 5050;
const _PORT_MAX = 5060;

// ── MV3 Service Worker Keepalive ────────────────────

const _ALARM_NAME = "sts-grok-keepalive";

function _startKeepAliveAlarm() {
  chrome.alarms.create(_ALARM_NAME, { periodInMinutes: 0.4 }); // ~24s
}

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name !== _ALARM_NAME) return;

  if (_ws && _ws.readyState === WebSocket.OPEN) {
    try { _ws.send(JSON.stringify({ type: "PONG" })); } catch(e) {}
  } else {
    if (_wsConnected) {
      _wsConnected = false;
      _broadcastStatus(0);
    }
    if (!_wsReconnectTimer) {
      connectWS(null);
    }
  }
});

_startKeepAliveAlarm();

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
    if (!tabs) return;
    for (const tab of tabs) {
      try {
        chrome.tabs.sendMessage(tab.id, { action: "STS_WS_MESSAGE", payload: msg });
      } catch(e) {}
    }
  });
}

function _broadcastStatus(port) {
  chrome.tabs.query({ url: "*://grok.com/*" }, (tabs) => {
    if (!tabs) return;
    const msg = { action: "STS_WS_STATUS", connected: _wsConnected, port: port || 0 };
    for (const tab of tabs) {
      try { chrome.tabs.sendMessage(tab.id, msg); } catch(e) {}
    }
  });
}

function _attachWS(ws, wsUrl, port) {
  _ws = ws;
  ws.onopen = () => {
    if (_ws !== ws) return;
    console.log("[STS BG] Connected to", wsUrl);
    _wsConnected = true;
    _wsReconnectAttempts = 0;
    try { ws.send(JSON.stringify({ type: "EXTENSION_READY", source: "sts-grok-sync" })); } catch(e) {}
    _broadcastStatus(port);
  };
  ws.onmessage = (evt) => {
    if (_ws !== ws) return;
    try {
      const msg = JSON.parse(evt.data);
      if (msg.type === "PING") {
        try { ws.send(JSON.stringify({ type: "PONG" })); } catch(e) {}
        return;
      }
      if (msg.type === "PONG") return;
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
    console.log("[STS BG] Connecting to:", manualWsUrl);
    let ws;
    try { ws = new WebSocket(manualWsUrl); } catch(e) {
      _wsConnected = false; _scheduleReconnect(); return;
    }
    _attachWS(ws, manualWsUrl, 0);
    return;
  }

  console.log("[STS BG] Scanning ports " + _PORT_MIN + "-" + _PORT_MAX + "...");
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

// Auto-connect on service worker start
connectWS(null);

// ── Message Handler ─────────────────────────────────

chrome.runtime.onInstalled.addListener(() => {
  console.log("[STS Grok Sync] Installed");
  _startKeepAliveAlarm();
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
    }
    sendResponse({ ok: true });
    return false;
  }
  if (msg.action === "STS_WS_SEND") {
    const ok = sendWS(msg.payload);
    sendResponse({ ok, connected: _wsConnected });
    return false;
  }
  if (msg.action === "STS_WS_GET_STATUS") {
    sendResponse({ connected: _wsConnected });
    return false;
  }
  if (msg.action === "STS_WS_RECONNECT") {
    if (_ws) { try { _ws.close(); } catch(e) {} }
    _ws = null; _wsConnected = false; _wsReconnectAttempts = 0;
    connectWS(msg.manualWsUrl || null);
    sendResponse({ ok: true });
    return false;
  }
  return false;
});
