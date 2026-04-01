// STS Orchestrator — Background Service Worker
// Central controller that manages tabs for all STS extensions.
// Connects to the STS backend via WebSocket and responds to tab control commands.

let _ws = null;
let _wsConnected = false;
let _wsReconnectTimer = null;
let _wsReconnectAttempts = 0;
const _WS_PATH = "/ws/orchestrator";
const _PORT_MIN = 5050;
const _PORT_MAX = 5059;

// ── Known STS extension tabs ───────────────────────────
// Maps a logical name to a URL pattern for quick lookup
const TAB_PATTERNS = {
  gemini: "*://gemini.google.com/*",
  grok: "*://grok.com/*",
};

// ── WebSocket Management ────────────────────────────────

function _tryPort(p) {
  return new Promise((resolve) => {
    const url = "ws://localhost:" + p + _WS_PATH;
    let ws;
    try { ws = new WebSocket(url); } catch (e) { resolve(null); return; }
    const timer = setTimeout(() => { try { ws.close(); } catch (e) {} resolve(null); }, 1500);
    ws.onopen = () => { clearTimeout(timer); resolve(ws); };
    ws.onerror = () => { clearTimeout(timer); resolve(null); };
  });
}

async function connectWS(manualUrl) {
  if (_ws && _wsConnected) return;
  if (_wsReconnectTimer) { clearTimeout(_wsReconnectTimer); _wsReconnectTimer = null; }

  let ws = null;

  if (manualUrl) {
    try { ws = await _tryPort(parseInt(manualUrl.match(/:(\d+)/)?.[1] || _PORT_MIN)); } catch (e) {}
  }

  if (!ws) {
    for (let p = _PORT_MIN; p <= _PORT_MAX; p++) {
      ws = await _tryPort(p);
      if (ws) break;
    }
  }

  if (!ws) {
    _wsReconnectAttempts++;
    const delay = Math.min(2000 * Math.pow(1.5, _wsReconnectAttempts), 30000);
    console.log("[STS Orchestrator] No server found, retry in " + Math.round(delay / 1000) + "s");
    _wsReconnectTimer = setTimeout(() => connectWS(), delay);
    _broadcastStatus();
    return;
  }

  _ws = ws;
  _wsConnected = true;
  _wsReconnectAttempts = 0;
  console.log("[STS Orchestrator] Connected to " + _ws.url);
  _broadcastStatus();

  // Announce ourselves
  sendWS({ type: "hello", extension: "orchestrator", version: "1.0.0" });

  _ws.onmessage = (ev) => {
    let msg;
    try { msg = JSON.parse(ev.data); } catch (e) { return; }
    console.log("[STS Orchestrator] ← ", msg);
    handleCommand(msg);
  };

  _ws.onclose = () => {
    console.log("[STS Orchestrator] WS closed");
    _ws = null;
    _wsConnected = false;
    _broadcastStatus();
    _wsReconnectTimer = setTimeout(() => connectWS(), 3000);
  };

  _ws.onerror = (e) => {
    console.log("[STS Orchestrator] WS error", e);
  };
}

function sendWS(payload) {
  if (_ws && _ws.readyState === WebSocket.OPEN) {
    _ws.send(JSON.stringify(payload));
  }
}

// ── Status broadcast (to popup) ─────────────────────────

let _popupPort = null;

chrome.runtime.onConnect.addListener((port) => {
  if (port.name !== "sts-orchestrator-popup") return;
  _popupPort = port;
  port.postMessage({ type: "STS_WS_STATUS", connected: _wsConnected });

  port.onDisconnect.addListener(() => { _popupPort = null; });

  port.onMessage.addListener((msg) => {
    if (msg.action === "STS_WS_RECONNECT") {
      if (_ws) { try { _ws.close(); } catch (e) {} }
      _ws = null; _wsConnected = false; _wsReconnectAttempts = 0;
      connectWS(msg.manualUrl || null);
    } else if (msg.action === "STS_LIST_TABS") {
      listTabs().then(tabs => port.postMessage({ type: "STS_TAB_LIST", tabs }));
    } else if (msg.action === "STS_FOCUS_TAB") {
      focusTab(msg.tabId);
    } else if (msg.action === "STS_FOCUS_BY_NAME") {
      focusByName(msg.name);
    }
  });
});

function _broadcastStatus() {
  if (_popupPort) {
    try { _popupPort.postMessage({ type: "STS_WS_STATUS", connected: _wsConnected }); } catch (e) {}
  }
}

// ── Tab Control Commands ────────────────────────────────

// List all open tabs with their id, title, url, and active state
async function listTabs() {
  const tabs = await chrome.tabs.query({});
  return tabs.map(t => ({
    id: t.id,
    windowId: t.windowId,
    title: t.title,
    url: t.url,
    active: t.active,
    favIconUrl: t.favIconUrl || "",
  }));
}

// Focus a specific tab by ID — activates the tab and focuses its window
async function focusTab(tabId) {
  try {
    const tab = await chrome.tabs.update(tabId, { active: true });
    await chrome.windows.update(tab.windowId, { focused: true });
    console.log("[STS Orchestrator] Focused tab " + tabId);
    sendWS({ type: "tab_focused", tabId, title: tab.title, url: tab.url });
    return { ok: true, tabId };
  } catch (e) {
    console.error("[STS Orchestrator] Failed to focus tab " + tabId, e);
    sendWS({ type: "error", command: "focus_tab", tabId, error: e.message });
    return { ok: false, error: e.message };
  }
}

// Focus a tab by logical name (e.g., "gemini", "grok") or URL substring
async function focusByName(name) {
  const pattern = TAB_PATTERNS[name.toLowerCase()];
  const query = pattern ? { url: pattern } : {};

  let tabs = await chrome.tabs.query(query);

  // If no pattern match, try a title/url substring search
  if (!tabs.length && !pattern) {
    const allTabs = await chrome.tabs.query({});
    const needle = name.toLowerCase();
    tabs = allTabs.filter(t =>
      (t.title && t.title.toLowerCase().includes(needle)) ||
      (t.url && t.url.toLowerCase().includes(needle))
    );
  }

  if (tabs.length > 0) {
    return focusTab(tabs[0].id);
  } else {
    console.log("[STS Orchestrator] No tab found for: " + name);
    sendWS({ type: "error", command: "focus_by_name", name, error: "No matching tab found" });
    return { ok: false, error: "No matching tab found" };
  }
}

// ── Screenshot any tab ─────────────────────────────────

async function screenshotTab(tabId, label) {
  label = label || "screenshot";
  try {
    let tab;
    if (tabId) {
      tab = await chrome.tabs.update(tabId, { active: true });
    } else {
      // Screenshot the currently active tab
      const [activeTab] = await chrome.tabs.query({ active: true, currentWindow: true });
      tab = activeTab;
    }
    if (!tab) {
      return { type: "screenshot_result", label, error: "No tab found", screenshot: null };
    }
    await chrome.windows.update(tab.windowId, { focused: true });
    await new Promise(r => setTimeout(r, 300));

    const dataUrl = await chrome.tabs.captureVisibleTab(tab.windowId, { format: "png" });
    console.log("[STS Orchestrator] Screenshot captured: " + label + " (tab " + tab.id + ")");
    return { type: "screenshot_result", label, error: null, screenshot: dataUrl, tabId: tab.id, title: tab.title };
  } catch (e) {
    return { type: "screenshot_result", label, error: e.message, screenshot: null };
  }
}

// ── Screenshot by name (gemini, grok, studio, or any URL substring) ──

async function screenshotByName(name, label) {
  const pattern = TAB_PATTERNS[name.toLowerCase()];
  let tabs;
  if (pattern) {
    tabs = await chrome.tabs.query({ url: pattern });
  }
  if (!tabs || !tabs.length) {
    const allTabs = await chrome.tabs.query({});
    const needle = name.toLowerCase();
    tabs = allTabs.filter(t =>
      (t.title && t.title.toLowerCase().includes(needle)) ||
      (t.url && t.url.toLowerCase().includes(needle))
    );
  }
  if (tabs.length > 0) {
    return screenshotTab(tabs[0].id, label || name);
  }
  return { type: "screenshot_result", label: label || name, error: "No tab found for: " + name, screenshot: null };
}

// ── Diagnose all STS extensions ────────────────────────

async function diagnoseAll() {
  const report = {
    type: "diagnose_report",
    ts: new Date().toISOString(),
    orchestrator: {
      wsConnected: _wsConnected,
      wsUrl: _ws ? _ws.url : null,
    },
    tabs: await listTabs(),
    extensions: {},
  };

  // Check which STS extension tabs are open
  for (const [name, pattern] of Object.entries(TAB_PATTERNS)) {
    const tabs = await chrome.tabs.query({ url: pattern });
    report.extensions[name] = {
      tabsOpen: tabs.length,
      tabs: tabs.map(t => ({ id: t.id, title: t.title, url: t.url, active: t.active })),
    };
  }

  // Also check for Studio tab
  const allTabs = await chrome.tabs.query({});
  const studioTabs = allTabs.filter(t =>
    (t.url && (t.url.includes("localhost:5174") || t.url.includes("localhost:5050") || t.url.includes("localhost:5173"))) ||
    (t.title && t.title.includes("ScriptToScene"))
  );
  report.extensions.studio = {
    tabsOpen: studioTabs.length,
    tabs: studioTabs.map(t => ({ id: t.id, title: t.title, url: t.url, active: t.active })),
  };

  return report;
}

// ── Handle incoming WS commands from backend ────────────

async function handleCommand(msg) {
  const { command, request_id } = msg;
  let result;

  switch (command) {
    case "list_tabs":
      result = await listTabs();
      sendWS({ type: "tab_list", request_id, tabs: result });
      break;

    case "focus_tab":
      result = await focusTab(msg.tabId || msg.tab_id);
      sendWS({ type: "result", request_id, ...result });
      break;

    case "focus_by_name":
      result = await focusByName(msg.name);
      sendWS({ type: "result", request_id, ...result });
      break;

    case "screenshot":
      // screenshot by tab ID or by name
      if (msg.name) {
        result = await screenshotByName(msg.name, msg.label);
      } else {
        result = await screenshotTab(msg.tabId || msg.tab_id, msg.label);
      }
      sendWS({ ...result, request_id });
      break;

    case "diagnose":
      result = await diagnoseAll();
      sendWS({ ...result, request_id });
      break;

    case "ping":
      sendWS({ type: "pong", request_id });
      break;

    default:
      console.log("[STS Orchestrator] Unknown command:", command);
      sendWS({ type: "error", request_id, error: "Unknown command: " + command });
  }
}

// ── Startup ─────────────────────────────────────────────

connectWS();
