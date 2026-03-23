console.log('=== ScriptToScene Assets Synchronizer v2 (Grok) ===');
if (window.__stsSyncActive) {
  console.log('Synchronizer already running');
  automaNextBlock();
  return;
}
window.__stsSyncActive = true;

const S = {
  studioUrl: localStorage.getItem('sts-url') || 'http://localhost:5050',
  scrollRows: parseInt(localStorage.getItem('sts-scroll-rows')) || 15,
  connected: false, autoSync: true, autoType: localStorage.getItem('sts-auto-type') === 'true', collapsed: true,
  showSettings: false, activeTab: 'typing',
  lastPoll: 0, projectId: null, arguments: '', aspectRatio: '9:16', grokMode: 'video', grokQuality: '480p', grokDuration: '6s',
  scenes: {}, sentScenes: {},
  pollInterval: 5000,
  jobComplete: false,
  _fetchErrors: 0,
  typing: {
    active: false,
    starting: false,
    queue: [],
    runId: 0,
    currentIndex: -1,
    typedCount: 0,
    batchCount: 0,
    countdown: 0,
    countdownType: '',
    stopRequested: false,
    autoPaused: false,
    nextAutoStartAt: 0,
  },
  ws: null,
  wsConnected: false,
  wsReconnectTimer: null,
};

// ── WebSocket Connection ──────────────────────────────────────
function connectWS() {
  if (S.ws && (S.ws.readyState === WebSocket.OPEN || S.ws.readyState === WebSocket.CONNECTING)) return;
  const wsUrl = S.studioUrl.replace(/^http/, 'ws') + '/ws/animator';
  console.log('[STS WS] Connecting to', wsUrl);
  try {
    S.ws = new WebSocket(wsUrl);
  } catch (e) {
    console.warn('[STS WS] Connection failed (CSP?):', e.message);
    S.wsConnected = false;
    scheduleWSReconnect();
    return;
  }
  S.ws.onopen = () => {
    console.log('[STS WS] Connected');
    S.wsConnected = true;
    S._fetchErrors = 0;
    S.connected = true;
    if (S.ws.readyState === WebSocket.OPEN) {
      S.ws.send(JSON.stringify({ type: 'EXTENSION_READY', source: 'automa-sync' }));
    }
    render();
  };
  S.ws.onmessage = (evt) => {
    try {
      const msg = JSON.parse(evt.data);
      handleWSMessage(msg);
    } catch (e) {
      console.warn('[STS WS] Bad message:', e);
    }
  };
  S.ws.onclose = () => {
    console.log('[STS WS] Disconnected');
    S.wsConnected = false;
    S.ws = null;
    render();
    scheduleWSReconnect();
  };
  S.ws.onerror = () => {
    S.wsConnected = false;
  };
}

function scheduleWSReconnect() {
  if (S.wsReconnectTimer) return;
  S.wsReconnectTimer = setTimeout(() => {
    S.wsReconnectTimer = null;
    connectWS();
  }, 5000);
}

function sendWS(msg) {
  if (S.ws && S.ws.readyState === WebSocket.OPEN) {
    try { S.ws.send(JSON.stringify(msg)); } catch (e) { console.warn('[STS WS] Send failed:', e.message); }
  }
}

function handleWSMessage(msg) {
  switch (msg.type) {
    case 'ANIMATE_JOB': {
      // Receive a job from the backend — add to typing queue
      const item = {
        projectId: msg.projectId,
        sceneIndex: msg.sceneIndex,
        prompt: msg.prompt,
        image: msg.image || null,
        mode: msg.mode || S.grokMode,
        duration: msg.duration || S.grokDuration,
        aspectRatio: msg.aspectRatio || S.aspectRatio,
        jobId: msg.jobId,
        status: 'queued',
        videoUrl: null,
        error: null,
      };
      S.projectId = msg.projectId;
      // Add to typing queue if not already there
      const exists = S.typing.queue.find(q => q.jobId === msg.jobId);
      if (!exists) {
        S.typing.queue.push({
          scene: String(msg.sceneIndex),
          displayPrompt: msg.prompt,
          fullPrompt: msg.prompt,
          prompt: msg.prompt,
          selected: true,
          status: 'queued',
          jobId: msg.jobId,
          sceneIndex: msg.sceneIndex,
          projectId: msg.projectId,
          image: msg.image || null,
          imageUrl: msg.image || null,
          mode: msg.mode || S.grokMode,
          duration: msg.duration || S.grokDuration,
          aspectRatio: msg.aspectRatio || S.aspectRatio,
        });
      }
      render();
      console.log(`[STS WS] Job received: ${msg.projectId} scene ${msg.sceneIndex}`);
      break;
    }
    case 'GRABBER_START': {
      // Receive full grabber batch from backend
      S.projectId = msg.projectId;
      S.aspectRatio = msg.aspectRatio || S.aspectRatio;
      S.grokMode = msg.grokMode || S.grokMode;
      S.grokDuration = msg.grokDuration || S.grokDuration;
      if (msg.autoType !== undefined) S.autoType = !!msg.autoType;
      renderAutoType();

      const scenes = msg.scenes || [];
      console.log(`[STS WS] Grabber started: ${msg.projectId} — ${scenes.length} scenes`);

      scenes.forEach(sc => {
        const k = String(sc.scene);
        // Image: prefer base64 data, fall back to URL
        const imgData = sc.image || (sc.image_url ? S.studioUrl + sc.image_url : null);
        // Sync tab
        if (!S.scenes[k]) {
          S.scenes[k] = { prompt: sc.prompt, status: 'pending', urls: [], fileCount: 0, imageUrl: imgData };
        } else if (imgData && !S.scenes[k].imageUrl) {
          S.scenes[k].imageUrl = imgData;
        }
        // Typing queue — add or update existing with image
        const existing = S.typing.queue.find(q => q.scene === k);
        if (!existing) {
          S.typing.queue.push({
            scene: k,
            displayPrompt: sc.prompt,
            fullPrompt: sc.prompt + ' [' + msg.projectId + '|' + sc.scene + ']',
            selected: true,
            status: 'queued',
            imageUrl: imgData,
          });
        } else if (imgData && !existing.imageUrl) {
          existing.imageUrl = imgData;
        }
      });

      render();

      // Auto-start typing if enabled
      if (S.autoType && !S.typing.active && !S.typing.starting) {
        console.log('[STS WS] Auto-starting typing from grabber push');
        setTimeout(() => startTyping(), 1000);
      }
      break;
    }
    case 'PING':
      sendWS({ type: 'PONG' });
      break;
  }
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

function shouldStopTyping(runId) {
  if (typeof runId === 'number') {
    return !S.typing.active || S.typing.stopRequested || S.typing.runId !== runId;
  }
  return !S.typing.active || S.typing.stopRequested;
}

function normalizeText(value) {
  return String(value || '').replace(/\s+/g, ' ').trim();
}

function isPendingGrabberUrl(url) {
  return /\/api\/assets\/grabber\/pending(?:$|\?)/.test(String(url || ''));
}

function isNoPendingGrabberPayload(payload) {
  if (!payload) return false;
  var text = '';
  if (typeof payload === 'string') text = payload;
  else if (payload && typeof payload === 'object') text = payload.error || payload.message || '';
  return /no pending grabber jobs/i.test(String(text || ''));
}

function buildFetchResponse(result, status, quiet) {
  return {
    ok: status >= 200 && status < 300,
    status: status,
    quiet: !!quiet,
    json: function() { return Promise.resolve(result); },
    text: function() { return Promise.resolve(typeof result === 'string' ? result : JSON.stringify(result)); },
  };
}
// CSP workaround: Grok blocks fetch() to localhost via Content Security Policy.
// automaFetch(type, {url, method, body, headers}) bypasses CSP from extension background.
// Includes retry logic (3 attempts, 2s backoff) and error spam suppression.
async function _fetch(url, opts) {
  if (typeof automaFetch !== 'undefined') {
    var maxRetries = 3;
    var retryDelay = 2000;
    for (var attempt = 0; attempt < maxRetries; attempt++) {
      try {
        var resource = { url: url };
        if (opts && opts.method) resource.method = opts.method;
        if (opts && opts.body) resource.body = opts.body;
        if (opts && opts.headers) resource.headers = opts.headers;
        var raw = await automaFetch('json', resource);
        var result = raw;
        if (raw && typeof raw === 'object' && 'success' in raw) {
          if (!raw.success) {
            S._fetchErrors = 0;
            if (isPendingGrabberUrl(url) && isNoPendingGrabberPayload(raw.response || raw)) {
              return buildFetchResponse(raw.response || raw, 404, true);
            }
            return buildFetchResponse(raw, raw.statusCode || raw.status || 0, false);
          }
          result = raw.response !== undefined ? raw.response : raw;
        }
        var hasError = result && typeof result === 'object' && result.error && !result.projectId;
        if (hasError && isPendingGrabberUrl(url) && isNoPendingGrabberPayload(result)) {
          S._fetchErrors = 0;
          return buildFetchResponse(result, 404, true);
        }
        S._fetchErrors = 0;
        return buildFetchResponse(result, hasError ? 404 : 200, false);
      } catch(e) {
        var errMsg = e && e.message ? e.message : String(e);
        if (isPendingGrabberUrl(url) && /not found/i.test(errMsg)) {
          S._fetchErrors = 0;
          return buildFetchResponse({ error: 'No pending grabber jobs' }, 404, true);
        }
        S._fetchErrors++;
        if (S._fetchErrors <= 1 || S._fetchErrors % 10 === 0) {
          console.error('automaFetch error (attempt ' + (attempt + 1) + '/' + maxRetries + '):', errMsg);
        }
        if (attempt < maxRetries - 1) {
          await sleep(retryDelay * (attempt + 1));
          continue;
        }
        return buildFetchResponse({ error: errMsg }, 0, false);
      }
    }
  }
  return fetch(url, opts);
}


// ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ Grok DOM Helpers (learned from Grok Automation extension) ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬

// Simulate a real click with full pointer event sequence (React/Radix need this)
function simulateClick(el) {
  if (!el) return;
  var events = ['pointerover','mouseover','pointerdown','mousedown','pointerup','mouseup','click'];
  for (var i = 0; i < events.length; i++) {
    el.dispatchEvent(new MouseEvent(events[i], { bubbles: true, cancelable: true, composed: true, view: window, detail: 1 }));
  }
}

// Check if element is visible and interactable
function isElReady(el) {
  if (!el) return false;
  var rect = el.getBoundingClientRect();
  if (rect.width === 0 || rect.height === 0) return false;
  var style = window.getComputedStyle(el);
  if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
  return true;
}

// Wait for element to appear in DOM and be visible
async function waitForEl(selector, timeoutMs, pollMs) {
  timeoutMs = timeoutMs || 10000;
  pollMs = pollMs || 300;
  var start = Date.now();
  while (Date.now() - start < timeoutMs) {
    var el = document.querySelector(selector);
    if (el && isElReady(el)) return el;
    await sleep(pollMs);
  }
  return null;
}

// Wait for element to disappear from DOM
async function waitForElGone(selector, timeoutMs, pollMs) {
  timeoutMs = timeoutMs || 30000;
  pollMs = pollMs || 500;
  var start = Date.now();
  while (Date.now() - start < timeoutMs) {
    var el = document.querySelector(selector);
    if (!el || !isElReady(el)) return true;
    await sleep(pollMs);
  }
  return false;
}

// Parse SVG circular progress (stroke-dasharray / stroke-dashoffset)
function parseSvgProgress() {
  var circles = document.querySelectorAll('svg circle[stroke-dasharray]');
  for (var i = 0; i < circles.length; i++) {
    var da = circles[i].getAttribute('stroke-dasharray') || '';
    var off = circles[i].getAttribute('stroke-dashoffset') || '';
    var circumference = parseFloat(da.split(' ')[0]);
    var offset = parseFloat(off);
    if (!isNaN(circumference) && !isNaN(offset) && circumference > 0) {
      var pct = Math.round(100 * (1 - offset / circumference));
      return Math.max(0, Math.min(100, pct));
    }
  }
  return -1;
}

// ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ Inject UI ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬
const root = document.createElement('div');
root.id = 'sts-sync';
root.innerHTML = `
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@300;400;500;600&display=swap');
  #sts-sync * { box-sizing: border-box; }
  #sts-sync {
    --bg: rgba(11,15,20,0.97);
    --bg-raised: rgba(19,26,36,0.98);
    --bg-hover: rgba(255,255,255,0.03);
    --border: #1a2535;
    --border-active: #243040;
    --text: #dce4ec;
    --text-dim: #8899aa;
    --text-muted: #5e7080;
    --accent: #4ECDC4;
    --accent-hover: #5edfd6;
    --accent-glow: rgba(78,205,196,0.20);
    --accent-bg: rgba(78,205,196,0.08);
    --green: #4ECDC4;
    --green-bg: rgba(78,205,196,0.10);
    --amber: #FFB347;
    --amber-bg: rgba(255,179,71,0.10);
    --red: #FF6B6B;
    --red-bg: rgba(255,107,107,0.10);
    --info: #56CCF2;
    --mono: 'JetBrains Mono', monospace;
    --sans: 'Inter', system-ui, sans-serif;
    --display: 'Inter', system-ui, sans-serif;
    --radius: 12px;
    --radius-sm: 8px;
    position: fixed; top: 0; bottom: 0; right: 0; z-index: 999999;
    font-family: var(--sans);
    font-size: 13px; color: var(--text); line-height: 1.5;
  }

  /* ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ Collapsed Pill ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ */
  .sts-pill {
    display: flex; align-items: center; gap: 12px;
    padding: 12px 20px;
    background: var(--bg);
    border: 1.5px solid rgba(255,255,255,0.10);
    border-radius: 100px;
    cursor: pointer;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    box-shadow: 0 4px 24px rgba(0,0,0,0.4), 0 0 0 1px rgba(255,255,255,0.02) inset;
    /* user-select: none; */
    backdrop-filter: blur(20px) saturate(1.5);
  }
  .sts-pill:hover {
    border-color: var(--accent);
    box-shadow: 0 4px 24px rgba(0,0,0,0.4), 0 0 20px var(--accent-glow);
    transform: translateY(-2px);
  }
  .sts-pill-dot {
    width: 8px; height: 8px; border-radius: 50%;
    background: var(--red); flex-shrink: 0;
    transition: all 0.4s; box-shadow: 0 0 0 2px rgba(248,113,113,0.15);
  }
  .sts-pill-dot.on {
    background: var(--green);
    box-shadow: 0 0 8px rgba(52,211,153,0.5), 0 0 0 2px rgba(52,211,153,0.15);
    animation: sts-breathe 3s ease-in-out infinite;
  }
  @keyframes sts-breathe {
    0%, 100% { box-shadow: 0 0 8px rgba(52,211,153,0.3), 0 0 0 2px rgba(52,211,153,0.1); }
    50% { box-shadow: 0 0 14px rgba(52,211,153,0.6), 0 0 0 3px rgba(52,211,153,0.2); }
  }
  .sts-pill-label { font-size: 12px; font-weight: 600; color: var(--text-dim); letter-spacing: 0.03em; font-family: var(--display); }
  .sts-pill-proj {
    font-size: 11px; font-family: var(--mono); font-weight: 500; color: var(--accent);
    opacity: 0.9; max-width: 120px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }
  .sts-pill-counts { display: flex; gap: 10px; font-family: var(--mono); font-size: 11px; font-weight: 500; }
  .sts-pill-counts span { opacity: 0.8; }
  .sts-c-pend { color: #ffffff; }
  .sts-c-proc { color: var(--amber); }
  .sts-c-rdy { color: var(--green); }
  .sts-c-sent { color: var(--accent); }

  /* ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ Expanded Panel ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ */
  .sts-panel {
    width: 525px;
    height: 100vh;
    display: flex;
    flex-direction: column;
    background: var(--bg);
    backdrop-filter: blur(24px) saturate(1.4);
    border-left: 1.5px solid rgba(255,255,255,0.10);
    border-radius: 0;
    box-shadow:
      0 24px 80px rgba(0,0,0,0.55),
      0 0 0 1px rgba(255,255,255,0.03) inset,
      0 1px 0 rgba(255,255,255,0.04) inset;
    overflow: hidden;
    animation: sts-up 0.35s cubic-bezier(0.16, 1, 0.3, 1);
    padding-left:1rem !important;
  }
  @keyframes sts-up {
    from { opacity: 0; transform: translateY(16px) scale(0.96); }
    to { opacity: 1; transform: translateY(0) scale(1); }
  }

  /* ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ Header ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ */
  .sts-head {
    display: flex; align-items: center; justify-content: space-between;
    padding: 16px 20px;
    background: linear-gradient(180deg, rgba(78,205,196,0.06) 0%, transparent 100%);
    border-bottom: 1px solid var(--border);
    position: relative;
  }
  .sts-head::after {
    content: ''; position: absolute; bottom: 0; left: 16px; right: 16px; height: 1px;
    background: linear-gradient(90deg, transparent, var(--accent-glow), transparent);
  }
  .sts-head-left { display: flex; align-items: center; gap: 10px; }
  .sts-head-dot {
    width: 8px; height: 8px; border-radius: 50%;
    background: var(--red); transition: all 0.4s;
  }
  .sts-head-dot.on { background: var(--green); box-shadow: 0 0 10px rgba(52,211,153,0.5); }
  .sts-head h3 {
    font-size: 16px; font-weight: 700; color: #ffffff;
    letter-spacing: -0.02em; font-family: var(--display);
  }
  .sts-head-proj {
    font-size: 11px; font-family: var(--mono); font-weight: 500; color: var(--accent);
    background: var(--accent-bg); padding: 4px 12px; border-radius: var(--radius-sm);
    max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    border: 1px solid rgba(78,205,196,0.12);
  }
  .sts-head-port {
    font-size: 11px; font-family: var(--mono); font-weight: 500; color: var(--text-muted);
    padding: 4px 8px; border-radius: var(--radius-sm); background: rgba(255,255,255,0.04);
    border: 1px solid var(--border);
  }
  .sts-head-autotype {
    font-size: 10px; font-family: var(--mono); font-weight: 600;
    padding: 4px 10px; border-radius: var(--radius-sm);
    text-transform: uppercase; letter-spacing: 0.04em;
    transition: all 0.2s; /* user-select: none; */
  }
  .sts-head-autotype.on {
    color: var(--accent); background: var(--accent-bg);
    border: 1px solid rgba(78,205,196,0.15);
  }
  .sts-head-autotype.off {
    color: var(--text-muted); background: rgba(255,255,255,0.04);
    border: 1px solid var(--border);
  }
  .sts-head-autotype:hover { opacity: 0.8; }

  .sts-head-btns { display: flex; gap: 4px; }
  .sts-hb {
    width: 32px; height: 32px; border-radius: var(--radius-sm);
    border: 1px solid transparent; background: transparent;
    color: var(--text-muted); cursor: pointer; font-size: 14px;
    display: flex; align-items: center; justify-content: center;
    transition: all 0.2s;
  }
  .sts-hb:hover { background: var(--bg-hover); color: var(--text-dim); border-color: var(--border); }
  .sts-hb.active { background: var(--accent-bg); color: var(--accent); border-color: rgba(78,205,196,0.15); }

  /* ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ Settings ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ */
  .sts-settings {
    padding: 14px 20px;
    border-bottom: 1px solid var(--border);
    background: rgba(0,0,0,0.25);
    display: none;
  }
  .sts-settings.open { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }
  .sts-settings label {
    font-size: 11px; color: var(--text-muted); font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.06em;
    font-family: var(--display);
  }
  .sts-url-input {
    flex: 1; min-width: 120px; padding: 6px 10px; border-radius: var(--radius-sm);
    border: 1px solid var(--border);
    background: rgba(255,255,255,0.03); color: var(--text);
    font-family: var(--mono); font-size: 10px; font-weight: 400;
    outline: none; transition: all 0.2s;
  }
  .sts-url-input:focus { border-color: var(--accent); box-shadow: 0 0 0 2px var(--accent-glow); }
  .sts-scroll-input {
    width: 42px; padding: 6px 8px; border-radius: var(--radius-sm); text-align: center;
    border: 1px solid var(--border);
    background: rgba(255,255,255,0.03); color: var(--text);
    font-family: var(--mono); font-size: 10px; font-weight: 400;
    outline: none; transition: all 0.2s;
  }
  .sts-scroll-input:focus { border-color: var(--accent); box-shadow: 0 0 0 2px var(--accent-glow); }
  .sts-url-save {
    padding: 8px 16px; border-radius: var(--radius-sm); border: none;
    background: linear-gradient(135deg, var(--accent), #3eb8b0);
    color: #0a0e13;
    font-size: 11px; font-weight: 700; cursor: pointer;
    font-family: var(--display); letter-spacing: 0.04em;
    text-transform: uppercase;
    transition: all 0.25s;
  }
  .sts-url-save:hover { background: linear-gradient(135deg, var(--accent-hover), var(--accent)); transform: translateY(-1px); box-shadow: 0 4px 16px var(--accent-glow); }

  /* ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ Timer ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ */
  .sts-timer {
    display: flex; align-items: center; justify-content: space-between;
    padding: 12px 20px;
    border-bottom: 1px solid var(--border);
    font-size: 11px; color: var(--text-muted); font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.04em;
    font-family: var(--display);
  }
  .sts-timer-val { font-family: var(--mono); color: var(--text-dim); font-weight: 400; text-transform: none; letter-spacing: 0; }

  /* --- Connection Status --- */
  .sts-conn-bar {
    display: flex; align-items: center; gap: 8px;
    padding: 8px 20px;
    border-bottom: 1px solid var(--border);
    background: var(--red-bg);
    font-size: 11px; font-weight: 600; color: var(--red);
    font-family: var(--display);
    animation: sts-pulse 2s ease-in-out infinite;
  }
  .sts-conn-bar.ok {
    background: var(--green-bg); color: var(--green);
    animation: none;
  }

  /* ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ Stats ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ */
  .sts-stats {
    display: grid; grid-template-columns: repeat(4, 1fr); gap: 1px;
    padding: 0; margin: 0;
    background: var(--border);
    border-bottom: 1px solid var(--border);
  }
  .sts-stat {
    display: flex; flex-direction: column; align-items: center;
    padding: 14px 8px 12px;
    background: var(--bg);
    transition: background 0.2s;
  }
  .sts-stat:hover { background: var(--bg-raised); }
  .sts-stat-n {
    font-family: var(--mono); font-size: 22px; font-weight: 600;
    line-height: 1; letter-spacing: -0.02em;
  }
  .sts-stat-l {
    font-size: 9px; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.1em; color: var(--text-muted); margin-top: 6px;
    font-family: var(--display);
  }

  /* ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ Tabs ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ */
  .sts-tabs {
    display: flex; gap: 4px; padding: 10px 20px;
    border-bottom: 1px solid var(--border);
    background: rgba(0,0,0,0.1);
  }
  .sts-tab {
    flex: 1; padding: 10px 0; text-align: center;
    font-size: 12px; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.08em; color: var(--text-muted);
    cursor: pointer; border: none;
    background: transparent; border-radius: var(--radius-sm);
    transition: all 0.2s;
    font-family: var(--display);
  }
  .sts-tab:hover { color: var(--text-dim); background: var(--bg-hover); }
  .sts-tab.active {
    color: var(--accent); background: var(--accent-bg);
    box-shadow: 0 0 0 1px rgba(78,205,196,0.12) inset;
  }

  /* ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ Progress Bar ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ */
  .sts-typing-prog {
    padding: 10px 20px;
    border-bottom: 1px solid var(--border);
    display: none;
  }
  .sts-typing-prog.show { display: block; }
  .sts-prog-text {
    font-size: 11px; color: var(--text-dim); margin-bottom: 8px;
    display: flex; justify-content: space-between; align-items: center;
    font-weight: 500;
  }
  .sts-prog-text .sts-cd { color: var(--amber); font-family: var(--mono); font-weight: 600; }
  .sts-prog-text .sts-cd.cool { color: #60a5fa; }
  .sts-prog-bar {
    height: 4px; border-radius: 4px; background: rgba(255,255,255,0.04);
    overflow: hidden; position: relative;
  }
  .sts-prog-fill {
    height: 100%; border-radius: 4px;
    background: linear-gradient(90deg, var(--accent), #3eb8b0, var(--accent));
    background-size: 200% 100%;
    animation: sts-shimmer 2s linear infinite;
    transition: width 0.4s cubic-bezier(0.4, 0, 0.2, 1);
  }
  @keyframes sts-shimmer {
    0% { background-position: 200% 0; }
    100% { background-position: -200% 0; }
  }
  .sts-typing-tools {
    padding: 10px 20px;
    border-bottom: 1px solid var(--border);
    display: none;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    background: rgba(255,255,255,0.02);
  }
  .sts-typing-tools.show { display: flex; }
  .sts-typing-tools-meta {
    font-size: 10px;
    color: var(--text-muted);
    font-family: var(--mono);
    font-weight: 500;
    letter-spacing: 0.04em;
    text-transform: uppercase;
  }
  .sts-mini-btn {
    padding: 8px 12px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border);
    background: rgba(255,255,255,0.03);
    color: var(--text-dim);
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    cursor: pointer;
    transition: all 0.2s ease;
    font-family: var(--display);
    line-height: 1;
  }
  .sts-mini-btn:hover:not(:disabled) {
    background: var(--accent-bg);
    color: var(--accent);
    border-color: rgba(78,205,196,0.18);
    box-shadow: 0 0 12px var(--accent-glow);
  }
  .sts-mini-btn:disabled {
    opacity: 0.45;
    cursor: not-allowed;
    box-shadow: none;
  }

  /* ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ Scene / Typing Lists ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ */
  .sts-list {
    max-height: 65vh; overflow-y: auto; flex: 1;
    scrollbar-width: thin; scrollbar-color: rgba(255,255,255,0.06) transparent;
  }
  .sts-list::-webkit-scrollbar { width: 3px; }
  .sts-list::-webkit-scrollbar-track { background: transparent; }
  .sts-list::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.08); border-radius: 3px; }
  .sts-list::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.15); }

  .sts-row {
    display: flex; align-items: center; gap: 10px;
    padding: 8px 20px;
    border-bottom: 1px solid var(--border);
    transition: all 0.2s;
  }
  .sts-row:hover { background: var(--bg-hover); }
  .sts-row:last-child { border-bottom: none; }
  .sts-row.highlight {
    background: var(--accent-bg);
    border-left: 2px solid var(--accent);
    padding-left: 18px;
  }
  .sts-row-num {
    width: 32px; height: 32px; border-radius: var(--radius-sm);
    display: flex; align-items: center; justify-content: center;
    font-family: var(--mono); font-size: 13px; font-weight: 600;
    background: var(--accent-bg); color: var(--accent); flex-shrink: 0;
    border: 1px solid rgba(78,205,196,0.1);
  }
  .sts-row-check-wrap {
    width: 18px;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
  }
  .sts-row-check {
    width: 14px;
    height: 14px;
    margin: 0;
    accent-color: var(--accent);
    cursor: pointer;
  }
  .sts-row-check:disabled {
    opacity: 0.45;
    cursor: not-allowed;
  }
  .sts-row-thumb {
    width: 36px; height: 36px; border-radius: 6px; object-fit: cover;
    border: 1px solid var(--border); flex-shrink: 0;
  }
  .sts-row-thumb-empty {
    display: flex; align-items: center; justify-content: center;
    background: var(--bg-raised); color: var(--text-muted); font-family: var(--mono);
    font-size: 10px; font-weight: 600;
  }
  .sts-row-info { flex: 1; min-width: 0; }
  .sts-row-prompt {
    font-size: 11px; color: var(--text-dim); font-weight: 400;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    max-width: 280px;
  }
  .sts-row-meta {
    font-size: 10px; color: var(--text-muted); margin-top: 4px;
    font-family: var(--mono); font-weight: 400;
    text-transform: uppercase; letter-spacing: 0.04em;
  }
  .sts-row-status { flex-shrink: 0; width: 24px; height: 24px; display: flex; align-items: center; justify-content: center; }

  .sts-d-q { width: 6px; height: 6px; border-radius: 50%; background: var(--text-muted); }
  .sts-d-typing {
    width: 10px; height: 10px; border-radius: 50%; background: var(--amber);
    box-shadow: 0 0 8px rgba(251,191,36,0.4);
    animation: sts-pulse 1.4s ease-in-out infinite;
  }
  @keyframes sts-pulse {
    0%, 100% { opacity: 1; transform: scale(1); box-shadow: 0 0 8px rgba(251,191,36,0.4); }
    50% { opacity: 0.5; transform: scale(0.6); box-shadow: 0 0 4px rgba(251,191,36,0.2); }
  }
  .sts-d-typed { color: var(--green); font-size: 15px; }
  .sts-d-ready { color: var(--green); font-size: 15px; }
  .sts-d-sent { color: var(--accent); font-size: 15px; }
  .sts-d-err { color: var(--red); font-size: 14px; }
  .sts-d-proc {
    width: 10px; height: 10px; border-radius: 50%; background: var(--amber);
    animation: sts-pulse 1.6s ease-in-out infinite;
  }
  .sts-d-pending { width: 6px; height: 6px; border-radius: 50%; background: var(--text-muted); }
  .sts-d-dl { color: var(--accent); font-size: 15px; }

  .sts-empty {
    padding: 32px 20px; text-align: center; color: var(--text-muted);
    font-size: 13px; font-weight: 500;
  }
  .sts-empty-icon { font-size: 24px; margin-bottom: 8px; opacity: 0.25; display: block; }

  /* ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ Sync Cards ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ */
  .sts-card {
    padding: 14px 20px;
    border-bottom: 1px solid var(--border);
    transition: all 0.2s;
  }
  .sts-card:hover { background: var(--bg-hover); }
  .sts-card:last-child { border-bottom: none; }
  .sts-card-head {
    display: flex; align-items: center; gap: 12px; margin-bottom: 8px;
  }
  .sts-card-num {
    width: 28px; height: 28px; border-radius: var(--radius-sm);
    display: flex; align-items: center; justify-content: center;
    font-family: var(--mono); font-size: 12px; font-weight: 600;
    background: var(--accent-bg); color: var(--accent); flex-shrink: 0;
    border: 1px solid rgba(78,205,196,0.1);
  }
  .sts-card-prompt {
    flex: 1; font-size: 12px; color: var(--text-muted); min-width: 0;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    font-weight: 400;
  }
  .sts-card-badge {
    font-size: 10px; font-family: var(--mono); padding: 4px 10px;
    border-radius: 100px; flex-shrink: 0; font-weight: 600;
    letter-spacing: 0.02em;
  }
  .sts-badge-pending { background: rgba(72,72,84,0.2); color: var(--text-muted); border: 1px solid rgba(72,72,84,0.2); }
  .sts-badge-processing { background: var(--amber-bg); color: var(--amber); border: 1px solid rgba(251,191,36,0.12); }
  .sts-badge-ready { background: var(--green-bg); color: var(--green); border: 1px solid rgba(52,211,153,0.12); }
  .sts-badge-uploading { background: var(--accent-bg); color: var(--accent); border: 1px solid rgba(78,205,196,0.12); }
  .sts-badge-sent { background: var(--accent-bg); color: var(--accent); border: 1px solid rgba(78,205,196,0.12); }
  .sts-badge-downloaded { background: var(--green-bg); color: var(--green); border: 1px solid rgba(52,211,153,0.12); }
  .sts-badge-error { background: var(--red-bg); color: var(--red); border: 1px solid rgba(248,113,113,0.12); }

  .sts-thumbs {
    display: grid; grid-template-columns: repeat(4, 1fr); gap: 3px;
    border-radius: var(--radius-sm); overflow: hidden;
  }
  .sts-thumbs.cols2 { grid-template-columns: repeat(2, 1fr); }
  .sts-thumb {
    aspect-ratio: 1; background: rgba(255,255,255,0.02);
    border-radius: 4px; overflow: hidden; position: relative;
  }
  .sts-thumb img {
    width: 100%; height: 100%; object-fit: cover;
    display: block; transition: all 0.3s;
  }
  .sts-thumb img.loading { opacity: 0.3; filter: saturate(0); }
  .sts-thumb:hover img { transform: scale(1.05); }
  .sts-thumb-placeholder {
    width: 100%; height: 100%;
    display: flex; align-items: center; justify-content: center;
    color: var(--text-muted); font-size: 14px;
  }
  .sts-card-noimg {
    padding: 12px 0 6px;
    font-size: 10px; color: var(--text-muted); text-align: center; font-weight: 500;
  }

  /* ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ Scroll Status ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ */
  .sts-scroll-status {
    display: none; padding: 10px 20px;
    border-bottom: 1px solid var(--border);
    background: rgba(96,165,250,0.06);
    font-size: 11px; font-weight: 600; color: #60a5fa;
    align-items: center; gap: 10px;
  }
  .sts-scroll-status.active { display: flex; }
  .sts-scroll-icon { animation: sts-bounce 0.5s ease-in-out infinite alternate; font-size: 11px; }
  @keyframes sts-bounce { from { transform: translateY(-2px); } to { transform: translateY(2px); } }
  .sts-scroll-bar { flex: 1; height: 3px; border-radius: 3px; background: rgba(255,255,255,0.04); overflow: hidden; }
  .sts-scroll-fill { height: 100%; border-radius: 3px; background: #60a5fa; transition: width 0.4s ease; }
  .sts-scroll-status.done { background: var(--green-bg); color: var(--green); }

  /* ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ Footer ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ */
  .sts-foot {
    display: flex; align-items: center; justify-content: space-between;
    padding: 16px 20px;
    border-top: 1px solid var(--border);
    background: rgba(0,0,0,0.25);
  }
  .sts-toggle { display: flex; align-items: center; gap: 10px; cursor: pointer; /* user-select: none;  */}
  .sts-toggle-track {
    width: 32px; height: 18px; border-radius: 9px;
    background: rgba(255,255,255,0.08); position: relative;
    transition: all 0.3s; border: 1px solid var(--border);
  }
  .sts-toggle-track.on { background: var(--accent); border-color: var(--accent); }
  .sts-toggle-thumb {
    width: 14px; height: 14px; border-radius: 50%;
    background: var(--text-muted); position: absolute; top: 1px; left: 1px;
    transition: all 0.3s cubic-bezier(0.68, -0.55, 0.27, 1.55);
    box-shadow: 0 1px 3px rgba(0,0,0,0.3);
  }
  .sts-toggle-track.on .sts-toggle-thumb {
    left: 15px; background: #fff;
    box-shadow: 0 1px 4px rgba(78,205,196,0.4);
  }
  .sts-toggle-label { font-size: 12px; color: var(--text-dim); font-weight: 600; font-family: var(--display); }
  .sts-btn {
    padding: 12px 24px; border-radius: var(--radius-sm); border: none;
    font-size: 12px; font-weight: 700; cursor: pointer;
    letter-spacing: 0.05em; text-transform: uppercase;
    transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
    font-family: var(--display);
    line-height: 1;
  }
  .sts-btn-primary {
    background: linear-gradient(135deg, var(--accent), #3eb8b0);
    color: #0a0e13;
    box-shadow: 0 2px 12px var(--accent-glow), 0 0 0 1px rgba(78,205,196,0.15) inset;
  }
  .sts-btn-primary:hover {
    background: linear-gradient(135deg, var(--accent-hover), var(--accent));
    box-shadow: 0 6px 24px var(--accent-glow), 0 0 0 1px rgba(78,205,196,0.25) inset;
    transform: translateY(-2px);
  }
  .sts-btn-danger {
    background: linear-gradient(135deg, var(--red), #e55a5a);
    color: #0a0e13;
    box-shadow: 0 2px 12px rgba(255,107,107,0.2);
  }
  .sts-btn-danger:hover {
    background: linear-gradient(135deg, #ff8585, var(--red));
    box-shadow: 0 6px 24px rgba(255,107,107,0.3);
    transform: translateY(-2px);
  }
  .sts-btn:active { transform: scale(0.96) translateY(0); }
  .sts-btn-ghost {
    background: rgba(255,255,255,0.03); color: var(--text-dim);
    border: 1px solid var(--border); box-shadow: none;
  }
  .sts-btn-ghost:hover {
    background: rgba(255,255,255,0.06); color: var(--text);
    border-color: var(--accent); box-shadow: 0 0 12px var(--accent-glow);
    transform: translateY(-2px);
  }
  .sts-foot-btns { display: flex; gap: 12px; }
  .sts-row.error-clickable { cursor: pointer; }
  .sts-row.error-clickable:hover { background: var(--red-bg); }
  button#sts-action-btn { padding: 1rem; }

  /* ── Pipeline Bar ── */
  .sts-pipeline-bar {
    display: flex; align-items: center; gap: 8px;
    padding: 8px 20px; border-bottom: 1px solid var(--border);
  }
  .sts-pipeline-btn {
    flex: 1; display: flex; align-items: center; gap: 10px;
    padding: 8px 14px; border-radius: var(--radius-sm);
    background: rgba(255,255,255,0.03); border: 1px solid var(--border);
    color: var(--text-muted); font-size: 11px; font-weight: 700;
    font-family: var(--sans);
    text-transform: uppercase; letter-spacing: 0.04em;
    cursor: pointer; transition: all 0.3s;
  }
  .sts-pipeline-btn:hover { border-color: var(--border-active); color: var(--text-dim); }
  .sts-pipeline-btn.active {
    background: rgba(78,205,196,0.08); border-color: rgba(78,205,196,0.25);
    color: var(--accent);
  }
  .sts-pipeline-icon {
    display: flex; align-items: center; justify-content: center;
    width: 24px; height: 24px; border-radius: 50%;
    background: var(--bg-raised); border: 1px solid var(--border);
    transition: all 0.3s; flex-shrink: 0;
  }
  .sts-pipeline-btn.active .sts-pipeline-icon {
    background: rgba(78,205,196,0.15); border-color: rgba(78,205,196,0.3);
    animation: sts-pipeline-pulse 2s ease-in-out infinite;
  }
  .sts-pipeline-btn.active .sts-pipeline-icon svg { stroke: var(--accent); }
  @keyframes sts-pipeline-pulse {
    0%,100% { box-shadow: 0 0 0 0 rgba(78,205,196,0); }
    50% { box-shadow: 0 0 0 4px rgba(78,205,196,0.2); }
  }
  .sts-pipeline-label { flex: 1; text-align: left; }
  .sts-pipeline-stop {
    display: flex; align-items: center; justify-content: center;
    width: 32px; height: 32px; border-radius: var(--radius-sm);
    background: var(--red-bg); border: 1px solid rgba(255,107,107,0.2);
    color: var(--red); cursor: pointer; transition: all 0.2s; flex-shrink: 0;
  }
  .sts-pipeline-stop:hover {
    background: rgba(255,107,107,0.2); border-color: rgba(255,107,107,0.4);
  }

  /* ── Settings Tab ── */
  .sts-settings-tab {
    padding: 12px 20px; overflow-y: auto; flex: 1;
  }
  .sts-settings-card {
    background: var(--bg-raised); border: 1px solid var(--border);
    border-radius: var(--radius-sm); padding: 14px; margin-bottom: 12px;
  }
  .sts-settings-title {
    font-size: 10px; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.06em; color: var(--text-muted); margin-bottom: 10px;
  }
  .sts-settings-label {
    display: block; font-size: 9px; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.06em; color: var(--text-muted); margin-bottom: 4px;
  }
  .sts-settings-input {
    width: 100%; padding: 8px 12px; border-radius: var(--radius-sm);
    border: 1px solid var(--border); background: rgba(255,255,255,0.03);
    color: var(--text); font-family: var(--mono); font-size: 11px; outline: none;
  }
  .sts-settings-input:focus {
    border-color: var(--accent); box-shadow: 0 0 0 2px rgba(78,205,196,0.15);
  }
  .sts-settings-row {
    display: flex; gap: 8px; margin-top: 10px;
  }
  .sts-settings-info {
    font-size: 10px; color: var(--text-muted); font-family: var(--mono); margin-top: 8px;
  }
  .sts-btn-sm { padding: 6px 14px; font-size: 10px; }
</style>

<div id="sts-pill" class="sts-pill">
  <div id="sts-pill-dot" class="sts-pill-dot"></div>
  <span class="sts-pill-label">Assets Sync</span>
  <span class="sts-pill-proj" id="sts-pill-proj"></span>
  <div class="sts-pill-counts">
    <span class="sts-c-pend" id="sts-pill-p">0</span>
    <span class="sts-c-rdy" id="sts-pill-r">0</span>
  </div>
</div>

<div id="sts-expanded" class="sts-panel" style="display:none">
  <div class="sts-head">
    <div class="sts-head-left">
      <div id="sts-head-dot" class="sts-head-dot"></div>
      <h3>Assets Sync</h3>
      <span class="sts-head-proj" id="sts-head-proj"></span>
      <span class="sts-head-port" id="sts-head-port"></span>
      <span class="sts-head-autotype" id="sts-head-autotype"></span>
    </div>
    <div class="sts-head-btns">
      <button class="sts-hb" id="sts-gear" title="Settings">&#x2699;</button>
      <button class="sts-hb" id="sts-collapse" title="Collapse">&minus;</button>
    </div>
  </div>

  <div class="sts-settings" id="sts-settings" style="display:none"></div>

  <div class="sts-timer">
    <span>Last poll</span>
    <span class="sts-timer-val" id="sts-timer-val">--</span>
  </div>

  <div id="sts-conn-bar" class="sts-conn-bar" style="display:none">
    <span id="sts-conn-icon">&#x26A0;</span>
    <span id="sts-conn-msg">Backend disconnected</span>
  </div>

  <div class="sts-scroll-status" id="sts-scroll-status">
    <span class="sts-scroll-icon" id="sts-scroll-icon">&#x25BC;</span>
    <span id="sts-scroll-label">Scrolling...</span>
    <div class="sts-scroll-bar"><div class="sts-scroll-fill" id="sts-scroll-fill" style="width:0%"></div></div>
  </div>

  <div class="sts-stats">
    <div class="sts-stat"><span class="sts-stat-n sts-c-pend" id="sts-n-q">0</span><span class="sts-stat-l">Queued</span></div>
    <div class="sts-stat"><span class="sts-stat-n sts-c-proc" id="sts-n-typed">0</span><span class="sts-stat-l">Typed</span></div>
    <div class="sts-stat"><span class="sts-stat-n sts-c-rdy" id="sts-n-rdy">0</span><span class="sts-stat-l">Ready</span></div>
    <div class="sts-stat"><span class="sts-stat-n sts-c-sent" id="sts-n-sent">0</span><span class="sts-stat-l">Synced</span></div>
  </div>


  <div class="sts-pipeline-bar">
    <button class="sts-pipeline-btn" id="sts-pipeline-btn" title="Enable/disable auto-processing">
      <span class="sts-pipeline-icon" id="sts-pipeline-icon">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg>
      </span>
      <span class="sts-pipeline-label" id="sts-pipeline-label">Pipeline Off</span>
    </button>
    <button class="sts-pipeline-stop" id="sts-pipeline-stop" style="display:none" title="Stop after current job">
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="6" width="12" height="12" rx="1"/></svg>
    </button>
  </div>

  <div class="sts-tabs">
    <button class="sts-tab active" id="sts-tab-typing" data-tab="typing">Typing</button>
    <button class="sts-tab" id="sts-tab-sync" data-tab="sync">Sync</button>
    <button class="sts-tab" id="sts-tab-settings" data-tab="settings">Settings</button>
  </div>

  <div class="sts-typing-prog" id="sts-typing-prog">
    <div class="sts-prog-text">
      <span id="sts-prog-label">Ready</span>
      <span class="sts-cd" id="sts-prog-cd"></span>
    </div>
    <div class="sts-prog-bar"><div class="sts-prog-fill" id="sts-prog-fill" style="width:0%"></div></div>
  </div>

  <div class="sts-typing-tools" id="sts-typing-tools">
    <span class="sts-typing-tools-meta" id="sts-selection-meta">0 of 0 selected</span>
    <button class="sts-mini-btn" id="sts-select-all-btn" type="button">Select All Prompts</button>
  </div>

  <div class="sts-list" id="sts-list"></div>

  <div class="sts-settings-tab" id="sts-settings-tab" style="display:none">
    <div class="sts-settings-card">
      <div class="sts-settings-title">Backend</div>
      <label class="sts-settings-label">WebSocket URL</label>
      <input type="text" class="sts-settings-input" id="sts-ws-url" />
      <div class="sts-settings-row">
        <button class="sts-btn sts-btn-primary sts-btn-sm" id="sts-ws-connect">Connect</button>
        <button class="sts-btn sts-btn-ghost sts-btn-sm" id="sts-ws-disconnect">Disconnect</button>
      </div>
      <div class="sts-settings-info" id="sts-ws-status">Not connected</div>
    </div>
    <div class="sts-settings-card">
      <div class="sts-settings-title">Studio URL</div>
      <input type="text" class="sts-settings-input" id="sts-studio-url" />
      <button class="sts-btn sts-btn-ghost sts-btn-sm" id="sts-save-url" style="margin-top:8px">Save</button>
    </div>
  </div>

  <div class="sts-foot">
    <div style="display:none" id="sts-toggle"></div>
    <div class="sts-foot-btns">
      <button class="sts-btn sts-btn-ghost" id="sts-retry-btn" style="display:none">Retry</button>
      <button class="sts-btn sts-btn-ghost" id="sts-redownload-btn" style="display:none">Redownload</button>
      <button class="sts-btn sts-btn-primary" id="sts-action-btn">Start Typing</button>
    </div>
  </div>
</div>
`;
document.body.appendChild(root);

const $id = (id) => document.getElementById(id);

// ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ Settings ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬
// Old settings inputs removed — now in Settings tab
// ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ Event Listeners ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬
$id('sts-pill').addEventListener('click', () => {
  S.collapsed = false;
  $id('sts-pill').style.display = 'none';
  $id('sts-expanded').style.display = '';
});
$id('sts-collapse').addEventListener('click', () => {
  S.collapsed = true;
  $id('sts-expanded').style.display = 'none';
  $id('sts-pill').style.display = 'flex';
});
$id('sts-gear').addEventListener('click', () => {
  S.activeTab = S.activeTab === 'settings' ? 'typing' : 'settings';
  renderTabs();
  render();
});
// Old sts-url-save removed — settings now in Settings tab
$id('sts-toggle').addEventListener('click', () => {
  S.autoSync = !S.autoSync;
  $id('sts-toggle-track').classList.toggle('on', S.autoSync);
});

// Pipeline toggle
S.pipelineEnabled = false;
S.pipelineStopping = false;
$id('sts-pipeline-btn').addEventListener('click', () => {
  S.pipelineEnabled = !S.pipelineEnabled;
  S.pipelineStopping = false;
  updatePipelineUI();
  if (S.pipelineEnabled && !S.typing.active) {
    const hasQueued = S.typing.queue.some(q => isTypingSelected(q) && q.status === 'queued');
    if (hasQueued) startTyping();
  }
});
$id('sts-pipeline-stop').addEventListener('click', () => {
  S.pipelineStopping = true;
  S.pipelineEnabled = false;
  if (S.typing.active) stopTyping();
  updatePipelineUI();
});
function updatePipelineUI() {
  const btn = $id('sts-pipeline-btn');
  const stop = $id('sts-pipeline-stop');
  const label = $id('sts-pipeline-label');
  btn.classList.toggle('active', S.pipelineEnabled);
  label.textContent = S.pipelineEnabled ? 'Pipeline On' : 'Pipeline Off';
  stop.style.display = S.pipelineEnabled ? '' : 'none';
}

// Auto-type toggle (click the badge in header)
// Auto-type is controlled from Studio UI, display only here

function renderAutoType() {
  const el = $id('sts-head-autotype');
  el.textContent = S.autoType ? 'auto-type: on' : 'auto-type: off';
  el.className = 'sts-head-autotype ' + (S.autoType ? 'on' : 'off');
}

// Tabs
$id('sts-tab-typing').addEventListener('click', () => { S.activeTab = 'typing'; renderTabs(); render(); });
$id('sts-tab-sync').addEventListener('click', () => { S.activeTab = 'sync'; renderTabs(); render(); });
$id('sts-tab-settings').addEventListener('click', () => { S.activeTab = 'settings'; renderTabs(); render(); });

// Settings tab controls
$id('sts-ws-url').value = S.studioUrl.replace(/^http/, 'ws') + '/ws/animator';
$id('sts-studio-url').value = S.studioUrl;
$id('sts-ws-connect').addEventListener('click', () => { connectWS(); });
$id('sts-ws-disconnect').addEventListener('click', () => {
  if (S.ws) { S.ws.close(); S.ws = null; S.wsConnected = false; }
  if (S.wsReconnectTimer) { clearTimeout(S.wsReconnectTimer); S.wsReconnectTimer = null; }
  render();
});
$id('sts-save-url').addEventListener('click', () => {
  const url = $id('sts-studio-url').value.trim();
  if (url) {
    S.studioUrl = url;
    localStorage.setItem('sts-url', url);
    $id('sts-ws-url').value = url.replace(/^http/, 'ws') + '/ws/animator';
    console.log('Studio URL saved:', url);
  }
});

function renderTabs() {
  $id('sts-tab-typing').classList.toggle('active', S.activeTab === 'typing');
  $id('sts-tab-sync').classList.toggle('active', S.activeTab === 'sync');
  $id('sts-tab-settings').classList.toggle('active', S.activeTab === 'settings');
  $id('sts-typing-prog').classList.toggle('show', S.activeTab === 'typing');
  $id('sts-typing-tools').classList.toggle('show', S.activeTab === 'typing');
  $id('sts-list').style.display = S.activeTab === 'settings' ? 'none' : '';
  $id('sts-settings-tab').style.display = S.activeTab === 'settings' ? '' : 'none';
  // Update WS status in settings
  if (S.activeTab === 'settings') {
    $id('sts-ws-status').textContent = S.wsConnected ? 'Connected' : 'Not connected';
    $id('sts-ws-status').style.color = S.wsConnected ? 'var(--green)' : 'var(--text-muted)';
  }
}

// Action button
$id('sts-action-btn').addEventListener('click', () => {
  if (S.activeTab === 'typing') {
    if (S.typing.active) stopTyping();
    else startTyping();
  } else {
    syncNow();
  }
});

function isTypingSelected(item) {
  return !!item && item.selected !== false;
}

function getSelectedTypingItems() {
  return S.typing.queue.filter(isTypingSelected);
}

function areAllTypingItemsSelected() {
  return S.typing.queue.length > 0 && S.typing.queue.every(isTypingSelected);
}

function selectAllTypingItems() {
  let changed = 0;
  S.typing.queue.forEach(item => {
    if (!item) return;
    if (!isTypingSelected(item)) changed++;
    item.selected = true;
  });
  return changed;
}

function findGrokStopButton() {
  var selectors = [
    'button[aria-label*="Stop generating"]',
    'button[aria-label*="stop generating"]',
    'button[aria-label*="Cancel generation"]',
    'button[aria-label*="cancel generation"]',
    'button[aria-label*="Stop"]',
    'button[aria-label*="stop"]',
    'button[aria-label*="Cancel"]',
    'button[aria-label*="cancel"]',
    'button[data-testid*="stop"]',
    'button[data-testid*="cancel"]'
  ];

  function isValid(btn) {
    return !!btn && !btn.closest('#sts-sync') && isElReady(btn);
  }

  for (var si = 0; si < selectors.length; si++) {
    var hits = document.querySelectorAll(selectors[si]);
    for (var hi = 0; hi < hits.length; hi++) {
      if (isValid(hits[hi])) return hits[hi];
    }
  }

  var buttons = document.querySelectorAll('button');
  for (var bi = 0; bi < buttons.length; bi++) {
    var btn = buttons[bi];
    if (!isValid(btn)) continue;
    var text = (btn.textContent || '').trim();
    var aria = btn.getAttribute('aria-label') || '';
    var combined = (aria + ' ' + text).toLowerCase();
    if (!/(stop|cancel)/.test(combined)) continue;
    if (/retry|redownload|sync saved|start typing/.test(combined)) continue;
    return btn;
  }

  return null;
}

function tryStopGrokGeneration() {
  try {
    var stopBtn = findGrokStopButton();
    if (!stopBtn) {
      console.log('No Grok stop button found; stopping workflow locally only');
      return false;
    }
    simulateClick(stopBtn);
    console.log('Clicked Grok stop button');
    return true;
  } catch (e) {
    console.warn('Failed to click Grok stop button:', e.message);
    return false;
  }
}

function resetTypingItem(item) {
  if (!item) return false;
  item.status = 'queued';
  item.errorCount = 0;
  delete item.videoUrl;
  delete item.allVideoUrls;
  delete S.sentScenes[item.scene];
  var sc = S.scenes[item.scene];
  if (sc) {
    sc.status = 'pending';
    sc.urls = [];
    sc.fileCount = 0;
    delete sc.previewUrl;
  }
  return true;
}

function requeueTypingItems(statuses) {
  const targetStatuses = statuses || ['error', 'failed'];
  let revived = 0;
  S.typing.queue.forEach(q => {
    if (targetStatuses.indexOf(q.status) !== -1 && resetTypingItem(q)) {
      revived++;
    }
  });
  if (revived) {
    console.log('Re-queued', revived, 'prompt(s) for typing');
  }
  return revived;
}

// Retry button - re-queues errors on current tab
$id('sts-retry-btn').addEventListener('click', () => {
  if (S.activeTab === 'typing') {
    requeueTypingItems(['error', 'failed']);
  } else {
    Object.values(S.scenes).forEach(sc => { if (sc.status === 'error') sc.status = 'pending'; });
    syncNow();
  }
  render();
});

// Redownload button - re-downloads failed/missing assets from server
$id('sts-redownload-btn').addEventListener('click', () => {
  redownload();
});

$id('sts-list').addEventListener('change', (e) => {
  const checkbox = e.target.closest('input[data-role="typing-checkbox"]');
  if (!checkbox) return;
  const idx = parseInt(checkbox.dataset.idx, 10);
  if (isNaN(idx)) return;
  const item = S.typing.queue[idx];
  if (!item) return;
  item.selected = !!checkbox.checked;
  render();
});

$id('sts-select-all-btn').addEventListener('click', () => {
  if (S.typing.active) return;
  const changed = selectAllTypingItems();
  if (changed > 0) {
    console.log('Selected all prompts for typing');
  }
  render();
});

// Click failed/error rows to re-queue individual prompts
$id('sts-list').addEventListener('click', (e) => {
  if (e.target.closest('input[data-role="typing-checkbox"]') || e.target.closest('.sts-row-check-wrap')) {
    return;
  }
  const row = e.target.closest('.sts-row.error-clickable');
  if (!row) return;
  const idx = parseInt(row.dataset.idx);
  if (isNaN(idx)) return;
  const item = S.typing.queue[idx];
  if (item && (item.status === 'error' || item.status === 'failed') && resetTypingItem(item)) {
    render();
  }
});

async function syncNow() {
  if (!S.projectId) { console.log('No project loaded - fetch pending first'); await fetchPending(); render(); }
  if (!S.projectId) { console.log('Still no project - cannot sync'); return; }
  console.log('Sync from thumbnail sidebar for project:', S.projectId);
  S.lastPoll = Date.now();

  // Find thumbnail buttons on the current post page
  // Thumbnails: button elements with img[alt^="Thumbnail"] inside the sidebar
  var thumbButtons = document.querySelectorAll('button img[alt^="Thumbnail"]');
  if (!thumbButtons.length) {
    console.log('No thumbnails found on current page - need to be on a post page');
    render();
    return;
  }

  var statusEl = $id('sts-scroll-status');
  var labelEl = $id('sts-scroll-label');
  var fillEl = $id('sts-scroll-fill');
  statusEl.classList.add('active');
  statusEl.classList.remove('done');

  var tagRe = new RegExp('\\[' + S.projectId.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '\\|(\\d+)\\]');
  var matched = 0;
  var total = thumbButtons.length;
  // Track UUIDs already sent to avoid duplicate downloads
  if (!S.sentUuids) S.sentUuids = new Set();
  console.log('Found', total, 'thumbnails to check (', S.sentUuids.size, 'UUIDs already sent)');

  // Track the previous sd-video UUID so we can detect when the view actually switches
  var prevVideoUuid = '';
  var sdvInit = document.getElementById('sd-video');
  if (sdvInit) {
    var initSrc = sdvInit.src || sdvInit.getAttribute('src') || '';
    var initMatch = initSrc.match(/generated\/([a-f0-9-]+)\//);
    prevVideoUuid = initMatch ? initMatch[1] : '';
  }

  for (var ti = 0; ti < total; ti++) {
    var thumbImg = thumbButtons[ti];
    var thumbBtn = thumbImg.closest('button');
    if (!thumbBtn) continue;

    labelEl.textContent = 'Checking thumbnail ' + (ti + 1) + '/' + total;
    fillEl.style.width = ((ti + 1) / total * 100) + '%';

    try {
      // Extract UUID from thumbnail preview image to check for duplicates early
      var thumbSrc = thumbImg.src || thumbImg.getAttribute('src') || '';
      var thumbUuidMatch = thumbSrc.match(/generated\/([a-f0-9-]+)\//);
      var thumbUuid = thumbUuidMatch ? thumbUuidMatch[1] : '';

      // Skip if this UUID was already sent (check early before clicking)
      if (thumbUuid && S.sentUuids.has(thumbUuid)) {
        console.log('Thumbnail', ti + 1, '- UUID', thumbUuid.substring(0, 8), 'already sent, skipping');
        continue;
      }

      // Scroll thumbnail into view so it's clickable
      thumbBtn.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      await sleep(300);

      // Click thumbnail to switch the main video view
      simulateClick(thumbBtn);
      console.log('Clicked thumbnail', ti + 1);

      // Wait for #sd-video UUID to change (or timeout after 6s)
      // This is more reliable than prompt text change ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â works even for duplicate prompts
      var videoSwitched = false;
      var sdVideo = null;
      var videoUrl = '';
      for (var vWait = 0; vWait < 20; vWait++) {
        await sleep(300);
        sdVideo = document.getElementById('sd-video');
        if (sdVideo) {
          var vSrc = sdVideo.src || sdVideo.getAttribute('src') || '';
          if (vSrc && vSrc.includes('.mp4')) {
            var vUuidMatch = vSrc.match(/generated\/([a-f0-9-]+)\//);
            var vUuid = vUuidMatch ? vUuidMatch[1] : '';
            // Accept if UUID changed from previous, OR if this is the first thumbnail
            // (already selected, UUID won't change), OR if UUID matches thumbnail
            if (vUuid && (vUuid !== prevVideoUuid || ti === 0 || vUuid === thumbUuid)) {
              videoUrl = vSrc;
              videoSwitched = true;
              break;
            }
          }
        }
      }
      if (!videoSwitched && ti === 0) {
        // First thumbnail might already be selected ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â accept whatever is loaded
        sdVideo = document.getElementById('sd-video');
        if (sdVideo) {
          var fallSrc = sdVideo.src || sdVideo.getAttribute('src') || '';
          if (fallSrc && fallSrc.includes('.mp4')) videoUrl = fallSrc;
        }
      }

      // Fallback: construct URL from thumbnail UUID
      if (!videoUrl && thumbUuid) {
        var userMatch = thumbSrc.match(/users\/([a-f0-9-]+)\//);
        if (userMatch) {
          videoUrl = 'https://assets.grok.com/users/' + userMatch[1] + '/generated/' + thumbUuid + '/generated_video.mp4';
          console.log('Constructed video URL from thumbnail:', videoUrl);
        }
      }
      if (!videoUrl) {
        console.log('Thumbnail', ti + 1, '- no video URL found');
        continue;
      }

      // Extract UUID from the video URL for dedup
      var videoUuidMatch = videoUrl.match(/generated\/([a-f0-9-]+)\//);
      var videoUuid = videoUuidMatch ? videoUuidMatch[1] : thumbUuid;

      // Update prevVideoUuid for next iteration's switch detection
      prevVideoUuid = videoUuid;

      // Double-check: skip if video UUID was already sent (thumb UUID check was early)
      if (videoUuid && S.sentUuids.has(videoUuid)) {
        console.log('Thumbnail', ti + 1, '- video UUID', videoUuid.substring(0, 8), 'already sent, skipping');
        continue;
      }

      // Read prompt text from the editor
      var editor = document.querySelector('.tiptap.ProseMirror');
      var promptText = '';
      if (editor) {
        var p = editor.querySelector('p');
        promptText = p ? p.textContent.trim() : editor.textContent.trim();
      }

      // Check if prompt matches our project tag
      var tm = promptText.match(tagRe);
      if (!tm) {
        console.log('Thumbnail', ti + 1, '- no project tag match in prompt');
        continue;
      }

      var sceneNum = tm[1];
      var sc = S.scenes[sceneNum];
      if (!sc) {
        console.log('Thumbnail', ti + 1, '- scene', sceneNum, 'not in project');
        continue;
      }

      // Match! Use UUID as filename to prevent duplicates on disk
      console.log('Thumbnail', ti + 1, '- MATCH scene', sceneNum, ', UUID:', videoUuid.substring(0, 8));
      matched++;
      sc.urls = sc.urls || [];
      if (!sc.urls.includes(videoUrl.replace(/\?.*$/, ''))) {
        sc.urls.push(videoUrl);
      }
      sc.previewUrl = thumbSrc || '';
      sc.fileCount = sc.urls.length;
      sc.status = 'ready';
      render();

      if (S.autoSync) {
        // Send with UUID-based filename hint: scene_num/uuid.mp4
        await sendResults(sceneNum, [videoUrl]);
        if (videoUuid) S.sentUuids.add(videoUuid);
      }

    } catch (e) {
      console.error('Error processing thumbnail', ti + 1, ':', e.message);
    }
  }

  // Done
  fillEl.style.width = '100%';
  statusEl.classList.add('done');
  labelEl.textContent = 'Sync complete - ' + matched + '/' + total + ' matched';
  console.log('Sync complete:', matched, 'scenes matched out of', total, 'thumbnails');
  setTimeout(function() { statusEl.classList.remove('active', 'done'); fillEl.style.width = '0%'; }, 4000);

  await fetchStatus();
  render();
}

// ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ Render ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬
function render() {
  // Count typing statuses
  const tq = S.typing.queue;
  const selectedTq = getSelectedTypingItems();
  const selectedTotal = selectedTq.length;
  const selectedTyped = selectedTq.filter(q => q.status === 'typed').length;
  let queued = 0, typed = 0;
  tq.forEach(q => { if (q.status === 'queued') queued++; else if (q.status === 'typed') typed++; });

  // Count sync statuses
  let rdy = 0, sent = 0;
  for (const sc of Object.values(S.scenes)) {
    if (sc.status === 'ready') rdy++;
    else if (sc.status === 'sent' || sc.status === 'downloaded') sent++;
  }

  // Pill
  $id('sts-pill-dot').classList.toggle('on', S.connected);
  $id('sts-pill-p').textContent = queued;
  $id('sts-pill-r').textContent = rdy + sent;
  $id('sts-pill-proj').textContent = S.projectId || '';

  // Header
  $id('sts-head-dot').classList.toggle('on', S.connected);
  $id('sts-head-proj').textContent = S.projectId || '';
  $id('sts-head-proj').style.display = S.projectId ? '' : 'none';

  // Port display
  try {
    var portMatch = S.studioUrl.match(/:(\d+)/);
    $id('sts-head-port').textContent = portMatch ? ':' + portMatch[1] : '';
    $id('sts-head-port').style.display = portMatch ? '' : 'none';
  } catch(e) {}

  // Connection status
  var connBar = $id('sts-conn-bar');
  if (connBar) {
    if (!S.connected && S._fetchErrors > 0 && !S.wsConnected) {
      connBar.style.display = 'flex';
      connBar.classList.remove('ok');
      $id('sts-conn-icon').innerHTML = '&#x26A0;';
      $id('sts-conn-msg').textContent = 'Backend disconnected (retry in ' + Math.round(S.pollInterval / 1000) + 's)';
    } else if (S.wsConnected) {
      connBar.style.display = 'flex';
      connBar.classList.add('ok');
      $id('sts-conn-icon').innerHTML = '&#x2713;';
      $id('sts-conn-msg').textContent = 'WS connected';
    } else if (S.connected && S._fetchErrors === 0) {
      connBar.style.display = 'none';
    }
  }

  // Stats
  $id('sts-n-q').textContent = queued;
  $id('sts-n-typed').textContent = typed;
  $id('sts-n-rdy').textContent = rdy;
  $id('sts-n-sent').textContent = sent;

  // Typing progress
  if (S.activeTab === 'typing') {
    const total = selectedTotal;
    const pct = total > 0 ? (selectedTyped / total) * 100 : 0;
    $id('sts-prog-fill').style.width = pct + '%';

    if (S.typing.active) {
      const ci = S.typing.currentIndex;
      const curItem = ci >= 0 && tq[ci] ? tq[ci] : null;
      const currentPos = curItem ? (selectedTq.indexOf(curItem) + 1) : 0;
      if (curItem && curItem.status === 'generating') {
        // Progress label is set directly by waitForGeneration (shows %)
        // Don't override it here
      } else {
        $id('sts-prog-label').textContent = total > 0 ? 'Typing ' + currentPos + '/' + total : 'Typing...';
      }
      $id('sts-prog-cd').textContent = getTypingCountdownLabel();
      $id('sts-prog-cd').className = 'sts-cd' + ((S.typing.countdownType === 'next' || S.typing.countdownType === 'retry') ? ' cool' : '');
    } else if (total > 0) {
      $id('sts-prog-label').textContent = selectedTyped === total ? 'All selected typed' : 'Selected \u00b7 ' + selectedTyped + '/' + total;
      $id('sts-prog-cd').textContent = '';
    } else if (tq.length > 0) {
      $id('sts-prog-label').textContent = 'No prompts selected';
      $id('sts-prog-cd').textContent = '';
    } else {
      $id('sts-prog-label').textContent = 'No prompts queued';
      $id('sts-prog-cd').textContent = '';
    }
  }

  const selectionMeta = $id('sts-selection-meta');
  const selectAllBtn = $id('sts-select-all-btn');
  if (selectionMeta) {
    selectionMeta.textContent = tq.length ? (selectedTotal + ' of ' + tq.length + ' selected') : 'No prompts queued';
  }
  if (selectAllBtn) {
    const allSelected = areAllTypingItemsSelected();
    selectAllBtn.textContent = allSelected ? 'All Prompts Selected' : 'Select All Prompts';
    selectAllBtn.disabled = S.typing.active || !tq.length || allSelected;
  }

  // Action button + retry + redownload
  const btn = $id('sts-action-btn');
  const retryBtn = $id('sts-retry-btn');
  const redownloadBtn = $id('sts-redownload-btn');
  const hasTypingErrors = S.typing.queue.some(q => isTypingSelected(q) && (q.status === 'error' || q.status === 'failed'));
  const hasSyncErrors = Object.values(S.scenes).some(sc => sc.status === 'error');
  const jobDone = isJobComplete();

  if (S.activeTab === 'typing') {
    retryBtn.style.display = (hasTypingErrors && !S.typing.active) ? '' : 'none';
    if (redownloadBtn) redownloadBtn.style.display = 'none';
    if (S.typing.active) {
      btn.textContent = 'Stop';
      btn.className = 'sts-btn sts-btn-danger';
      btn.disabled = false;
    } else if (S.typing.starting) {
      btn.textContent = 'Starting...';
      btn.className = 'sts-btn sts-btn-ghost';
      btn.disabled = true;
    } else {
      btn.textContent = selectedTotal > 0 ? 'Start Typing' : 'Select Prompts';
      btn.className = 'sts-btn sts-btn-primary';
      btn.disabled = false;
    }
  } else {
    retryBtn.style.display = hasSyncErrors ? '' : 'none';
    if (redownloadBtn) redownloadBtn.style.display = (jobDone && hasSyncErrors) ? '' : 'none';
    btn.textContent = 'Sync Saved';
    btn.className = 'sts-btn sts-btn-primary';
    btn.disabled = false;
  }

  // List content
  const list = $id('sts-list');
  if (S.activeTab === 'typing') {
    if (!tq.length) {
      list.innerHTML = '<div class="sts-empty"><div class="sts-empty-icon">&#x270D;</div>No prompts queued yet.<br>Click Assets Grabber in Studio.</div>';
      return;
    }
    list.innerHTML = tq.map((q, i) => {
      const pr = (q.displayPrompt || '').length > 46 ? q.displayPrompt.substring(0, 46) + '...' : q.displayPrompt || '';
      let sHTML = '', meta = '';
      const isSelected = isTypingSelected(q);
      const isCurrent = S.typing.active && i === S.typing.currentIndex;
      if (q.status === 'queued') { sHTML = '<div class="sts-d-q"></div>'; meta = 'queued'; }
      else if (q.status === 'typing') { sHTML = '<div class="sts-d-typing"></div>'; meta = 'typing...'; }
      else if (q.status === 'generating') { sHTML = '<div class="sts-d-proc"></div>'; meta = 'generating...'; }
      else if (q.status === 'typed') { sHTML = '<span class="sts-d-typed">&#x2714;</span>'; meta = 'typed'; }
      else if (q.status === 'failed') { sHTML = '<span class="sts-d-err">&#x2718;</span>'; meta = 'failed (' + (q.errorCount || 0) + 'x)'; }
      else if (q.status === 'error') { sHTML = '<span class="sts-d-err">&#x2718;</span>'; meta = 'error' + (q.errorCount > 1 ? ' (' + q.errorCount + 'x)' : ''); }
      if (!isSelected) meta = 'unchecked' + (meta ? ' \u00b7 ' + meta : '');
      var rowCls = 'sts-row' + (isCurrent ? ' highlight' : '') + ((q.status === 'error' || q.status === 'failed') ? ' error-clickable' : '');
      var checkboxHtml = '<label class="sts-row-check-wrap"><input type="checkbox" class="sts-row-check" data-role="typing-checkbox" data-idx="' + i + '"' + (isSelected ? ' checked' : '') + (S.typing.active ? ' disabled' : '') + '></label>';
      var thumbHtml = q.imageUrl ? '<img class="sts-row-thumb" src="' + q.imageUrl + '" alt="">' : '<div class="sts-row-thumb sts-row-thumb-empty">' + q.scene + '</div>';
      return '<div class="' + rowCls + '" data-idx="' + i + '">' + checkboxHtml + thumbHtml + '<div class="sts-row-num">' + q.scene + '</div><div class="sts-row-info"><div class="sts-row-prompt">' + pr.replace(/</g, '&lt;') + '</div><div class="sts-row-meta">' + meta + '</div></div><div class="sts-row-status">' + sHTML + '</div></div>';
    }).join('');
  } else {
    const keys = Object.keys(S.scenes).sort((a, b) => parseInt(a) - parseInt(b));
    if (!keys.length) {
      list.innerHTML = '<div class="sts-empty"><div class="sts-empty-icon">&#x1F4E1;</div>Waiting for generations...</div>';
      return;
    }
    list.innerHTML = keys.map(num => {
      const sc = S.scenes[num];
      const pr = (sc.prompt || '').length > 52 ? sc.prompt.substring(0, 52) + '...' : sc.prompt || '';

      const badgeMap = {
        pending: ['pending', 'pending'],
        processing: ['processing', 'generating\u2026'],
        ready: ['ready', sc.fileCount + ' ready'],
        uploading: ['uploading', 'uploading\u2026'],
        sent: ['sent', sc.fileCount + ' sent'],
        downloaded: ['downloaded', sc.fileCount + ' synced'],
        error: ['error', 'error'],
      };
      const [bCls, bText] = badgeMap[sc.status] || ['pending', sc.status];

      let thumbsHTML = '';
      const urls = sc.urls || [];
      if (urls.length > 0) {
        // Use preview image for display (videos can't render as <img>)
        const displayUrl = sc.previewUrl || urls[0].replace(/generated_video\.mp4(\?.*)?$/, 'preview_image.jpg');
        const cols = urls.length <= 2 ? ' cols2' : '';
        thumbsHTML = '<div class="sts-thumbs' + cols + '">' +
          '<div class="sts-thumb"><img src="' + displayUrl.replace(/"/g, '&quot;') + '" loading="lazy" onerror="this.style.display=\'none\'" /></div>' +
        '</div>';
      } else if (sc.status === 'processing') {
        thumbsHTML = '<div class="sts-card-noimg">&#x23F3; Generating images\u2026</div>';
      } else if (sc.status === 'pending') {
        thumbsHTML = '<div class="sts-card-noimg">Waiting for generation</div>';
      }

      return '<div class="sts-card">' +
        '<div class="sts-card-head">' +
          '<div class="sts-card-num">' + num + '</div>' +
          '<div class="sts-card-prompt">' + pr.replace(/</g, '&lt;') + '</div>' +
          '<span class="sts-card-badge sts-badge-' + bCls + '">' + bText + '</span>' +
        '</div>' +
        thumbsHTML +
      '</div>';
    }).join('');
  }
}

// ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ Timer ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬
function updateTimer() {
  if (!S.lastPoll) { $id('sts-timer-val').textContent = '--'; return; }
  $id('sts-timer-val').textContent = Math.floor((Date.now() - S.lastPoll) / 1000) + 's ago';
}

function getTypingCountdownLabel() {
  if (!S.typing.countdown) return '';
  var type = S.typing.countdownType || 'wait';
  var labels = {
    next: 'next in',
    retry: 'retry in',
    settle: 'settle',
  };
  return (labels[type] || type) + ' ' + S.typing.countdown + 's';
}

// ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ Typing Engine ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬
async function startTyping() {
  if (S.typing.active || S.typing.starting) {
    console.log('Typing is already running');
    return;
  }
  const tq = S.typing.queue;
  if (!tq.length) { console.log('No prompts to type'); return; }
  if (!getSelectedTypingItems().length) { console.log('No checked prompts to type'); render(); return; }

  S.typing.starting = true;
  S.typing.stopRequested = false;
  S.typing.autoPaused = false;
  requeueTypingItems(['error', 'failed']);
  let runItems = getSelectedTypingItems().filter(function(item) { return item.status !== 'typed'; });
  if (!runItems.length) {
    const rerunCount = getSelectedTypingItems().reduce(function(count, item) {
      if (item.status !== 'typed') return count;
      return resetTypingItem(item) ? count + 1 : count;
    }, 0);
    if (rerunCount) {
      console.log('Re-queued', rerunCount, 'typed prompt(s) for re-run');
      runItems = getSelectedTypingItems().filter(function(item) { return item.status !== 'typed'; });
    }
  }
  if (!runItems.length) {
    S.typing.starting = false;
    console.log('All checked prompts are already typed');
    render();
    return;
  }

  const runId = S.typing.runId + 1;
  S.typing.runId = runId;
  S.typing.active = true;
  S.typing.starting = false;
  S.typing.nextAutoStartAt = Date.now() + 3000;
  S.typing.typedCount = 0;
  S.typing.batchCount = 0;
  render();
  console.log('=== PHASE 1: Typing', runItems.length, 'checked prompts ===');

  // Setup Grok video mode before first prompt
  try { await setupGrokMode(); } catch(e) { console.warn('Grok mode setup failed:', e.message); }

  // Collect ALL existing video URLs on the page before we start typing
  // Strip query params for reliable comparison (Grok appends ?cache=N)
  var seenVideoUrls = new Set();
  function addSeen(url) {
    if (!url) return;
    var clean = url.replace(/\?.*$/, '');
    seenVideoUrls.add(clean);
    // Reserve the eventual video URL for any generated asset UUID,
    // regardless of the original filename (preview_image, image_0, etc.)
    var um = clean.match(/\/users\/([a-f0-9-]+)\/generated\/([a-f0-9-]+)\//);
    if (um) {
      seenVideoUrls.add('https://assets.grok.com/users/' + um[1] + '/generated/' + um[2] + '/generated_video.mp4');
    }
  }
  document.querySelectorAll('video[src*="assets.grok.com"]').forEach(function(v) {
    addSeen(v.src || v.getAttribute('src') || '');
  });
  // Also pre-seed from existing thumbnail/generated images already on the page
  document.querySelectorAll('img[src*="assets.grok.com"][src*="/generated/"]').forEach(function(img) {
    addSeen(img.src || img.getAttribute('src') || '');
  });
  var sdv = document.getElementById('sd-video');
  if (sdv && sdv.src) addSeen(sdv.src);
  console.log('Pre-existing assets to ignore:', seenVideoUrls.size);

  for (let i = 0; i < tq.length; i++) {
    if (shouldStopTyping(runId)) break;
    const item = tq[i];
    if (!isTypingSelected(item)) continue;
    if (item.status === 'typed') continue;

    // Skip permanently failed scenes (3+ errors)
    if (item.errorCount >= 3) { item.status = 'failed'; continue; }

    S.typing.currentIndex = i;
    item.status = 'typing';
    render();

    try {
      // Snapshot current video srcs to ignore (grows after each generation)
      document.querySelectorAll('video[src*="assets.grok.com"]').forEach(function(v) {
        var s = v.src || v.getAttribute('src') || '';
        if (s) addSeen(s);
      });
      // Upload storyboard image if available (before typing prompt)
      if (item.imageUrl && item.imageUrl.startsWith('data:')) {
        console.log('Uploading storyboard image for scene', item.scene);
        var imgOk = await uploadImageToGrok(item.imageUrl);
        if (!imgOk) console.warn('Image upload failed for scene', item.scene, '- continuing with prompt only');
      }
      // Type the prompt and submit
      await typeIntoGrok(item.fullPrompt);
      console.log('Submitted scene', item.scene, '- waiting for generation...');
      item.status = 'generating';
      render();

      const genResult = await waitForGeneration(item.scene, seenVideoUrls, undefined, runId);

      if (shouldStopTyping(runId)) { item.status = item.status === 'generating' ? 'queued' : item.status; break; }
      if (genResult) {
        const videoUrl = genResult.primary;
        const allVideoUrls = genResult.allUrls || [videoUrl];
        addSeen(videoUrl);  // Track primary URL so next scene ignores it
        allVideoUrls.forEach(function(u) { addSeen(u); });
        item.status = 'typed';
        item.videoUrl = videoUrl;
        item.allVideoUrls = allVideoUrls;
        S.typing.typedCount++;
        S.typing.batchCount++;
        console.log('Scene', item.scene, 'generated:', allVideoUrls.length, 'video(s)');

        // Update scene state and immediately send results (don't wait for batch)
        const sc = S.scenes[item.scene];
        if (sc) {
          sc.urls = allVideoUrls;
          sc.previewUrl = videoUrl.replace(/generated_video\.mp4(\?.*)?$/, 'preview_image.jpg');
          sc.fileCount = allVideoUrls.length;
          sc.status = 'ready';
        }
        render();
        // Send immediately ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â grab each asset as it finishes
        if (!shouldStopTyping(runId)) {
          try {
            await sendResults(item.scene, allVideoUrls);
            console.log('Scene', item.scene, 'sent immediately after generation');
          } catch (sendErr) {
            console.error('Immediate send failed for scene', item.scene, ':', sendErr.message);
          }
        }
      } else {
        item.errorCount = (item.errorCount || 0) + 1;
        item.status = 'error';
        console.error('Generation timed out for scene', item.scene, '(error #' + item.errorCount + ')');
      }
      render();

      // Wait before next prompt
      const hasMore = tq.slice(i + 1).some(q => isTypingSelected(q) && q.status !== 'typed' && q.status !== 'failed');
      if (hasMore && !shouldStopTyping(runId)) {
        await doCountdown(5, 'next', runId);
        await waitForPageReady();
      }
    } catch (e) {
      item.errorCount = (item.errorCount || 0) + 1;
      console.error('Failed for scene', item.scene, '(error #' + item.errorCount + '):', e.message);
      item.status = 'error';
      render();
      await doCountdown(5, 'retry', runId);
    }
  }

  if (shouldStopTyping(runId)) {
    console.log('Typing stopped by user - skipping retry and post-processing');
    S.typing.currentIndex = -1;
    render();
    return;
  }

  // === Retry pass: re-attempt any failed/error scenes ===
  var retryMax = 2;
  for (var retry = 0; retry < retryMax; retry++) {
    var failedItems = tq.filter(function(q) { return isTypingSelected(q) && q.status === 'error' && (q.errorCount || 0) < 3; });
    if (!failedItems.length || shouldStopTyping(runId)) break;
    console.log('Retry pass', retry + 1, ':', failedItems.length, 'failed scenes');
    await doCountdown(5, 'retry', runId);
    await waitForPageReady();

    for (var fi = 0; fi < failedItems.length; fi++) {
      if (shouldStopTyping(runId)) break;
      var item = failedItems[fi];
      item.status = 'typing';
      S.typing.currentIndex = tq.indexOf(item);
      render();

      try {
        document.querySelectorAll('video[src*="assets.grok.com"]').forEach(function(v) {
          var s = v.src || v.getAttribute('src') || '';
          if (s) addSeen(s);
        });

        // Upload storyboard image on retry too
        if (item.imageUrl && item.imageUrl.startsWith('data:')) {
          var imgOk = await uploadImageToGrok(item.imageUrl);
          if (!imgOk) console.warn('Retry image upload failed for scene', item.scene);
        }
        await typeIntoGrok(item.fullPrompt);
        console.log('Retry: submitted scene', item.scene);
        item.status = 'generating';
        render();

        var genResult = await waitForGeneration(item.scene, seenVideoUrls, undefined, runId);

        if (shouldStopTyping(runId)) { item.status = item.status === 'generating' ? 'queued' : item.status; break; }
        if (genResult) {
          var videoUrl = genResult.primary;
          var allVideoUrls = genResult.allUrls || [videoUrl];
          addSeen(videoUrl);
          allVideoUrls.forEach(function(u) { addSeen(u); });
          item.status = 'typed';
          item.videoUrl = videoUrl;
          S.typing.typedCount++;
          S.typing.batchCount++;
          var sc = S.scenes[item.scene];
          if (sc) { sc.urls = allVideoUrls; sc.previewUrl = videoUrl.replace(/generated_video\.mp4(\?.*)?$/, 'preview_image.jpg'); sc.fileCount = allVideoUrls.length; sc.status = 'ready'; }
          item.allVideoUrls = allVideoUrls;
          render();
          if (!shouldStopTyping(runId)) {
            try { await sendResults(item.scene, allVideoUrls); } catch (sendErr) { console.error('Retry send failed:', sendErr.message); }
          }
        } else {
          item.errorCount = (item.errorCount || 0) + 1;
          item.status = item.errorCount >= 3 ? 'failed' : 'error';
          console.error('Retry failed for scene', item.scene, '(error #' + item.errorCount + ')');
        }
        render();

        if (fi < failedItems.length - 1 && !shouldStopTyping(runId)) {
          await doCountdown(5, 'retry', runId);
          await waitForPageReady();
        }
      } catch (e) {
        item.errorCount = (item.errorCount || 0) + 1;
        console.error('Retry error for scene', item.scene, '(error #' + item.errorCount + '):', e.message);
        item.status = item.errorCount >= 3 ? 'failed' : 'error';
        render();
        await doCountdown(5, 'retry', runId);
      }
    }
  }

  if (shouldStopTyping(runId)) {
    console.log('Typing stopped by user - skipping verify and rescan');
    S.typing.currentIndex = -1;
    render();
    return;
  }

  // === Verify pass: check all scenes got sent, re-send any unsent ===
  await fetchStatus();
  var unsent = [];
  for (var qi = 0; qi < tq.length; qi++) {
    var q = tq[qi];
    if (q.status === 'typed' && q.videoUrl && !S.sentScenes[q.scene]) {
      unsent.push(q);
    }
  }
  if (unsent.length > 0) {
    console.log('Verify pass:', unsent.length, 'scenes with URLs not confirmed on server, re-sending...');
    for (var ui = 0; ui < unsent.length; ui++) {
      if (shouldStopTyping(runId)) break;
      try {
        await sendResults(unsent[ui].scene, unsent[ui].allVideoUrls || [unsent[ui].videoUrl]);
      } catch (e) { console.error('Re-send failed for scene', unsent[ui].scene); }
    }
  }

  // Mark remaining errors with 3+ attempts as permanently failed
  tq.forEach(function(q) { if (q.status === 'error' && (q.errorCount || 0) >= 3) q.status = 'failed'; });

  // Phase 2 removed ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â assets are now sent immediately after each generation completes

  // === Rescan pass: click all thumbnails to catch any missed videos ===
  console.log('Starting rescan pass - checking all thumbnails...');
  var rescanThumbs = document.querySelectorAll('button img[alt^="Thumbnail"]');
  var rescanTagRe = new RegExp('\\[' + S.projectId.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '\\|(\\d+)\\]');
  var rescanFound = 0;
  for (var ri = 0; ri < rescanThumbs.length; ri++) {
    if (shouldStopTyping(runId)) break;
    var rThumbImg = rescanThumbs[ri];
    var rThumbBtn = rThumbImg.closest('button');
    if (!rThumbBtn) continue;
    try {
      simulateClick(rThumbBtn);
      await sleep(1200);
      var rSdVideo = document.getElementById('sd-video');
      var rAttempts = 0;
      while ((!rSdVideo || !rSdVideo.src) && rAttempts < 6) {
        await sleep(400);
        rSdVideo = document.getElementById('sd-video');
        rAttempts++;
      }
      var rVideoUrl = rSdVideo ? (rSdVideo.src || rSdVideo.getAttribute('src') || '') : '';
      var rThumbSrc = rThumbImg.src || rThumbImg.getAttribute('src') || '';
      if (!rVideoUrl) {
        var rUuidMatch = rThumbSrc.match(/generated\/([a-f0-9-]+)\//);
        var rUserMatch = rThumbSrc.match(/users\/([a-f0-9-]+)\//);
        if (rUuidMatch && rUserMatch) {
          rVideoUrl = 'https://assets.grok.com/users/' + rUserMatch[1] + '/generated/' + rUuidMatch[1] + '/generated_video.mp4';
        }
      }
      if (!rVideoUrl) continue;
      var rEditor = document.querySelector('.tiptap.ProseMirror');
      var rPrompt = '';
      if (rEditor) { var rP = rEditor.querySelector('p'); rPrompt = rP ? rP.textContent.trim() : rEditor.textContent.trim(); }
      var rMatch = rPrompt.match(rescanTagRe);
      if (!rMatch) continue;
      var rSceneNum = rMatch[1];
      var rSc = S.scenes[rSceneNum];
      if (!rSc) continue;
      // Always update preview from thumbnail
      rSc.previewUrl = rThumbSrc || rVideoUrl.replace(/generated_video\.mp4(\?.*)?$/, 'preview_image.jpg');
      if (!S.sentScenes[rSceneNum]) {
        console.log('Rescan: found unsent scene', rSceneNum, '- sending video...');
        var rAllUrls = [rVideoUrl];
        rSc.urls = rAllUrls;
        rSc.fileCount = rAllUrls.length;
        rSc.status = 'ready';
        render();
        await sendResults(rSceneNum, rAllUrls);
        rescanFound++;
      } else {
        render();
      }
    } catch (re) { console.error('Rescan error thumbnail', ri + 1, ':', re.message); }
  }
  if (rescanFound > 0) console.log('Rescan: uploaded', rescanFound, 'missed scenes');

  // Final status confirmation
  await fetchStatus();

  var finalScope = getSelectedTypingItems();
  var finalFailed = finalScope.filter(function(q) { return q.status === 'error' || q.status === 'failed'; }).length;
  var finalTyped = finalScope.filter(function(q) { return q.status === 'typed'; }).length;
  console.log('=== BATCH COMPLETE:', finalTyped, '/', finalScope.length, 'selected prompts succeeded,', finalFailed, 'failed ===');

  // Browser notification
  try {
    if (Notification.permission === 'granted') {
      new Notification('STS Assets Sync', { body: finalTyped + '/' + finalScope.length + ' selected scenes completed' + (finalFailed > 0 ? ' (' + finalFailed + ' failed)' : '') });
    }
  } catch(e) {}

  S.typing.active = false;
  S.typing.stopRequested = false;
  S.typing.currentIndex = -1;
  S.typing.countdown = 0;
  S.typing.countdownType = '';
  render();
}

function stopTyping() {
  S.typing.stopRequested = true;
  S.typing.autoPaused = true;
  S.typing.active = false;
  S.typing.starting = false;
  S.typing.countdown = 0;
  S.typing.countdownType = '';
  S.typing.nextAutoStartAt = Date.now() + 15000;
  tryStopGrokGeneration();
  // Reset any in-progress items back to queued
  const tq = S.typing.queue;
  for (var si = 0; si < tq.length; si++) {
    if (tq[si].status === 'typing' || tq[si].status === 'generating') {
      tq[si].status = 'queued';
    }
  }
  S.typing.currentIndex = -1;
  console.log('Typing stopped');
  render();
}

// --- Wait for Grok generation to complete ---
// Two-phase approach:
//   Phase 1: Wait for generation to START (sd-video disappears, canvas/Generating appears)
//   Phase 2: Wait for generation to FINISH (new sd-video appears with different src)

// Collect NEW video .mp4 URLs from thumbnail buttons in the LATEST article only.
// Each thumbnail has an img with a preview_image.jpg URL; derive .mp4 from UUID.
// seenUrls: Set of URLs from previous generations to exclude (prevents cross-scene mixing).
function collectAllVideoUrls(seenUrls) {
  var urls = [];
  var seen = new Set();
  // Normalize seenUrls to strip query params for reliable comparison
  var seenClean = new Set();
  if (seenUrls) {
    seenUrls.forEach(function(u) { seenClean.add(u.replace(/\?.*$/, '')); });
  }
  // Scope to latest article to avoid picking up previous generations
  var articles = document.querySelectorAll('article');
  var scope = articles.length > 0 ? articles[articles.length - 1] : document;
  // Method 1: thumbnail buttons with preview images (within latest article)
  var thumbImgs = scope.querySelectorAll('button img[alt^="Thumbnail"]');
  for (var ti = 0; ti < thumbImgs.length; ti++) {
    var src = thumbImgs[ti].src || thumbImgs[ti].getAttribute('src') || '';
    var uuidMatch = src.match(/generated\/([a-f0-9-]+)\//);
    var userMatch = src.match(/users\/([a-f0-9-]+)\//);
    if (uuidMatch && userMatch) {
      var mp4 = 'https://assets.grok.com/users/' + userMatch[1] + '/generated/' + uuidMatch[1] + '/generated_video.mp4';
      if (!seen.has(mp4) && !seenClean.has(mp4)) { seen.add(mp4); urls.push(mp4); }
    }
  }
  // Method 2: also grab sd-video src as fallback
  var sdv = document.getElementById('sd-video');
  if (sdv) {
    var sdSrc = (sdv.src || sdv.getAttribute('src') || '').replace(/\?.*$/, '');
    if (sdSrc && sdSrc.includes('.mp4') && !seen.has(sdSrc) && !seenClean.has(sdSrc)) { seen.add(sdSrc); urls.push(sdSrc); }
  }
  return urls;
}


function isVideoModeJob() {
  return (S.grokMode || '').toLowerCase() === 'video';
}


function isVideoAssetUrl(url) {
  var clean = String(url || '').replace(/\?.*$/, '').toLowerCase();
  return clean.endsWith('.mp4') || clean.endsWith('.webm') || clean.endsWith('.mov') || clean.includes('/generated_video');
}


// previousSrc: the video src from the previous generation (to distinguish old from new)
async function waitForGeneration(sceneId, seenUrls, timeoutMs, runId) {
  timeoutMs = timeoutMs || 300000;
  var pollInterval = 2000;
  var maxPolls = Math.ceil(timeoutMs / pollInterval);
  console.log('waitForGeneration: scene', sceneId, '| ignoring', seenUrls.size, 'known URLs');

  // --- Phase 1: Wait for generation to START (max 60s) ---
  var previousUrl = window.location.href;
  var started = false;
  for (var a = 0; a < 30; a++) {
    if (shouldStopTyping(runId)) return null;

    // Multiple signals that generation has begun
    var videoGone = !document.getElementById('sd-video');
    var hasCanvas = !!document.querySelector('canvas');
    var hasSpin = !!document.querySelector('.animate-spin');
    var genSpan = document.querySelector('span.animate-pulse');
    var hasGen = genSpan && /generating/i.test(genSpan.textContent);
    var urlChanged = window.location.href !== previousUrl;
    var svgPct = parseSvgProgress();

    if (videoGone || hasCanvas || hasSpin || hasGen || urlChanged || svgPct >= 0) {
      started = true;
      console.log('Generation STARTED:', [videoGone && 'video-gone', hasCanvas && 'canvas', hasSpin && 'spinner', hasGen && 'generating-text', urlChanged && 'url-changed', svgPct >= 0 && ('svg-' + svgPct + '%')].filter(Boolean).join(', '));
      break;
    }
    $id('sts-prog-label').textContent = 'Waiting to start...';
    $id('sts-prog-cd').textContent = '';
    await sleep(pollInterval);
  }

  if (!started) console.warn('No start signal after 60s, continuing anyway');

  // --- Phase 2: Wait for generation to FINISH (max 5min) ---
  for (var p = 0; p < maxPolls; p++) {
    if (shouldStopTyping(runId)) return null;

    // Detect active generation: "Generating" text, spinner, canvas, SVG progress
    var isActive = false;
    var pctText = '';

    // Method 1: "Generating XX%" text spans
    var gs = document.querySelector('span.animate-pulse');
    if (gs && /generating/i.test(gs.textContent)) {
      isActive = true;
      var tabNums = gs.parentElement ? gs.parentElement.querySelector('.tabular-nums') : null;
      pctText = tabNums ? tabNums.textContent.trim() : '';
    }

    // Method 2: SVG circle progress (more accurate percentage)
    var svgPct = parseSvgProgress();
    if (svgPct >= 0 && svgPct < 100) {
      isActive = true;
      pctText = svgPct + '%';
    }

    // Method 3: Loading spinner
    if (document.querySelector('.animate-spin')) isActive = true;

    // Method 4: Canvas visible (preview placeholder during generation)
    if (document.querySelector('canvas')) isActive = true;

    if (isActive) started = true;

    // Update progress UI
    if (isActive && pctText) {
      $id('sts-prog-label').textContent = 'Generating... ' + pctText;
      $id('sts-prog-cd').textContent = '';
      console.log('Generating...', pctText);
    } else if (isActive) {
      $id('sts-prog-label').textContent = 'Generating...';
      $id('sts-prog-cd').textContent = '';
    }

    // Don't check for result while generation is active
    if (isActive) {
      await sleep(pollInterval);
      continue;
    }

    // Generation indicators gone ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â check for completed video
    if (started) {
      // Use .last() pattern: latest article's video is the newest generation
      var articles = document.querySelectorAll('article');
      var lastArticle = articles.length > 0 ? articles[articles.length - 1] : document;
      var videos = lastArticle.querySelectorAll('video[src*="assets.grok.com"]');
      var latestVideo = videos.length > 0 ? videos[videos.length - 1] : null;
      var vSrc = latestVideo ? (latestVideo.src || latestVideo.getAttribute('src') || '') : '';

      // Also check by id (sd-video)
      if (!vSrc) {
        var sdv = document.getElementById('sd-video');
        vSrc = sdv ? (sdv.src || sdv.getAttribute('src') || '') : '';
      }

      // Must be a NEW video not seen before
      if (vSrc && !seenUrls.has(vSrc.replace(/\?.*$/, '')) && vSrc.includes('.mp4')) {
        console.log('NEW video ready:', vSrc.split('/').pop());
        // Collect ALL variant video URLs from thumbnails
        var allUrls = collectAllVideoUrls(seenUrls);
        if (!allUrls.length) allUrls = [vSrc];
        console.log('Found', allUrls.length, 'video variant(s) for scene', sceneId);
        return { primary: vSrc, allUrls: allUrls };
      }

      // Fallback: check for generated image
      var imgs = lastArticle.querySelectorAll('img[src*="assets.grok.com"][src*="/generated/"]');
      var latestImg = imgs.length > 0 ? imgs[imgs.length - 1] : null;
      var iSrc = latestImg ? (latestImg.src || latestImg.getAttribute('src') || '') : '';
      if (iSrc && !seenUrls.has(iSrc.replace(/\?.*$/, '')) && iSrc.includes('assets.grok.com')) {
        if (isVideoModeJob()) {
          console.warn('Ignoring image fallback while waiting for video:', iSrc.split('/').pop());
          await sleep(pollInterval);
          continue;
        }
        console.log('NEW image ready:', iSrc.split('/').pop());
        return { primary: iSrc, allUrls: [iSrc] };
      }
    }

    await sleep(pollInterval);
  }

  if (shouldStopTyping(runId)) return null;
  console.error('Generation timed out after', timeoutMs / 1000, 'seconds');
  // Try clicking Regenerate button before giving up
  await tryRegenerate();
  // Check one more time after regenerate attempt
  await sleep(5000);
  if (shouldStopTyping(runId)) return null;
  var articles = document.querySelectorAll('article');
  var lastArt = articles.length > 0 ? articles[articles.length - 1] : document;
  var lastVids = lastArt.querySelectorAll('video[src*="assets.grok.com"]');
  var lastV = lastVids.length > 0 ? lastVids[lastVids.length - 1] : null;
  var lastSrc = lastV ? (lastV.src || lastV.getAttribute('src') || '') : '';
  if (lastSrc && !seenUrls.has(lastSrc.replace(/\?.*$/, '')) && lastSrc.includes('.mp4')) {
    console.log('Regenerate succeeded! Video:', lastSrc.split('/').pop());
    var regenUrls = collectAllVideoUrls(seenUrls);
    if (!regenUrls.length) regenUrls = [lastSrc];
    return { primary: lastSrc, allUrls: regenUrls };
  }
  return null;
}

function findGrokInputElement() {
  var selectors = [
    '.tiptap.ProseMirror[contenteditable="true"]',
    '.tiptap.ProseMirror',
    'div[role="textbox"][contenteditable="true"]',
    '[contenteditable="true"][data-lexical-editor="true"]',
    'textarea[placeholder]',
    'textarea',
    '[contenteditable="true"]'
  ];
  for (var si = 0; si < selectors.length; si++) {
    var hits = document.querySelectorAll(selectors[si]);
    for (var hi = 0; hi < hits.length; hi++) {
      var el = hits[hi];
      if (!el || el.closest('#sts-sync') || !isElReady(el)) continue;
      return el;
    }
  }
  return null;
}

function getComposerRoot(inputEl) {
  if (!inputEl) return null;
  return inputEl.closest('form') ||
    inputEl.closest('[data-testid*="composer"]') ||
    inputEl.closest('[class*="composer"]') ||
    inputEl.closest('[class*="input"]') ||
    inputEl.parentElement ||
    inputEl;
}

function getComposerText(inputEl) {
  if (!inputEl) return '';
  if (inputEl instanceof HTMLTextAreaElement || inputEl instanceof HTMLInputElement) {
    return inputEl.value || '';
  }
  return inputEl.textContent || '';
}

function setNativeFieldValue(inputEl, value) {
  if (!inputEl) return;
  var proto = inputEl instanceof HTMLTextAreaElement ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
  var descriptor = Object.getOwnPropertyDescriptor(proto, 'value');
  if (descriptor && descriptor.set) descriptor.set.call(inputEl, value);
  else inputEl.value = value;
}

function dispatchComposerInput(inputEl, text) {
  if (!inputEl) return;
  try {
    inputEl.dispatchEvent(new InputEvent('input', {
      bubbles: true,
      cancelable: true,
      data: text || '',
      inputType: text ? 'insertText' : 'deleteContentBackward'
    }));
  } catch (e) {
    inputEl.dispatchEvent(new Event('input', { bubbles: true, cancelable: true }));
  }
  inputEl.dispatchEvent(new Event('change', { bubbles: true, cancelable: true }));
}

function selectComposerContents(inputEl) {
  if (!inputEl || inputEl instanceof HTMLTextAreaElement || inputEl instanceof HTMLInputElement) return;
  var selection = window.getSelection ? window.getSelection() : null;
  if (!selection) return;
  var range = document.createRange();
  range.selectNodeContents(inputEl);
  selection.removeAllRanges();
  selection.addRange(range);
}

function clearComposer(inputEl) {
  if (!inputEl) return;
  if (inputEl instanceof HTMLTextAreaElement || inputEl instanceof HTMLInputElement) {
    setNativeFieldValue(inputEl, '');
    dispatchComposerInput(inputEl, '');
    return;
  }
  selectComposerContents(inputEl);
  try { document.execCommand('delete', false, null); } catch (e) {}
  if (normalizeText(getComposerText(inputEl))) {
    inputEl.textContent = '';
  }
  dispatchComposerInput(inputEl, '');
}

function setComposerText(inputEl, text) {
  if (!inputEl) return;
  if (inputEl instanceof HTMLTextAreaElement || inputEl instanceof HTMLInputElement) {
    setNativeFieldValue(inputEl, text);
    if (typeof inputEl.selectionStart === 'number') {
      inputEl.selectionStart = inputEl.value.length;
      inputEl.selectionEnd = inputEl.value.length;
    }
    dispatchComposerInput(inputEl, text);
    return;
  }

  selectComposerContents(inputEl);
  try {
    inputEl.dispatchEvent(new InputEvent('beforeinput', {
      bubbles: true,
      cancelable: true,
      data: text,
      inputType: 'insertText'
    }));
  } catch (e) {}
  try { document.execCommand('insertText', false, text); } catch (e) {}

  if (!normalizeText(getComposerText(inputEl))) {
    var paragraph = inputEl.querySelector('p');
    if (!paragraph && inputEl.classList && inputEl.classList.contains('ProseMirror')) {
      inputEl.innerHTML = '<p></p>';
      paragraph = inputEl.querySelector('p');
    }
    if (paragraph) paragraph.textContent = text;
    else inputEl.textContent = text;
  }
  dispatchComposerInput(inputEl, text);
}

function composerHasPrompt(inputEl, text) {
  var current = normalizeText(getComposerText(inputEl));
  var expected = normalizeText(text);
  if (!current || !expected) return false;
  if (current === expected) return true;
  var probe = expected.slice(0, Math.min(expected.length, 48));
  return !!probe && current.indexOf(probe) !== -1;
}

function findGrokSubmitButton(inputEl) {
  var root = getComposerRoot(inputEl);
  var buttons = document.querySelectorAll('button');
  var best = null;
  var bestScore = -1;

  for (var bi = 0; bi < buttons.length; bi++) {
    var btn = buttons[bi];
    if (!btn || btn.closest('#sts-sync') || btn.disabled || !isElReady(btn)) continue;

    var label = normalizeText(btn.textContent);
    var aria = btn.getAttribute('aria-label') || '';
    var testId = btn.getAttribute('data-testid') || '';
    var combined = (label + ' ' + aria + ' ' + testId).toLowerCase();
    if (/stop|cancel|retry|regenerate|redownload|sync saved|start typing/.test(combined)) continue;

    var score = 0;
    if (/send|submit|generate|create/.test(combined)) score += 6;
    if ((btn.getAttribute('type') || '').toLowerCase() === 'submit') score += 4;
    if (/send|submit/.test(testId.toLowerCase())) score += 4;
    if (root && root !== btn && root.contains(btn)) score += 4;
    if (inputEl && inputEl.form && btn.form === inputEl.form) score += 3;

    if (score > bestScore) {
      bestScore = score;
      best = btn;
    }
  }

  return bestScore > 0 ? best : null;
}

function dispatchEnterSubmit(inputEl) {
  if (!inputEl) return;
  var events = ['keydown', 'keypress', 'keyup'];
  for (var i = 0; i < events.length; i++) {
    inputEl.dispatchEvent(new KeyboardEvent(events[i], {
      key: 'Enter',
      code: 'Enter',
      keyCode: 13,
      which: 13,
      bubbles: true,
      cancelable: true
    }));
  }
}

function hasSubmissionSignal(state) {
  if (!state) return false;
  if (window.location.href !== state.url) return true;
  if (document.querySelectorAll('article').length > state.articleCount) return true;
  if (state.hadVideo && !document.getElementById('sd-video')) return true;
  if (document.querySelector('canvas')) return true;
  if (document.querySelector('.animate-spin')) return true;
  if (parseSvgProgress() >= 0) return true;
  var genSpan = document.querySelector('span.animate-pulse');
  return !!(genSpan && /generating/i.test(genSpan.textContent || ''));
}

async function waitForSubmissionAccepted(inputEl, text, state, timeoutMs) {
  timeoutMs = timeoutMs || 4000;
  var started = Date.now();
  while (Date.now() - started < timeoutMs) {
    var currentInput = findGrokInputElement() || inputEl;
    if (!composerHasPrompt(currentInput, text)) return true;
    if (hasSubmissionSignal(state)) return true;
    await sleep(250);
  }
  return hasSubmissionSignal(state);
}

// --- Wait for /imagine page to be ready after navigation ---
async function waitForPageReady(timeoutMs) {
  timeoutMs = timeoutMs || 15000;
  var pollInterval = 500;
  var maxAttempts = Math.ceil(timeoutMs / pollInterval);
  for (var i = 0; i < maxAttempts; i++) {
    var editor = findGrokInputElement();
    if (editor) {
      console.log('Page ready - composer found');
      return true;
    }
    await sleep(pollInterval);
  }
  console.warn('Page ready timeout - composer not found');
  return false;
}

async function doCountdown(seconds, type, runId) {
  S.typing.countdown = seconds;
  S.typing.countdownType = type;
  render();
  for (let i = seconds; i > 0; i--) {
    if (shouldStopTyping(runId)) break;
    S.typing.countdown = i;
    render();
    await sleep(1000);
  }
  S.typing.countdown = 0;
  S.typing.countdownType = '';
  render();
}


// ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ Grok Mode Setup (Video, 480p, 6s, aspect ratio) ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬

async function setupGrokMode() {
  console.log('Setting up Grok mode:', S.grokMode + ',', S.grokQuality + ',', S.grokDuration + ', aspect=' + S.aspectRatio);

  // Detect UI version (from Grok Automation extension pattern)
  var uiVersion = 3;
  if (document.querySelector('.group\\/attach-button')) {
    uiVersion = 1;
  } else if (document.querySelector('div.inline-flex > div[role="radiogroup"]')) {
    uiVersion = 3;
  } else {
    uiVersion = 2;
  }
  console.log('Detected Grok UI version:', uiVersion);

  // -- Step 1: Select mode (Video / Image) --
  var radioGroup = document.querySelector('div[role="radiogroup"]');
  if (radioGroup) {
    var radios = radioGroup.querySelectorAll('[role="radio"]');
    for (var r of radios) {
      if (r.textContent.trim().toLowerCase() === S.grokMode) {
        simulateClick(r);
        console.log('Selected mode:', S.grokMode);
        await sleep(800);
        break;
      }
    }
  }

  // -- Step 2: Select aspect ratio --
  var targetRatio = S.aspectRatio || '9:16';
  if (uiVersion === 3) {
    // v3: find div.inline-flex[data-state="closed"] that is NOT the radiogroup
    var closedDivs = document.querySelectorAll('div.inline-flex[data-state="closed"]');
    var arDiv = null;
    for (var cd of closedDivs) {
      if (!cd.querySelector('[role="radiogroup"]') && !cd.closest('[role="radiogroup"]')) {
        arDiv = cd;
        break;
      }
    }
    if (arDiv) {
      var arBtn = arDiv.querySelector('button');
      if (arBtn) {
        simulateClick(arBtn);
        await sleep(600);
      }
    }
  } else {
    // v1/v2: open the mode config trigger dropdown
    var configTrigger = document.querySelector('button[data-testid="mode-config-trigger"]');
    if (configTrigger) {
      simulateClick(configTrigger);
      await sleep(600);
    }
  }
  // Now find and click the ratio option in the open dropdown/menu
  var ratioFound = false;
  for (var attempt = 0; attempt < 15 && !ratioFound; attempt++) {
    // Try data-aspect-ratio attribute first (v1/v2)
    var ratioBtn = document.querySelector('button[data-aspect-ratio="' + targetRatio + '"]');
    if (ratioBtn) {
      simulateClick(ratioBtn);
      console.log('Selected aspect ratio (data-attr):', targetRatio);
      ratioFound = true;
      await sleep(400);
      break;
    }
    // Try Radix menuitem with text match (v3)
    var menuItems = document.querySelectorAll('[role="menu"] [role="menuitem"]');
    for (var mi of menuItems) {
      var span = mi.querySelector('span');
      if (span && span.textContent.trim() === targetRatio) {
        simulateClick(mi);
        console.log('Selected aspect ratio (menu):', targetRatio);
        ratioFound = true;
        await sleep(400);
        break;
      }
    }
    if (!ratioFound) await sleep(200);
  }
  if (!ratioFound) console.warn('Aspect ratio not found:', targetRatio);

  // -- Step 3: Select duration (6s / 10s) --
  if (uiVersion !== 3) {
    var wrapper = document.querySelector('[data-testid="mode-selected-wrapper"]');
    if (!wrapper) {
      var trigger = document.querySelector('button[data-testid="mode-config-trigger"]');
      if (trigger) { simulateClick(trigger); await sleep(600); }
    }
  }
  var targetDur = S.grokDuration.replace(/\s/g, '');
  var durFound = false;
  var allBtns = document.querySelectorAll('button');
  for (var btn of allBtns) {
    var t = btn.textContent.trim();
    if (t === targetDur || t === targetDur.replace('s', ' s')) {
      simulateClick(btn);
      console.log('Selected duration:', targetDur);
      durFound = true;
      await sleep(400);
      break;
    }
  }
  if (!durFound) console.warn('Duration option not found:', targetDur);

  // -- Step 4: Select quality (480p / 720p) --
  var qualFound = false;
  allBtns = document.querySelectorAll('button');
  for (var btn of allBtns) {
    if (btn.textContent.trim() === S.grokQuality) {
      simulateClick(btn);
      console.log('Selected quality:', S.grokQuality);
      qualFound = true;
      await sleep(400);
      break;
    }
  }
  if (!qualFound) console.warn('Quality option not found:', S.grokQuality);

  // Close dropdown if v1/v2 left it open
  if (uiVersion !== 3) {
    var openWrapper = document.querySelector('[data-testid="mode-selected-wrapper"]');
    if (openWrapper) {
      var closeTrigger = document.querySelector('button[data-testid="mode-config-trigger"]');
      if (closeTrigger) { simulateClick(closeTrigger); await sleep(300); }
    }
  }

  console.log('Grok mode setup complete');
}
// Try clicking Regenerate button if generation failed
async function tryRegenerate() {
  try {
    var regenBtn = document.querySelector('button[aria-label*="Regenerate"], button[aria-label*="regenerate"]');
    if (!regenBtn) {
      var allBtns = document.querySelectorAll('button');
      for (var b = 0; b < allBtns.length; b++) {
        if (/regenerate/i.test(allBtns[b].textContent)) { regenBtn = allBtns[b]; break; }
      }
    }
    if (regenBtn && isElReady(regenBtn)) {
      console.log('Clicking Regenerate button...');
      simulateClick(regenBtn);
      await sleep(2000);
    }
  } catch(e) { console.log('No regenerate button found'); }
}

async function uploadImageToGrok(base64Data) {
  if (!base64Data) return false;

  // Decode base64 to File object
  var raw = base64Data.includes(',') ? base64Data.split(',').pop() : base64Data;
  var binaryString = atob(raw);
  var bytes = new Uint8Array(binaryString.length);
  for (var i = 0; i < binaryString.length; i++) {
    bytes[i] = binaryString.charCodeAt(i);
  }

  var mimeMatch = base64Data.match(/data:([^;]+);/);
  var mimeType = mimeMatch ? mimeMatch[1] : 'image/jpeg';
  var blob = new Blob([bytes], { type: mimeType });
  var file = new File([blob], 'sts-input-' + Date.now() + '.jpg', { type: mimeType });

  // Find Grok's hidden file input
  var fileInput = document.querySelector('input[type="file"]');
  if (!fileInput) {
    // Wait for it
    for (var attempt = 0; attempt < 20; attempt++) {
      await sleep(500);
      fileInput = document.querySelector('input[type="file"]');
      if (fileInput) break;
    }
  }
  if (!fileInput) {
    console.error('[STS] File input not found on page');
    return false;
  }

  // Inject via DataTransfer API
  var dataTransfer = new DataTransfer();
  dataTransfer.items.add(file);
  fileInput.files = dataTransfer.files;
  fileInput.dispatchEvent(new Event('change', { bubbles: true }));

  console.log('[STS] Image injected, waiting for upload...');

  // Wait for upload spinner to disappear
  await sleep(1000);
  for (var w = 0; w < 60; w++) {
    var spinner = document.querySelector('.animate-spin, [class*="uploading"], [class*="loading"]');
    if (!spinner) break;
    await sleep(500);
  }
  await sleep(500);

  console.log('[STS] Image upload complete');
  return true;
}

async function typeIntoGrok(text) {
  var inputEl = findGrokInputElement();
  if (!inputEl) throw new Error('Grok input not found');
  var submitState = {
    url: window.location.href,
    articleCount: document.querySelectorAll('article').length,
    hadVideo: !!document.getElementById('sd-video')
  };

  simulateClick(inputEl);
  inputEl.focus();
  await sleep(250);

  clearComposer(inputEl);
  await sleep(150);
  setComposerText(inputEl, text);
  await sleep(350);

  if (!composerHasPrompt(inputEl, text)) {
    inputEl = findGrokInputElement() || inputEl;
    setComposerText(inputEl, text);
    await sleep(350);
  }
  if (!composerHasPrompt(inputEl, text)) {
    throw new Error('Prompt did not land in Grok composer');
  }

  dispatchEnterSubmit(inputEl);
  var accepted = await waitForSubmissionAccepted(inputEl, text, submitState, 2500);
  if (accepted) {
    console.log('Prompt submitted via Enter');
    return;
  }

  var submitBtn = findGrokSubmitButton(inputEl);
  if (submitBtn) {
    simulateClick(submitBtn);
    accepted = await waitForSubmissionAccepted(inputEl, text, submitState, 4000);
    if (accepted) {
      console.log('Prompt submitted via send button');
      return;
    }
  }

  if (inputEl.form && typeof inputEl.form.requestSubmit === 'function') {
    try {
      inputEl.form.requestSubmit();
      accepted = await waitForSubmissionAccepted(inputEl, text, submitState, 3000);
      if (accepted) {
        console.log('Prompt submitted via form.requestSubmit()');
        return;
      }
    } catch (e) {}
  }

  throw new Error('Prompt did not submit to Grok');
}

// ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ API ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬
function isJobComplete() {
  if (!S.projectId) return false;
  const scenes = Object.values(S.scenes);
  return scenes.length > 0 && scenes.every(sc => sc.status === 'downloaded' || sc.status === 'error');
}

async function fetchPending() {
  // Don't re-fetch when all scenes are already downloaded/errored
  if (isJobComplete()) return;
  try {
    const r = await _fetch(S.studioUrl + '/api/assets/grabber/pending');
    S.connected = r.quiet ? true : !!r.ok;
    if (!r.ok) { render(); return; }
    const d = await r.json();
    if (!d || !d.projectId || !d.scenes) { render(); return; }
    S.projectId = d.projectId;
    S.arguments = d.arguments || '';
    S.aspectRatio = d.aspect_ratio || '9:16';
    S.grokMode = d.grok_mode || 'video';
    S.grokQuality = d.grok_quality || '480p';
    S.grokDuration = d.grok_duration || '6s';
    if ('auto_type' in d) S.autoType = !!d.auto_type;
    console.log('Project:', d.projectId, '-', d.scenes.length, 'scenes');

    d.scenes.forEach(sc => {
      const k = String(sc.scene);
      // Image: prefer base64 data already in payload
      const imgData = sc.image || null;
      // Sync tab scenes
      if (!S.scenes[k]) {
        S.scenes[k] = { prompt: sc.prompt, status: 'pending', urls: [], fileCount: 0, imageUrl: imgData };
      } else if (imgData && !S.scenes[k].imageUrl) {
        S.scenes[k].imageUrl = imgData;
      }
      // Typing queue — add or update existing with image
      const existing = S.typing.queue.find(q => q.scene === k);
      if (!existing) {
        const args = S.arguments ? ' ' + S.arguments : '';
        S.typing.queue.push({
          scene: k,
          displayPrompt: sc.prompt,
          fullPrompt: sc.prompt + ' [' + d.projectId + '|' + sc.scene + ']' + args,
          selected: true,
          status: 'queued',
          imageUrl: imgData,
        });
      } else if (imgData && !existing.imageUrl) {
        existing.imageUrl = imgData;
      }
    });

  } catch (e) { S.connected = false; }
}

async function fetchStatus() {
  if (!S.projectId) return;
  try {
    const r = await _fetch(S.studioUrl + '/api/assets/grabber/status/' + encodeURIComponent(S.projectId));
    S.connected = true;
    if (!r.ok) return;
    const d = await r.json();
    for (const [num, info] of Object.entries(d.scene_statuses || {})) {
      const sc = S.scenes[num];
      if (!sc) continue;
      const serverFiles = (info.local_files || []).length;
      // Always sync status from backend
      if (info.status === 'ready' && serverFiles > 0) {
        if (sc.status !== 'downloaded' || sc.fileCount !== serverFiles) {
          sc.status = 'downloaded'; sc.fileCount = serverFiles;
          console.log('Scene', num, 'synced:', serverFiles, 'files on server');
        }
      } else if (info.status === 'error') {
        sc.status = 'error';
      } else if (info.status === 'downloading' && sc.status !== 'uploading') {
        sc.status = 'processing';
      }
    }
  } catch (e) { S.connected = false; }
}

async function sendResults(num, urls) {
  const sc = S.scenes[num];
  if (sc) sc.status = 'uploading';
  render();

  if (isVideoModeJob()) {
    const filteredUrls = (urls || []).filter(isVideoAssetUrl);
    if (filteredUrls.length !== (urls || []).length) {
      console.warn('Scene', num, '- ignoring', (urls || []).length - filteredUrls.length, 'non-video URL(s) in video mode');
    }
    urls = filteredUrls;
  }

  // Fast path: send URLs via WebSocket — backend downloads server-side
  if (S.wsConnected && urls && urls.length) {
    sendWS({ type: 'ASSET_RESULT', projectId: S.projectId, scene: parseInt(num), urls: urls });
    console.log('Scene', num, '- sent', urls.length, 'URL(s) to backend via WebSocket for server-side download');
    if (sc) sc.status = 'sent';
    S.sentScenes[num] = true;
    render();
    return;
  }

  if (!urls || !urls.length) {
    console.error('Scene', num, '- no valid assets to upload for current mode:', S.grokMode);
    if (sc) sc.status = 'error';
    render();
    return;
  }

  console.log('Fetching', urls.length, isVideoModeJob() ? 'video assets' : 'images', 'for scene', num, 'as blobs...');

  async function fetchBlob(url) {
    const strategies = [
      { credentials: 'include' },
      { mode: 'cors', credentials: 'omit' },
      {},
    ];
    for (var si = 0; si < strategies.length; si++) {
      try {
        const r = await fetch(url, strategies[si]);
        if (r.ok) return await r.blob();
        console.warn('Blob fetch strategy ' + (si + 1) + ' for', url.split('/').pop(), '(' + r.status + ')');
      } catch (e) { /* CORS may block, try next strategy */ }
    }
    return null;
  }

  const images = [];
  const failedUrls = [];
  for (const url of urls) {
    try {
      var blob = null;
      for (var fetchRetry = 0; fetchRetry < 3 && !blob; fetchRetry++) {
        blob = await fetchBlob(url);
        if (!blob && fetchRetry < 2) { console.log('Blob fetch retry', fetchRetry + 1, 'for', url.split('/').pop()); await sleep(2000); }
      }
      if (!blob) { console.warn('Browser fetch failed for', url, 'ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â will delegate to server'); failedUrls.push(url); continue; }
      const b64 = await new Promise((res, rej) => {
        const reader = new FileReader();
        reader.onload = () => res(reader.result);
        reader.onerror = rej;
        reader.readAsDataURL(blob);
      });
      // Detect extension from content-type or URL
      const ct = blob.type || '';
      let ext = '.png';
      if (ct.includes('webp') || url.includes('.webp')) ext = '.webp';
      else if (ct.includes('webm') || url.includes('.webm')) ext = '.webm';
      else if (ct.includes('quicktime') || url.includes('.mov')) ext = '.mov';
      else if (ct.includes('mp4') || url.includes('.mp4')) ext = '.mp4';
      else if (ct.includes('jpeg') || ct.includes('jpg')) ext = '.jpg';

      if (isVideoModeJob() && ['.mp4', '.webm', '.mov'].indexOf(ext) === -1) {
        console.warn('Scene', num, '- rejecting non-video blob in video mode:', url);
        continue;
      }

      // Extract UUID from URL for dedup-safe filename: generated/{uuid}/generated_video.mp4
      var urlUuidMatch = url.match(/generated\/([a-f0-9-]+)\//);
      var urlUuid = urlUuidMatch ? urlUuidMatch[1] : '';
      images.push({ data: b64, source_url: url, ext, filename: urlUuid });
      console.log('Fetched', url.split('/').slice(-2).join('/'), '(' + (blob.size / 1024).toFixed(0) + ' KB,', ext + ')', urlUuid ? 'UUID:' + urlUuid.substring(0, 8) : '');

      // Skip preview image ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â backend generates thumbnails via FFmpeg
    } catch (e) { console.warn('Blob fetch failed for', url, e.message); failedUrls.push(url); }
  }

  // Server-side download for URLs that browser couldn't fetch (403/CORS)
  if (failedUrls.length) {
    console.log('Delegating', failedUrls.length, 'URLs to server-side download...');
    try {
      const dr = await _fetch(S.studioUrl + '/api/assets/grabber/download-urls', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ projectId: S.projectId, scenes: [{ scene: parseInt(num), urls: failedUrls }] })
      });
      if (dr.ok) {
        console.log('Server-side download started for', failedUrls.length, 'URLs');
      } else {
        console.error('Server-side download request failed:', dr.status);
      }
    } catch (de) { console.error('Server-side download request error:', de.message); }
  }

  if (!images.length && !failedUrls.length) {
    console.error('No images fetched for scene', num);
    if (sc) sc.status = 'error';
    render();
    return;
  }

  // All handled by server-side download, no base64 to upload
  if (!images.length) {
    if (sc) sc.status = failedUrls.length ? 'sent' : 'error';
    S.sentScenes[num] = true;
    render();
    return;
  }

  try {
    const r = await _fetch(S.studioUrl + '/api/assets/grabber/upload', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ projectId: S.projectId, scenes: [{ scene: parseInt(num), images }] })
    });
    if (r.ok) {
      if (sc) sc.status = 'sent';
      S.sentScenes[num] = true;
      console.log('Scene', num, 'uploaded:', images.length, 'images');
      // Notify backend via WebSocket too
      sendWS({ type: 'ASSET_UPLOADED', projectId: S.projectId, scene: parseInt(num), count: images.length });
    } else {
      console.error('Upload failed for scene', num, r.status);
      if (sc) sc.status = 'error';
    }
  } catch (e) {
    console.error('Upload error:', num, e);
    if (sc) sc.status = 'error';
  }
  render();
}



// ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ Scroll to load all blocks ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬
// MJ uses virtualized rendering ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â only blocks near the viewport are in the DOM.
// Scroll through #pageScroll to force all blocks to render, then scan.

// ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ CSS highlight styles (injected once at startup) ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬
function injectPickStyles() {
  if (document.getElementById('__sts_pick_styles')) return;
  const s = document.createElement('style');
  s.id = '__sts_pick_styles';
  s.textContent = '.sts-picked{border:3px dotted #00ff3b!important;border-radius:12px;box-shadow:0 0 0 2px rgba(16,185,129,.15);transition:all .2s ease;background:rgba(16,185,129,.05)!important}.sts-batch{border:2px solid #06f!important;box-shadow:0 0 8px rgba(0,102,255,.3)}';
  document.head.appendChild(s);
}

// ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ Highlight a single block's media grid ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬
function highlightBlock(block) {
  if (!block.classList.contains('sts-picked')) {
    block.classList.add('sts-picked', 'sts-batch');
    setTimeout(() => block.classList.remove('sts-batch'), 2000);
  }
}

// ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ Quick highlight pass for all currently visible project blocks ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬
// Used during scroll steps to mark blocks before MJ virtualizes them away

// ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ Poll ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬

// Navigate back to /imagine/saved
// No longer needed: goBackToSaved, waitForSavedPage, readPostPage, scrollAndCollectCards
// Sync now uses the thumbnail sidebar on the current post page

async function redownload() {
  if (!S.projectId) { console.log('No project to redownload'); return; }
  try {
    const r = await _fetch(S.studioUrl + '/api/assets/redownload/' + encodeURIComponent(S.projectId), { method: 'POST' });
    S.connected = true;
    if (r.ok) {
      const d = await r.json();
      console.log('Redownload started:', d);
      // Reset errored/pending scenes so polling picks up new status
      for (const sc of Object.values(S.scenes)) {
        if (sc.status === 'error' || sc.status === 'pending') {
          sc.status = 'processing';
        }
      }
      S.jobComplete = false;
      render();
    } else {
      console.warn('Redownload failed:', r.status);
    }
  } catch (e) { console.error('Redownload error:', e); S.connected = false; }
}

async function poll() {
  S.lastPoll = Date.now();
  await fetchPending();
  await fetchStatus();

  // Check if job just completed
  if (isJobComplete() && !S.jobComplete) {
    S.jobComplete = true;
    console.log('All scenes downloaded/errored ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â stopping active polling');
  }

  render();

  // Auto-start typing when enabled and there are queued prompts
  if (S.autoType && !S.typing.active && !S.typing.starting && !S.typing.autoPaused && Date.now() >= (S.typing.nextAutoStartAt || 0)) {
    const hasQueued = S.typing.queue.some(q => isTypingSelected(q) && q.status === 'queued');
    if (hasQueued) {
      console.log('Auto-type: starting typing automatically');
      startTyping();
    }
  }

  // Adaptive poll interval
  if (S.jobComplete) {
    S.pollInterval = 60000; // Slow poll when done (1min)
  } else if (S.connected) {
    S.pollInterval = 5000;
  } else {
    if (S.pollInterval <= 5000) S.pollInterval = 10000;
    else if (S.pollInterval <= 10000) S.pollInterval = 30000;
    else S.pollInterval = 30000;
  }
}

// ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ Start ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬
console.log('Synchronizer v2 (Grok) injected');
injectPickStyles();
renderTabs();
renderAutoType();
connectWS(); // Start WebSocket connection
// Start polling (no auto-scroll ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â wait for user to press Sync Now)
(async () => {
  await poll();
  async function adaptivePoll() {
    await poll();
    setTimeout(adaptivePoll, S.pollInterval);
  }
  setTimeout(adaptivePoll, S.pollInterval);
  setInterval(updateTimer, 1000);
})();

automaNextBlock();
