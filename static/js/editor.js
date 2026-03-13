/* ================================================================
   ScriptToScene Studio — Editor Module (Timeline Editor iframe)
   ================================================================ */

function getStoredEditorBootProject() {
  const candidates = [
    sessionStorage.getItem('sts-staged-timeline'),
    localStorage.getItem('sts-editor-boot-project'),
    localStorage.getItem('sts-editor-scenes'),
  ];

  for (const raw of candidates) {
    if (!raw) continue;
    try {
      const data = JSON.parse(raw);
      if (data && Array.isArray(data.scenes) && data.scenes.length) {
        return data;
      }
    } catch (_) { /* ignore malformed bridge data */ }
  }

  return null;
}

function initEditorIframe() {
  const iframe = $('#editor-iframe');
  const targetSrc = '/timeline-editor/editor.html';
  const entrySource = sessionStorage.getItem('sts-editor-entry-source') || 'internal';
  if (STATE.editorLoaded && iframe.src.includes(targetSrc)) return;
  STATE.editorLoaded = false;
  iframe.style.display = 'none';
  const loadingEl = $('#editor-loading');
  let loadFinalized = false;
  let bridgeSynced = false;
  // Restore spinner in case it was replaced with empty-state message
  loadingEl.innerHTML = `
    <div style="text-align:center">
      <div style="width:36px;height:36px;border:2.5px solid rgba(255,255,255,0.08);border-top-color:var(--accent);border-radius:50%;animation:spin 0.8s linear infinite;margin:0 auto 16px"></div>
      <p style="color:var(--text-secondary)">Loading Timeline Editor...</p>
      <p style="font-size:11px;margin-top:4px;color:var(--text-muted);opacity:0.7">Make sure the editor server is running</p>
    </div>`;
  loadingEl.style.display = 'flex';

  if (window._editorShellReadyHandler) {
    window.removeEventListener('message', window._editorShellReadyHandler);
    window._editorShellReadyHandler = null;
  }

  const finalizeEditorLoad = () => {
    if (loadFinalized) return;
    loadFinalized = true;
    if (window._editorLoadTimeout) { clearTimeout(window._editorLoadTimeout); window._editorLoadTimeout = null; }
    STATE.editorLoaded = true;
    $('#editor-loading').style.display = 'none';
    iframe.style.display = 'block';
  };

  const syncEditorBridgeData = () => {
    if (bridgeSynced || !iframe.contentWindow) return;
    bridgeSynced = true;

    const bootProject = getStoredEditorBootProject();

    if (bootProject && entrySource !== 'menu') {
      try {
        iframe.contentWindow.postMessage({
          type: 'load-scenes',
          data: bootProject,
        }, '*');
      } catch (e) { console.error('Editor postMessage:', e); }
    }

    // Determine current project's source_folder and project_id for caption scoping
    const currentSourceFolder = localStorage.getItem('sts-editor-source-folder') || bootProject?.source_folder || '';
    const currentProjectId = bootProject?.project_id || localStorage.getItem('sts-editor-last-project-id') || '';

    // Send captions data if available and matching current project.
    // Skip auto-generation when the editor loads from a server project
    // (the WIP/initial JSON carries its own captions).
    const captionsData = localStorage.getItem('sts-editor-captions');
    if (captionsData) {
      try {
        const capData = JSON.parse(captionsData);
        // Skip stale captions from a different project
        if (currentSourceFolder && capData.source_folder && capData.source_folder !== currentSourceFolder) {
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
    if (window._editorShellReadyHandler) {
      window.removeEventListener('message', window._editorShellReadyHandler);
      window._editorShellReadyHandler = null;
    }
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

  window._editorShellReadyHandler = (event) => {
    if (!event.data || event.data.type !== 'editor-shell-ready') return;
    if (event.source !== iframe.contentWindow) return;

    const state = event.data.state || 'ready';
    if (state === 'loading' || state === 'ready') {
      finalizeEditorLoad();
    }
    if (state === 'ready') {
      syncEditorBridgeData();
      window.removeEventListener('message', window._editorShellReadyHandler);
      window._editorShellReadyHandler = null;
    }
  };
  window.addEventListener('message', window._editorShellReadyHandler);

  iframe.onload = () => {
    // Keep the shell loader visible until the editor reports its own boot state.
  };
  iframe.onerror = () => {
    if (loadFinalized) return;
    loadFinalized = true;
    if (window._editorLoadTimeout) { clearTimeout(window._editorLoadTimeout); window._editorLoadTimeout = null; }
    if (window._editorShellReadyHandler) {
      window.removeEventListener('message', window._editorShellReadyHandler);
      window._editorShellReadyHandler = null;
    }
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
    if (STATE.alignResult?.alignment?.length) {
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
        alignment = STATE.captionAlignment.word_alignment;
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
