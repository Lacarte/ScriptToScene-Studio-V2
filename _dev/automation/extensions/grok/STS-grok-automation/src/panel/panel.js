// ── STS Grok Automation — Side Panel ─────────────────────

// ── DOM ──────────────────────────────────────────────────
const statusBadge = document.getElementById("status");
const connBar = document.getElementById("conn-bar");
const connText = document.getElementById("conn-text");
const wsBar = document.getElementById("ws-bar");
const wsText = document.getElementById("ws-text");
const headerDot = document.getElementById("header-dot");
const projectBadge = document.getElementById("project-badge");
const connectionInfo = document.getElementById("connection-info");
const btnPing = document.getElementById("btn-ping");
const btnConnect = document.getElementById("btn-connect");
const btnDisconnect = document.getElementById("btn-disconnect");
const btnClear = document.getElementById("btn-clear");
const btnStop = document.getElementById("btn-stop");
const btnRetryAll = document.getElementById("btn-retry-all");
const wsUrlInput = document.getElementById("ws-url");
const jobList = document.getElementById("job-list");
const statQueued = document.getElementById("stat-queued");
const statActive = document.getElementById("stat-active");
const statDone = document.getElementById("stat-done");
const statErrors = document.getElementById("stat-errors");
const overallWrap = document.getElementById("overall-wrap");
const overallFill = document.getElementById("overall-fill");
const overallLbl = document.getElementById("overall-lbl");

// ── Blocked overlay ─────────────────────────────────────
const blockedOverlay = document.getElementById("blocked-overlay");
const appEl = document.getElementById("app");

function isAllowedUrl(url) {
  if (!url) return false;
  if (url === "about:blank") return true;
  try {
    const u = new URL(url);
    return u.hostname === "grok.com" || u.hostname.endsWith(".grok.com");
  } catch { return false; }
}

async function checkPageAllowed() {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    const allowed = isAllowedUrl(tab?.url);
    blockedOverlay.style.display = allowed ? "none" : "";
    appEl.classList.toggle("blurred", !allowed);
  } catch {
    blockedOverlay.style.display = "";
    appEl.classList.add("blurred");
  }
}

// Check on load and on tab changes
checkPageAllowed();
setInterval(checkPageAllowed, 2000);
chrome.tabs.onActivated?.addListener(() => setTimeout(checkPageAllowed, 200));
chrome.tabs.onUpdated?.addListener((_, info) => { if (info.status === "complete") setTimeout(checkPageAllowed, 200); });

// Link handlers in overlay
document.getElementById("open-grok")?.addEventListener("click", (e) => {
  e.preventDefault();
  chrome.tabs.create({ url: "https://grok.com/imagine" });
});
document.getElementById("open-blank")?.addEventListener("click", (e) => {
  e.preventDefault();
  chrome.tabs.create({ url: "about:blank" });
});

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// ── State ───────────────────────────────────────────────
let contentScriptReady = false;
let ws = null;
let wsConnected = false;
let reconnectTimer = null;
let reconnectDelay = 1000;
let autoReconnect = true;
let stopRequested = false;
const MAX_RECONNECT_DELAY = 30000;
const MAX_RETRIES = 2;
const RETRY_DELAY = 5000;
const BETWEEN_JOBS_DELAY = 3000;
const jobs = [];
const pendingMessages = [];

// ── Tabs ────────────────────────────────────────────────
document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
    document.querySelectorAll(".tab-content").forEach((c) => (c.style.display = "none"));
    tab.classList.add("active");
    document.getElementById(`tab-${tab.dataset.tab}`).style.display = "";
  });
});

// ── Page Detection ──────────────────────────────────────
async function checkGrokPage() {
  try {
    const tab = await getPreferredGrokTab();
    if (!tab?.id) { setGrokStatus("offline"); contentScriptReady = false; return; }

    const wasReady = contentScriptReady;
    const page = await probeGrokTab(tab.id);
    contentScriptReady = !!page?.isImaginePage;
    setGrokStatus(getGrokStatus(tab, page));

    if (contentScriptReady && !wasReady) processQueue();
  } catch { setGrokStatus("offline"); contentScriptReady = false; }
}

async function getPreferredGrokTab() {
  const [activeTab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (activeTab?.url?.includes("grok.com")) return activeTab;

  const grokTabs = await chrome.tabs.query({ url: "*://grok.com/*" });
  const imagineTab = grokTabs.find((tab) => tab.url?.includes("/imagine"));
  return imagineTab || grokTabs[0] || null;
}

async function probeGrokTab(tabId) {
  if (!tabId) return null;
  try {
    return await chrome.tabs.sendMessage(tabId, { type: "CHECK_PAGE" });
  } catch {
    return null;
  }
}

function getGrokStatus(tab, page) {
  if (!tab?.id) return "offline";
  if (page?.isImaginePage) return "connected";
  if (tab.url?.includes("/imagine")) return "needs-reload";
  if (tab.url?.includes("grok.com")) return "needs-imagine";
  return "offline";
}

function setGrokStatus(state) {
  if (state === "connected") {
    statusBadge.textContent = "Ready"; statusBadge.className = "badge online";
    connBar.className = "pill ok"; connText.textContent = "Grok ready";
    headerDot.className = "dot on";
  } else if (state === "needs-imagine") {
    statusBadge.textContent = "Navigate"; statusBadge.className = "badge warn";
    connBar.className = "pill wrn"; connText.textContent = "Open grok.com/imagine";
    headerDot.className = "dot warn";
  } else if (state === "needs-reload") {
    statusBadge.textContent = "Reload"; statusBadge.className = "badge warn";
    connBar.className = "pill wrn"; connText.textContent = "Reload grok tab";
    headerDot.className = "dot warn";
  } else {
    statusBadge.textContent = "Offline"; statusBadge.className = "badge offline";
    connBar.className = "pill err"; connText.textContent = "No Grok tab";
    headerDot.className = "dot off";
  }
}
setInterval(checkGrokPage, 2000);
checkGrokPage();

// ── WebSocket ───────────────────────────────────────────
function connectWS() {
  const url = wsUrlInput.value.trim();
  if (!url) return;

  autoReconnect = true;
  chrome.storage.local.set({ wsUrl: url });

  if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
  if (ws) {
    try {
      ws.onopen = null;
      ws.onmessage = null;
      ws.onclose = null;
      ws.onerror = null;
      ws.close();
    } catch {}
  }

  const socket = new WebSocket(url);
  ws = socket;
  wsConnected = false;
  wsBar.className = "pill wrn";
  wsText.textContent = "WS connecting";

  socket.onopen = () => {
    if (ws !== socket) {
      try { socket.close(); } catch {}
      return;
    }

    wsConnected = true; reconnectDelay = 1000;
    wsBar.className = "pill ok"; wsText.textContent = "Backend OK";
    try { socket.send(JSON.stringify({ type: "EXTENSION_READY" })); } catch {}
    flushPendingMessages(socket);
  };

  socket.onmessage = (e) => {
    if (ws !== socket) return;
    try { handleBackendMessage(JSON.parse(e.data)); } catch {}
  };

  socket.onclose = () => {
    if (ws !== socket) return;

    ws = null;
    wsConnected = false;
    wsBar.className = "pill err"; wsText.textContent = "WS offline";
    if (autoReconnect) scheduleReconnect();
  };

  socket.onerror = () => {
    if (ws !== socket) return;
    wsBar.className = "pill wrn";
    wsText.textContent = "WS retrying";
  };
}

function disconnectWS() {
  autoReconnect = false;
  if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
  if (ws) try { ws.close(); } catch {}
  ws = null; wsConnected = false;
  wsBar.className = "pill err"; wsText.textContent = "WS offline";
}

function scheduleReconnect() {
  if (reconnectTimer) clearTimeout(reconnectTimer);
  reconnectTimer = setTimeout(() => {
    connectWS();
    reconnectDelay = Math.min(reconnectDelay * 2, MAX_RECONNECT_DELAY);
  }, reconnectDelay);
}

function sendToBackend(msg) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    try { ws.send(JSON.stringify(msg)); } catch (e) { console.warn("[STS] WS send failed:", e.message); pendingMessages.push(msg); }
  } else {
    pendingMessages.push(msg);
  }
}

function flushPendingMessages(socket = ws) {
  while (pendingMessages.length > 0 && socket && socket === ws && socket.readyState === WebSocket.OPEN) {
    const msg = pendingMessages.shift();
    try { socket.send(JSON.stringify(msg)); } catch { pendingMessages.unshift(msg); break; }
  }
}

// ── Backend Messages ────────────────────────────────────
function handleBackendMessage(msg) {
  if (msg.type === "ANIMATE_JOB") enqueueJob(msg);
}

// ── Job Queue ───────────────────────────────────────────
function enqueueJob(msg) {
  const existing = jobs.find((j) => j.jobId === msg.jobId && j.sceneIndex === msg.sceneIndex);
  if (existing) {
    console.log(`[STS] Duplicate job ignored: ${msg.jobId}#${msg.sceneIndex}`);
    return;
  }

  const images = Array.isArray(msg.images)
    ? msg.images.filter(Boolean)
    : (msg.image ? [msg.image] : []);

  jobs.push({
    jobId: msg.jobId, projectId: msg.projectId, sceneIndex: msg.sceneIndex,
    prompt: msg.prompt || "", image: msg.image || images[0] || null, images,
    mode: msg.mode || "imageToVideo", duration: msg.duration || "6s",
    aspectRatio: msg.aspectRatio || "9:16",
    status: "queued", percentage: 0, error: null, startedAt: null,
    retries: 0,
  });
  // Show project badge
  if (msg.projectId) {
    projectBadge.textContent = msg.projectId;
    projectBadge.classList.add("show");
  }
  // Show stop button
  btnStop.style.display = "";
  stopRequested = false;
  updateUI();
  processQueue();
}

let processing = false;

// Transient errors that warrant a retry
function isTransientError(err) {
  const msg = (err || "").toLowerCase();
  return msg.includes("receiving end does not exist") ||
    msg.includes("asynchronous response") ||
    msg.includes("moved to back") ||
    msg.includes("extension port") ||
    msg.includes("animator busy") ||
    msg.includes("could not establish connection") ||
    msg.includes("message port closed") ||
    msg.includes("no grok.com tab");
}

async function ensureContentScript(freshStart = false) {
  for (let attempt = 0; attempt < 3; attempt++) {
    let tabId = null;
    try {
      const resp = await chrome.runtime.sendMessage({ type: "ENSURE_GROK_TAB", freshStart });
      tabId = resp?.tabId || null;
    } catch {}

    for (let poll = 0; poll < 10; poll++) {
      let tab = null;
      try {
        tab = tabId ? await chrome.tabs.get(tabId) : await getPreferredGrokTab();
      } catch {}

      const page = tab?.id ? await probeGrokTab(tab.id) : null;
      contentScriptReady = !!page?.isImaginePage;
      setGrokStatus(getGrokStatus(tab, page));
      if (contentScriptReady) return tab;

      await sleep(1000);
    }
  }
  return null;
}

async function navigateToImagine(tabId) {
  // Click the sidebar /imagine link via content script (SPA navigation, no reload)
  console.log("[STS] Clicking /imagine nav link...");
  try {
    const resp = await chrome.tabs.sendMessage(tabId, { type: "NAVIGATE_IMAGINE" });
    if (resp?.success) {
      contentScriptReady = true;
      setGrokStatus("connected");
      console.log("[STS] /imagine page ready (SPA)");
      return true;
    }
    console.warn("[STS] Nav click failed:", resp?.error);
  } catch (e) {
    console.warn("[STS] Nav message failed:", e.message);
  }

  // Fallback — full page navigation if click didn't work
  console.log("[STS] Falling back to full navigation...");
  try {
    await chrome.tabs.update(tabId, { url: "https://grok.com/imagine" });
  } catch {
    contentScriptReady = false;
    const tab = await ensureContentScript();
    return !!tab?.id;
  }

  for (let i = 0; i < 20; i++) {
    await sleep(1500);
    const page = await probeGrokTab(tabId);
    if (page?.isImaginePage) {
      contentScriptReady = true;
      setGrokStatus("connected");
      return true;
    }
  }

  contentScriptReady = false;
  const tab = await ensureContentScript();
  return !!tab?.id;
}

async function processQueue() {
  if (processing || stopRequested) return;
  const next = jobs.find((j) => j.status === "queued");
  if (!next) return;

  // ── Step 0: Ensure /imagine is loaded and ready ──
  contentScriptReady = false;
  let tab = await ensureContentScript(true);
  if (!tab?.id) { setTimeout(processQueue, 5000); return; }

  processing = true;
  next.status = "processing";
  next.percentage = 0;
  next.startedAt = Date.now();
  next.error = null;

  updateUI();

  let result = null;
  let error = null;

  // ── Step 1: Generate — send ANIMATE to content script ──
  try {
    if (!tab?.id) throw new Error("No grok.com tab");

    result = await chrome.tabs.sendMessage(tab.id, {
      type: "ANIMATE", jobId: next.jobId, sceneIndex: next.sceneIndex,
      prompt: next.prompt, image: next.image, images: next.images, mode: next.mode,
      duration: next.duration, aspectRatio: next.aspectRatio,
    });
  } catch (err) {
    error = err.message || String(err);
  }

  if (result?.success) {
    next.percentage = 100;
    updateUI();
    sendToBackend({ type: "ANIMATE_RESULT", jobId: next.jobId, sceneIndex: next.sceneIndex, success: true, videoUrl: result.videoUrl || null });

    next.status = "done";
    updateUI();

    // ── Step 3: Navigate to /imagine and wait for page ready ──
    const hasMoreQueued = jobs.some((j) => j !== next && j.status === "queued");
    if (hasMoreQueued && !stopRequested) {
      contentScriptReady = false;
      await sleep(2000);
    }
  } else {
    const errMsg = error || result?.error || "Unknown error";

    // Retry on transient errors
    if (isTransientError(errMsg) && next.retries < MAX_RETRIES) {
      next.retries++;
      next.status = "queued";
      next.error = null;
      next.percentage = 0;
      console.log(`[STS] Retrying job ${next.jobId} scene ${next.sceneIndex} (attempt ${next.retries}/${MAX_RETRIES}): ${errMsg}`);
      processing = false;
      updateUI();
      contentScriptReady = false;
      setTimeout(processQueue, RETRY_DELAY);
      return;
    }

    next.status = "error";
    next.error = next.retries > 0 ? `${errMsg} (after ${next.retries} retries)` : errMsg;
    sendToBackend({ type: "ANIMATE_RESULT", jobId: next.jobId, sceneIndex: next.sceneIndex, success: false, error: next.error });
  }

  processing = false;
  updateUI();

  // Check if batch complete
  const remaining = jobs.filter((j) => j.status === "queued").length;
  if (remaining === 0) {

    btnStop.style.display = "none";
  }

  // ── Step 4: Proceed to next job ──
  if (!stopRequested && remaining > 0) processQueue();
}

// ── Progress from content script ────────────────────────
chrome.runtime.onMessage.addListener((msg) => {
  if (msg.type === "ANIMATE_PROGRESS") {
    const job = jobs.find((j) => j.jobId === msg.jobId && j.sceneIndex === msg.sceneIndex);
    if (job) {
      job.percentage = msg.percentage || 0;
      renderJobs();
      sendToBackend({ type: "ANIMATE_PROGRESS", jobId: msg.jobId, sceneIndex: msg.sceneIndex, percentage: msg.percentage });
    }
  }
});

// ── Stop handler ────────────────────────────────────────
btnStop.addEventListener("click", () => {
  stopRequested = true;
  // Mark all queued as cancelled
  jobs.forEach((j) => {
    if (j.status === "queued") { j.status = "error"; j.error = "Stopped by user"; }
  });
  stopElapsed();
  btnStop.style.display = "none";
  updateUI();
});

// ── UI ──────────────────────────────────────────────────
function updateUI() {
  const q = jobs.filter((j) => j.status === "queued").length;
  const a = jobs.filter((j) => j.status === "processing").length;
  const d = jobs.filter((j) => j.status === "done").length;
  const e = jobs.filter((j) => j.status === "error").length;
  statQueued.textContent = q;
  statActive.textContent = a;
  statDone.textContent = d;
  statErrors.textContent = e;
  btnRetryAll.style.display = e > 0 ? "" : "none";

  // Overall progress
  const total = jobs.length;
  const completed = d + e;
  if (total > 0) {
    overallWrap.style.display = "";
    overallFill.style.width = `${Math.round(100 * completed / total)}%`;
    overallLbl.textContent = `${completed}/${total}`;
  } else {
    overallWrap.style.display = "none";
  }

  renderJobs();
}

function renderJobs() {
  if (jobs.length === 0) {
    jobList.innerHTML = `<div class="empty"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" opacity=".2"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg><span>Waiting for jobs...</span></div>`;
    return;
  }

  jobList.innerHTML = jobs.map((job) => {
    const cls = job.status === "processing" ? "is-active" : job.status === "error" ? "is-error" : job.status === "done" ? "is-done" : "";
    const sClass = job.status === "done" ? "text-green" : job.status === "error" ? "text-red" : job.status === "processing" ? "text-accent" : "text-muted";

    let sLabel;
    if (job.status === "processing") {
      sLabel = `${job.percentage}%`;
    } else if (job.status === "done") {
      sLabel = "✓";
    } else if (job.status === "error") {
      sLabel = "✗";
    } else {
      sLabel = "QUEUE";
    }

    // Elapsed for this job
    let elapsed = "";
    if (job.startedAt && (job.status === "processing" || job.status === "done")) {
      const end = job.status === "done" ? Date.now() : Date.now();
      const s = Math.floor((end - job.startedAt) / 1000);
      elapsed = s >= 60 ? `${Math.floor(s/60)}m${s%60}s` : `${s}s`;
    }

    const prompt = esc(job.prompt.length > 60 ? job.prompt.slice(0, 60) + "…" : job.prompt);
    const thumb = job.image
      ? `<img class="job-thumb" src="${job.image}" />`
      : `<div class="job-thumb job-thumb--empty"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M21 15l-5-5L5 21"/></svg></div>`;

    return `<div class="row ${cls}">
      ${thumb}
      <div class="row-num">${job.sceneIndex}</div>
      <div class="row-body">
        <div class="row-top">
          <span class="row-prompt">${prompt}</span>
          <span class="row-status ${sClass}">${sLabel}</span>
        </div>
        <div class="row-meta">${job.projectId || ""} · #${job.sceneIndex} · ${job.mode.replace("To", "→")} · ${job.duration}${elapsed ? ` · ${elapsed}` : ""}</div>
        ${job.status === "processing" ? `<div class="pbar"><div class="pfill" style="width:${job.percentage}%"></div></div>` : ""}
        ${job.error ? `<div class="row-error">${esc(job.error)}<button class="btn-retry" data-scene="${job.sceneIndex}" data-job="${job.jobId}" title="Retry">↻</button></div>` : ""}
      </div>
    </div>`;
  }).join("");
}

function esc(s) { const d = document.createElement("div"); d.textContent = s; return d.innerHTML; }

// ── Retry handlers ──────────────────────────────────────
jobList.addEventListener("click", (e) => {
  const btn = e.target.closest(".btn-retry");
  if (!btn) return;
  const jobId = btn.dataset.job;
  const sceneIndex = parseInt(btn.dataset.scene, 10);
  retryJob(jobId, sceneIndex);
});

function retryJob(jobId, sceneIndex) {
  const job = jobs.find((j) => j.jobId === jobId && j.sceneIndex === sceneIndex);
  if (!job || job.status !== "error") return;
  job.status = "queued";
  job.error = null;
  job.percentage = 0;
  job.retries = 0;
  job.startedAt = null;
  stopRequested = false;
  btnStop.style.display = "";
  updateUI();
  processQueue();
}

function retryAllFailed() {
  const failed = jobs.filter((j) => j.status === "error");
  if (failed.length === 0) return;
  for (const job of failed) {
    job.status = "queued";
    job.error = null;
    job.percentage = 0;
    job.retries = 0;
    job.startedAt = null;
  }
  stopRequested = false;
  btnStop.style.display = "";

  updateUI();
  processQueue();
}

// ── Button Handlers ─────────────────────────────────────
btnConnect.addEventListener("click", connectWS);
btnDisconnect.addEventListener("click", disconnectWS);

btnPing.addEventListener("click", async () => {
  connectionInfo.textContent = "Pinging...";
  try {
    const grokTabs = await chrome.tabs.query({ url: "*://grok.com/*" });
    if (!grokTabs[0]?.id) { connectionInfo.textContent = "No grok.com tab"; return; }
    const t0 = performance.now();
    const r = await chrome.tabs.sendMessage(grokTabs[0].id, { type: "PING" });
    connectionInfo.textContent = r?.pong ? `OK ${Math.round(performance.now() - t0)}ms` : "No response";
  } catch (e) { connectionInfo.textContent = e.message; }
});

btnRetryAll.addEventListener("click", () => retryAllFailed());

btnClear.addEventListener("click", () => {
  const keep = jobs.filter((j) => j.status === "queued" || j.status === "processing");
  jobs.length = 0;
  jobs.push(...keep);
  if (jobs.length === 0) { projectBadge.classList.remove("show"); }
  updateUI();
});

// ── Init ────────────────────────────────────────────────
chrome.storage.local.get("wsUrl", (data) => {
  if (data.wsUrl) wsUrlInput.value = data.wsUrl;
  connectWS();
});
