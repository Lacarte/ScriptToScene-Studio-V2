/* ================================================================
   ScriptToScene Studio - Export Library
   ================================================================ */

const _expLibState = {
  loaded: false,
  items: [],
  filtered: [],   // items after filter + sort applied
};

function _expLibStopOtherVideos(activeVideo) {
  if (typeof window.stsAudioStopAll === 'function') {
    window.stsAudioStopAll(activeVideo);
  }
  const list = document.getElementById('export-library-list');
  if (!list) return;
  const videos = list.querySelectorAll('video');
  videos.forEach(video => {
    if (video === activeVideo) return;
    if (!video.paused) video.pause();
    video.currentTime = 0;
  });
}

function _expLibBindSinglePlayback() {
  const list = document.getElementById('export-library-list');
  if (!list) return;
  const videos = list.querySelectorAll('video');
  videos.forEach(video => {
    video.addEventListener('play', () => _expLibStopOtherVideos(video));
  });
}

function _expLibFmtBytes(bytes) {
  const n = Number(bytes || 0);
  if (!Number.isFinite(n) || n <= 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  let value = n;
  let idx = 0;
  while (value >= 1024 && idx < units.length - 1) {
    value /= 1024;
    idx += 1;
  }
  return `${value.toFixed(value >= 100 || idx === 0 ? 0 : 1)} ${units[idx]}`;
}

// Duration formatter: 93.5 → "1:33"
function _expLibFmtDuration(sec) {
  const s = Number(sec || 0);
  if (!s || s <= 0) return '';
  const m = Math.floor(s / 60);
  const ss = Math.floor(s % 60);
  return m > 0 ? `${m}:${String(ss).padStart(2, '0')}` : `0:${String(ss).padStart(2, '0')}`;
}

// Ratio label helper: "1080:1920" → "9:16"
function _expLibRatioLabel(ratio) {
  if (!ratio) return '';
  const [w, h] = ratio.split(':').map(Number);
  if (!w || !h) return ratio;
  // Common ratios
  const r = w / h;
  if (Math.abs(r - 9 / 16) < 0.02) return '9:16';
  if (Math.abs(r - 16 / 9) < 0.02) return '16:9';
  if (Math.abs(r - 1) < 0.02) return '1:1';
  if (Math.abs(r - 4 / 5) < 0.02) return '4:5';
  return `${w}:${h}`;
}

// Style label using scene templates if available
function _expLibStyleLabel(styleId) {
  if (!styleId) return '';
  if (typeof _scnStyleLabel === 'function') {
    const name = _scnStyleLabel(styleId);
    if (name) return name;
  }
  // Fallback: title-case the id
  return styleId.replace(/[_-]/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function _expLibStyleColor(styleId) {
  if (!styleId) return 'var(--text-muted)';
  if (typeof _scnStyleColor === 'function') return _scnStyleColor(styleId);
  return 'var(--text-muted)';
}

// --- Toolbar: populate filter dropdowns ---

function _expLibPopulateFilters() {
  const items = _expLibState.items || [];
  const toolbar = $('#explib-toolbar');
  if (toolbar) toolbar.style.display = items.length ? 'flex' : 'none';

  // Styles
  const styleSel = $('#explib-filter-style');
  if (styleSel) {
    const styles = [...new Set(items.map(i => i.style).filter(Boolean))].sort();
    const cur = styleSel.value;
    styleSel.innerHTML = '<option value="">All styles</option>' +
      styles.map(s => `<option value="${esc(s)}">${esc(_expLibStyleLabel(s))}</option>`).join('');
    if (cur && styles.includes(cur)) styleSel.value = cur;
  }

  // Ratios — prefer video_ratio (actual file dimensions), fall back to ratio (export config)
  const ratioSel = $('#explib-filter-ratio');
  if (ratioSel) {
    const ratios = [...new Set(items.map(i => _expLibRatioLabel(i.video_ratio || i.ratio)).filter(Boolean))].sort();
    const cur = ratioSel.value;
    ratioSel.innerHTML = '<option value="">All ratios</option>' +
      ratios.map(r => `<option value="${esc(r)}">${esc(r)}</option>`).join('');
    if (cur && ratios.includes(cur)) ratioSel.value = cur;
  }
}

// --- Filter + Sort ---

function _expLibApplyFilters() {
  const items = _expLibState.items || [];

  const sortVal = ($('#explib-sort') || {}).value || 'date-desc';
  const styleFilter = ($('#explib-filter-style') || {}).value || '';
  const ratioFilter = ($('#explib-filter-ratio') || {}).value || '';
  const durationFilter = ($('#explib-filter-duration') || {}).value || '';

  let filtered = items.slice();

  // Filter by style
  if (styleFilter) {
    filtered = filtered.filter(i => i.style === styleFilter);
  }

  // Filter by ratio (use video_ratio from actual file, fallback to config ratio)
  if (ratioFilter) {
    filtered = filtered.filter(i => _expLibRatioLabel(i.video_ratio || i.ratio) === ratioFilter);
  }

  // Filter by duration range
  if (durationFilter) {
    const [minStr, maxStr] = durationFilter.split('-');
    const min = Number(minStr) || 0;
    const max = maxStr ? Number(maxStr) : Infinity;
    filtered = filtered.filter(i => {
      const d = i.duration || 0;
      return d >= min && d < max;
    });
  }

  // Sort
  switch (sortVal) {
    case 'date-asc':
      filtered.sort((a, b) => (a.modified_at || '').localeCompare(b.modified_at || ''));
      break;
    case 'duration-desc':
      filtered.sort((a, b) => (b.duration || 0) - (a.duration || 0));
      break;
    case 'duration-asc':
      filtered.sort((a, b) => (a.duration || 0) - (b.duration || 0));
      break;
    case 'size-desc':
      filtered.sort((a, b) => (b.size_bytes || 0) - (a.size_bytes || 0));
      break;
    case 'size-asc':
      filtered.sort((a, b) => (a.size_bytes || 0) - (b.size_bytes || 0));
      break;
    default: // date-desc
      filtered.sort((a, b) => (b.modified_at || '').localeCompare(a.modified_at || ''));
  }

  _expLibState.filtered = filtered;
  _expLibRenderGrid();
}

// --- Rendering ---

function _expLibRenderLoading() {
  const list = $('#export-library-list');
  const count = $('#export-library-count');
  if (count) count.textContent = 'Loading...';
  if (!list) return;
  list.innerHTML = `
    <section class="card p-5">
      <p class="font-mono" style="font-size:12px;color:var(--text-muted);text-align:center">Loading export library...</p>
    </section>
  `;
}

function _expLibRenderError(msg) {
  const list = $('#export-library-list');
  const count = $('#export-library-count');
  if (count) count.textContent = '0 videos';
  if (!list) return;
  list.innerHTML = `
    <section class="card p-5" style="border-color:rgba(255,107,107,0.35)">
      <p style="font-size:13px;color:var(--coral);text-align:center">${esc(msg || 'Failed to load export library')}</p>
    </section>
  `;
}

function _expLibRender() {
  const count = $('#export-library-count');
  const items = _expLibState.items || [];
  if (count) count.textContent = `${items.length} video${items.length !== 1 ? 's' : ''}`;

  _expLibPopulateFilters();
  _expLibRenderStats();
  _expLibApplyFilters();
}

function _expLibRenderStats() {
  const el = $('#explib-stats');
  if (!el) return;
  const items = _expLibState.items || [];
  if (!items.length) { el.style.display = 'none'; return; }

  const now = Date.now();
  const DAY = 86400000;

  // Total content duration
  const totalDur = items.reduce((s, i) => s + (i.duration || 0), 0);
  // Total file size
  const totalSize = items.reduce((s, i) => s + (i.size_bytes || 0), 0);

  // Exports per time period
  const today = items.filter(i => i.modified_at && (now - new Date(i.modified_at).getTime()) < DAY).length;
  const week = items.filter(i => i.modified_at && (now - new Date(i.modified_at).getTime()) < 7 * DAY).length;
  const month = items.filter(i => i.modified_at && (now - new Date(i.modified_at).getTime()) < 30 * DAY).length;

  // Most used style
  const styleCounts = {};
  items.forEach(i => { if (i.style) styleCounts[i.style] = (styleCounts[i.style] || 0) + 1; });
  const topStyle = Object.entries(styleCounts).sort((a, b) => b[1] - a[1])[0];
  const topStyleLabel = topStyle ? _expLibStyleLabel(topStyle[0]) : '—';
  const topStyleColor = topStyle ? _expLibStyleColor(topStyle[0]) : 'var(--text-muted)';
  const topStyleCount = topStyle ? topStyle[1] : 0;

  // Most used ratio
  const ratioCounts = {};
  items.forEach(i => {
    const r = _expLibRatioLabel(i.video_ratio || i.ratio);
    if (r) ratioCounts[r] = (ratioCounts[r] || 0) + 1;
  });
  const topRatio = Object.entries(ratioCounts).sort((a, b) => b[1] - a[1])[0];

  // Days since first export
  const dates = items.map(i => new Date(i.modified_at).getTime()).filter(Boolean);
  const firstExport = dates.length ? Math.min(...dates) : now;
  const daysSinceFirst = Math.max(1, Math.ceil((now - firstExport) / DAY));
  const avgPerWeek = items.length >= 2 ? (items.length / (daysSinceFirst / 7)).toFixed(1) : '—';

  // Streak: consecutive days with at least one export (counting back from today)
  const daySet = new Set();
  items.forEach(i => {
    if (i.modified_at) {
      const d = new Date(i.modified_at);
      daySet.add(`${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`);
    }
  });
  let streak = 0;
  for (let d = 0; d < 365; d++) {
    const dt = new Date(now - d * DAY);
    const key = `${dt.getFullYear()}-${dt.getMonth()}-${dt.getDate()}`;
    if (daySet.has(key)) { streak++; } else if (d > 0) break;
  }

  const sep = '<span style="opacity:0.15;margin:0 2px">|</span>';
  const stat = (label, value, color = 'var(--text)') =>
    `<div style="display:flex;flex-direction:column;align-items:center;gap:2px;min-width:70px">
      <span style="font-size:18px;font-weight:700;color:${color};line-height:1">${value}</span>
      <span style="font-size:9px;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.05em">${label}</span>
    </div>`;

  el.style.display = '';
  el.innerHTML = `
    <section class="card p-4 mb-4">
      <div style="display:flex;align-items:center;gap:16px;flex-wrap:wrap;justify-content:space-around;font-family:'JetBrains Mono',monospace">
        ${stat('Total', items.length, '#4ECDC4')}
        ${stat('Today', today, today > 0 ? '#26DE81' : 'var(--text-muted)')}
        ${stat('This Week', week, '#FFB347')}
        ${stat('This Month', month, 'var(--text-secondary)')}
        ${stat('Avg / Week', avgPerWeek, 'var(--text-secondary)')}
        ${stat('Streak', streak > 0 ? streak + 'd' : '—', streak > 0 ? '#FF6B6B' : 'var(--text-muted)')}
        ${stat('Duration', _expLibFmtDuration(totalDur) || '—', '#A78BFA')}
        ${stat('Size', _expLibFmtBytes(totalSize), 'var(--text-secondary)')}
        ${topStyle ? stat('Top Style', topStyleLabel, topStyleColor) : ''}
        ${topRatio ? stat('Top Ratio', topRatio[0], '#A78BFA') : ''}
      </div>
    </section>`;
}

function _expLibRenderGrid() {
  const list = $('#export-library-list');
  if (!list) return;

  const items = _expLibState.filtered || [];
  const total = (_expLibState.items || []).length;

  // Update filter count
  const filterCount = $('#explib-filter-count');
  if (filterCount) {
    filterCount.textContent = items.length < total ? `Showing ${items.length} of ${total}` : '';
  }

  if (!items.length) {
    list.innerHTML = `
      <section class="card p-6">
        <p style="text-align:center;font-size:13px;color:var(--text-secondary)">${total > 0 ? 'No videos match the current filters.' : 'No exported videos found yet.'}</p>
      </section>
    `;
    return;
  }

  // Map filtered items back to their original index for download handlers
  const allItems = _expLibState.items || [];

  list.innerHTML = `
    <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:14px">
      ${items.map(item => {
        const origIdx = allItems.indexOf(item);
        const styleLabel = _expLibStyleLabel(item.style);
        const styleColor = _expLibStyleColor(item.style);
        const ratioLabel = _expLibRatioLabel(item.video_ratio || item.ratio);
        const sceneCount = item.scene_count || 0;
        const durLabel = _expLibFmtDuration(item.duration);

        // Build meta line with bar separators and colors
        const metaParts = [];
        if (sceneCount) metaParts.push(`<span style="color:#4ECDC4">${sceneCount} scene${sceneCount !== 1 ? 's' : ''}</span>`);
        if (durLabel) metaParts.push(`<span style="color:#FFB347">${durLabel}</span>`);
        metaParts.push(`<span style="color:var(--text-secondary)">${_expLibFmtBytes(item.size_bytes)}</span>`);
        metaParts.push(`<span>${timeAgo(item.modified_at)}</span>`);
        if (ratioLabel) metaParts.push(`<span style="color:#A78BFA">${esc(ratioLabel)}</span>`);
        if (styleLabel) metaParts.push(`<span style="display:inline-flex;align-items:center;gap:3px"><span style="width:6px;height:6px;border-radius:50%;background:${styleColor};display:inline-block"></span><span style="color:${styleColor};font-weight:600">${esc(styleLabel)}</span></span>`);
        const metaHtml = metaParts.join('<span style="opacity:0.3;margin:0 3px">/</span>');

        return `
        <article class="card" style="overflow:hidden">
          <div style="background:var(--bg-darkest);border-bottom:1px solid var(--border)">
            <video controls preload="none" playsinline data-src="${esc(item.preview_url)}"
              style="width:100%;display:block;aspect-ratio:9/16;max-height:360px;background:black"></video>
          </div>
          <div style="padding:12px 12px 10px">
            <p style="font-size:13px;color:var(--text);font-weight:600;margin:0 0 4px;word-break:break-word">${esc(item.project_id || item.video_name)}</p>
            <p class="font-mono" style="font-size:10px;color:var(--text-muted);margin:0 0 2px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(item.video_name || '')}">${esc(item.video_name || '')}</p>
            <div class="font-mono" style="font-size:10px;color:var(--text-muted);margin:4px 0 10px;display:flex;align-items:center;gap:0;flex-wrap:wrap;line-height:1.8">${metaHtml}</div>

            <div style="display:flex;gap:8px;flex-wrap:wrap">
              <button class="action-btn hover-accent" onclick="expLibDownloadVideo(${origIdx}, this)"
                style="padding:7px 10px;font-size:11px;display:inline-flex;align-items:center">
                Download Video
              </button>
              ${item.zip_download_url
                ? `<button class="action-btn hover-accent" onclick="expLibDownloadZip(${origIdx}, this)"
                style="padding:7px 10px;font-size:11px;display:inline-flex;align-items:center;border-color:var(--accent);color:var(--accent)">
                Download Project ZIP
              </button>`
                : `<span class="action-btn" style="padding:7px 10px;font-size:11px;opacity:.45;cursor:not-allowed">ZIP Not Available</span>`}
            </div>
          </div>
        </article>`;
      }).join('')}
    </div>
  `;

  // Lazy-load videos as they scroll into view
  const observer = new IntersectionObserver((entries, obs) => {
    for (const entry of entries) {
      if (entry.isIntersecting) {
        const video = entry.target;
        video.src = video.dataset.src;
        video.preload = 'metadata';
        obs.unobserve(video);
      }
    }
  }, { rootMargin: '200px' });
  list.querySelectorAll('video[data-src]').forEach(v => observer.observe(v));
  _expLibBindSinglePlayback();
}

async function loadExportLibrary(force = false) {
  if (_expLibState.loaded && !force) {
    _expLibRender();
    return;
  }

  _expLibRenderLoading();
  try {
    const data = await api('/api/export/library');
    _expLibState.items = (data && data.items) || [];
    _expLibState.loaded = true;
    _expLibRender();
  } catch (e) {
    _expLibRenderError(e.message);
  }
}

async function expLibDownloadVideo(index, btn) {
  const item = (_expLibState.items || [])[index];
  if (!item || !item.video_download_url) {
    toast('Video download unavailable', 'error');
    return;
  }
  const old = btn ? btn.textContent : '';
  if (btn) { btn.disabled = true; btn.textContent = 'Downloading...'; }
  try {
    const result = await downloadFileFromApi(item.video_download_url, item.video_name || 'export.mp4');
    const sizeMB = (result.sizeBytes / 1024 / 1024).toFixed(1);
    toast(`Video downloaded (${sizeMB} MB)`, 'success');
  } catch (e) {
    toast('Video download failed: ' + e.message, 'error');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = old || 'Download Video'; }
  }
}

async function expLibDownloadZip(index, btn) {
  const item = (_expLibState.items || [])[index];
  if (!item || !item.zip_download_url) {
    toast('ZIP download unavailable', 'error');
    return;
  }
  const old = btn ? btn.textContent : '';
  if (btn) { btn.disabled = true; btn.textContent = 'Downloading...'; }
  try {
    const result = (item.project_id && item.zip_source !== 'file')
      ? await downloadProjectZip(item.project_id)
      : await downloadFileFromApi(item.zip_download_url, `${item.project_id || 'project'}.zip`);
    const sizeMB = (result.sizeBytes / 1024 / 1024).toFixed(1);
    toast(`Project ZIP downloaded (${sizeMB} MB)`, 'success');
  } catch (e) {
    toast('ZIP download failed: ' + e.message, 'error');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = old || 'Download Project ZIP'; }
  }
}
