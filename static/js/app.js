/* ================================================================
   ScriptToScene Studio — App Core (navigation, toast, confirm, api)
   ================================================================ */

const $ = s => document.querySelector(s);
const $$ = s => document.querySelectorAll(s);
const esc = s => s ? s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;') : '';

// ---- Welcome Overlay (first visit) ----
const _welcomeQuotes = [
  '"The secret of getting ahead is getting started." — Mark Twain',
  '"Creativity is intelligence having fun." — Albert Einstein',
  '"Vision without execution is just hallucination." — Thomas Edison',
  '"The best way to predict the future is to create it." — Peter Drucker',
  '"Do what you can, with what you have, where you are." — Theodore Roosevelt',
  '"Simplicity is the ultimate sophistication." — Leonardo da Vinci',
  '"Make it work, make it right, make it fast." — Kent Beck',
  '"Start where you are. Use what you have. Do what you can." — Arthur Ashe',
  '"Every master was once a disaster." — T. Harv Eker',
  '"Ideas are easy. Execution is everything." — John Doerr',
];

function _initWelcome() {
  if (localStorage.getItem('sts-welcome-seen')) return;
  showWelcome();
}

function dismissWelcome() {
  const overlay = $('#welcome-overlay');
  if (!overlay) return;
  localStorage.setItem('sts-welcome-seen', '1');
  overlay.classList.add('dismissing');
  overlay.addEventListener('animationend', () => overlay.remove(), { once: true });
}

function showWelcome() {
  let overlay = $('#welcome-overlay');
  if (overlay) overlay.remove();
  const tpl = document.getElementById('welcome-template');
  if (!tpl) return;
  const clone = tpl.content.cloneNode(true);
  document.body.prepend(clone);
  overlay = $('#welcome-overlay');
  const q = overlay.querySelector('#welcome-quote');
  if (q) q.textContent = _welcomeQuotes[Math.floor(Math.random() * _welcomeQuotes.length)];
  overlay.style.display = 'flex';
}

document.addEventListener('DOMContentLoaded', _initWelcome);

// ---- Settings Manager (server JSON with .bak, localStorage only for sts-sidebar) ----
window.STS = {
  _cache: {},           // in-memory cache of all settings
  _defaults: {},        // from app-config.json
  _localKeys: new Set(),// keys that also mirror to localStorage
  _saveTimer: null,
  _dirty: false,

  /** Get a setting value. Sync — reads from memory cache. */
  get(key) {
    const v = this._cache[key];
    if (v !== undefined) return v;
    // Check localStorage for local-only keys
    const ls = localStorage.getItem(key);
    if (ls !== null) return ls === 'true' ? true : ls === 'false' ? false : (isNaN(ls) ? ls : +ls);
    return this._defaults[key] ?? null;
  },

  /** Set a setting value. Writes to memory + queues server save. */
  set(key, value) {
    this._cache[key] = value;
    if (this._localKeys.has(key)) localStorage.setItem(key, value);
    this._queueSave();
  },

  /** Queue a debounced save to server (300ms). */
  _queueSave() {
    this._dirty = true;
    clearTimeout(this._saveTimer);
    this._saveTimer = setTimeout(() => this._persist(), 300);
  },

  /** Persist all settings to server via PATCH. */
  async _persist() {
    if (!this._dirty) return;
    this._dirty = false;
    try {
      await fetch('/api/settings', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(this._cache),
      });
    } catch (_) { /* silent — next save will retry */ }
  },

  /** Reset all settings to defaults. */
  async reset() {
    this._cache = {};
    try { await fetch('/api/settings', { method: 'DELETE' }); } catch (_) {}
  },

  /** Load from server + app-config.json defaults. Returns a promise. */
  async init() {
    try {
      const [cfgRes, srvRes] = await Promise.all([
        fetch('/app-config.json').then(r => r.json()).catch(() => ({})),
        fetch('/api/settings').then(r => r.json()).catch(() => ({})),
      ]);
      this._defaults = cfgRes.defaults || {};
      (cfgRes.localStorage || []).forEach(k => this._localKeys.add(k));
      // Merge: defaults < server settings
      this._cache = { ...this._defaults, ...srvRes };
      // Mirror local keys to localStorage
      for (const k of this._localKeys) {
        const v = this._cache[k];
        if (v !== undefined) localStorage.setItem(k, v);
      }
    } catch (_) {
      this._defaults = {};
      this._cache = {};
    }
  }
};
window._stsReady = window.STS.init();

// ---- Shared State ----
window.STATE = {
  alignFile: null,
  alignResult: null,
  alignHistory: [],
  segmenterResult: null,
  segmenterAlignment: null,
  scenesSegData: null,
  scenesResult: null,
  assetsSceneData: null,
  assetStatuses: {},
  editorLoaded: false,
  captionData: null,
  captionAlignment: null,
};

// ---- Global Audio Registry ----
// Tracks all audio instances across modules so they can be stopped from one place.
window._stsAudioRegistry = {};

window.stsStopExportVideos = function (exceptVideo = null) {
  const list = document.getElementById('export-library-list');
  if (!list) return [];
  const stopped = [];
  list.querySelectorAll('video').forEach(video => {
    if (!video || video === exceptVideo) return;
    if (!video.paused) {
      video.pause();
      video.currentTime = 0;
      stopped.push('Export Library');
    } else if (video.currentTime > 0) {
      video.currentTime = 0;
    }
  });
  return stopped;
};

/**
 * Register an Audio element (or HTMLMediaElement) with a label.
 * @param {string} label  — e.g. "Captions", "Alignment", "TTS"
 * @param {HTMLMediaElement} audioEl
 */
window.stsAudioRegister = function (label, audioEl) {
  if (!audioEl) return;
  window._stsAudioRegistry[label] = audioEl;
  if (audioEl.__stsExclusiveBound) return;
  audioEl.__stsExclusiveBound = true;
  audioEl.addEventListener('play', () => {
    for (const [otherLabel, otherEl] of Object.entries(window._stsAudioRegistry)) {
      if (!otherEl || otherEl === audioEl) continue;
      if (!otherEl.paused) {
        otherEl.pause();
        otherEl.currentTime = 0;
      }
    }
    if (typeof window.stsStopExportVideos === 'function') {
      window.stsStopExportVideos();
    }
  });
};

/** Unregister an audio element by label */
window.stsAudioUnregister = function (label) {
  delete window._stsAudioRegistry[label];
};

/** Stop all registered audio and return which ones were playing */
window.stsAudioStopAll = function (exceptExportVideo = null) {
  const stopped = [];
  for (const [label, el] of Object.entries(window._stsAudioRegistry)) {
    if (el && !el.paused) {
      el.pause();
      el.currentTime = 0;
      stopped.push(label);
    }
  }
  if (typeof window.stsStopExportVideos === 'function') {
    const exportStopped = window.stsStopExportVideos(exceptExportVideo);
    if (exportStopped.length) stopped.push(...exportStopped);
  }
  return stopped;
};

/** Get the label of the currently-playing audio (first found), or null */
window.stsAudioGetPlaying = function () {
  for (const [label, el] of Object.entries(window._stsAudioRegistry)) {
    if (el && !el.paused) return label;
  }
  return null;
};

// Poll for audio state changes and update the sidebar indicator
let _stsAudioPollId = null;
function _stsAudioStartPoll() {
  if (_stsAudioPollId) return;
  _stsAudioPollId = setInterval(() => {
    const btn = document.getElementById('sidebar-audio-btn');
    if (!btn) return;
    const playing = window.stsAudioGetPlaying();
    const labelEl = btn.querySelector('.audio-source-label');
    if (playing) {
      btn.classList.add('audio-playing');
      btn.title = `Playing: ${playing} — click to stop`;
      if (labelEl) labelEl.textContent = playing;
    } else {
      btn.classList.remove('audio-playing');
      btn.title = 'No audio playing';
      if (labelEl) labelEl.textContent = '';
    }
  }, 250);
}
document.addEventListener('DOMContentLoaded', _stsAudioStartPoll);

function stsAudioToggle() {
  const playing = window.stsAudioGetPlaying();
  if (playing) {
    window.stsAudioStopAll();
    toast(`Stopped: ${playing}`, 'info');
  } else {
    toast('No audio playing', 'info');
  }
}

// ---- Navigation ----
function switchPage(page, editorSource = 'internal') {
  $$('.page').forEach(p => p.classList.remove('active'));
  document.getElementById('page-' + page).classList.add('active');
  $$('.nav-item[data-page]').forEach(n => {
    n.classList.toggle('active', n.dataset.page === page);
  });
  $$('#mobile-nav button[data-page]').forEach(b => {
    const isActive = b.dataset.page === page;
    b.style.color = isActive ? 'var(--accent)' : 'var(--text-muted)';
    b.classList.toggle('active', isActive);
  });
  if (page === 'editor') {
    try {
      sessionStorage.setItem('sts-editor-entry-source', editorSource || 'internal');
    } catch (_) {}
    $('#main-content').style.overflowY = 'hidden';
    if (!localStorage.getItem('sts-editor-scenes')) {
      // Hide the loading spinner and show empty state
      const loadingEl = $('#editor-loading');
      if (loadingEl) {
        loadingEl.innerHTML = `
          <div style="text-align:center">
            <svg width="40" height="40" fill="none" stroke="var(--text-muted)" stroke-width="1.5" viewBox="0 0 24 24" style="margin:0 auto 12px;opacity:0.4">
              <rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M9 21V9"/>
            </svg>
            <p style="color:var(--text-secondary);font-size:13px">No scenes or assets available</p>
            <p style="font-size:11px;margin-top:6px;color:var(--text-muted);opacity:0.7">Generate content first, then open the editor</p>
          </div>`;
      }
      return;
    }
    initEditorIframe();
  } else {
    $('#main-content').style.overflowY = 'auto';
  }
  if (page === 'assets' && typeof loadAssetsHistory === 'function') {
    loadAssetsHistory();
  }
  if (page === 'export-library' && typeof loadExportLibrary === 'function') {
    loadExportLibrary();
  }
}

// Explicit editor entry from sidebar/mobile menu.
function openEditorFromMenu() {
  switchPage('editor', 'menu');
}

function toggleSidebar() {
  $('#sidebar').classList.toggle('collapsed');
  STS.set('sts-sidebar', $('#sidebar').classList.contains('collapsed'));
}

// Restore sidebar state (read localStorage directly — runs before STS.init resolves)
if (localStorage.getItem('sts-sidebar') === 'true') {
  $('#sidebar').classList.add('collapsed');
}

// ---- Toast ----
function toast(msg, type = 'success') {
  const el = document.createElement('div');
  const bg = { success: 'rgba(78,205,196,0.92)', error: 'rgba(255,107,107,0.92)', info: 'rgba(30,42,58,0.92)' };
  el.className = 'toast-item';
  el.style.background = bg[type] || bg.info;
  el.textContent = msg;
  $('#toast-wrap').appendChild(el);
  setTimeout(() => {
    el.style.opacity = '0'; el.style.transition = 'opacity 0.3s, transform 0.3s';
    el.style.transform = 'translateX(20px)';
    setTimeout(() => el.remove(), 300);
  }, 3500);
}

// ---- Confirm Dialog ----
function confirmDialog({ title, desc, message, confirmLabel } = {}) {
  return new Promise(resolve => {
    const modal = $('#confirm-modal');
    $('#confirm-title').textContent = title || 'Move to Trash?';
    $('#confirm-desc').textContent = desc || 'This action can be undone from the TRASH folder.';
    $('#confirm-message').textContent = message || '';
    $('#confirm-detail').style.display = message ? '' : 'none';
    $('#confirm-ok').textContent = confirmLabel || 'Move to Trash';
    modal.classList.remove('hidden');
    modal.style.display = 'flex';
    function cleanup(result) {
      modal.classList.add('hidden'); modal.style.display = '';
      $('#confirm-ok').removeEventListener('click', onOk);
      $('#confirm-cancel').removeEventListener('click', onCancel);
      document.removeEventListener('keydown', onKey);
      resolve(result);
    }
    function onOk() { cleanup(true); }
    function onCancel() { cleanup(false); }
    function onKey(e) { if (e.key === 'Escape') cleanup(false); else if (e.key === 'Enter') cleanup(true); }
    $('#confirm-ok').addEventListener('click', onOk);
    $('#confirm-cancel').addEventListener('click', onCancel);
    document.addEventListener('keydown', onKey);
  });
}

// ---- API Helper ----
async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.error || `HTTP ${res.status}`); }
  return res.json();
}

function _downloadFilenameFromDisposition(disposition) {
  if (!disposition) return '';
  const utf8Match = disposition.match(/filename\*\s*=\s*UTF-8''([^;]+)/i);
  if (utf8Match && utf8Match[1]) {
    try { return decodeURIComponent(utf8Match[1]); } catch (_) { return utf8Match[1]; }
  }
  const plainMatch = disposition.match(/filename\s*=\s*"?([^"]+)"?/i);
  return plainMatch && plainMatch[1] ? plainMatch[1] : '';
}

async function downloadFileFromApi(url, fallbackFilename = 'download.bin') {
  const res = await fetch(url);
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    throw new Error(d.error || `Download failed (${res.status})`);
  }
  const blob = await res.blob();
  const contentDisposition = res.headers.get('Content-Disposition') || '';
  const filename = _downloadFilenameFromDisposition(contentDisposition) || fallbackFilename;
  const objectUrl = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = objectUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
  return { filename, sizeBytes: blob.size };
}

async function downloadProjectZip(projectId) {
  if (!projectId) throw new Error('Missing project id');
  return downloadFileFromApi(`/api/editor/export-zip/${encodeURIComponent(projectId)}`, `${projectId}.zip`);
}

// ---- Settings (backed by STS server settings manager) ----
window.STS_SETTINGS = { normalize: true, clean: true };

/** Play the completion chime if sound is enabled */
window.playDoneSound = function () {
  if (!STS.get('sts-sound-enabled')) return;
  try { new Audio('/assets/sounds/effects/done.mp3').play(); } catch (_) {}
};

function settingsToggle(key, val) {
  STS_SETTINGS[key] = val;
  STS.set('sts-' + key, val);
}

// Restore toggles on load (after STS.init resolves)
document.addEventListener('DOMContentLoaded', () => {
  window._stsReady.then(() => {
    STS_SETTINGS.normalize = STS.get('sts-normalize');
    STS_SETTINGS.clean = STS.get('sts-clean');

    const normEl = $('#setting-normalize');
    const cleanEl = $('#setting-clean');
    if (normEl) normEl.checked = STS_SETTINGS.normalize;
    if (cleanEl) cleanEl.checked = STS_SETTINGS.clean;

    const storageEl = $('#setting-editor-localstorage');
    const sessionStorageEl = $('#setting-editor-sessionstorage');
    if (storageEl) storageEl.checked = STS.get('sts-editor-storage');
    if (sessionStorageEl) sessionStorageEl.checked = STS.get('sts-editor-session-storage');

    const soundEl = $('#setting-sound-notifications');
    if (soundEl) soundEl.checked = STS.get('sts-sound-enabled');
  });
});

// ---- Settings: Clear All Projects ----
let _clearChallenge = '';
function _renderClearPreview(modules, totalItems) {
  const box = $('#settings-clear-preview');
  if (!box) return;
  const rows = (modules || []).map(m => {
    const count = Number(m.items || 0);
    const entries = Array.isArray(m.entries) ? m.entries : [];
    const list = entries.length
      ? `<div style="margin-top:4px;display:flex;flex-direction:column;gap:2px">${entries.map(name => `<span class="font-mono" style="font-size:10px;color:var(--text-muted)">${esc(name)}</span>`).join('')}</div>`
      : '<div style="margin-top:4px"><span class="font-mono" style="font-size:10px;color:var(--text-muted)">empty</span></div>';
    return `<div style="padding:6px 0;border-bottom:1px solid rgba(255,255,255,0.04)">
      <div style="display:flex;justify-content:space-between;gap:10px">
        <span style="font-size:11px;color:var(--text-secondary)">${esc(m.page)} � ${esc(m.module)}</span>
        <span class="font-mono" style="font-size:11px;color:${count > 0 ? '#ef4444' : 'var(--text-muted)'}">${count}</span>
      </div>
      ${list}
    </div>`;
  }).join('');
  box.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
      <span style="font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--text-muted);font-weight:700">Items that will be moved to TRASH</span>
      <span class="font-mono" style="font-size:11px;color:#ef4444;font-weight:700">${totalItems || 0} total</span>
    </div>
    ${rows || '<p style="font-size:11px;color:var(--text-muted);text-align:center;margin:0">Nothing to clear</p>'}
  `;
}

async function settingsClearAllProjects() {
  const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
  _clearChallenge = '';
  for (let i = 0; i < 6; i++) _clearChallenge += chars[Math.random() * chars.length | 0];
  $('#settings-clear-challenge').textContent = _clearChallenge;
  $('#settings-clear-input').value = '';
  $('#settings-clear-error').style.display = 'none';
  const preview = $('#settings-clear-preview');
  if (preview) preview.innerHTML = '<p class="font-mono" style="font-size:11px;color:var(--text-muted);margin:0;text-align:center">Loading modules to clear...</p>';
  const btn = $('#settings-clear-confirm-btn');
  btn.disabled = true;
  btn.style.opacity = '0.4';
  const dlg = $('#settings-clear-dialog');
  dlg.style.display = 'flex';
  try {
    const data = await api('/api/settings/clear-all-projects/preview');
    _renderClearPreview(data.modules || [], data.total_items || 0);
  } catch (e) {
    if (preview) preview.innerHTML = `<p style="font-size:11px;color:var(--coral);margin:0;text-align:center">Failed to load preview: ${esc(e.message || 'unknown error')}</p>`;
  }
  setTimeout(() => $('#settings-clear-input').focus(), 100);
}

function settingsClearDialogClose() {
  $('#settings-clear-dialog').style.display = 'none';
  _clearChallenge = '';
}

function settingsClearInputCheck() {
  const val = $('#settings-clear-input').value.toUpperCase().trim();
  const match = val === _clearChallenge;
  const btn = $('#settings-clear-confirm-btn');
  btn.disabled = !match;
  btn.style.opacity = match ? '1' : '0.4';
}

async function settingsClearConfirm() {
  const val = $('#settings-clear-input').value.toUpperCase().trim();
  if (val !== _clearChallenge) {
    $('#settings-clear-error').textContent = 'Characters do not match. Try again.';
    $('#settings-clear-error').style.display = 'block';
    return;
  }
  const btn = $('#settings-clear-confirm-btn');
  btn.disabled = true;
  btn.textContent = 'Clearing...';
  try {
    const resp = await fetch('/api/settings/clear-all-projects', { method: 'DELETE' });
    const data = await resp.json();
    settingsClearDialogClose();
    if (data.status === 'cleared') {
      // Reset all in-memory state
      STATE.alignFile = null;
      STATE.alignResult = null;
      STATE.alignHistory = [];
      STATE.segmenterResult = null;
      STATE.segmenterAlignment = null;
      STATE.scenesSegData = null;
      STATE.scenesResult = null;
      STATE.assetsSceneData = null;
      STATE.assetStatuses = {};
      STATE.captionData = null;
      STATE.captionAlignment = null;
      // Nuke all browser storage and reset server settings
      localStorage.clear();
      sessionStorage.clear();
      STS.reset();
      // Clear module badges
      ['tts', 'timing', 'segmenter', 'scenes', 'assets', 'pipeline'].forEach(m => setModuleBadge(m, ''));
      // Refresh ALL history lists across every module
      if (typeof loadScenesHistory === 'function') loadScenesHistory();
      if (typeof pipelineLoadHistory === 'function') pipelineLoadHistory();
      if (typeof loadAlignHistory === 'function') loadAlignHistory();
      if (typeof loadSegHistory === 'function') loadSegHistory();
      if (typeof loadCaptionsHistory === 'function') loadCaptionsHistory();
      if (typeof loadAssetsHistory === 'function') loadAssetsHistory();
      if (typeof loadExportLibrary === 'function') loadExportLibrary(true);
      // Clear visible results
      const scenesResults = document.getElementById('scenes-results');
      if (scenesResults) scenesResults.style.display = 'none';
      const assetsControls = document.getElementById('assets-controls');
      if (assetsControls) assetsControls.style.display = 'none';
      const assetsEmpty = document.getElementById('assets-empty');
      if (assetsEmpty) assetsEmpty.style.display = '';
      const exportsMsg = data.exports_deleted ? ` (${data.exports_deleted} export item${data.exports_deleted !== 1 ? 's' : ''} deleted)` : '';
      toast(`Cleared ${data.count} project item${data.count !== 1 ? 's' : ''}${exportsMsg}`, 'success');
      setTimeout(() => location.reload(), 600);
    } else {
      toast(data.error || 'Failed to clear projects', 'error');
    }
  } catch (e) {
    toast('Failed to clear projects: ' + e.message, 'error');
  } finally {
    btn.textContent = 'Delete All';
    btn.disabled = false;
  }
}

// Close dialog on Escape key
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && $('#settings-clear-dialog').style.display === 'flex') {
    settingsClearDialogClose();
  }
});

// ---- Auto-Forward (Continue to Next Step) ----
function showContinueBar(containerId, nextPage, label, setupFn) {
  const container = document.getElementById(containerId);
  if (!container) return;
  const existing = container.querySelector('.continue-bar');
  if (existing) existing.remove();
  const bar = document.createElement('div');
  bar.className = 'continue-bar';
  bar.style.cssText = 'display:flex;align-items:center;gap:12px;padding:12px 16px;margin-top:16px;background:rgba(78,205,196,0.06);border:1px solid rgba(78,205,196,0.2);border-radius:10px;animation:reveal 0.4s cubic-bezier(0.16,1,0.3,1)';
  bar.innerHTML = `<svg width="16" height="16" fill="none" stroke="var(--accent)" stroke-width="2" viewBox="0 0 24 24"><path d="M5 12h14"/><path d="M12 5l7 7-7 7"/></svg><span style="font-size:13px;color:var(--text-secondary)">Ready for next step</span>`;
  const btn = document.createElement('button');
  btn.style.cssText = 'margin-left:auto;padding:8px 20px;background:var(--accent);color:var(--bg-darkest);border:none;border-radius:8px;font-size:12px;font-weight:600;cursor:pointer;transition:opacity 0.15s';
  btn.textContent = label;
  btn.onmouseenter = () => btn.style.opacity = '0.85';
  btn.onmouseleave = () => btn.style.opacity = '1';
  btn.onclick = () => { if (setupFn) setupFn(); switchPage(nextPage); };
  bar.appendChild(btn);
  container.appendChild(bar);
}

// ---- Module Project Badge ----
function setModuleBadge(moduleId, text) {
  const el = document.getElementById('badge-' + moduleId);
  if (!el) return;
  if (text) {
    el.textContent = text;
    el.classList.add('visible');
  } else {
    el.textContent = '';
    el.classList.remove('visible');
  }
}

// ---- Time Ago ----
function timeAgo(ts) {
  if (!ts) return '';
  const diff = (Date.now() - new Date(ts).getTime()) / 1000;
  if (diff < 60) return 'just now';
  if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
  if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
  return Math.floor(diff / 86400) + 'd ago';
}




