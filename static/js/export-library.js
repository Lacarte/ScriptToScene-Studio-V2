/* ================================================================
   ScriptToScene Studio - Export Library
   ================================================================ */

const _expLibState = {
  loaded: false,
  items: [],
};

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
  const list = $('#export-library-list');
  const count = $('#export-library-count');
  if (!list || !count) return;

  const items = _expLibState.items || [];
  count.textContent = `${items.length} video${items.length !== 1 ? 's' : ''}`;

  if (!items.length) {
    list.innerHTML = `
      <section class="card p-6">
        <p style="text-align:center;font-size:13px;color:var(--text-secondary)">No exported videos found yet.</p>
      </section>
    `;
    return;
  }

  list.innerHTML = `
    <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:14px">
      ${items.map((item, idx) => `
        <article class="card" style="overflow:hidden">
          <div style="background:var(--bg-darkest);border-bottom:1px solid var(--border)">
            <video controls preload="none" playsinline data-src="${esc(item.preview_url)}"
              style="width:100%;display:block;aspect-ratio:9/16;max-height:360px;background:black"></video>
          </div>
          <div style="padding:12px 12px 10px">
            <p style="font-size:13px;color:var(--text);font-weight:600;margin:0 0 6px;word-break:break-word">${esc(item.project_id || item.video_name)}</p>
            <p class="font-mono" style="font-size:10px;color:var(--text-muted);margin:0 0 2px">File: ${esc(item.video_name || '')}</p>
            <p class="font-mono" style="font-size:10px;color:var(--text-muted);margin:0 0 2px">Folder: ${esc(item.folder_relpath || '.')}</p>
            <p class="font-mono" style="font-size:10px;color:var(--text-muted);margin:0 0 10px">${_expLibFmtBytes(item.size_bytes)} - ${timeAgo(item.modified_at)}</p>

            <div style="display:flex;gap:8px;flex-wrap:wrap">
              <button class="action-btn hover-accent" onclick="expLibDownloadVideo(${idx}, this)"
                style="padding:7px 10px;font-size:11px;display:inline-flex;align-items:center">
                Download Video
              </button>
              ${item.zip_download_url
                ? `<button class="action-btn hover-accent" onclick="expLibDownloadZip(${idx}, this)"
                style="padding:7px 10px;font-size:11px;display:inline-flex;align-items:center;border-color:var(--accent);color:var(--accent)">
                Download Project ZIP
              </button>`
                : `<span class="action-btn" style="padding:7px 10px;font-size:11px;opacity:.45;cursor:not-allowed">ZIP Not Available</span>`}
            </div>
          </div>
        </article>
      `).join('')}
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
