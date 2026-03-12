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
  let loadFinalized = false;
  // Restore spinner in case it was replaced with empty-state message
  loadingEl.innerHTML = `
    <div style="text-align:center">
      <div style="width:36px;height:36px;border:2.5px solid rgba(255,255,255,0.08);border-top-color:var(--accent);border-radius:50%;animation:spin 0.8s linear infinite;margin:0 auto 16px"></div>
      <p style="color:var(--text-secondary)">Loading Timeline Editor...</p>
      <p style="font-size:11px;margin-top:4px;color:var(--text-muted);opacity:0.7">Make sure the editor server is running</p>
    </div>`;
  loadingEl.style.display = 'flex';

  if (window._editorReadyPoll) {
    clearInterval(window._editorReadyPoll);
    window._editorReadyPoll = null;
  }

  const finalizeEditorLoad = () => {
    if (loadFinalized) return;
    loadFinalized = true;
    if (window._editorLoadTimeout) { clearTimeout(window._editorLoadTimeout); window._editorLoadTimeout = null; }
    if (window._editorReadyPoll) { clearInterval(window._editorReadyPoll); window._editorReadyPoll = null; }
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

    // Determine current project's source_folder and project_id for caption scoping
    let currentSourceFolder = localStorage.getItem('sts-editor-source-folder') || '';
    let currentProjectId = '';
    try {
      const scenes = JSON.parse(localStorage.getItem('sts-editor-scenes') || '{}');
      if (!currentSourceFolder) currentSourceFolder = scenes.source_folder || '';
      currentProjectId = scenes.project_id || '';
    } catch { /* ignore */ }

    // Send captions data if available and matching current project.
    // Skip auto-generation when the editor loads from a server project
    // (the WIP/initial JSON carries its own captions).
    const captionsData = localStorage.getItem('sts-editor-captions');
    if (captionsData) {
      try {
        const capData = JSON.parse(captionsData);
        // Skip stale captions from a different project
        if (currentSourceFolder && capData.source_folder && capData.source_folder !== currentSourceFolder) {
          console.log('Skipping stale captions (source_folder mismatch):', capData.source_folder, '!=', currentSourceFolder);
          localStorage.removeItem('sts-editor-captions');
          // Only auto-generate for internal pipeline entries, not direct/menu loads
          if (entrySource !== 'menu') {
            _editorAutoGenerateCaptions(iframe, currentSourceFolder, currentProjectId);
          }
        } else {
          iframe.contentWindow.postMessage({
            type: 'load-captions',
            data: capData,
          }, '*');
        }
      } catch (e) { console.error('Editor captions postMessage:', e); }
    } else if (entrySource !== 'menu') {
      // No captions stored — try to auto-generate only for pipeline entries
      _editorAutoGenerateCaptions(iframe, currentSourceFolder, currentProjectId);
    }
  };

  // Timeout: show retry UI if iframe doesn't load within 12s
  if (window._editorLoadTimeout) clearTimeout(window._editorLoadTimeout);
  window._editorLoadTimeout = setTimeout(() => {
    if (loadFinalized || STATE.editorLoaded) return;
    if (window._editorReadyPoll) { clearInterval(window._editorReadyPoll); window._editorReadyPoll = null; }
    loadingEl.innerHTML = `
      <div style="text-align:center">
        <svg width="40" height="40" fill="none" stroke="var(--coral)" stroke-width="1.5" viewBox="0 0 24 24" style="margin:0 auto 12px;opacity:0.7">
          <circle cx="12" cy="12" r="10"/><path d="M12 8v4M12 16h.01"/>
        </svg>
        <p style="color:var(--coral);margin-bottom:4px">Timeline Editor didn't respond</p>
        <p style="font-size:11px;color:var(--text-muted);margin-bottom:14px">The editor server may not be running or is slow to respond.</p>
        <button onclick="initEditorIframe()" style="padding:6px 18px;border-radius:6px;border:1px solid rgba(255,255,255,0.12);background:var(--bg-surface);color:var(--text-secondary);cursor:pointer;font-size:12px;transition:border-color .2s" onmouseover="this.style.borderColor='var(--accent)'" onmouseout="this.style.borderColor='rgba(255,255,255,0.12)'">Retry</button>
      </div>`;
  }, 12000);

  iframe.onload = finalizeEditorLoad;
  iframe.onerror = () => {
    if (loadFinalized) return;
    loadFinalized = true;
    if (window._editorLoadTimeout) { clearTimeout(window._editorLoadTimeout); window._editorLoadTimeout = null; }
    if (window._editorReadyPoll) { clearInterval(window._editorReadyPoll); window._editorReadyPoll = null; }
    $('#editor-loading').innerHTML = `
      <div style="text-align:center">
        <svg width="40" height="40" fill="none" stroke="var(--coral)" stroke-width="1.5" viewBox="0 0 24 24" style="margin:0 auto 12px;opacity:0.7">
          <circle cx="12" cy="12" r="10"/><path d="M15 9l-6 6M9 9l6 6"/>
        </svg>
        <p style="color:var(--coral)">Failed to load Timeline Editor</p>
        <p style="font-size:11px;margin-top:4px;color:var(--text-muted)">Ensure the editor files are served at /timeline-editor/</p>
      </div>`;
  };

  // Attach handlers before assigning src so cached iframe loads cannot beat the callback.
  iframe.src = targetSrc + '?t=' + Date.now();

  // Some refresh paths do not dispatch iframe.onload reliably. Same-origin polling
  // lets the shell detect when the editor document is already ready.
  window._editorReadyPoll = setInterval(() => {
    if (loadFinalized) return;
    try {
      const pathname = iframe.contentWindow?.location?.pathname || '';
      const isEditorPath = pathname === targetSrc || pathname.endsWith(targetSrc);
      const hasEditorDoc = !!iframe.contentDocument?.documentElement;
      if (isEditorPath && hasEditorDoc) {
        finalizeEditorLoad();
      }
    } catch (_) { /* same-origin access may not be ready yet */ }
  }, 250);
}

/**
 * Auto-generate captions from alignment data and send to the editor iframe.
 * Tries STATE.alignResult first, then falls back to fetching the most recent alignment from history.
 */
async function _editorAutoGenerateCaptions(iframe, projectSourceFolder = '', editorProjectId = '') {
  try {
    // Check if captions already exist on the server for this source folder
    // to avoid creating duplicate caption folders on every editor load
    if (projectSourceFolder) {
      try {
        const history = await api('/api/captions/history');
        if (history?.length) {
          const match = history.find(c => c.source_folder === projectSourceFolder);
          if (match?.project_id) {
            // Fetch full caption data from the matched project
            const fullData = await api(`/api/captions/${encodeURIComponent(match.project_id)}`);
            if (fullData?.captions?.length) {
              console.log('Captions already exist for this project, reusing', match.project_id);
              localStorage.setItem('sts-editor-captions', JSON.stringify(fullData));
              iframe.contentWindow.postMessage({ type: 'load-captions', data: fullData }, '*');
              return;
            }
          }
        }
      } catch { /* ignore, proceed to generate */ }
    }

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
        ...(editorProjectId ? { project_id: editorProjectId } : {}),
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
