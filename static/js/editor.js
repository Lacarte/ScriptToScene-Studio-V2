/* ================================================================
   ScriptToScene Studio — Editor Module (inline, no iframe)
   ================================================================
   The timeline editor is now inlined in index.html inside #editor-shell.
   video-editor.js exposes window.initEditor(), window.editorLoadScenes(),
   and window.editorLoadCaptions() for direct communication.
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

/**
 * Initialize the inline editor. Called by switchPage('editor').
 * Replaces the old initEditorIframe() — no iframe, no postMessage.
 */
function initEditorInline() {
  // Editor module (video-editor.js) exposes window.initEditor after loading.
  // It's a type="module" script so it's deferred — guaranteed available by
  // the time a user can click the editor nav item.
  if (typeof window.initEditor !== 'function') {
    console.warn('Editor module not loaded yet');
    return;
  }

  // Hide the project browser overlay, show the editor shell
  const loadingEl = document.getElementById('editor-loading');
  const shell = document.getElementById('editor-shell');
  if (loadingEl) loadingEl.style.display = 'none';
  if (shell) shell.style.display = '';

  const wasLoaded = STATE.editorLoaded;
  STATE.editorLoaded = true;

  // Set up the callback for editor ready notification
  window._onEditorReady = (state) => {
    if (state === 'ready') {
      _syncEditorBridgeData();
    }
  };

  // First time: full init. Subsequent: reload data from storage.
  if (!wasLoaded) {
    window.initEditor();
  } else {
    // Editor already initialized — just sync new data
    _syncEditorBridgeData();
  }
}

/**
 * Sync scene and caption data directly to the editor (no postMessage).
 */
function _syncEditorBridgeData() {
  const entrySource = sessionStorage.getItem('sts-editor-entry-source') || 'internal';
  const bootProject = getStoredEditorBootProject();

  if (bootProject && entrySource !== 'menu') {
    if (typeof window.editorLoadScenes === 'function') {
      window.editorLoadScenes(bootProject);
    }
  }

  // Determine current project's source_folder and project_id for caption scoping
  const currentSourceFolder = localStorage.getItem('sts-editor-source-folder') || bootProject?.source_folder || '';
  const currentProjectId = bootProject?.project_id || localStorage.getItem('sts-editor-last-project-id') || '';

  // Send captions data if available and matching current project.
  const captionsData = localStorage.getItem('sts-editor-captions');
  if (captionsData) {
    try {
      const capData = JSON.parse(captionsData);
      if (currentSourceFolder && capData.source_folder && capData.source_folder !== currentSourceFolder) {
        localStorage.removeItem('sts-editor-captions');
        if (entrySource !== 'menu') {
          _editorAutoGenerateCaptions(currentSourceFolder, currentProjectId);
        }
      } else if (typeof window.editorLoadCaptions === 'function') {
        window.editorLoadCaptions(capData);
      }
    } catch (e) { console.error('Editor captions sync:', e); }
  } else if (entrySource !== 'menu') {
    _editorAutoGenerateCaptions(currentSourceFolder, currentProjectId);
  }
}

/**
 * Auto-generate captions from alignment data and send directly to the editor.
 */
async function _editorAutoGenerateCaptions(projectSourceFolder = '', editorProjectId = '') {
  try {
    // Check if captions already exist on the server for this source folder
    if (projectSourceFolder) {
      try {
        const history = await api('/api/captions/history');
        if (history?.length) {
          const match = history.find(c => c.source_folder === projectSourceFolder);
          if (match?.project_id) {
            const fullData = await api(`/api/captions/${encodeURIComponent(match.project_id)}`);
            if (fullData?.captions?.length) {
              localStorage.setItem('sts-editor-captions', JSON.stringify(fullData));
              if (typeof window.editorLoadCaptions === 'function') {
                window.editorLoadCaptions(fullData);
              }
              return;
            }
          }
        }
      } catch { /* ignore, proceed to generate */ }
    }

    let alignment = null;
    let sourceFolder = '';

    // 1) Try current alignment result
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

    // 3) Fallback: fetch alignment from history
    if (!alignment) {
      try {
        const history = await api('/api/timing/history');
        if (history && history.length) {
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
      localStorage.setItem('sts-editor-captions', JSON.stringify(res));
      if (typeof window.editorLoadCaptions === 'function') {
        window.editorLoadCaptions(res);
      }
    }
  } catch (e) {
    console.error('Auto-generate captions failed:', e);
  }
}
