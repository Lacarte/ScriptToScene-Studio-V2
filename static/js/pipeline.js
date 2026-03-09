/* ================================================================
   ScriptToScene Studio — Pipeline Dashboard
   Runs the full TTS → Timing → Segment → Scenes pipeline with SSE progress.
   ================================================================ */

let _plJobId = null;
let _plEventSource = null;
let _plSteps = [
  { id: 'tts', label: 'TTS', icon: '🎤' },
  { id: 'timing', label: 'Timing', icon: '⏱' },
  { id: 'segment', label: 'Segment', icon: '✂' },
  { id: 'scenes', label: 'Scenes', icon: '🎬' },
];
let _plStepStatus = {};
let _plLog = [];

// ---- Start Pipeline ----

async function pipelineStart() {
  const text = $('#pipeline-text').value.trim();
  if (!text) { toast('Enter story text', 'error'); return; }

  const btn = $('#pipeline-run-btn');
  btn.disabled = true;
  btn.textContent = 'Starting...';

  const autoScenes = $('#pipeline-auto-scenes')?.checked !== false;
  // Use the webhook URL from scenes settings (localStorage) so pipeline hits the same endpoint
  const webhookUrl = localStorage.getItem('sts-scenes-webhook-url') || $('#scenes-webhook-url')?.value || '';
  const config = {
    text,
    voice: $('#pipeline-voice')?.value || 'af_heart',
    speed: parseFloat($('#pipeline-speed')?.value || '1.0'),
    style: $('#pipeline-style')?.value || 'cinematic',
    auto_scenes: autoScenes,
    webhook_url: webhookUrl || undefined,
  };

  try {
    const res = await api('/api/pipeline/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config),
    });
    _plJobId = res.job_id;
    _plStepStatus = {};
    _plLog = [];
    _plRenderProgress('running');
    _plStartSSE(res.job_id);
    toast('Pipeline started');
  } catch (e) {
    toast(e.message || 'Pipeline failed to start', 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Run Pipeline';
  }
}

// ---- SSE Stream ----

function _plStartSSE(jobId) {
  if (_plEventSource) { _plEventSource.close(); _plEventSource = null; }
  _plEventSource = new EventSource(`/api/pipeline/progress/${jobId}`);
  _plEventSource.onmessage = (e) => {
    const event = JSON.parse(e.data);
    _plLog.push(event);
    _plUpdateStep(event);
    if (event.step === 'done' || event.step === 'error') {
      _plEventSource.close();
      _plEventSource = null;
    }
  };
  _plEventSource.onerror = () => {
    _plEventSource.close();
    _plEventSource = null;
  };
}

// ---- Render Progress ----

function _plRenderProgress(globalStatus) {
  const section = $('#pipeline-progress');
  section.style.display = '';

  const stepsHtml = _plSteps.map((step, i) => {
    const status = _plStepStatus[step.id] || 'pending';
    let dotColor = 'var(--border)';
    let textColor = 'var(--text-muted)';
    let icon = step.icon;
    if (status === 'running') { dotColor = 'var(--accent)'; textColor = 'var(--accent)'; }
    if (status === 'done') { dotColor = '#26DE81'; textColor = '#26DE81'; icon = '✓'; }
    if (status === 'skipped') { dotColor = 'var(--text-muted)'; textColor = 'var(--text-muted)'; icon = '—'; }
    if (status === 'error') { dotColor = '#FF6B6B'; textColor = '#FF6B6B'; icon = '✗'; }

    const connector = i < _plSteps.length - 1
      ? `<div style="flex:1;height:2px;background:${_plStepStatus[_plSteps[i + 1]?.id] === 'done' || status === 'done' ? '#26DE81' : 'var(--border)'};margin:0 4px"></div>`
      : '';

    return `
      <div style="display:flex;flex-direction:column;align-items:center;min-width:60px">
        <div style="width:32px;height:32px;border-radius:50%;background:${dotColor}15;border:2px solid ${dotColor};display:flex;align-items:center;justify-content:center;font-size:14px;transition:all 0.3s${status === 'running' ? ';animation:pulse 1.5s infinite' : ''}">${icon}</div>
        <span style="font-size:10px;font-weight:600;color:${textColor};margin-top:4px">${step.label}</span>
      </div>${connector}`;
  }).join('');

  $('#pipeline-steps').innerHTML = `<div style="display:flex;align-items:center;width:100%">${stepsHtml}</div>`;

  // Current step message
  const lastEvent = _plLog[_plLog.length - 1];
  if (lastEvent) {
    const msg = lastEvent.message || '';
    const isErr = lastEvent.step === 'error';
    $('#pipeline-current-step').innerHTML = `
      <div style="display:flex;align-items:center;gap:8px">
        ${globalStatus === 'running' ? '<div style="width:12px;height:12px;border:2px solid rgba(78,205,196,0.3);border-top-color:var(--accent);border-radius:50%;animation:spin 0.6s linear infinite;flex-shrink:0"></div>' : ''}
        <span style="font-size:12px;color:${isErr ? '#FF6B6B' : 'var(--text-secondary)'}">${esc(msg)}</span>
      </div>`;
  }

  // Log
  _plRenderLog();
}

function _plHighlightMenu(step, status) {
  document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('pipeline-running', 'pipeline-done-scenes'));
  document.querySelectorAll('#mobile-nav button').forEach(el => el.classList.remove('pipeline-running', 'pipeline-done-scenes'));

  if (status === 'running') {
    const stepMap = {
      'tts': 'tts',
      'timing': 'timing',
      'segment': 'segmenter',
      'scenes': 'scenes'
    };

    const pageId = stepMap[step];
    if (pageId) {
      const navItem = document.querySelector(`.nav-item[data-page="${pageId}"]`);
      if (navItem) navItem.classList.add('pipeline-running');

      const mobileNavItem = document.querySelector(`#mobile-nav button[data-page="${pageId}"]`);
      if (mobileNavItem) mobileNavItem.classList.add('pipeline-running');
    }
  } else if (step === 'done') {
    const navItem = document.querySelector(`.nav-item[data-page="scenes"]`);
    if (navItem) navItem.classList.add('pipeline-done-scenes');

    const mobileNavItem = document.querySelector(`#mobile-nav button[data-page="scenes"]`);
    if (mobileNavItem) mobileNavItem.classList.add('pipeline-done-scenes');
  }
}

function _plUpdateStep(event) {
  const step = event.step;
  const status = event.status;

  _plHighlightMenu(step, status);

  if (step === 'done') {
    _plRenderProgress('done');
    $('#pipeline-current-step').innerHTML = `<span style="font-size:13px;color:#26DE81;font-weight:600">Pipeline complete</span>`;
    if (typeof playDoneSound === 'function') playDoneSound();
    // Small delay to ensure scenes.json is flushed to disk before reading
    setTimeout(() => pipelineLoadHistory(), 500);

    // Store results for scenes page and editor
    if (event.summary?.segment) {
      STATE.scenesSegData = event.summary.segment;
    }
    if (event.summary?.scenes) {
      STATE.scenesResult = event.summary.scenes;
      setModuleBadge('pipeline', event.summary.scenes.project_id);
      localStorage.setItem('sts-editor-scenes', JSON.stringify(event.summary.scenes));
      // Refresh scenes history so the new project shows with style
      if (typeof loadScenesHistory === 'function') loadScenesHistory();
    }

    // Sync pipeline style to scene generator
    const _plStyle = $('#pipeline-style')?.value;
    if (_plStyle && typeof scenesSelectStyle === 'function') {
      scenesSelectStyle(_plStyle);
    }

    // Show continue bar to Scene Generator
    showContinueBar('pipeline-progress', 'scenes', 'Go to Scene Generator →', () => {
      if (STATE.scenesResult) {
        _updateScenesSource();
        renderSceneResults(STATE.scenesResult);
      }
    });
    return;
  }
  if (step === 'error') {
    _plRenderProgress('error');
    return;
  }

  _plStepStatus[step] = status;
  _plRenderProgress('running');
}

function _plRenderLog() {
  const section = $('#pipeline-log-section');
  section.style.display = _plLog.length ? '' : 'none';

  const logHtml = _plLog.map(e => {
    const isErr = e.step === 'error';
    const isDone = e.status === 'done';
    const icon = isErr ? '✗' : isDone ? '✓' : '→';
    const color = isErr ? '#FF6B6B' : isDone ? '#26DE81' : 'var(--text-muted)';
    return `<div style="padding:3px 0;color:${color}"><span style="opacity:0.6">${icon}</span> <span style="color:var(--accent)">${esc(e.step || '')}</span> ${esc(e.message || '')}</div>`;
  }).join('');

  $('#pipeline-log').innerHTML = logHtml;
  const logEl = $('#pipeline-log');
  logEl.scrollTop = logEl.scrollHeight;
}

// ---- History ----

async function pipelineLoadHistory() {
  try {
    const jobs = await api('/api/pipeline/jobs');
    const list = $('#pipeline-jobs');
    if (!jobs.length) {
      list.innerHTML = '<p style="text-align:center;padding:24px;font-size:12px;color:var(--text-muted)">No pipeline jobs yet</p>';
      return;
    }
    // Store jobs for click handler
    window._pipelineJobs = jobs;
    list.innerHTML = jobs.map((j, i) => {
      const color = j.status === 'done' ? '#26DE81' : j.status === 'error' ? '#FF6B6B' : 'var(--accent)';
      const scenes = j.scene_count ? `${j.scene_count} scenes` : '';
      const date = j.timestamp ? timeAgo(j.timestamp) : '';
      const styleName = typeof _scnStyleLabel === 'function' ? _scnStyleLabel(j.style) : '';
      const styleColor = typeof _scnStyleColor === 'function' ? _scnStyleColor(j.style) : 'var(--text-muted)';
      const styleHtml = styleName ? ` · <span style="display:inline-flex;align-items:center;gap:3px"><span style="width:6px;height:6px;border-radius:50%;background:${styleColor};display:inline-block"></span><span style="color:${styleColor};font-weight:600">${esc(styleName)}</span></span>` : '';
      return `
      <div onclick="pipelineLoadFromHistory(${i})" style="display:flex;align-items:center;gap:10px;padding:10px 16px;border-bottom:1px solid var(--border);cursor:pointer;transition:background 0.15s" onmouseenter="this.style.background='var(--surface-hover)'" onmouseleave="this.style.background=''">
        <span style="width:8px;height:8px;border-radius:50%;background:${color};flex-shrink:0"></span>
        <div style="min-width:0;flex:1">
          <div class="font-mono" style="font-size:12px;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(j.label || j.project_id)}</div>
          <div style="font-size:10px;color:var(--text-muted);margin-top:1px">${esc(j.project_id)}${scenes ? ' · ' + scenes : ''}${styleHtml}</div>
        </div>
        <span class="font-mono" style="font-size:10px;color:var(--text-muted);flex-shrink:0;text-align:right">${date}</span>
      </div>`;
    }).join('');
  } catch (e) { console.error('Pipeline history:', e); }
}

function pipelineLoadFromHistory(index) {
  const j = (window._pipelineJobs || [])[index];
  if (!j) return;
  setModuleBadge('pipeline', j.project_id);
  if (j.text) $('#pipeline-text').value = j.text;
  if (j.voice) $('#pipeline-voice').value = j.voice;
  if (j.speed) $('#pipeline-speed').value = j.speed;
  if (j.style) {
    // Try matching by style id first, fallback to visual_style text
    const sel = $('#pipeline-style');
    const match = [...sel.options].find(o => j.style.toLowerCase().includes(o.value));
    if (match) sel.value = match.value;
  }
  // Scroll to top so user sees the populated form
  $('#pipeline-text').scrollIntoView({ behavior: 'smooth', block: 'center' });
  $('#pipeline-text').focus();
}

// ---- Random Story ----
let _plLastStoryIdx = -1;
function pipelineRandomStory() {
  if (typeof RANDOM_STORIES === 'undefined' || !RANDOM_STORIES.length) return;
  let idx;
  do { idx = Math.floor(Math.random() * RANDOM_STORIES.length); } while (idx === _plLastStoryIdx && RANDOM_STORIES.length > 1);
  _plLastStoryIdx = idx;
  const ta = $('#pipeline-text');
  if (!ta) return;
  ta.value = RANDOM_STORIES[idx];
  ta.dispatchEvent(new Event('input'));
  ta.focus();
  toast('Random story loaded');
}

// ---- Reset progress on config change ----

function _plResetProgress() {
  _plStepStatus = {};
  _plLog = [];
  const section = $('#pipeline-progress');
  if (section) section.style.display = 'none';
  const logSection = $('#pipeline-log-section');
  if (logSection) logSection.style.display = 'none';
  const currentStep = $('#pipeline-current-step');
  if (currentStep) currentStep.innerHTML = '';
  // Clear menu highlights
  document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('pipeline-running', 'pipeline-done-scenes'));
  document.querySelectorAll('#mobile-nav button').forEach(el => el.classList.remove('pipeline-running', 'pipeline-done-scenes'));
}

['pipeline-text', 'pipeline-voice', 'pipeline-speed', 'pipeline-style'].forEach(id => {
  const el = document.getElementById(id);
  if (!el) return;
  const evt = el.tagName === 'TEXTAREA' || (el.tagName === 'INPUT' && el.type !== 'number') ? 'input' : 'change';
  el.addEventListener(evt, _plResetProgress);
});

// Populate pipeline style dropdown from templates API, then load history
(async function _plInit() {
  try {
    const templates = await api('/api/scenes/templates');
    const sel = $('#pipeline-style');
    const current = sel.value;
    sel.innerHTML = templates.map(t =>
      `<option value="${t.id}"${t.id === current ? ' selected' : ''}>${t.name}</option>`
    ).join('');
    // Store in _scnTemplates if scenes.js hasn't loaded them yet
    if (typeof _scnTemplates !== 'undefined' && !_scnTemplates.length) {
      _scnTemplates = templates;
    }
  } catch (e) { /* keep fallback option */ }
  pipelineLoadHistory();
})();
