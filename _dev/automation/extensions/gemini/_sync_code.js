console.log('=== STS Gemini Image Synchronizer v1 ===');
if (window.__stsGeminiActive) {
  console.log('Synchronizer already running');
  return;
}
window.__stsGeminiActive = true;

var S = {
  wsUrl: localStorage.getItem('sts-gemini-ws') || 'ws://localhost:5055/ws/image-gemini',
  connected: false,
  collapsed: localStorage.getItem('sts-gemini-collapsed') === 'true',
  showSettings: false,
  projectId: null,
  ws: null,
  wsConnected: false,
  wsReconnectTimer: null,
  typing: {
    active: false, starting: false, queue: [], runId: 0,
    currentIndex: -1, typedCount: 0, stopRequested: false, toolsEnabled: false,
  },
};

function sleep(ms) { return new Promise(function(r) { setTimeout(r, ms); }); }

function smartClick(el) {
  if (!el) return;
  var events = ['pointerover','mouseover','pointerdown','mousedown','pointerup','mouseup','click'];
  for (var i = 0; i < events.length; i++) {
    el.dispatchEvent(new MouseEvent(events[i], {
      bubbles: true, cancelable: true, composed: true, view: window, detail: 1
    }));
  }
}

// ── WebSocket ─────────────────────────────────────────
function connectWS() {
  if (S.ws && (S.ws.readyState === WebSocket.OPEN || S.ws.readyState === WebSocket.CONNECTING)) return;
  console.log('[STS WS] Connecting to', S.wsUrl);
  try { S.ws = new WebSocket(S.wsUrl); } catch (e) {
    console.warn('[STS WS] Connection failed:', e.message);
    S.wsConnected = false; scheduleWSReconnect(); return;
  }
  S.ws.onopen = function() {
    console.log('[STS WS] Connected');
    S.wsConnected = true; S.connected = true;
    if (S.ws.readyState === WebSocket.OPEN) {
      S.ws.send(JSON.stringify({ type: 'EXTENSION_READY', source: 'automa-gemini' }));
    }
    render();
  };
  S.ws.onmessage = function(evt) {
    try { handleWSMessage(JSON.parse(evt.data)); } catch (e) { console.warn('[STS WS] Bad msg:', e); }
  };
  S.ws.onclose = function() {
    console.log('[STS WS] Disconnected');
    S.wsConnected = false; S.ws = null; render(); scheduleWSReconnect();
  };
  S.ws.onerror = function() { S.wsConnected = false; };
}

function scheduleWSReconnect() {
  if (S.wsReconnectTimer) return;
  S.wsReconnectTimer = setTimeout(function() { S.wsReconnectTimer = null; connectWS(); }, 5000);
}

function sendWS(msg) {
  if (S.ws && S.ws.readyState === WebSocket.OPEN) {
    try { S.ws.send(JSON.stringify(msg)); } catch (e) { console.warn('[STS WS] Send failed:', e.message); }
  }
}

function handleWSMessage(msg) {
  switch (msg.type) {
    case 'IMAGE_JOB': {
      S.projectId = msg.projectId;
      var scenes = msg.scenes || [];
      console.log('[STS WS] IMAGE_JOB:', msg.projectId, '-', scenes.length, 'scenes');
      for (var si = 0; si < scenes.length; si++) {
        var sc = scenes[si];
        var k = String(sc.scene);
        var exists = false;
        for (var qi = 0; qi < S.typing.queue.length; qi++) {
          if (S.typing.queue[qi].scene === k) { exists = true; break; }
        }
        if (!exists) {
          S.typing.queue.push({
            scene: k, displayPrompt: sc.prompt,
            fullPrompt: sc.prompt + ' [' + msg.projectId + '|' + sc.scene + ']',
            selected: true, status: 'queued', error: null,
          });
        }
      }
      render();
      if (msg.autoType && !S.typing.active && !S.typing.starting) {
        console.log('[STS WS] Auto-starting typing');
        setTimeout(function() { startTyping(); }, 2000);
      }
      break;
    }
    case 'PONG': break;
  }
}

// ── Enable Image Tool (once per session) ─────────────
function enableImageTool() {
  return new Promise(function(resolve) {
    if (S.typing.toolsEnabled) { resolve(); return; }
    console.log('Enabling image generation tool...');
    var toolsBtn = document.querySelector('button.toolbox-drawer-button');
    if (!toolsBtn) {
      var icon = document.querySelector('button mat-icon[fonticon="page_info"]');
      if (icon) toolsBtn = icon.closest('button');
    }
    if (!toolsBtn) {
      console.warn('Tools button not found - may already be in image mode');
      S.typing.toolsEnabled = true; resolve(); return;
    }
    smartClick(toolsBtn);
    setTimeout(function() {
      var createImgBtn = document.querySelector('#toolbox-drawer-menu toolbox-drawer-item:first-child button');
      if (!createImgBtn) {
        var imgIcon = document.querySelector('mat-icon[fonticon="photo_prints"]');
        if (imgIcon) createImgBtn = imgIcon.closest('button');
      }
      if (createImgBtn) {
        var isChecked = createImgBtn.getAttribute('aria-checked');
        if (isChecked !== 'true') { smartClick(createImgBtn); console.log('Create Image tool enabled'); }
        else { console.log('Create Image tool already active'); }
      } else { console.warn('Create Image button not found'); }
      setTimeout(function() {
        var tbAgain = document.querySelector('button.toolbox-drawer-button');
        if (tbAgain && tbAgain.classList.contains('menu-open')) smartClick(tbAgain);
        S.typing.toolsEnabled = true; resolve();
      }, 300);
    }, 500);
  });
}

// ── Type into Gemini ─────────────────────────────────
function typeIntoGemini(text) {
  return new Promise(function(resolve, reject) {
    // Selectors from Gemini Automator extension (proven to work)
    var selectors = [
      '.ql-editor.textarea',
      'div[aria-label="Enter a prompt here"]',
      'rich-textarea .ql-editor[contenteditable="true"]',
      '.ql-editor[contenteditable="true"]',
      'div[contenteditable="true"][role="textbox"]',
    ];
    var inputEl = null;
    for (var si = 0; si < selectors.length; si++) {
      inputEl = document.querySelector(selectors[si]);
      if (inputEl) { console.log('Found input via:', selectors[si]); break; }
    }
    if (!inputEl) { reject(new Error('Gemini text input not found')); return; }

    inputEl.focus();
    inputEl.click();
    setTimeout(function() {
      // Clear existing content
      inputEl.textContent = '';
      inputEl.dispatchEvent(new Event('input', { bubbles: true }));
      setTimeout(function() {
        // Use execCommand('insertText') — this is how the native Gemini Automator does it
        // Quill/Angular properly recognizes execCommand input
        var success = document.execCommand('insertText', false, text);
        if (!success) {
          // Fallback: set innerText directly
          inputEl.innerText = text;
        }
        inputEl.dispatchEvent(new Event('input', { bubbles: true }));
        setTimeout(function() {
          var editorText = inputEl.textContent || '';
          if (editorText.trim().length < 5) { reject(new Error('Prompt did not land in editor')); return; }
          console.log('Prompt typed (' + text.length + ' chars)');
          resolve();
        }, 300);
      }, 150);
    }, 200);
  });
}

// ── Submit ────────────────────────────────────────────
function submitPrompt(inputEl) {
  return new Promise(function(resolve, reject) {
    // Method 1: Press Enter (like Gemini Automator does)
    var target = inputEl || document.querySelector('.ql-editor.textarea') || document.querySelector('rich-textarea');
    if (target) {
      target.dispatchEvent(new KeyboardEvent('keydown', {
        bubbles: true, cancelable: true, key: 'Enter', code: 'Enter', keyCode: 13
      }));
    }

    // Method 2: Click Send button as backup (after short delay)
    setTimeout(function() {
      var sendBtn = document.querySelector('button[aria-label*="Send"]');
      if (!sendBtn) sendBtn = document.querySelector('button.send-button');
      if (sendBtn && !sendBtn.disabled) {
        sendBtn.click();
        console.log('Prompt submitted via Send button');
      } else {
        console.log('Prompt submitted via Enter key');
      }
      setTimeout(resolve, 1000);
    }, 500);
  });
}

// ── Check if Gemini is generating (from Gemini Automator extension) ──
function isGeminiGenerating() {
  var stopBtn = document.querySelector('button[aria-label="Stop response"]');
  var thinkingAvatar = document.querySelector('.bard-avatar.thinking');
  var textLoader = document.querySelector('.gpi-static-text-loader');
  var processingContainer = document.querySelector('.processing-state_container--processing');
  var loadingSpan = document.querySelector('span[aria-label="Loading"]');
  var justASec = null;
  var spans = document.querySelectorAll('span');
  for (var i = 0; i < spans.length; i++) {
    if (spans[i].textContent.indexOf('Just a sec') !== -1) { justASec = spans[i]; break; }
  }
  return !!(stopBtn || thinkingAvatar || textLoader || processingContainer || loadingSpan || justASec);
}

// ── Wait for image generation (proven pattern from Gemini Automator) ──
function waitForImageGeneration(timeoutMs) {
  timeoutMs = timeoutMs || 120000;
  return new Promise(function(resolve) {
    var start = Date.now();
    var seenLoading = false;
    var stableCount = 0;
    var requiredStable = 5; // 5 seconds of no loading indicators
    console.log('Waiting for image (timeout: ' + (timeoutMs / 1000) + 's)...');

    var checkInterval = setInterval(function() {
      var generating = isGeminiGenerating();

      if (generating) {
        if (!seenLoading) { seenLoading = true; console.log('Generation started'); }
        stableCount = 0;
      } else {
        if (seenLoading) {
          stableCount++;
          // Check positive completion signals
          var showMore = document.querySelector('button[aria-label*="Show more"]');
          var regenerate = document.querySelector('button[aria-label*="Regenerate"]');
          var modifyResponse = document.querySelector('button[aria-label*="Modify response"]');
          if (showMore || regenerate || modifyResponse) {
            console.log('Completion buttons detected');
            stableCount = requiredStable; // Force completion
          }
        } else {
          // Haven't seen loading yet — check for fallback
          if (Date.now() - start > 15000) {
            var dlBtn = document.querySelector('mat-icon[fonticon="download"]');
            if (dlBtn) {
              console.log('Download icon found (fallback)');
              seenLoading = true; stableCount = requiredStable;
            }
          }
        }
      }

      // Check for image once generation seems done
      if (seenLoading && stableCount >= requiredStable) {
        clearInterval(checkInterval);
        // Find the image in the last response container
        var containers = document.querySelectorAll('response-container');
        if (containers.length > 0) {
          var lastContainer = containers[containers.length - 1];
          var imgs = lastContainer.querySelectorAll('img');
          for (var i = 0; i < imgs.length; i++) {
            if (imgs[i].src && imgs[i].src.indexOf('http') === 0 &&
                imgs[i].src.indexOf('googleusercontent.com/a/') === -1) {
              console.log('Image found:', imgs[i].src.substring(0, 80) + '...');
              resolve(imgs[i].src); return;
            }
          }
        }
        // Fallback: check generated-image elements
        var genImgs = document.querySelectorAll('generated-image img.image.loaded');
        if (genImgs.length > 0) {
          var last = genImgs[genImgs.length - 1];
          if (last.src && last.src.indexOf('http') === 0) {
            console.log('Image found (generated-image):', last.src.substring(0, 80) + '...');
            resolve(last.src); return;
          }
        }
        console.warn('Generation complete but no image found');
        resolve(null);
        return;
      }

      if (Date.now() - start > timeoutMs) {
        clearInterval(checkInterval); console.error('Image generation timed out'); resolve(null);
      }
    }, 1000);
  });
}

// ── Fetch image as base64 ────────────────────────────
function fetchImageAsBase64(imageUrl) {
  console.log('Fetching image as base64...');
  var strategies = [{ credentials: 'include' }, { mode: 'cors', credentials: 'omit' }, {}];
  var attempt = 0;
  function tryNext() {
    if (attempt >= strategies.length) { console.error('All fetch strategies failed'); return Promise.resolve(null); }
    var opts = strategies[attempt]; attempt++;
    return fetch(imageUrl, opts).then(function(r) {
      if (r.ok) {
        return r.blob().then(function(blob) {
          return new Promise(function(res, rej) {
            var reader = new FileReader();
            reader.onload = function() { res(reader.result); };
            reader.onerror = rej;
            reader.readAsDataURL(blob);
          }).then(function(b64) {
            console.log('Image fetched (' + (blob.size / 1024).toFixed(0) + ' KB, ' + blob.type + ')');
            return b64;
          });
        });
      }
      console.warn('Fetch strategy ' + attempt + ' returned ' + r.status);
      return tryNext();
    }).catch(function(e) { console.warn('Fetch ' + attempt + ' failed:', e.message); return tryNext(); });
  }
  return tryNext();
}

// ── Main Typing Loop ─────────────────────────────────
function startTyping() {
  if (S.typing.active || S.typing.starting) { console.log('Typing already running'); return; }
  var tq = S.typing.queue;
  if (!tq.length) { console.log('No prompts to type'); return; }
  S.typing.starting = true; S.typing.stopRequested = false;
  var runItems = [];
  for (var ri = 0; ri < tq.length; ri++) {
    if (tq[ri].selected && tq[ri].status !== 'completed') runItems.push(tq[ri]);
  }
  if (!runItems.length) {
    for (var rri = 0; rri < tq.length; rri++) { if (tq[rri].status === 'completed') tq[rri].status = 'queued'; }
    for (var rr2 = 0; rr2 < tq.length; rr2++) {
      if (tq[rr2].selected && tq[rr2].status !== 'completed') runItems.push(tq[rr2]);
    }
  }
  if (!runItems.length) { S.typing.starting = false; console.log('All done'); render(); return; }
  S.typing.runId++; S.typing.active = true; S.typing.starting = false; S.typing.typedCount = 0;
  render();
  console.log('=== Starting typing: ' + runItems.length + ' prompts ===');

  var seenImageUrls = {};
  var existingImgs = document.querySelectorAll('generated-image img.image.loaded');
  for (var ei = 0; ei < existingImgs.length; ei++) {
    if (existingImgs[ei].src) seenImageUrls[existingImgs[ei].src] = true;
  }

  var idx = 0;
  function processNext() {
    if (S.typing.stopRequested || idx >= tq.length) {
      S.typing.active = false; S.typing.currentIndex = -1; render();
      var completed = 0, failed = 0;
      for (var ci = 0; ci < tq.length; ci++) {
        if (tq[ci].status === 'completed') completed++;
        if (tq[ci].status === 'error') failed++;
      }
      console.log('=== Typing complete: ' + completed + ' done, ' + failed + ' failed ===');
      if (completed === tq.length) sendWS({ type: 'JOB_COMPLETE', projectId: S.projectId });
      return;
    }
    var item = tq[idx];
    if (!item.selected || item.status === 'completed') { idx++; processNext(); return; }

    S.typing.currentIndex = idx; item.status = 'typing'; render();
    sendWS({ type: 'STATUS_UPDATE', scene: parseInt(item.scene), status: 'typing' });

    var curImgs = document.querySelectorAll('generated-image img.image.loaded');
    for (var ci2 = 0; ci2 < curImgs.length; ci2++) {
      if (curImgs[ci2].src) seenImageUrls[curImgs[ci2].src] = true;
    }

    enableImageTool()
      .then(function() { return typeIntoGemini(item.fullPrompt); })
      .then(function() { return sleep(500); })
      .then(function() { return submitPrompt(); })
      .then(function() {
        item.status = 'generating'; render();
        sendWS({ type: 'STATUS_UPDATE', scene: parseInt(item.scene), status: 'generating' });
        return waitForImageGeneration(90000);
      })
      .then(function(imageUrl) {
        if (S.typing.stopRequested) { item.status = 'queued'; return null; }
        if (imageUrl && !seenImageUrls[imageUrl]) {
          seenImageUrls[imageUrl] = true;
          return fetchImageAsBase64(imageUrl).then(function(base64Data) {
            if (base64Data) {
              sendWS({ type: 'IMAGE_UPLOAD', projectId: S.projectId, scene: parseInt(item.scene),
                image: { data: base64Data, source_url: imageUrl } });
              item.status = 'completed'; S.typing.typedCount++;
              console.log('Scene ' + item.scene + ' completed and sent');
            } else { item.status = 'error'; item.error = 'Failed to fetch image'; }
          });
        } else if (!imageUrl) {
          item.status = 'error'; item.error = 'Timed out';
          console.log('Refreshing page...'); window.location.reload(); return 'STOP';
        } else { item.status = 'error'; item.error = 'Duplicate image'; }
        return null;
      })
      .then(function(signal) {
        if (signal === 'STOP') return;
        render(); idx++;
        var hasMore = false;
        for (var hm = idx; hm < tq.length; hm++) {
          if (tq[hm].selected && tq[hm].status !== 'completed') { hasMore = true; break; }
        }
        if (hasMore && !S.typing.stopRequested) {
          console.log('Waiting 3s...'); setTimeout(processNext, 3000);
        } else { processNext(); }
      })
      .catch(function(e) {
        console.error('Error scene ' + item.scene + ':', e.message);
        item.status = 'error'; item.error = e.message; render();
        idx++; setTimeout(processNext, 3000);
      });
  }
  processNext();
}

function stopTyping() { S.typing.stopRequested = true; console.log('Stop requested'); render(); }

// ── UI Overlay ───────────────────────────────────────
function render() {
  var panel = document.getElementById('sts-gemini-panel');
  if (!panel) { panel = document.createElement('div'); panel.id = 'sts-gemini-panel'; document.body.appendChild(panel); }
  var tq = S.typing.queue;
  var total = tq.length, completed = 0, failed = 0;
  for (var ci = 0; ci < tq.length; ci++) {
    if (tq[ci].status === 'completed') completed++;
    if (tq[ci].status === 'error') failed++;
  }
  var pct = total > 0 ? Math.round(completed / total * 100) : 0;
  var wsColor = S.wsConnected ? '#5cb85c' : '#d9534f';
  var wsLabel = S.wsConnected ? 'Connected' : 'Disconnected';

  if (S.collapsed) {
    panel.style.cssText = 'position:fixed;top:12px;right:12px;z-index:99999;background:#1e1e2e;border:1px solid #333;border-radius:10px;padding:8px 14px;font-family:Inter,system-ui,sans-serif;font-size:12px;color:#ccc;cursor:pointer;box-shadow:0 4px 20px rgba(0,0,0,0.4);display:flex;align-items:center;gap:8px;';
    panel.innerHTML = '<span style="width:8px;height:8px;border-radius:50%;background:' + wsColor + ';"></span><span style="font-weight:600;">STS Gemini</span><span style="color:#888;">' + completed + '/' + total + '</span>';
    panel.onclick = function() { S.collapsed = false; localStorage.setItem('sts-gemini-collapsed', 'false'); render(); };
    return;
  }

  panel.style.cssText = 'position:fixed;top:12px;right:12px;z-index:99999;background:#1e1e2e;border:1px solid #333;border-radius:14px;width:340px;max-height:80vh;overflow-y:auto;font-family:Inter,system-ui,sans-serif;font-size:12px;color:#ccc;box-shadow:0 4px 30px rgba(0,0,0,0.5);';
  panel.onclick = null;

  var settingsHtml = '';
  if (S.showSettings) {
    settingsHtml = '<div style="padding:10px 14px;border-top:1px solid #333;"><label style="font-size:11px;color:#888;">WebSocket URL</label><input id="sts-ws-url" type="text" value="' + S.wsUrl + '" style="width:100%;box-sizing:border-box;background:#2a2a3e;border:1px solid #444;border-radius:6px;padding:6px 8px;color:#eee;font-size:11px;margin-top:4px;outline:none;"><button id="sts-ws-save" style="margin-top:6px;background:#4a90d9;border:none;color:#fff;padding:5px 12px;border-radius:6px;font-size:11px;cursor:pointer;">Save & Reconnect</button></div>';
  }

  var scenesHtml = '';
  for (var si = 0; si < tq.length; si++) {
    var item = tq[si];
    var statusColors = { queued:'#888', typing:'#f0ad4e', generating:'#5bc0de', completed:'#5cb85c', error:'#d9534f' };
    var statusIcons = { queued:'\u23F3', typing:'\u270D', generating:'\u2728', completed:'\u2705', error:'\u274C' };
    var sColor = statusColors[item.status] || '#888';
    var sIcon = statusIcons[item.status] || '\u23F3';
    var short = item.displayPrompt.substring(0, 50) + (item.displayPrompt.length > 50 ? '...' : '');
    var activeBorder = si === S.typing.currentIndex ? 'border-left:3px solid ' + sColor + ';' : 'border-left:3px solid transparent;';
    var errHtml = item.error ? '<div style="color:#d9534f;font-size:10px;margin-top:2px;">' + item.error + '</div>' : '';
    scenesHtml += '<div style="padding:6px 10px;' + activeBorder + '"><div style="display:flex;align-items:center;gap:6px;"><span style="font-size:10px;">' + sIcon + '</span><span style="font-weight:600;min-width:20px;color:' + sColor + ';">#' + item.scene + '</span><span style="flex:1;color:#aaa;font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">' + short + '</span></div>' + errHtml + '</div>';
  }

  var btnLabel = S.typing.active ? 'Stop' : 'Start Typing';
  var btnColor = S.typing.active ? '#d9534f' : '#5cb85c';
  var btnId = S.typing.active ? 'sts-stop-btn' : 'sts-start-btn';

  panel.innerHTML =
    '<div style="padding:10px 14px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid #333;"><div style="display:flex;align-items:center;gap:8px;"><span style="width:8px;height:8px;border-radius:50%;background:' + wsColor + ';"></span><span style="font-weight:700;font-size:13px;color:#eee;">STS Gemini</span><span style="font-size:10px;color:#888;">' + wsLabel + '</span></div><div style="display:flex;gap:6px;"><button id="sts-settings-toggle" style="background:none;border:none;color:#888;cursor:pointer;font-size:14px;padding:2px;">\u2699</button><button id="sts-collapse-btn" style="background:none;border:none;color:#888;cursor:pointer;font-size:14px;padding:2px;">\u2212</button></div></div>' +
    (S.projectId ? '<div style="padding:6px 14px;font-size:11px;color:#888;border-bottom:1px solid #2a2a3e;">Project: <b style="color:#ccc;">' + S.projectId + '</b></div>' : '') +
    '<div style="padding:8px 14px;"><div style="display:flex;gap:12px;margin-bottom:8px;"><span style="color:#5cb85c;font-weight:600;">' + completed + ' done</span><span style="color:#d9534f;">' + failed + ' err</span><span style="color:#888;">' + total + ' total</span></div><div style="height:4px;background:#333;border-radius:2px;overflow:hidden;margin-bottom:8px;"><div style="height:100%;width:' + pct + '%;background:linear-gradient(90deg,#5cb85c,#4cae4c);transition:width 0.3s;"></div></div><button id="' + btnId + '" style="width:100%;padding:7px;border:none;border-radius:8px;background:' + btnColor + ';color:#fff;font-weight:600;font-size:12px;cursor:pointer;">' + btnLabel + '</button></div>' +
    '<div style="max-height:300px;overflow-y:auto;border-top:1px solid #333;">' + (scenesHtml || '<div style="padding:12px 14px;color:#666;text-align:center;">No scenes loaded</div>') + '</div>' +
    settingsHtml;

  setTimeout(function() {
    var collapseBtn = document.getElementById('sts-collapse-btn');
    if (collapseBtn) collapseBtn.onclick = function(e) { e.stopPropagation(); S.collapsed = true; localStorage.setItem('sts-gemini-collapsed', 'true'); render(); };
    var settingsToggle = document.getElementById('sts-settings-toggle');
    if (settingsToggle) settingsToggle.onclick = function(e) { e.stopPropagation(); S.showSettings = !S.showSettings; render(); };
    var startBtn = document.getElementById('sts-start-btn');
    if (startBtn) startBtn.onclick = function(e) { e.stopPropagation(); startTyping(); };
    var stopBtn = document.getElementById('sts-stop-btn');
    if (stopBtn) stopBtn.onclick = function(e) { e.stopPropagation(); stopTyping(); };
    var saveBtn = document.getElementById('sts-ws-save');
    if (saveBtn) saveBtn.onclick = function(e) {
      e.stopPropagation();
      var urlInput = document.getElementById('sts-ws-url');
      if (urlInput && urlInput.value) {
        S.wsUrl = urlInput.value; localStorage.setItem('sts-gemini-ws', S.wsUrl);
        if (S.ws) { try { S.ws.close(); } catch(ex){} }
        S.ws = null; S.wsConnected = false; connectWS(); render();
      }
    };
  }, 50);
}

// ── Boot ─────────────────────────────────────────────
render();
connectWS();
console.log('STS Gemini Synchronizer initialized');
// Do NOT call automaNextBlock — script stays alive
