/* ================================================================
   ScriptToScene Studio — Assets Module (Automa Grabber)
   Consumes scene data → sends prompts to Automa → polls for results.
   ================================================================ */

// ---- Scene Type Config ----

const _ASSET_TYPES = {
  video: { color: '#4ECDC4', bg: 'rgba(78,205,196,0.12)', label: 'VIDEO' },
  image: { color: '#A78BFA', bg: 'rgba(167,139,250,0.12)', label: 'IMAGE' },
  text:  { color: '#FFB347', bg: 'rgba(255,179,71,0.12)',  label: 'TEXT' },
};

const _PROVIDER_URLS = {
  midjourney: 'https://www.midjourney.com/imagine',
  grok: 'https://grok.com/imagine',
  'meta-ai': 'https://www.meta.ai/media',
};

function _typeConf(type) {
  return _ASSET_TYPES[type] || _ASSET_TYPES.video;
}

const _VIDEO_EXTS = /\.(mp4|webm|mov|avi|mkv)$/i;
function _isVideoFile(url) { return _VIDEO_EXTS.test(url); }
function _mediaTag(url, idx, i, opts = '') {
  if (_isVideoFile(url)) {
    return `<div style="position:relative;width:100%;height:100%" onclick="assetsOpenLightbox(${idx},${i})"
      onmouseenter="this.querySelector('video').play();this.querySelector('.vid-play-icon').style.opacity='0'"
      onmouseleave="var v=this.querySelector('video');v.pause();v.currentTime=0.1;this.querySelector('.vid-play-icon').style.opacity='1'">
      <video src="${esc(url)}#t=0.1" muted preload="auto" style="width:100%;height:100%;object-fit:cover;${opts}"></video>
      <span class="vid-play-icon" style="position:absolute;top:6px;right:6px;width:22px;height:22px;border-radius:50%;background:rgba(0,0,0,0.6);display:flex;align-items:center;justify-content:center;pointer-events:none;transition:opacity 0.2s">
        <svg width="10" height="10" fill="white" viewBox="0 0 24 24"><polygon points="6,3 20,12 6,21"/></svg>
      </span>
    </div>`;
  }
  return `<img src="${esc(url)}" alt="Scene ${idx} #${i}" style="width:100%;height:100%;object-fit:cover;${opts}" />`;
}

// ---- Grabber polling state ----
let _grabberPollTimer = null;

// ---- Source Loading ----

function loadScenesForAssets() {
  if (!STATE.scenesResult || !STATE.scenesResult.scenes) {
    toast('No scenes available. Generate scenes first.', 'error');
    return;
  }
  STATE.assetsSceneData = STATE.scenesResult;
  STATE.assetStatuses = {};  // Clear stale statuses from previous project
  STATE.assetSelected = {};  // Clear selection
  setModuleBadge('assets', STATE.scenesResult.project_id);
  renderAssetsFromScenes();
  loadAssetsHistory(); // refresh to highlight active row
  toast(`Loaded ${STATE.scenesResult.scenes.length} scenes`);
}

async function assetsPickSceneHistory() {
  let items;
  try {
    items = await api('/api/scenes/history');
  } catch (e) {
    toast('Failed to load scene history', 'error');
    return;
  }
  if (!items || !items.length) {
    toast('No scene history. Generate scenes first.', 'error');
    return;
  }

  const modal = $('#assets-scene-picker-modal');
  modal.classList.remove('hidden');
  modal.style.display = 'flex';

  const currentPid = STATE.assetsSceneData?.project_id || null;

  $('#assets-scene-picker-list').innerHTML = items.map(item => {
    const isActive = currentPid && item.project_id === currentPid;
    const styleName = typeof _scnStyleLabel === 'function' ? _scnStyleLabel(item.style) : '';
    const styleColor = typeof _scnStyleColor === 'function' ? _scnStyleColor(item.style) : 'var(--text-muted)';
    const parentLabel = item.parent_id ? `<span style="color:var(--text-muted);font-size:10px">from ${esc(item.parent_id)}</span>` : '';

    return `
    <div class="hist-item${isActive ? ' active' : ''}" style="cursor:pointer;transition:background 0.15s" onclick="assetsSelectSceneProject('${esc(item.project_id)}')" onmouseover="this.style.background='var(--bg-darkest)'" onmouseout="this.style.background=''"
      <div style="display:flex;align-items:center;gap:10px;padding:10px 12px 10px 14px">
        <div style="flex:1;min-width:0">
          <div style="display:flex;align-items:center;gap:8px">
            <p style="font-size:13px;color:${isActive ? '#ff9f43' : 'var(--text)'};margin:0;font-weight:${isActive ? '600' : '400'}">${esc(item.project_id)}</p>
            ${isActive ? '<span class="font-mono" style="font-size:8px;padding:1px 6px;border-radius:3px;background:rgba(255,159,67,0.15);color:#ff9f43;letter-spacing:0.05em;flex-shrink:0">ACTIVE</span>' : ''}
            ${parentLabel}
          </div>
          <p class="font-mono" style="font-size:10px;color:var(--text-muted);margin:2px 0 0">${item.scene_count} scenes · ${timeAgo(item.timestamp)}${styleName ? ` · <span style="display:inline-flex;align-items:center;gap:3px"><span style="width:6px;height:6px;border-radius:50%;background:${styleColor};display:inline-block"></span><span style="color:${styleColor};font-weight:600">${esc(styleName)}</span></span>` : ''}</p>
        </div>
        ${item.source_folder ? `<span class="font-mono" style="font-size:9px;color:var(--text-muted);flex-shrink:0;background:var(--bg-darkest);padding:2px 6px;border-radius:4px">${esc(item.source_folder.length > 30 ? item.source_folder.slice(0, 30) + '...' : item.source_folder)}</span>` : ''}
        <svg width="14" height="14" fill="none" stroke="${isActive ? '#ff9f43' : 'var(--text-muted)'}" stroke-width="1.5" viewBox="0 0 24 24" style="flex-shrink:0;opacity:${isActive ? '0.8' : '0.4'}"><path d="M9 18l6-6-6-6"/></svg>
      </div>
    </div>`;
  }).join('');
}

async function assetsSelectSceneProject(projectId) {
  assetsCloseScenePicker();
  try {
    const data = await api(`/api/scenes/${projectId}`);
    if (!data.scenes || !data.scenes.length) throw new Error('No scenes found');
    STATE.assetsSceneData = data;
    STATE.assetStatuses = {};  // Clear stale statuses from previous project
  STATE.assetSelected = {};  // Clear selection
    setModuleBadge('assets', data.project_id || projectId);
    renderAssetsFromScenes();
    loadAssetsHistory(); // refresh to highlight active row
    toast(`Loaded ${data.scenes.length} scenes from history`);
  } catch (e) {
    toast(e.message || 'Failed to load scene project', 'error');
  }
}

function assetsCloseScenePicker() {
  const modal = $('#assets-scene-picker-modal');
  modal.classList.add('hidden');
  modal.style.display = '';
}

function importAssetsJSON() {
  $('#assets-json-input').click();
}

function handleAssetsJSONImport(input) {
  const file = input.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = (e) => {
    try {
      const data = JSON.parse(e.target.result);
      if (!data.scenes || !Array.isArray(data.scenes)) {
        toast('Invalid JSON — must contain a "scenes" array', 'error');
        return;
      }
      STATE.assetsSceneData = data;
      STATE.assetStatuses = {};  // Clear stale statuses from previous project
  STATE.assetSelected = {};  // Clear selection
      setModuleBadge('assets', data.project_id);
      renderAssetsFromScenes();
      loadAssetsHistory(); // refresh to highlight active row
      toast(`Loaded ${data.scenes.length} scenes from file`);
    } catch (err) {
      toast('Failed to parse JSON', 'error');
    }
  };
  reader.readAsText(file);
  input.value = '';
}

// ---- Provider toggle ----

function assetsProviderChanged() {
  const provider = $('#assets-provider').value;
  const argsWrap = $('#assets-args-wrap');
  const argsInput = $('#assets-arguments');
  const kieOpts = $('#assets-kie-opts');
  const grokOpts = $('#assets-grok-opts');
  const showArgs = provider === 'midjourney' || provider === 'meta-ai';
  argsWrap.style.display = showArgs ? '' : 'none';
  kieOpts.style.display = provider === 'kie-ai' ? 'flex' : 'none';
  grokOpts.style.display = provider === 'grok' ? 'flex' : 'none';
  // Set default arguments per provider
  if (provider === 'midjourney') {
    if (!argsInput.value) argsInput.value = '--c 70 --v 7 --ar 9:16';
  } else if (!showArgs) {
    argsInput.value = '';
  }
}

// Sync aspect ratio → Midjourney --ar argument
document.addEventListener('DOMContentLoaded', () => {
  const aspectSel = document.getElementById('assets-aspect');
  if (aspectSel) {
    aspectSel.addEventListener('change', () => {
      const argsInput = document.getElementById('assets-arguments');
      if (!argsInput) return;
      const ratio = aspectSel.value;
      const val = argsInput.value;
      if (/--ar\s+\S+/.test(val)) {
        argsInput.value = val.replace(/--ar\s+\S+/, `--ar ${ratio}`);
      } else {
        argsInput.value = (val ? val + ' ' : '') + `--ar ${ratio}`;
      }
    });
  }
  // Init auto-type checkbox from localStorage
  const autoTypeCb = document.getElementById('assets-auto-type');
  if (autoTypeCb) autoTypeCb.checked = STS.get('sts-auto-type') === 'true';
});

// ---- Main Render ----

function renderAssetsFromScenes() {
  if (!STATE.assetsSceneData || !STATE.assetsSceneData.scenes) return;
  const scenes = STATE.assetsSceneData.scenes;
  const data = STATE.assetsSceneData;

  // Source label
  const pid = data.project_id ? `${data.project_id} · ` : '';
  const _astStyleName = typeof _scnStyleLabel === 'function' ? _scnStyleLabel(data.style) : '';
  const _astStyleColor = typeof _scnStyleColor === 'function' ? _scnStyleColor(data.style) : 'var(--text-muted)';
  const styleSuffix = _astStyleName ? ` · <span style="display:inline-flex;align-items:center;gap:3px"><span style="width:6px;height:6px;border-radius:50%;background:${_astStyleColor};display:inline-block"></span><span style="color:${_astStyleColor};font-weight:600">${_astStyleName}</span></span>` : '';
  $('#assets-source-label').innerHTML = `${pid}${scenes.length} scenes${styleSuffix}`;
  $('#assets-source-label').style.color = 'var(--accent)';

  // Show controls, hide empty state
  $('#assets-controls').style.display = '';
  $('#assets-empty').style.display = 'none';

  // Init statuses (keyed by scene index)
  scenes.forEach(s => {
    if (!STATE.assetStatuses[s.index]) {
      STATE.assetStatuses[s.index] = { status: 'pending', urls: [], local_files: [], editedPrompt: null };
    }
  });

  // Render sections
  _renderAnalysisBar(data);
  _renderTypeMix(data);
  renderAssetGrid(scenes);
  updateAssetsProgress();
  assetsLoadAudio();

  // Refresh history to show/update inline assemble buttons
  loadAssetsHistory();
}

function _renderAnalysisBar(data) {
  const bar = $('#assets-analysis-bar');
  const a = data.analysis;
  if (!a) { bar.style.display = 'none'; return; }
  bar.style.display = '';

  const labelColors = {
    Mood: '#FF6B6B', Env: '#4ECDC4', Palette: '#A78BFA',
    Tone: '#FFB347', Style: '#45B7D1', Theme: '#F7DC6F',
  };
  const chips = [];
  if (a.core_theme) chips.push({ label: 'Theme', value: a.core_theme });
  if (a.mood) chips.push({ label: 'Mood', value: a.mood });
  if (a.environment) chips.push({ label: 'Env', value: a.environment });
  if (a.color_palette) chips.push({ label: 'Palette', value: a.color_palette });
  if (a.tone) chips.push({ label: 'Tone', value: a.tone });
  if (a.visual_style) chips.push({ label: 'Style', value: a.visual_style });

  const chipsEl = $('#assets-analysis-chips');
  chipsEl.innerHTML = chips.map((c, i) => {
    const color = labelColors[c.label] || 'var(--text-muted)';
    return `
    <div style="display:flex;align-items:baseline;gap:5px${i > 0 ? ';padding-left:16px;border-left:1px solid var(--border)' : ''}">
      <span style="font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:0.08em;color:${color};white-space:nowrap">${c.label}</span>
      <span style="font-size:11px;color:var(--text-secondary)">${esc(c.value)}</span>
    </div>`;
  }).join('');

  // Show script/story text from segmenter data
  const scriptEl = $('#assets-analysis-script');
  const scriptText = $('#assets-analysis-script-text');
  const script = STATE.scenesSegData?.metadata?.transcript || '';
  if (script && scriptEl && scriptText) {
    scriptEl.style.display = '';
    scriptText.textContent = script;
  } else if (scriptEl) {
    scriptEl.style.display = 'none';
  }

  // Collapse by default, restore from localStorage
  const collapsed = STS.get('sts-analysis-collapsed') !== 'false';
  chipsEl.style.display = collapsed ? 'none' : 'flex';
  const arrow = $('#assets-analysis-arrow');
  if (arrow) arrow.style.transform = collapsed ? 'rotate(-90deg)' : '';

  const toggle = $('#assets-analysis-toggle');
  if (toggle && !toggle._bound) {
    toggle._bound = true;
    toggle.addEventListener('click', () => {
      const hidden = chipsEl.style.display === 'none';
      chipsEl.style.display = hidden ? 'flex' : 'none';
      if (arrow) arrow.style.transform = hidden ? '' : 'rotate(-90deg)';
      STS.set('sts-analysis-collapsed', !hidden);
    });
  }
}

function _renderTypeMix(data) {
  const mix = data.type_mix;
  const el = $('#assets-type-mix');
  if (!mix) { el.style.display = 'none'; return; }
  el.style.display = 'flex';
  el.style.gap = '6px';

  const entries = [];
  if (mix.video) entries.push({ type: 'video', pct: mix.video });
  if (mix.image) entries.push({ type: 'image', pct: mix.image });
  if (mix.text) entries.push({ type: 'text', pct: mix.text });

  el.innerHTML = entries.map(e => {
    const tc = _typeConf(e.type);
    return `<span class="font-mono" style="font-size:9px;padding:2px 6px;border-radius:4px;background:${tc.bg};color:${tc.color}">${tc.label} ${e.pct}</span>`;
  }).join('');
}

// ---- Asset Grid ----

function renderAssetGrid(scenes) {
  $('#assets-grid').innerHTML = scenes.map((s, i) => _buildAssetCard(s, i)).join('');
}

function _buildAssetCard(scene, sceneNum) {
  const idx = scene.index;
  const st = STATE.assetStatuses[idx] || { status: 'pending' };
  const tc = _typeConf(scene.type_of_scene);
  const files = st.local_files || [];
  const hasImage = st.status === 'ready' && files.length > 0;
  const isGenerating = st.status === 'generating';
  const isDownloading = st.status === 'downloading';
  const isError = st.status === 'error';
  const prompt = st.editedPrompt || scene.image_prompt || '';

  // Preview area — show gallery thumbnails when multiple files
  let previewContent;
  if (hasImage) {
    if (files.length === 1) {
      previewContent = `
        ${_mediaTag(files[0], idx, 0, 'cursor:pointer')}`;
    } else {
      // Multi-image grid (2x2 for 4, 1x2/1x3 for 2-3)
      const thumbs = files.slice(0, 4).map((f, i) => `
        <div style="overflow:hidden;cursor:pointer;position:relative" onclick="assetsOpenLightbox(${idx},${i})">
          ${_mediaTag(f, idx, i, 'display:block;transition:transform 0.2s')}
        </div>`).join('');

      const cols = Math.min(files.length, 2);
      const rowCount = files.length <= 2 ? 1 : 2;
      previewContent = `<div style="display:grid;grid-template-columns:repeat(${cols},1fr);grid-template-rows:repeat(${rowCount},1fr);gap:2px;height:100%">${thumbs}</div>`;
      if (files.length > 4) {
        previewContent += `<span style="position:absolute;bottom:6px;right:6px;background:rgba(0,0,0,0.75);color:white;font-size:9px;padding:2px 8px;border-radius:4px;font-family:'JetBrains Mono',monospace;pointer-events:none">+${files.length - 4} more</span>`;
      }
    }
    previewContent += `<span style="position:absolute;top:6px;right:6px;background:rgba(0,0,0,0.7);color:white;font-size:9px;padding:2px 6px;border-radius:4px;font-family:'JetBrains Mono',monospace;pointer-events:none">${files.length} file${files.length > 1 ? 's' : ''}</span>`;
  } else if (isGenerating) {
    previewContent = `
      <div style="text-align:center;color:#A78BFA">
        <div style="width:24px;height:24px;border:2px solid rgba(255,255,255,0.1);border-top-color:#A78BFA;border-radius:50%;animation:spin 1.2s linear infinite;margin:0 auto 8px"></div>
        <p style="font-size:10px;font-weight:500;opacity:0.8">Generating...</p>
      </div>`;
  } else if (isDownloading) {
    previewContent = `
      <div style="text-align:center;color:${tc.color}">
        <div style="width:24px;height:24px;border:2px solid rgba(255,255,255,0.1);border-top-color:${tc.color};border-radius:50%;animation:spin 0.8s linear infinite;margin:0 auto 8px"></div>
        <p style="font-size:10px;font-weight:500;opacity:0.8">Downloading...</p>
      </div>`;
  } else if (isError) {
    previewContent = `
      <div style="text-align:center;color:var(--coral)">
        <svg width="24" height="24" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" style="margin:0 auto 6px">
          <circle cx="12" cy="12" r="10"/><path d="M15 9l-6 6M9 9l6 6"/>
        </svg>
        <p style="font-size:10px;font-weight:500">Failed</p>
      </div>`;
  } else {
    const typeIcons = {
      video: `<svg width="24" height="24" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><polygon points="5 3 19 12 5 21"/></svg>`,
      image: `<svg width="24" height="24" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M21 15l-5-5L5 21"/></svg>`,
      text:  `<svg width="24" height="24" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><path d="M4 7V4h16v3"/><line x1="12" y1="4" x2="12" y2="20"/><line x1="8" y1="20" x2="16" y2="20"/></svg>`,
    };
    previewContent = `
      <div style="text-align:center;color:var(--text-muted);opacity:0.5">
        ${typeIcons[scene.type_of_scene] || typeIcons.video}
        <p style="font-size:10px;margin-top:6px">#${sceneNum}</p>
      </div>`;
  }

  // Status badge — hide when ready with files (file count badge is enough)
  const statusLabels = { pending: 'Pending', generating: 'Generating', downloading: 'Downloading', ready: 'Ready', error: 'Error' };
  const statusClass = (st.status === 'downloading' || st.status === 'generating') ? 'generating' : st.status;
  const statusBadge = hasImage
    ? ''
    : `<span class="status-badge ${statusClass}">${statusLabels[st.status] || st.status}</span>`;

  // Text content display (for text-type scenes)
  const textContentHTML = scene.text_content
    ? `<div style="margin-bottom:8px;padding:8px 10px;border-radius:6px;background:${tc.bg};border:1px solid rgba(255,179,71,0.15)">
        <p style="font-size:12px;font-weight:600;color:${tc.color};margin:0;letter-spacing:0.02em">"${esc(scene.text_content)}"</p>
      </div>`
    : '';

  const checked = STATE.assetSelected?.[idx] ? 'checked' : '';

  return `
  <div class="asset-card" id="asset-card-${idx}">
    <div class="asset-preview" style="height:180px;display:flex;align-items:center;justify-content:center;position:relative;overflow:hidden">
      ${previewContent}
      ${statusBadge}
      <label class="asset-check" onclick="event.stopPropagation()">
        <input type="checkbox" ${checked} onchange="assetsToggleSelect(${idx},this.checked)" />
        <span class="mark"><svg viewBox="0 0 16 16"><polyline points="3.5 8.5 6.5 11.5 12.5 5"/></svg></span>
      </label>
    </div>
    <div style="padding:14px">
      <!-- Header -->
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;gap:8px">
        <div style="display:flex;align-items:center;gap:8px;min-width:0">
          <span class="font-mono" style="font-size:10px;color:var(--text-muted);flex-shrink:0">#${sceneNum}</span>
          <span style="font-size:13px;font-weight:600;color:var(--text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(scene.title || '')}</span>
        </div>
        <div style="display:flex;gap:4px;align-items:center;flex-shrink:0">
          <span class="font-mono" style="font-size:8px;font-weight:700;padding:2px 6px;border-radius:4px;background:${tc.bg};color:${tc.color};text-transform:uppercase;letter-spacing:0.05em">${tc.label}</span>
          ${scene.narrative_role ? `<span class="font-mono" style="font-size:8px;padding:2px 6px;border-radius:4px;background:var(--bg-darkest);color:var(--text-muted);letter-spacing:0.03em">${esc(scene.narrative_role)}</span>` : ''}
          <span class="font-mono" style="font-size:9px;color:var(--text-muted)">${(scene.duration || 0).toFixed(1)}s</span>
        </div>
      </div>

      ${textContentHTML}

      <!-- Prompt (view/edit) -->
      <div id="asset-prompt-wrap-${idx}">
        <div id="asset-prompt-view-${idx}" style="display:flex;gap:6px;align-items:flex-start">
          <p style="flex:1;font-size:11px;color:var(--text-secondary);line-height:1.5;margin:0;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden">${esc(prompt)}</p>
          <button onclick="event.stopPropagation();assetsCopyPrompt(${idx})" style="background:none;border:none;cursor:pointer;color:var(--text-muted);padding:2px;flex-shrink:0;opacity:0.5;transition:opacity 0.2s" onmouseover="this.style.opacity='1'" onmouseout="this.style.opacity='0.5'" title="Copy prompt">
            <svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>
          </button>
          <button onclick="assetsEditPrompt(${idx})" style="background:none;border:none;cursor:pointer;color:var(--text-muted);padding:2px;flex-shrink:0;opacity:0.5;transition:opacity 0.2s" onmouseover="this.style.opacity='1'" onmouseout="this.style.opacity='0.5'" title="Edit prompt">
            <svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
          </button>
        </div>
        <div id="asset-prompt-edit-${idx}" style="display:none">
          <textarea id="asset-prompt-input-${idx}" class="input-field" style="width:100%;padding:8px 10px;font-size:11px;line-height:1.5;resize:vertical;font-family:inherit;min-height:60px" rows="3">${esc(prompt)}</textarea>
          <div style="display:flex;gap:6px;margin-top:6px">
            <button onclick="assetsSavePrompt(${idx})" class="action-btn hover-accent" style="font-size:10px">Save</button>
            <button onclick="assetsCancelPromptEdit(${idx})" class="action-btn" style="font-size:10px;color:var(--text-muted)">Cancel</button>
          </div>
        </div>
      </div>

      <!-- Actions -->
      <div style="display:flex;gap:6px;margin-top:10px">
        <button onclick="downloadAssetImage(${idx})" class="action-btn hover-accent" ${hasImage ? '' : 'disabled style="opacity:0.4"'}>${hasImage ? `Download (${files.length})` : 'Download'}</button>
        <button onclick="openAssetFolder(${idx})" class="action-btn" style="color:var(--text-muted);padding:6px 10px" title="Open folder" ${hasImage ? '' : 'disabled style="opacity:0.4"'}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/></svg>
        </button>
      </div>
    </div>
  </div>`;
}

// ---- Open Asset Folder ----
async function openAssetFolder(sceneIndex) {
  const pid = STATE.assetsSceneData?.project_id;
  if (!pid) { toast('No project loaded', 'error'); return; }
  try {
    const res = await fetch(`/api/assets/open-folder/${encodeURIComponent(pid)}/${sceneIndex}`, { method: 'POST' });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || 'Failed to open folder');
    }
  } catch (e) {
    toast('Could not open folder: ' + e.message, 'error');
  }
}

// ---- Lightbox for viewing full-size images ----

function assetsOpenLightbox(sceneIndex, fileIndex) {
  const st = STATE.assetStatuses[sceneIndex];
  if (!st || !st.local_files || !st.local_files.length) return;
  const files = st.local_files;

  // Remove existing lightbox
  const existing = document.getElementById('assets-lightbox');
  if (existing) existing.remove();

  let currentIdx = fileIndex;

  const overlay = document.createElement('div');
  overlay.id = 'assets-lightbox';
  overlay.style.cssText = 'position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,0.92);display:flex;flex-direction:column;align-items:center;justify-content:center;backdrop-filter:blur(10px)';

  function render() {
    overlay.innerHTML = `
      <div style="position:absolute;top:16px;right:16px;display:flex;gap:8px;z-index:10">
        <span class="font-mono" style="font-size:11px;color:rgba(255,255,255,0.5);padding:6px 12px;background:rgba(255,255,255,0.08);border-radius:6px">Scene #${sceneIndex} · ${currentIdx + 1}/${files.length}</span>
        <button onclick="document.getElementById('assets-lightbox').remove()" style="background:rgba(255,255,255,0.1);border:none;color:white;width:32px;height:32px;border-radius:6px;cursor:pointer;font-size:18px;display:flex;align-items:center;justify-content:center">&times;</button>
      </div>
      ${_isVideoFile(files[currentIdx])
        ? `<video src="${esc(files[currentIdx])}" controls autoplay muted style="max-width:90vw;max-height:80vh;object-fit:contain;border-radius:8px;box-shadow:0 8px 40px rgba(0,0,0,0.5)"></video>`
        : `<img src="${esc(files[currentIdx])}" style="max-width:90vw;max-height:80vh;object-fit:contain;border-radius:8px;box-shadow:0 8px 40px rgba(0,0,0,0.5)" />`
      }
      ${files.length > 1 ? `
        <div style="display:flex;gap:8px;margin-top:16px;padding:8px;border-radius:8px;background:rgba(255,255,255,0.05)">
          ${files.map((f, i) => `
            <div onclick="event.stopPropagation();document.getElementById('assets-lightbox')._goto(${i})" style="width:56px;height:56px;border-radius:6px;overflow:hidden;cursor:pointer;border:2px solid ${i === currentIdx ? 'var(--accent)' : 'transparent'};opacity:${i === currentIdx ? '1' : '0.6'};transition:all 0.2s">
              ${_isVideoFile(f) ? `<video src="${esc(f)}#t=0.1" muted preload="auto" style="width:100%;height:100%;object-fit:cover"></video>` : `<img src="${esc(f)}" style="width:100%;height:100%;object-fit:cover" />`}
            </div>
          `).join('')}
        </div>
      ` : ''}
    `;
  }

  overlay._goto = (i) => { currentIdx = i; render(); };
  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) overlay.remove();
  });

  // Keyboard nav
  const onKey = (e) => {
    if (e.key === 'Escape') { overlay.remove(); document.removeEventListener('keydown', onKey); }
    if (e.key === 'ArrowRight' && currentIdx < files.length - 1) { currentIdx++; render(); }
    if (e.key === 'ArrowLeft' && currentIdx > 0) { currentIdx--; render(); }
  };
  document.addEventListener('keydown', onKey);
  overlay.addEventListener('remove', () => document.removeEventListener('keydown', onKey));

  render();
  document.body.appendChild(overlay);
}

// ---- Single Card Update ----

function updateAssetCard(sceneIndex) {
  if (!STATE.assetsSceneData) return;
  const scenes = STATE.assetsSceneData.scenes;
  const pos = scenes.findIndex(s => s.index === sceneIndex);
  if (pos === -1) return;
  const el = document.getElementById(`asset-card-${sceneIndex}`);
  if (el) {
    el.outerHTML = _buildAssetCard(scenes[pos], pos);
  }
}

// ---- Progress ----

function updateAssetsProgress() {
  if (!STATE.assetsSceneData || !STATE.assetsSceneData.scenes) return;
  const scenes = STATE.assetsSceneData.scenes;
  const total = scenes.length;
  const ready = scenes.filter(s => STATE.assetStatuses[s.index]?.status === 'ready').length;
  const generating = scenes.filter(s => STATE.assetStatuses[s.index]?.status === 'generating').length;
  const downloading = scenes.filter(s => STATE.assetStatuses[s.index]?.status === 'downloading').length;
  const totalFiles = scenes.reduce((sum, s) => sum + (STATE.assetStatuses[s.index]?.local_files?.length || 0), 0);

  let text = `${ready} / ${total} complete`;
  if (totalFiles > 0) text += ` · ${totalFiles} files`;
  if (generating > 0) text += ` · ${generating} generating`;
  if (downloading > 0) text += ` · ${downloading} downloading`;
  $('#assets-progress').textContent = text;

  // Progress bar
  const barWrap = $('#assets-progress-bar-wrap');
  if (ready > 0 || downloading > 0 || generating > 0) {
    barWrap.style.display = '';
    const pct = total > 0 ? (ready / total) * 100 : 0;
    $('#assets-progress-bar').style.width = pct + '%';
  } else {
    barWrap.style.display = 'none';
  }
}

// ---- Prompt Editing ----

function assetsEditPrompt(sceneIndex) {
  $(`#asset-prompt-view-${sceneIndex}`).style.display = 'none';
  $(`#asset-prompt-edit-${sceneIndex}`).style.display = '';
  const input = $(`#asset-prompt-input-${sceneIndex}`);
  input.focus();
  input.setSelectionRange(input.value.length, input.value.length);
}

function assetsSavePrompt(sceneIndex) {
  const input = $(`#asset-prompt-input-${sceneIndex}`);
  const newPrompt = input.value.trim();
  if (!newPrompt) {
    toast('Prompt cannot be empty', 'error');
    return;
  }
  if (!STATE.assetStatuses[sceneIndex]) {
    STATE.assetStatuses[sceneIndex] = { status: 'pending', urls: [], local_files: [], editedPrompt: null };
  }
  STATE.assetStatuses[sceneIndex].editedPrompt = newPrompt;

  // Update view mode
  $(`#asset-prompt-view-${sceneIndex}`).style.display = 'flex';
  $(`#asset-prompt-edit-${sceneIndex}`).style.display = 'none';
  const viewP = $(`#asset-prompt-view-${sceneIndex} p`);
  if (viewP) viewP.textContent = newPrompt;
  toast('Prompt updated');
}

function assetsCancelPromptEdit(sceneIndex) {
  $(`#asset-prompt-view-${sceneIndex}`).style.display = 'flex';
  $(`#asset-prompt-edit-${sceneIndex}`).style.display = 'none';
  const scene = STATE.assetsSceneData?.scenes?.find(s => s.index === sceneIndex);
  const currentPrompt = STATE.assetStatuses[sceneIndex]?.editedPrompt || scene?.image_prompt || '';
  $(`#asset-prompt-input-${sceneIndex}`).value = currentPrompt;
}

function assetsCopyPrompt(sceneIndex) {
  const scene = STATE.assetsSceneData?.scenes?.find(s => s.index === sceneIndex);
  const prompt = STATE.assetStatuses[sceneIndex]?.editedPrompt || scene?.image_prompt || '';
  if (!prompt) { toast('No prompt to copy', 'error'); return; }
  navigator.clipboard.writeText(prompt)
    .then(() => toast('Prompt copied'))
    .catch(() => toast('Copy failed', 'error'));
}

// ---- Scene Selection ----

function assetsToggleSelect(idx, checked) {
  if (!STATE.assetSelected) STATE.assetSelected = {};
  STATE.assetSelected[idx] = checked;
  _updateSelectionUI();
}

function assetsSelectAll() {
  if (!STATE.assetsSceneData?.scenes) return;
  const allSelected = _getSelectedCount() === STATE.assetsSceneData.scenes.length;
  STATE.assetSelected = {};
  STATE.assetsSceneData.scenes.forEach(s => { STATE.assetSelected[s.index] = !allSelected; });
  renderAssetGrid(STATE.assetsSceneData.scenes);
  _updateSelectionUI();
}

function assetsSelectPending() {
  if (!STATE.assetsSceneData?.scenes) return;
  STATE.assetSelected = {};
  STATE.assetsSceneData.scenes.forEach(s => {
    const st = STATE.assetStatuses[s.index];
    if (!st || st.status !== 'ready') STATE.assetSelected[s.index] = true;
  });
  renderAssetGrid(STATE.assetsSceneData.scenes);
  _updateSelectionUI();
}

function _getSelectedCount() {
  return Object.values(STATE.assetSelected || {}).filter(Boolean).length;
}

function _updateSelectionUI() {
  const count = _getSelectedCount();
  const bar = $('#assets-selection-bar');
  if (!bar) return;
  if (count > 0) {
    bar.style.display = '';
    $('#assets-selection-count').textContent = `${count} selected`;
  } else {
    bar.style.display = 'none';
  }
}

async function assetsResendSelected() {
  if (!STATE.assetsSceneData?.scenes) return;
  const scenes = STATE.assetsSceneData.scenes;
  const selected = scenes.filter((s, i) => STATE.assetSelected?.[s.index]);
  if (!selected.length) { toast('No scenes selected', 'error'); return; }

  const provider = $('#assets-provider').value;
  const arguments_ = provider === 'midjourney' ? ($('#assets-arguments').value || '--c 70 --v 7 --ar 9:16') : '';
  const projectId = STATE.assetsSceneData.project_id || 'default';

  // Build payload with original sequential positions
  const scenesPayload = selected.map(s => {
    const pos = scenes.indexOf(s);
    return {
      prompt: STATE.assetStatuses[s.index]?.editedPrompt || s.image_prompt,
      scene: pos,
    };
  }).filter(s => s.prompt);

  if (!scenesPayload.length) { toast('No prompts for selected scenes', 'error'); return; }

  _setGrabberStatus('Re-sending selected scenes...');

  const resendBody = {
    project_id: projectId,
    provider,
    arguments: arguments_,
    scenes: scenesPayload,
    aspect_ratio: $('#assets-aspect')?.value || '9:16',
  };
  if (provider === 'kie-ai') {
    resendBody.model = $('#assets-kie-model')?.value || 'google/nano-banana';
    resendBody.resolution = $('#assets-kie-resolution')?.value || '1';
    resendBody.output_format = $('#assets-kie-format')?.value || 'jpg';
  }

  try {
    const res = await fetch('/api/assets/grabber/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(resendBody),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Failed to start grabber');

    // Mark selected scenes as pending
    selected.forEach(s => {
      if (STATE.assetStatuses[s.index]) STATE.assetStatuses[s.index].status = 'pending';
    });
    renderAssetGrid(scenes);
    updateAssetsProgress();

    if (provider === 'kie-ai') {
      _setGrabberStatus(`Generating ${data.scene_count} selected scenes via Kie AI...`);
      toast(`Kie AI generating ${data.scene_count} selected scenes`);
    } else {
      const providerUrl = _PROVIDER_URLS[provider] || _PROVIDER_URLS.midjourney;
      window.open(providerUrl, 'sts-provider-tab');
      _setGrabberStatus(`${data.scene_count} selected scenes queued — activate Automa`);
      toast(`${data.scene_count} scenes re-sent to grabber`);
    }

    _startGrabberPolling(projectId);
    _setGrabberUI(true);

    // Clear selection
    STATE.assetSelected = {};
    _updateSelectionUI();
  } catch (e) {
    toast(e.message || 'Resend failed', 'error');
    _setGrabberStatus('');
  }
}

// ---- Assets Grabber ----

let _grabberRunning = false;

function assetsToggleGrabber() {
  if (_grabberRunning) {
    assetsStopGrabber();
  } else {
    assetsStartGrabber();
  }
}

function _setGrabberUI(running) {
  _grabberRunning = running;
  const label = $('#assets-grabber-label');
  const icon = $('#assets-grabber-icon');
  const btn = $('#assets-grabber-btn');
  if (running) {
    label.textContent = 'Stop Grabber';
    icon.innerHTML = '<rect x="6" y="6" width="12" height="12" rx="1"/>';
    btn.style.background = '#FF6B6B';
  } else {
    label.textContent = 'Start Grabber';
    icon.innerHTML = '<path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>';
    btn.style.background = '';
  }
}

function assetsStopGrabber() {
  if (_grabberPollTimer) {
    clearInterval(_grabberPollTimer);
    _grabberPollTimer = null;
  }
  _setGrabberUI(false);
  _setGrabberStatus('Grabber stopped');
  toast('Grabber stopped');
}

async function assetsStartGrabber() {
  if (!STATE.assetsSceneData || !STATE.assetsSceneData.scenes) {
    toast('No scenes loaded', 'error');
    return;
  }

  const scenes = STATE.assetsSceneData.scenes;
  const provider = $('#assets-provider').value;
  const arguments_ = provider === 'midjourney' ? ($('#assets-arguments').value || '--c 70 --v 7 --ar 9:16') : '';
  const projectId = STATE.assetsSceneData.project_id || 'default';

  // Build scenes payload (respect edited prompts, sequential folder numbering)
  // Keep track of which original scenes are included for status updates
  const scenesWithPrompts = scenes.filter(s => s.image_prompt || STATE.assetStatuses[s.index]?.editedPrompt);
  const scenesPayload = scenesWithPrompts.map((s, i) => ({
    prompt: STATE.assetStatuses[s.index]?.editedPrompt || s.image_prompt,
    scene: i,
  }));

  if (!scenesPayload.length) {
    toast('No prompts available', 'error');
    return;
  }

  // Disable button
  const btn = $('#assets-grabber-btn');
  btn.disabled = true;
  btn.style.opacity = '0.6';

  _setGrabberStatus('Initializing grabber job...');

  // Build request body
  const reqBody = {
    project_id: projectId,
    provider: provider,
    arguments: arguments_,
    scenes: scenesPayload,
    aspect_ratio: $('#assets-aspect')?.value || '9:16',
  };

  // Add Grok options if applicable
  if (provider === 'grok') {
    reqBody.grok_mode = $('#assets-grok-mode')?.value || 'video';
    reqBody.grok_quality = $('#assets-grok-quality')?.value || '480p';
    reqBody.grok_duration = $('#assets-grok-duration')?.value || '6s';
    reqBody.auto_type = $('#assets-auto-type')?.checked || false;
  }

  // Add Kie AI options if applicable
  if (provider === 'kie-ai') {
    reqBody.model = $('#assets-kie-model')?.value || 'google/nano-banana';
    reqBody.resolution = $('#assets-kie-resolution')?.value || '1';
    reqBody.output_format = $('#assets-kie-format')?.value || 'jpg';
  }

  try {
    const res = await fetch('/api/assets/grabber/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(reqBody),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Failed to start grabber');

    // Mark all included scenes as pending (use scene.index, not sequential position)
    scenesWithPrompts.forEach(s => {
      if (STATE.assetStatuses[s.index]) {
        STATE.assetStatuses[s.index].status = 'pending';
      }
    });
    renderAssetGrid(scenes);
    updateAssetsProgress();

    if (provider === 'kie-ai') {
      // Kie AI is server-side — no browser tab needed
      _setGrabberStatus(`Generating ${data.scene_count} images via Kie AI...`);
      toast(`Kie AI generating ${data.scene_count} images server-side`);
    } else {
      // Open provider tab (reuse existing tab if already open)
      const providerUrl = _PROVIDER_URLS[provider] || _PROVIDER_URLS.midjourney;
      window.open(providerUrl, 'sts-provider-tab');
      const providerLabel = { midjourney: 'Midjourney', grok: 'Grok', 'meta-ai': 'Meta AI' }[provider] || provider;
      _setGrabberStatus(`Prompts ready (${data.scene_count} scenes) — activate Automa in the ${providerLabel} tab to start`);
      toast(`Grabber ready — ${data.scene_count} prompts queued. Activate Automa to begin.`);
    }

    // Start polling for results
    _startGrabberPolling(projectId);
    _setGrabberUI(true);
  } catch (e) {
    toast(e.message || 'Grabber failed', 'error');
    _setGrabberStatus('');
    _setGrabberUI(false);
  } finally {
    btn.disabled = false;
    btn.style.opacity = '';
  }
}

function _setGrabberStatus(text) {
  const el = $('#assets-grabber-status');
  const textEl = $('#assets-grabber-status-text');
  if (text) {
    el.style.display = '';
    textEl.textContent = text;
  } else {
    el.style.display = 'none';
  }
}

function _startGrabberPolling(projectId) {
  if (_grabberPollTimer) clearInterval(_grabberPollTimer);

  _grabberPollTimer = setInterval(async () => {
    try {
      const res = await fetch(`/api/assets/grabber/status/${encodeURIComponent(projectId)}`);
      if (!res.ok) return;
      const data = await res.json();

      // Update per-scene statuses
      // sceneNum is sequential (0,1,2...), map to scene.index for STATE lookup
      const sceneStatuses = data.scene_statuses || {};
      const scenes = STATE.assetsSceneData?.scenes || [];
      let anyChange = false;

      for (const [sceneNum, ss] of Object.entries(sceneStatuses)) {
        const pos = parseInt(sceneNum);
        const scene = scenes[pos];
        const idx = scene ? scene.index : pos;
        if (!STATE.assetStatuses[idx]) continue;
        const prev = STATE.assetStatuses[idx].status;

        const filesChanged = (ss.local_files?.length || 0) !== (STATE.assetStatuses[idx].local_files?.length || 0);
        if (ss.status !== prev || filesChanged) {
          STATE.assetStatuses[idx].status = ss.status;
          STATE.assetStatuses[idx].local_files = ss.local_files || [];
          STATE.assetStatuses[idx].urls = ss.urls || [];
          updateAssetCard(idx);
          anyChange = true;

          if (ss.status === 'ready' && prev !== 'ready') {
            toast(`Scene #${sceneNum} — ${ss.local_files.length} file(s) downloaded`);
          }
        }
      }

      if (anyChange) updateAssetsProgress();

      // Update status message
      const statusMap = { waiting: 'Waiting for Automa...', grabbing: 'Automa is submitting prompts...', generating: 'Generating images via Kie AI...', downloading: 'Downloading images...', done: 'All assets downloaded!', error: 'Grabber encountered errors' };
      _setGrabberStatus(statusMap[data.status] || data.status);

      // Stop polling when done
      if (data.status === 'done' || data.status === 'error') {
        clearInterval(_grabberPollTimer);
        _grabberPollTimer = null;
        _setGrabberUI(false);
        loadAssetsHistory(); // refresh history
        if (data.status === 'done') {
          if (typeof playDoneSound === 'function') playDoneSound();
        }
      }
    } catch (e) {
      // Network error — keep polling
    }
  }, 5000);
}

// ---- Re-download (retry failed/pending scenes) ----

async function assetsRedownload() {
  const projectId = STATE.assetsSceneData?.project_id;
  if (!projectId) {
    toast('No project loaded', 'error');
    return;
  }

  const btn = $('#assets-redownload-btn');
  if (btn) { btn.disabled = true; btn.textContent = 'Retrying...'; }

  try {
    const res = await fetch(`/api/assets/redownload/${encodeURIComponent(projectId)}`, { method: 'POST' });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Retry failed');

    if (data.status === 'nothing_to_retry') {
      toast('All scenes already downloaded');
    } else {
      toast(`Retrying ${data.scenes_retrying} scene(s)...`);
      _startGrabberPolling(projectId);
    }
  } catch (e) {
    toast(e.message || 'Retry failed', 'error');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'Retry Downloads'; }
  }
}

// ---- Download ----

function downloadAssetImage(sceneIndex) {
  const st = STATE.assetStatuses[sceneIndex];
  if (!st || !st.local_files || !st.local_files.length) return;
  st.local_files.forEach((url, i) => {
    setTimeout(() => {
      const a = document.createElement('a');
      a.href = url;
      a.download = url.split('/').pop();
      document.body.appendChild(a); a.click(); a.remove();
    }, i * 200);
  });
}

function downloadAllAssets() {
  if (!STATE.assetsSceneData || !STATE.assetsSceneData.scenes) return;
  const readyScenes = STATE.assetsSceneData.scenes.filter(s =>
    STATE.assetStatuses[s.index]?.status === 'ready' && STATE.assetStatuses[s.index]?.local_files?.length
  );
  if (!readyScenes.length) {
    toast('No images ready for download', 'error');
    return;
  }
  let delay = 0;
  readyScenes.forEach(s => {
    const files = STATE.assetStatuses[s.index].local_files;
    files.forEach(url => {
      setTimeout(() => {
        const a = document.createElement('a');
        a.href = url;
        a.download = url.split('/').pop();
        document.body.appendChild(a); a.click(); a.remove();
      }, delay);
      delay += 200;
    });
  });
  toast(`Downloading assets from ${readyScenes.length} scenes`);
}

// ---- Assets History ----

async function loadAssetsHistory() {
  const container = $('#assets-history-list');
  if (!container) return;

  try {
    const projects = await api('/api/assets/history');
    if (!projects || !projects.length) {
      container.innerHTML = `<p style="text-align:center;color:var(--text-muted);font-size:12px;padding:20px 0">No asset projects yet</p>`;
      return;
    }

    const currentPid = STATE.assetsSceneData?.project_id || null;

    container.innerHTML = projects.map(p => {
      const isActive = currentPid && p.project_id === currentPid;
      const statusColors = { done: '#4ECDC4', downloading: '#FFB347', error: '#FF6B6B', waiting: '#8B8B8B', grabbing: '#A78BFA' };
      const statusColor = statusColors[p.status] || '#8B8B8B';
      const statusLabel = p.status || 'unknown';
      const sceneCount = p.scene_count || 0;
      const readyCount = p.ready_count || 0;
      const diskFiles = p.disk_files || 0;
      const time = p.created_at ? timeAgo(p.created_at) : timeAgo(p.timestamp);

      return `
      <div class="hist-item${isActive ? ' active' : ''}" data-project-id="${esc(p.project_id)}" style="cursor:pointer;transition:background 0.15s" onclick="assetsLoadFromHistory('${esc(p.project_id)}')" onmouseover="this.style.background='var(--bg-darkest)'" onmouseout="this.style.background=''">
        <div style="display:flex;align-items:center;gap:12px;padding:10px 14px">
          ${p.preview
            ? `<div style="width:48px;height:48px;border-radius:6px;overflow:hidden;flex-shrink:0;border:1px solid ${isActive ? '#ff9f43' : 'var(--border)'}"><img src="${esc(p.preview)}" style="width:100%;height:100%;object-fit:cover" /></div>`
            : `<div style="width:48px;height:48px;border-radius:6px;flex-shrink:0;background:var(--bg-darkest);display:flex;align-items:center;justify-content:center;border:1px solid ${isActive ? '#ff9f43' : 'transparent'}">
                <svg width="20" height="20" fill="none" stroke="${isActive ? '#ff9f43' : 'var(--text-muted)'}" stroke-width="1.5" viewBox="0 0 24 24" style="opacity:${isActive ? '0.8' : '0.4'}"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M21 15l-5-5L5 21"/></svg>
              </div>`
          }
          <div style="flex:1;min-width:0">
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:3px">
              <span style="font-size:12px;font-weight:600;color:${isActive ? '#ff9f43' : 'var(--text)'};overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(p.project_id)}</span>
              ${isActive ? '<span class="font-mono" style="font-size:8px;padding:1px 6px;border-radius:3px;background:rgba(255,159,67,0.15);color:#ff9f43;letter-spacing:0.05em;flex-shrink:0">ACTIVE</span>' : ''}
              <span style="display:inline-block;width:6px;height:6px;border-radius:50%;background:${statusColor};flex-shrink:0"></span>
              <span class="font-mono" style="font-size:9px;color:${statusColor};text-transform:uppercase;letter-spacing:0.05em">${esc(statusLabel)}</span>
            </div>
            <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;font-family:'JetBrains Mono',monospace;font-size:10px">
              <span style="color:#4ECDC4">${sceneCount} scene${sceneCount !== 1 ? 's' : ''}</span>
              ${readyCount > 0 ? `<span style="opacity:0.3">/</span><span style="color:#26DE81">${readyCount} ready</span>` : ''}
              ${diskFiles > 0 ? `<span style="opacity:0.3">/</span><span style="color:var(--text-secondary)">${diskFiles} files</span>` : ''}
              <span style="opacity:0.3">/</span>
              <span style="color:var(--text-muted)">${time}</span>
              ${p.provider ? `<span style="opacity:0.3">/</span><span style="font-size:8px;padding:1px 5px;border-radius:3px;background:rgba(167,139,250,0.1);color:#A78BFA">${esc(p.provider)}</span>` : ''}
            </div>
          </div>
          ${readyCount > 0 ? `<button onclick="event.stopPropagation(); assetsAssembleFromHistory('${esc(p.project_id)}')" style="flex-shrink:0;padding:5px 12px;background:var(--accent);color:var(--bg-darkest);border:none;border-radius:6px;font-size:10px;font-weight:600;cursor:pointer;white-space:nowrap;transition:opacity 0.15s" onmouseover="this.style.opacity='0.85'" onmouseout="this.style.opacity='1'">Assemble & Edit</button>` : `<svg width="16" height="16" fill="none" stroke="${isActive ? '#ff9f43' : 'var(--text-muted)'}" stroke-width="1.5" viewBox="0 0 24 24" style="flex-shrink:0;opacity:${isActive ? '0.8' : '0.4'}"><path d="M9 18l6-6-6-6"/></svg>`}
        </div>
      </div>`;
    }).join('');
  } catch (e) {
    container.innerHTML = `<p style="text-align:center;color:var(--coral);font-size:11px;padding:16px">Failed to load history</p>`;
  }
}

async function assetsLoadFromHistory(projectId) {
  try {
    const data = await api(`/api/assets/project/${encodeURIComponent(projectId)}`);
    if (!data) throw new Error('No data returned');

    // Load corresponding scene data if available
    let sceneData = null;
    try {
      sceneData = await api(`/api/scenes/${encodeURIComponent(projectId)}`);
    } catch (e) {
      // Scene data might not exist — that's fine
    }

    if (sceneData && sceneData.scenes && sceneData.scenes.length) {
      STATE.assetsSceneData = sceneData;
    } else {
      // Build minimal scene data from the asset project
      const scenes = [];
      const prompts = data.prompts || {};
      for (const [sceneNum, sceneInfo] of Object.entries(data.scenes)) {
        scenes.push({
          index: parseInt(sceneNum),
          title: `Scene ${sceneNum}`,
          type_of_scene: 'image',
          image_prompt: prompts[sceneNum] || '',
          duration: 3,
          text_content: null,
        });
      }
      scenes.sort((a, b) => a.index - b.index);
      STATE.assetsSceneData = { project_id: projectId, scenes };
    }
    setModuleBadge('assets', projectId);

    // Populate asset statuses from the project data
    // Metadata keys are sequential (0,1,2...) but STATE.assetStatuses must be
    // keyed by scene.index (raw segment index, e.g. 0,1,3,4,6,8,9,11,13).
    STATE.assetStatuses = {};
    STATE.assetSelected = {};
    const scenes = STATE.assetsSceneData.scenes;
    for (const [seqNum, sceneInfo] of Object.entries(data.scenes)) {
      const pos = parseInt(seqNum);
      const scene = scenes[pos];
      const idx = scene ? scene.index : pos;  // map sequential → scene.index
      const localFiles = sceneInfo.files_on_disk
        ? sceneInfo.files_on_disk.map(f => f.url)
        : sceneInfo.local_files || [];
      const ss = data.scene_statuses?.[seqNum];

      STATE.assetStatuses[idx] = {
        status: localFiles.length > 0 ? 'ready' : (ss?.status || 'pending'),
        urls: sceneInfo.source_urls || ss?.urls || [],
        local_files: localFiles,
        editedPrompt: null,
      };
    }

    renderAssetsFromScenes();
    loadAssetsHistory(); // refresh to highlight active row
    toast(`Loaded project ${projectId} (${Object.keys(data.scenes).length} scenes)`);
  } catch (e) {
    toast(e.message || 'Failed to load project', 'error');
  }
}

// ---- Auto-Assemble & Send to Editor ----

async function assetsAssembleFromHistory(projectId) {
  try {
    toast('Loading project...', 'info');
    await assetsLoadFromHistory(projectId);
    await autoAssembleAndSendToEditor();
    switchPage('editor');
  } catch (e) {
    toast(e.message || 'Failed to assemble', 'error');
  }
}

async function autoAssembleAndSendToEditor() {
  if (!STATE.assetsSceneData) {
    toast('No scenes loaded', 'error');
    return;
  }
  const projectId = STATE.assetsSceneData.project_id;

  // Fetch fresh asset data from API — bypasses fragile STATE.assetStatuses mapping.
  // The API scans disk and returns files_on_disk with correct URLs for every scene.
  let assetsData;
  try {
    assetsData = await api(`/api/assets/project/${encodeURIComponent(projectId)}`);
  } catch (e) {
    // Fallback: build from STATE if API fails
    assetsData = { scenes: {}, scene_statuses: {} };
    if (STATE.assetsSceneData.scenes) {
      STATE.assetsSceneData.scenes.forEach((scene, i) => {
        const st = STATE.assetStatuses[scene.index] || {};
        assetsData.scenes[String(i)] = {
          files_on_disk: (st.local_files || []).map(f => ({ url: f })),
        };
        assetsData.scene_statuses[String(i)] = {
          status: st.status || 'pending',
          local_files: st.local_files || [],
        };
      });
    }
  }

  // Build staged timeline so the editor opens directly (no import panel).
  const sourceScenes = STATE.assetsSceneData.scenes || [];
  let t = 0;
  const stagedScenes = sourceScenes.map((scene, i) => {
    const assetScene = assetsData?.scenes?.[String(i)] || {};
    const filesOnDisk = Array.isArray(assetScene.files_on_disk) ? assetScene.files_on_disk : [];
    const firstImage = filesOnDisk.length > 0 ? filesOnDisk[0].url : '';
    const duration = scene.duration || 3;
    const row = {
      scene_id: i,
      type: scene.type_of_scene || scene.type || 'image',
      image_prompt: scene.image_prompt || '',
      text_content: scene.text_content || null,
      duration,
      timestamp: t,
      image_url: firstImage,
      visual_fx: scene.visual_fx || 'none',
      narrative_role: scene.narrative_role || scene.role || '',
      status: firstImage ? 'done' : 'pending',
    };
    t += duration;
    return row;
  });

  const stagedTimeline = {
    project_id: projectId,
    project_name: projectId,
    style: STATE.assetsSceneData?.style || '',
    source_folder: STATE.assetsSceneData?.source_folder || '',
    total_duration: stagedScenes.reduce((sum, s) => sum + (s.duration || 0), 0),
    scene_count: stagedScenes.length,
    staged_at: new Date().toISOString(),
    scenes: stagedScenes,
  };

  // Add audio if available from current source folder.
  const sf = STATE.assetsSceneData?.source_folder;
  if (sf) {
    try {
      const audioRes = await api(`/api/scenes/audio/${encodeURIComponent(sf)}`);
      if (audioRes?.url) {
        stagedTimeline.audio = {
          url: audioRes.url,
          source_file: audioRes.source_file || '',
          duration: audioRes.duration_seconds || 0,
        };
      }
    } catch (_) { /* optional */ }
  }

  sessionStorage.setItem('sts-staged-timeline', JSON.stringify(stagedTimeline));

  // Keep bridge payload for compatibility with the older editor flow.
  const storeData = {
    ...STATE.assetsSceneData,
    _autoAssemble: true,
    _assetsData: assetsData,
  };
  localStorage.setItem('sts-editor-scenes', JSON.stringify(storeData));
  // Store source_folder for caption scoping by the parent shell
  if (STATE.assetsSceneData?.source_folder) {
    localStorage.setItem('sts-editor-source-folder', STATE.assetsSceneData.source_folder);
  }
  // Clear stale captions so they auto-regenerate from current alignment
  localStorage.removeItem('sts-editor-captions');

  // Force a fresh editor iframe boot so stale modal/UI state cannot persist.
  STATE.editorLoaded = false;
  const iframe = document.getElementById('editor-iframe');
  if (iframe) {
    iframe.style.display = 'none';
    iframe.src = '';
  }

  switchPage('editor');
  toast('Auto-assembling timeline...', 'info');
}

// ---- Audio Player ----

let _assetsAudio = null;
let _assetsAudioFrame = null;

async function assetsLoadAudio() {
  assetsStopAudio();
  const bar = $('#assets-audio-bar');
  if (!bar) return;

  const sf = STATE.assetsSceneData?.source_folder;
  if (!sf) { bar.style.display = 'none'; return; }

  let url = null;
  // Try to resolve from alignment state first
  if (STATE.segmenterAlignment?.folder === sf && STATE.segmenterAlignment?.source_file) {
    url = `/output/alignments/${sf}/${STATE.segmenterAlignment.source_file}`;
  } else if (STATE.alignResult?.folder === sf && STATE.alignResult?.source_file) {
    url = `/output/alignments/${sf}/${STATE.alignResult.source_file}`;
  } else if (STATE.alignHistory) {
    const match = STATE.alignHistory.find(h => h.folder === sf);
    if (match) url = `/output/alignments/${match.folder}/${match.source_file}`;
  }

  // Fallback: ask the API
  if (!url) {
    try {
      const res = await api(`/api/scenes/audio/${encodeURIComponent(sf)}`);
      if (res?.url) url = res.url;
    } catch { /* ignore */ }
  }

  if (!url) { bar.style.display = 'none'; return; }

  _assetsAudio = new Audio(url);
  stsAudioRegister('Assets', _assetsAudio);
  _assetsAudio.addEventListener('loadedmetadata', () => {
    bar.style.display = '';
    _assetsAudioUpdateTime();
    _assetsAudioRenderSceneMarkers();
  });
  _assetsAudio.addEventListener('ended', () => _assetsAudioReset());
  _assetsAudio.addEventListener('error', () => { bar.style.display = 'none'; });
}

function assetsStopAudio() {
  if (_assetsAudioFrame) { cancelAnimationFrame(_assetsAudioFrame); _assetsAudioFrame = null; }
  if (_assetsAudio) { _assetsAudio.pause(); _assetsAudio = null; }
  const bar = $('#assets-audio-bar');
  if (bar) bar.style.display = 'none';
}

function assetsToggleAudio() {
  if (!_assetsAudio) return;
  if (_assetsAudio.paused) {
    _assetsAudio.play();
    _assetsAudioAnimate();
    $('#assets-audio-icon').innerHTML = '<rect x="5" y="3" width="4" height="18" rx="1"/><rect x="15" y="3" width="4" height="18" rx="1"/>';
  } else {
    _assetsAudio.pause();
    if (_assetsAudioFrame) { cancelAnimationFrame(_assetsAudioFrame); _assetsAudioFrame = null; }
    $('#assets-audio-icon').innerHTML = '<polygon points="5,3 19,12 5,21"/>';
  }
}

function assetsAudioSeek(e) {
  if (!_assetsAudio || !_assetsAudio.duration) return;
  const rect = e.currentTarget.getBoundingClientRect();
  const pct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
  _assetsAudio.currentTime = pct * _assetsAudio.duration;
  _assetsAudioUpdateUI();
}

function _assetsAudioAnimate() {
  if (!_assetsAudio || _assetsAudio.paused) return;
  _assetsAudioUpdateUI();
  _assetsAudioFrame = requestAnimationFrame(_assetsAudioAnimate);
}

function _assetsAudioUpdateUI() {
  if (!_assetsAudio || !_assetsAudio.duration) return;
  const pct = (_assetsAudio.currentTime / _assetsAudio.duration) * 100;
  const progress = $('#assets-audio-progress');
  const playhead = $('#assets-audio-playhead');
  if (progress) progress.style.width = pct + '%';
  if (playhead) { playhead.style.left = pct + '%'; playhead.style.opacity = '1'; }
  _assetsAudioUpdateTime();
  _assetsAudioHighlightScene();
}

function _assetsAudioUpdateTime() {
  const el = $('#assets-audio-time');
  if (!el || !_assetsAudio) return;
  const cur = _assetsAudio.currentTime || 0;
  const dur = _assetsAudio.duration || 0;
  el.textContent = `${_fmtTime(cur)} / ${_fmtTime(dur)}`;
}

function _fmtTime(s) {
  if (!s || !isFinite(s)) return '0:00';
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, '0')}`;
}

function _assetsAudioReset() {
  if (_assetsAudioFrame) { cancelAnimationFrame(_assetsAudioFrame); _assetsAudioFrame = null; }
  $('#assets-audio-icon').innerHTML = '<polygon points="5,3 19,12 5,21"/>';
  const progress = $('#assets-audio-progress');
  const playhead = $('#assets-audio-playhead');
  if (progress) progress.style.width = '0%';
  if (playhead) playhead.style.opacity = '0';
  _assetsAudioUpdateTime();
  // Remove highlight from all cards
  document.querySelectorAll('.asset-card').forEach(c => c.style.boxShadow = '');
}

function _assetsAudioRenderSceneMarkers() {
  const container = $('#assets-audio-scenes');
  if (!container || !_assetsAudio?.duration || !STATE.assetsSceneData?.scenes) return;

  const scenes = STATE.assetsSceneData.scenes;
  const audioDur = _assetsAudio.duration;
  const typeColors = { video: '174,58%,55%', image: '263,68%,65%' };

  // Build timings from scene durations
  let t = 0;
  const timings = scenes.map(s => {
    const start = t;
    const dur = s.duration || 2.5;
    t += dur;
    return { start, end: t, scene: s };
  });
  // Normalize against scene total so markers always fill the full bar
  const totalDur = t || 1;

  container.innerHTML = timings.map((tm, i) => {
    const left = (tm.start / totalDur * 100).toFixed(2);
    const width = Math.max((tm.end - tm.start) / totalDur * 100, 0.3).toFixed(2);
    const hue = typeColors[tm.scene.type_of_scene] || '210,20%,45%';
    const label = (tm.scene.title || '').split(' ').slice(0, 2).join(' ');
    return `<div data-scene-idx="${i}" style="position:absolute;left:${left}%;width:${width}%;height:100%;background:hsla(${hue},0.35);display:flex;align-items:center;justify-content:center;overflow:hidden;border-right:1px solid var(--bg-darkest)">
      <span style="font-size:7px;color:rgba(255,255,255,0.6);font-family:'JetBrains Mono',monospace;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;padding:0 3px">${esc(label)}</span>
    </div>`;
  }).join('');
}

function _assetsAudioHighlightScene() {
  if (!_assetsAudio || !STATE.assetsSceneData?.scenes) return;
  const scenes = STATE.assetsSceneData.scenes;
  const ct = _assetsAudio.currentTime;

  // Find which scene is playing based on cumulative durations
  let t = 0;
  let activeIdx = -1;
  for (let i = 0; i < scenes.length; i++) {
    const dur = scenes[i].duration || 2.5;
    if (ct >= t && ct < t + dur) { activeIdx = i; break; }
    t += dur;
  }

  // Highlight active card, remove from others
  scenes.forEach((s, i) => {
    const card = document.getElementById(`asset-card-${s.index}`);
    if (!card) return;
    if (i === activeIdx) {
      card.style.boxShadow = 'inset 0 0 0 1px var(--accent), 0 0 12px rgba(78,205,196,0.15)';
    } else {
      card.style.boxShadow = '';
    }
  });
}

