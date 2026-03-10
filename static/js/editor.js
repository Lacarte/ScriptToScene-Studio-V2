/* ================================================================
   ScriptToScene Studio — Editor Module (Timeline Editor iframe)
   ================================================================ */

function initEditorIframe() {
  const iframe = $('#editor-iframe');
  const targetSrc = '/timeline-editor/editor.html';
  if (STATE.editorLoaded && iframe.src.includes(targetSrc)) return;
  STATE.editorLoaded = false;
  iframe.style.display = 'none';
  const loadingEl = $('#editor-loading');
  // Restore spinner in case it was replaced with empty-state message
  loadingEl.innerHTML = `
    <div style="text-align:center">
      <div style="width:36px;height:36px;border:2.5px solid rgba(255,255,255,0.08);border-top-color:var(--accent);border-radius:50%;animation:spin 0.8s linear infinite;margin:0 auto 16px"></div>
      <p style="color:var(--text-secondary)">Loading Timeline Editor...</p>
      <p style="font-size:11px;margin-top:4px;color:var(--text-muted);opacity:0.7">Make sure the editor server is running</p>
    </div>`;
  loadingEl.style.display = 'flex';
  // Cache-bust to force reload+onload when src is already set
  iframe.src = targetSrc + '?t=' + Date.now();
  iframe.onload = () => {
    STATE.editorLoaded = true;
    $('#editor-loading').style.display = 'none';
    iframe.style.display = 'block';

    const entrySource = sessionStorage.getItem('sts-editor-entry-source') || 'internal';

    // Send scenes data only for internal flows (Auto-Assemble / Send to Editor).
    // When opened directly from menu, let the editor decide via no-data/import UI.
    const scenesData = localStorage.getItem('sts-editor-scenes');
    if (scenesData && entrySource !== 'menu') {
      try {
        iframe.contentWindow.postMessage({
          type: 'load-scenes',
          data: JSON.parse(scenesData),
        }, '*');
      } catch (e) { console.error('Editor postMessage:', e); }
    }

    // Determine current project's source_folder for caption scoping
    let currentSourceFolder = '';
    try {
      const scenes = JSON.parse(localStorage.getItem('sts-editor-scenes') || '{}');
      currentSourceFolder = scenes.source_folder || '';
    } catch { /* ignore */ }
    if (!currentSourceFolder) {
      try {
        const staged = JSON.parse(sessionStorage.getItem('staged_timeline') || '{}');
        currentSourceFolder = staged.source_folder || '';
      } catch { /* ignore */ }
    }

    // Send captions data if available and matching current project
    const captionsData = localStorage.getItem('sts-editor-captions');
    if (captionsData) {
      try {
        const capData = JSON.parse(captionsData);
        // Skip stale captions from a different project
        if (currentSourceFolder && capData.source_folder && capData.source_folder !== currentSourceFolder) {
          console.log('Skipping stale captions (source_folder mismatch):', capData.source_folder, '!=', currentSourceFolder);
          localStorage.removeItem('sts-editor-captions');
          _editorAutoGenerateCaptions(iframe, currentSourceFolder);
        } else {
          iframe.contentWindow.postMessage({
            type: 'load-captions',
            data: capData,
          }, '*');
        }
      } catch (e) { console.error('Editor captions postMessage:', e); }
    } else {
      // No captions stored — try to auto-generate from alignment data
      _editorAutoGenerateCaptions(iframe, currentSourceFolder);
    }
  };
  iframe.onerror = () => {
    $('#editor-loading').innerHTML = `
      <div style="text-align:center">
        <svg width="40" height="40" fill="none" stroke="var(--coral)" stroke-width="1.5" viewBox="0 0 24 24" style="margin:0 auto 12px;opacity:0.7">
          <circle cx="12" cy="12" r="10"/><path d="M15 9l-6 6M9 9l6 6"/>
        </svg>
        <p style="color:var(--coral)">Failed to load Timeline Editor</p>
        <p style="font-size:11px;margin-top:4px;color:var(--text-muted)">Ensure the editor files are served at /timeline-editor/</p>
      </div>`;
  };
}

/**
 * Auto-generate captions from alignment data and send to the editor iframe.
 * Tries STATE.alignResult first, then falls back to fetching the most recent alignment from history.
 */
async function _editorAutoGenerateCaptions(iframe, projectSourceFolder = '') {
  try {
    let alignment = null;
    let sourceFolder = '';

    // 1) Try current alignment result (only if it matches the current project)
    if (STATE.alignResult && STATE.alignResult.alignment && STATE.alignResult.alignment.length) {
      const folder = STATE.alignResult.folder || '';
      if (!projectSourceFolder || !folder || folder === projectSourceFolder) {
        alignment = STATE.alignResult.alignment;
        sourceFolder = folder;
      }
    }

    // 2) Try captionAlignment (set by captions module)
    if (!alignment && STATE.captionAlignment) {
      const folder = STATE.captionAlignment.folder || '';
      if (!projectSourceFolder || !folder || folder === projectSourceFolder) {
        alignment = STATE.captionAlignment.word_alignment || STATE.captionAlignment.alignment;
        sourceFolder = folder;
      }
    }

    // 3) Fallback: fetch alignment from history matching the current project
    if (!alignment) {
      try {
        const history = await api('/api/timing/history');
        if (history && history.length) {
          // Find alignment matching the current project's source_folder
          const match = projectSourceFolder
            ? history.find(h => h.folder === projectSourceFolder)
            : history[0];
          if (match) {
            alignment = match.word_alignment;
            sourceFolder = match.folder || '';
          }
        }
      } catch { /* ignore */ }
    }

    if (!alignment || !alignment.length) return;

    // Call the captions generate API
    const res = await api('/api/captions/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        alignment,
        words_per_group: 3,
        preset: 'bold_popup',
        source_folder: sourceFolder,
      }),
    });

    if (res && res.captions && res.captions.length) {
      // Store for persistence
      localStorage.setItem('sts-editor-captions', JSON.stringify(res));

      // Send to iframe
      iframe.contentWindow.postMessage({
        type: 'load-captions',
        data: res,
      }, '*');

      console.log(`Auto-generated ${res.captions.length} captions from alignment`);
    }
  } catch (e) {
    console.error('Auto-generate captions failed:', e);
  }
}

// Listen for messages from the editor iframe
window.addEventListener('message', (e) => {
  if (!e.data) return;
  if (e.data.type === 'editor-export') {
    toast('Export received from editor', 'info');
  }
  if (e.data.type === 'switch-page' && e.data.page) {
    switchPage(e.data.page);
  }
});
