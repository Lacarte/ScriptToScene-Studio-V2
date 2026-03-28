(function() {
  // ═══════════════════════════════════════════════════════
  // STS Gemini Image Synchronizer — Content Script v1
  // Runs as native content script (bypasses Trusted Types)
  // ═══════════════════════════════════════════════════════
  if (window !== window.top) return; // Skip iframes

  console.log('[STS Gemini] Content script loaded');

  // Listen for start/stop from popup
  chrome.runtime.onMessage.addListener(function(request, sender, sendResponse) {
    if (request.action === 'STS_START') {
      console.log('[STS Gemini] START received, wsUrl:', request.wsUrl);
      if (request.wsUrl) {
        localStorage.setItem('sts-gemini-ws', request.wsUrl);
      }
      initSync(request.wsUrl);
      sendResponse({ ok: true });
    } else if (request.action === 'STS_STATUS') {
      var s = window.__stsGeminiState;
      sendResponse({
        connected: !!(s && s.wsConnected),
        projectId: s ? s.projectId : null,
        sceneCount: s ? Object.keys(s.scenes).length : 0,
      });
      return true;
    } else if (request.action === 'STS_DIAGNOSE') {
      var s = window.__stsGeminiState;
      var connBar = document.getElementById('sts-conn-bar');
      var connMsg = document.getElementById('sts-conn-msg');
      var headDot = document.getElementById('sts-head-dot');
      sendResponse({
        active: !!window.__stsGeminiActive,
        wsConnected: s ? s.wsConnected : null,
        connected: s ? s.connected : null,
        wsUrl: s ? s.wsUrl : null,
        projectId: s ? s.projectId : null,
        scenesCount: s ? Object.keys(s.scenes).length : 0,
        queueLength: s ? s.typing.queue.length : 0,
        typingActive: s ? s.typing.active : false,
        panelExists: !!document.getElementById('sts-sync'),
        connBarDisplay: connBar ? connBar.style.display : null,
        connBarClass: connBar ? connBar.className : null,
        connMsgText: connMsg ? connMsg.textContent : null,
        headDotClass: headDot ? headDot.className : null,
      });
      return true;
    } else if (request.action === 'STS_STOP') {
      console.log('[STS Gemini] STOP received');
      if (window.__stsGeminiState) {
        window.__stsGeminiState.typing.stopRequested = true;
      }
      var panel = document.getElementById('sts-sync');
      if (panel) panel.remove();
      window.__stsGeminiActive = false;
      chrome.storage.local.set({ stsRunning: false });
      sendResponse({ ok: true });
    }
  });

  // Always auto-start on Gemini — connect WS and show panel immediately
  console.log('[STS Gemini] Auto-starting on page load');
  initSync(null);

  function initSync(wsUrlOverride) {
    console.log('=== STS Gemini Image Synchronizer v1 ===');
    if (window.__stsGeminiActive) {
      console.log('Synchronizer already running');
      return;
    }
    window.__stsGeminiActive = true;

    var S = {
      wsUrl: wsUrlOverride || localStorage.getItem('sts-gemini-ws') || 'ws://localhost:5050/ws/image-gemini',
      connected: false,
      collapsed: localStorage.getItem('sts-gemini-collapsed') === 'true',
      showSettings: false,
      activeTab: 'typing',
      projectId: null,
      aspectRatio: '',
      scenes: {},
      wsConnected: false,
      typing: {
        active: false, starting: false, queue: [], runId: 0,
        currentIndex: -1, typedCount: 0, stopRequested: false, toolsEnabled: false,
      },
    };
    window.__stsGeminiState = S;

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

    // ── WebSocket (proxied via background service worker) ──
    // Port keeps the service worker alive. sendMessage handles all communication.

    // Keep service worker alive with a persistent port
    (function keepAlive() {
      try {
        var port = chrome.runtime.connect({ name: 'sts-gemini-alive' });
        port.onDisconnect.addListener(function() { setTimeout(keepAlive, 1000); });
      } catch(e) { setTimeout(keepAlive, 2000); }
    })();

    // Receive WS messages + status pushed from background
    chrome.runtime.onMessage.addListener(function(msg, sender, sendResponse) {
      if (msg.action === 'STS_WS_MESSAGE') {
        if (!S.wsConnected) { S.wsConnected = true; S.connected = true; render(); }
        try { handleWSMessage(msg.payload); } catch(e) { console.warn('[STS WS] Bad msg:', e); }
      } else if (msg.action === 'STS_WS_STATUS') {
        S.wsConnected = msg.connected;
        S.connected = msg.connected;
        if (msg.wsUrl) S.wsUrl = msg.wsUrl;
        render();
      }
    });

    // Poll background for WS status every 2s
    setInterval(function() {
      try {
        chrome.runtime.sendMessage({ action: 'STS_WS_GET_STATUS' }, function(resp) {
          if (chrome.runtime.lastError || !resp) return;
          S.wsConnected = resp.connected;
          S.connected = resp.connected;
          if (resp.wsUrl) S.wsUrl = resp.wsUrl;
          render();
        });
      } catch(e) {}
    }, 2000);

    function connectWS() {
      var manualUrl = localStorage.getItem('sts-gemini-ws-manual') || null;
      try { chrome.runtime.sendMessage({ action: 'STS_WS_RECONNECT', manualUrl: manualUrl }); } catch(e) {}
    }

    function sendWS(msg) {
      try { chrome.runtime.sendMessage({ action: 'STS_WS_SEND', payload: msg }); } catch(e) {}
    }

    function handleWSMessage(msg) {
      switch (msg.type) {
        case 'IMAGE_JOB': {
          S.projectId = msg.projectId;
          S.aspectRatio = msg.aspectRatio || S.aspectRatio || '';
          var scenes = msg.scenes || [];
          var pid = msg.projectId;
          console.log('[STS WS] IMAGE_JOB:', pid, '-', scenes.length, 'scenes', 'aspect:', S.aspectRatio);
          for (var si = 0; si < scenes.length; si++) {
            var sc = scenes[si];
            var k = String(sc.scene);
            var queueKey = pid + '|' + k; // Unique key per project+scene
            var scAspect = sc.aspectRatio || S.aspectRatio || '';
            // Populate scenes for sync tab
            if (!S.scenes[queueKey]) {
              S.scenes[queueKey] = { prompt: sc.prompt, status: 'pending', imageUrl: null, projectId: pid };
            }
            var exists = false;
            for (var qi = 0; qi < S.typing.queue.length; qi++) {
              if (S.typing.queue[qi].queueKey === queueKey) { exists = true; break; }
            }
            if (!exists) {
              var arSuffix = scAspect ? ' ' + scAspect : '';
              S.typing.queue.push({
                scene: k, queueKey: queueKey, projectId: pid,
                displayPrompt: sc.prompt,
                aspectRatio: scAspect,
                fullPrompt: sc.prompt + arSuffix,
                selected: true, status: 'queued', error: null,
              });
            }
          }
          render();
          chrome.runtime.sendMessage({ type: 'ACTIVATE_TAB' });
          if (msg.autoType && !S.typing.active && !S.typing.starting) {
            console.log('[STS WS] Auto-starting typing');
            setTimeout(function() { startTyping(); }, 2000);
          }
          break;
        }
        case 'ACTIVATE_TAB':
          chrome.runtime.sendMessage({ type: 'ACTIVATE_TAB' });
          break;
        case 'PONG': break;
      }
    }

    // ── Enable Image Tool (once) ─────────────────────
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

    // ── Type into Gemini (execCommand pattern) ───────
    function typeIntoGemini(text) {
      return new Promise(function(resolve, reject) {
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
          if (inputEl) { console.log('[TYPE] Found input via:', selectors[si]); break; }
        }
        if (!inputEl) { reject(new Error('Gemini text input not found')); return; }

        console.log('[TYPE] Focusing input...');
        inputEl.focus();
        setTimeout(function() {
          console.log('[TYPE] Clearing content...');
          // Select all and delete instead of setting textContent
          document.execCommand('selectAll', false, null);
          document.execCommand('delete', false, null);

          setTimeout(function() {
            console.log('[TYPE] Inserting text (' + text.length + ' chars)...');
            var success = document.execCommand('insertText', false, text);
            console.log('[TYPE] execCommand insertText result:', success);
            if (!success) {
              console.log('[TYPE] Fallback: setting innerText');
              inputEl.innerText = text;
              inputEl.dispatchEvent(new Event('input', { bubbles: true }));
            }

            setTimeout(function() {
              var editorText = inputEl.textContent || '';
              console.log('[TYPE] Editor content length:', editorText.trim().length);
              if (editorText.trim().length < 5) { reject(new Error('Prompt did not land in editor')); return; }
              console.log('[TYPE] Done. Text in editor, NOT submitting yet.');
              resolve();
            }, 500);
          }, 200);
        }, 300);
      });
    }

    // ── Submit ────────────────────────────────────────
    function submitPrompt() {
      return new Promise(function(resolve, reject) {
        console.log('[SUBMIT] Looking for Send button...');
        var sendBtn = document.querySelector('button.send-button[aria-label="Send message"]');
        if (!sendBtn) sendBtn = document.querySelector('button[aria-label*="Send"]:not([disabled])');
        if (!sendBtn) sendBtn = document.querySelector('button.send-button');

        console.log('[SUBMIT] Send button found:', !!sendBtn,
          sendBtn ? 'disabled=' + sendBtn.disabled + ' aria-disabled=' + sendBtn.getAttribute('aria-disabled') : '');

        if (sendBtn && !sendBtn.disabled && sendBtn.getAttribute('aria-disabled') !== 'true') {
          console.log('[SUBMIT] Clicking Send button NOW');
          sendBtn.click();
        } else {
          console.log('[SUBMIT] No enabled Send button found');
          reject(new Error('Send button not found or disabled'));
          return;
        }

        // Wait for Gemini to accept the prompt — watch for the thinking avatar
        console.log('[SUBMIT] Waiting for Gemini to start processing...');
        var start = Date.now();
        var checkInterval = setInterval(function() {
          var thinkingAvatar = document.querySelector('.bard-avatar.thinking');
          var processing = document.querySelector('.processing-state_container--processing');
          var stopBtn = document.querySelector('button[aria-label="Stop response"]');

          if (thinkingAvatar || processing || stopBtn) {
            clearInterval(checkInterval);
            console.log('[SUBMIT] Gemini accepted prompt —',
              thinkingAvatar ? 'avatar thinking' : '',
              processing ? 'processing state' : '',
              stopBtn ? 'stop button' : '');
            resolve();
            return;
          }

          if (Date.now() - start > 10000) {
            clearInterval(checkInterval);
            console.warn('[SUBMIT] No thinking state after 10s — proceeding anyway');
            resolve();
          }
        }, 300);
      });
    }

    // ── Rate limit detection & countdown ──────────
    function checkRateLimit() {
      // Look for the quota disclaimer element
      var disclaimer = document.querySelector('image-generation-quota-disclaimer');
      if (!disclaimer) return null;
      var titleEl = disclaimer.querySelector('.title');
      if (!titleEl || titleEl.textContent.indexOf('reached your image generation limit') === -1) return null;

      // Extract reset time from the text: "Your limit resets on Mar 24, 6:17 PM"
      var textEl = disclaimer.querySelector('.main-text span');
      var resetTime = null;
      if (textEl) {
        var match = textEl.textContent.match(/resets on\s+(.+?)\./);
        if (match) {
          try {
            // Parse the date string — add current year
            var dateStr = match[1].trim();
            var year = new Date().getFullYear();
            resetTime = new Date(dateStr + ' ' + year);
            // If parsed date is in the past, try next year
            if (resetTime < new Date()) resetTime = new Date(dateStr + ' ' + (year + 1));
          } catch(e) { /* parsing failed */ }
        }
      }
      console.log('[RATE LIMIT] Detected! Reset:', resetTime ? resetTime.toLocaleString() : 'unknown');
      return { resetTime: resetTime, text: textEl ? textEl.textContent.trim() : 'Rate limited' };
    }

    function waitForRateLimitReset(resetTime) {
      return new Promise(function(resolve) {
        console.log('[RATE LIMIT] Waiting until', resetTime ? resetTime.toLocaleString() : 'unknown');
        S.typing.rateLimited = true;
        render();

        var checkInterval = setInterval(function() {
          // Update countdown in panel
          render();

          // Check if rate limit is gone
          var stillLimited = checkRateLimit();
          if (!stillLimited) {
            clearInterval(checkInterval);
            console.log('[RATE LIMIT] Limit cleared!');
            S.typing.rateLimited = false;
            S.typing.rateLimitReset = null;
            render();
            resolve();
            return;
          }

          // Also resolve if we're past the reset time
          if (resetTime && new Date() > resetTime) {
            clearInterval(checkInterval);
            console.log('[RATE LIMIT] Past reset time, refreshing page...');
            S.typing.rateLimited = false;
            window.location.reload();
            resolve();
            return;
          }

          if (S.typing.stopRequested) {
            clearInterval(checkInterval);
            S.typing.rateLimited = false;
            resolve();
          }
        }, 5000); // Check every 5 seconds
      });
    }

    function formatCountdown(targetDate) {
      if (!targetDate) return '??:??:??';
      var diff = targetDate - new Date();
      if (diff <= 0) return '00:00:00';
      var h = Math.floor(diff / 3600000);
      var m = Math.floor((diff % 3600000) / 60000);
      var s = Math.floor((diff % 60000) / 1000);
      return (h < 10 ? '0' : '') + h + ':' + (m < 10 ? '0' : '') + m + ':' + (s < 10 ? '0' : '') + s;
    }

    // ── Generation detection (from Gemini Automator) ─
    function isGeminiGenerating() {
      // Based on DOM activity analysis — these are reliable generating indicators:
      // 1. processing-state without hidden attr = actively processing
      var processingStates = document.querySelectorAll('processing-state:not([hidden])');
      var hasActiveProcessing = false;
      for (var p = 0; p < processingStates.length; p++) {
        if (!processingStates[p].hasAttribute('hidden')) { hasActiveProcessing = true; break; }
      }
      // 2. response-element with "pending" or "animating" class
      var pendingResponse = document.querySelector('response-element.pending, response-element.animating');
      // 3. Attachment container still pending
      var pendingAttachment = document.querySelector('.attachment-container.generated-images.pending');
      // 4. Classic indicators
      var stopBtn = document.querySelector('button[aria-label="Stop response"]');
      var processingContainer = document.querySelector('.processing-state_container--processing');

      return !!(hasActiveProcessing || pendingResponse || pendingAttachment || stopBtn || processingContainer);
    }

    function isValidImageSrc(src) {
      return src && (src.indexOf('http') === 0 || src.indexOf('blob:') === 0);
    }

    function findImageInContainer(container) {
      if (!container) return null;
      // Based on DOM activity analysis, the reliable lifecycle is:
      //   1. aria-busy="false" on markdown div (generation done)
      //   2. src gets blob: URL on <img> (image available)
      //   3. class "image" → "image loaded" (final render)
      // We accept ANY img with a blob: src — don't require .loaded class
      // because .loaded appears much later and causes timeouts.

      // Strategy 1: img with blob: src inside single-image (most reliable)
      var imgs = container.querySelectorAll('single-image img');
      for (var i = imgs.length - 1; i >= 0; i--) {
        if (imgs[i].src && imgs[i].src.indexOf('blob:') === 0) {
          console.log('[IMAGE] Found blob src in single-image img' + (imgs[i].classList.contains('loaded') ? ' (loaded)' : ' (not yet loaded)'));
          return imgs[i].src;
        }
      }
      // Strategy 2: img with blob: src inside generated-image
      var genImgs = container.querySelectorAll('generated-image img');
      for (var j = genImgs.length - 1; j >= 0; j--) {
        if (genImgs[j].src && genImgs[j].src.indexOf('blob:') === 0) {
          console.log('[IMAGE] Found blob src in generated-image img');
          return genImgs[j].src;
        }
      }
      // Strategy 3: any img with blob: or googleusercontent src
      var allImgs = container.querySelectorAll('img');
      for (var k = allImgs.length - 1; k >= 0; k--) {
        var s = allImgs[k].src;
        if (s && (s.indexOf('blob:') === 0 || s.indexOf('googleusercontent.com') !== -1)) {
          console.log('[IMAGE] Found img via fallback');
          return s;
        }
      }
      return null;
    }

    // Scene-to-container index mapping (set after each submit)
    var sceneContainerMap = {};

    var _capturedContainerIds = {};

    function captureContainerForScene(sceneKey) {
      // Count containers BEFORE submit to know how many existed already
      var countBefore = document.querySelectorAll('.conversation-container').length;
      var attempts = 0;
      var maxAttempts = 20; // 20 x 500ms = 10s max wait

      var poll = setInterval(function() {
        attempts++;
        // Only match REAL containers (div.conversation-container), NOT pending-request.conversation-container
        // Gemini creates a temporary <pending-request> container first, then replaces it with the real <div>
        var containers = document.querySelectorAll('div.conversation-container');

        // Look for a container we haven't captured yet (by its id attribute)
        for (var i = containers.length - 1; i >= 0; i--) {
          var c = containers[i];
          // Skip pending-request containers (Angular will remove them)
          if (c.tagName === 'PENDING-REQUEST') continue;
          var cId = c.id || ('idx-' + i);
          if (!cId || cId.indexOf('idx-') === 0) continue; // Skip containers without a real id
          if (!_capturedContainerIds[cId]) {
            clearInterval(poll);
            _capturedContainerIds[cId] = sceneKey;
            sceneContainerMap[sceneKey] = c;
            console.log('[TRACK] Mapped scene ' + sceneKey + ' to container id=' + cId + ' (attempt ' + attempts + ')');
            injectSceneBadge(c, sceneKey);
            return;
          }
        }

        if (attempts >= maxAttempts) {
          clearInterval(poll);
          // Fallback: use last container even if already captured
          var last = containers[containers.length - 1];
          if (last) {
            sceneContainerMap[sceneKey] = last;
            console.warn('[TRACK] Fallback: mapped scene ' + sceneKey + ' to last container (attempt ' + attempts + ')');
            injectSceneBadge(last, sceneKey);
          }
        }
      }, 500);
    }

    function injectSceneBadge(container, sceneKey) {
      if (!container) return;
      var wrapperId = 'sts-badge-' + sceneKey;
      if (document.getElementById(wrapperId)) return;

      // Find the user-query element inside this conversation-container
      // Angular won't re-render user queries after submit, so this is stable
      var userQuery = container.querySelector('user-query');
      if (!userQuery) return;

      var badge = document.createElement('div');
      badge.id = wrapperId;
      badge.className = 'sts-scene-badge';
      badge.textContent = '[' + S.projectId + '|' + sceneKey + ']';
      badge.style.cssText = 'background:#00d4aa;color:#0d1117;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:700;font-family:monospace;display:inline-block;margin:4px 8px;';

      // Append inside user-query — each prompt gets its own badge
      userQuery.appendChild(badge);
    }

    function waitForImageGeneration(timeoutMs, projectId, sceneNum) {
      timeoutMs = timeoutMs || 180000;
      return new Promise(function(resolve) {
        var start = Date.now();
        var label = projectId + '|' + sceneNum;
        console.log('[IMAGE] Waiting for image for scene ' + label + ' (timeout: ' + (timeoutMs / 1000) + 's)');

        var checkInterval = setInterval(function() {
          // Try mapped container first
          var container = sceneContainerMap[sceneNum];

          // Fallback: if container not mapped yet, check the last conversation-container
          if (!container) {
            var allContainers = document.querySelectorAll('.conversation-container');
            if (allContainers.length > 0) {
              container = allContainers[allContainers.length - 1];
            }
          }

          if (container) {
            var modelResponse = container.querySelector('model-response');
            if (modelResponse) {
              var img = findImageInContainer(modelResponse);
              if (img) {
                clearInterval(checkInterval);
                // Also ensure container is mapped if it wasn't
                if (!sceneContainerMap[sceneNum]) {
                  sceneContainerMap[sceneNum] = container;
                  injectSceneBadge(container, sceneNum);
                }
                console.log('[IMAGE] Found for scene ' + label + ':', img.substring(0, 80) + '...');
                resolve(img);
                return;
              }
            }
          }

          var elapsed = Date.now() - start;

          // Check aria-busy="false" on the response's markdown div
          // This is the most reliable "generation complete" signal (from DOM activity analysis)
          if (container) {
            var markdownDiv = container.querySelector('.markdown[aria-busy="false"]');
            var footerDone = container.querySelector('.response-footer.complete, .response-footer.gap.complete');
            if (markdownDiv || footerDone) {
              // Generation is confirmed done — if no image found after 10s more, it failed
              if (elapsed > timeoutMs || elapsed > 30000) {
                clearInterval(checkInterval);
                console.error('[IMAGE] aria-busy=false but no image found for scene ' + label);
                resolve(null);
                return;
              }
            }
          }

          // Soft timeout: if past timeout and not generating, give up
          if (elapsed > timeoutMs && !isGeminiGenerating()) {
            clearInterval(checkInterval);
            console.error('[IMAGE] Timed out for scene ' + label + ' (soft)');
            resolve(null);
            return;
          }
          // Hard timeout: 2x the soft timeout — give up no matter what
          if (elapsed > timeoutMs * 2) {
            clearInterval(checkInterval);
            console.error('[IMAGE] Timed out for scene ' + label + ' (hard)');
            resolve(null);
            return;
          }
        }, 1000);
      });
    }

    // ── Get image as base64 ─────────────────────────
    function fetchImageAsBase64(imageUrl) {
      console.log('[FETCH] Getting image as base64...');

      // Strategy 1: XHR from content script (uses page cookies automatically)
      return new Promise(function(resolve) {
        var xhr = new XMLHttpRequest();
        xhr.open('GET', imageUrl, true);
        xhr.responseType = 'blob';
        xhr.withCredentials = true;
        xhr.onload = function() {
          if (xhr.status === 200) {
            var blob = xhr.response;
            var reader = new FileReader();
            reader.onload = function() {
              var sizeKB = Math.round(blob.size / 1024);
              console.log('[FETCH] XHR success (' + sizeKB + ' KB, ' + blob.type + ')');
              resolve(reader.result);
            };
            reader.onerror = function() {
              console.warn('[FETCH] FileReader failed, trying background...');
              fetchViaBackground(imageUrl, resolve);
            };
            reader.readAsDataURL(blob);
          } else {
            console.warn('[FETCH] XHR returned ' + xhr.status + ', trying background...');
            fetchViaBackground(imageUrl, resolve);
          }
        };
        xhr.onerror = function() {
          console.warn('[FETCH] XHR failed, trying background...');
          fetchViaBackground(imageUrl, resolve);
        };
        xhr.send();
      });
    }

    function fetchViaBackground(imageUrl, resolve) {
      chrome.runtime.sendMessage(
        { action: 'FETCH_IMAGE_BASE64', url: imageUrl },
        function(response) {
          if (response && response.success) {
            var sizeKB = Math.round(response.data.length * 3 / 4 / 1024);
            console.log('[FETCH] Background fetch success (' + sizeKB + ' KB)');
            resolve(response.data);
          } else {
            console.error('[FETCH] All fetch methods failed:', response ? response.error : 'no response');
            resolve(null);
          }
        }
      );
    }

    // ── Main Typing Loop ─────────────────────────────
    function startTyping() {
      if (S.typing.active || S.typing.starting) return;
      var tq = S.typing.queue;
      if (!tq.length) { console.log('No prompts'); return; }
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
      if (!runItems.length) { S.typing.starting = false; render(); return; }
      S.typing.runId++; S.typing.active = true; S.typing.starting = false; S.typing.typedCount = 0;
      render();
      console.log('=== Starting: ' + runItems.length + ' prompts ===');

      var seenImageUrls = {};
      document.querySelectorAll('img').forEach(function(img) {
        if (isValidImageSrc(img.src)) seenImageUrls[img.src] = true;
      });

      var idx = 0;
      function processNext() {
        if (S.typing.stopRequested || idx >= tq.length) {
          S.typing.active = false; S.typing.currentIndex = -1; render();
          var completed = 0, failed = 0;
          tq.forEach(function(q) { if (q.status === 'completed') completed++; if (q.status === 'error') failed++; });
          console.log('=== Done: ' + completed + ' ok, ' + failed + ' failed ===');
          if (completed === tq.length) sendWS({ type: 'JOB_COMPLETE', projectId: S.projectId });
          return;
        }
        var item = tq[idx];
        if (!item.selected || item.status === 'completed') { idx++; processNext(); return; }

        S.typing.currentIndex = idx; item.status = 'typing'; render();
        sendWS({ type: 'STATUS_UPDATE', scene: parseInt(item.scene), status: 'typing' });

        document.querySelectorAll('generated-image img.image.loaded').forEach(function(img) {
          if (img.src) seenImageUrls[img.src] = true;
        });

        // Check rate limit before starting
        var rateCheck = checkRateLimit();
        if (rateCheck) {
          S.typing.rateLimitReset = rateCheck.resetTime;
          item.status = 'queued'; render();
          waitForRateLimitReset(rateCheck.resetTime).then(function() {
            if (!S.typing.stopRequested) processNext(); // Retry same idx
          });
          return;
        }

        enableImageTool()
          .then(function() { console.log('[FLOW] Step 1: Typing prompt...'); return typeIntoGemini(item.fullPrompt); })
          .then(function() { console.log('[FLOW] Step 2: Waiting 1s before submit...'); return sleep(1000); })
          .then(function() { console.log('[FLOW] Step 3: Submitting...'); return submitPrompt(); })
          .then(function() {
            // Start polling for the new conversation container (async, non-blocking)
            captureContainerForScene(item.scene);
          })
          .then(function() {
            // Check rate limit after submit (it may appear after trying to generate)
            return sleep(2000).then(function() {
              var postSubmitLimit = checkRateLimit();
              if (postSubmitLimit) {
                console.log('[FLOW] Rate limit hit after submit!');
                S.typing.rateLimitReset = postSubmitLimit.resetTime;
                item.status = 'queued'; render();
                return waitForRateLimitReset(postSubmitLimit.resetTime).then(function() {
                  return 'RATE_LIMITED';
                });
              }
              return null;
            });
          })
          .then(function(signal) {
            if (signal === 'RATE_LIMITED') {
              if (!S.typing.stopRequested) processNext(); // Retry same idx
              return Promise.reject('RATE_LIMITED_SKIP');
            }
          })
          .then(function() {
            item.status = 'generating';
            if (S.scenes[item.queueKey]) S.scenes[item.queueKey].status = 'generating';
            render();
            sendWS({ type: 'STATUS_UPDATE', scene: parseInt(item.scene), status: 'generating' });
            return waitForImageGeneration(180000, item.projectId || S.projectId, item.scene);
          })
          .then(function(imageUrl) {
            if (S.typing.stopRequested) { item.status = 'queued'; return null; }
            if (imageUrl) {
              seenImageUrls[imageUrl] = true;
              if (S.scenes[item.queueKey]) S.scenes[item.queueKey].status = 'uploading';
              render();
              console.log('[FLOW] Scene ' + item.scene + ' image found, fetching base64...');
              return fetchImageAsBase64(imageUrl).then(function(b64) {
                if (b64) {
                  sendWS({ type: 'IMAGE_UPLOAD', projectId: item.projectId || S.projectId, scene: parseInt(item.scene),
                    image: { data: b64, source_url: imageUrl } });
                  item.status = 'completed'; item.imageUrl = imageUrl; S.typing.typedCount++;
                  if (S.scenes[item.queueKey]) { S.scenes[item.queueKey].status = 'done'; S.scenes[item.queueKey].imageUrl = imageUrl; }
                  console.log('Scene ' + item.scene + ' completed');
                } else {
                  item.status = 'error'; item.error = 'Fetch failed';
                  if (S.scenes[item.queueKey]) S.scenes[item.queueKey].status = 'error';
                }
              });
            } else {
              item.status = 'error'; item.error = 'Timed out';
              if (S.scenes[item.queueKey]) S.scenes[item.queueKey].status = 'error';
            }
            return null;
          })
          .then(function() {
            render(); idx++;
            var hasMore = tq.slice(idx).some(function(q) { return q.selected && q.status !== 'completed'; });
            if (hasMore && !S.typing.stopRequested) {
              var delay = 2000 + Math.floor(Math.random() * 4000); // 2-6 seconds
              console.log('Next in ' + (delay/1000).toFixed(1) + 's...'); setTimeout(processNext, delay);
            } else { processNext(); }
          })
          .catch(function(e) {
            if (e === 'RATE_LIMITED_SKIP') return; // Already handled
            console.error('Error scene ' + item.scene + ':', e.message || e);
            item.status = 'error'; item.error = e.message || String(e); render();
            idx++; setTimeout(processNext, 3000);
          });
      }
      processNext();
    }

    function stopTyping() { S.typing.stopRequested = true; render(); }

    // ── UI ───────────────────────────────────────────
    function $id(id) { return document.getElementById(id); }
    function escHtml(s) { var d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

    function injectUI() {
      if (document.getElementById('sts-sync')) return;
      var root = document.createElement('div');
      root.id = 'sts-sync';
      root.innerHTML =
        '<!-- Collapsed Pill -->' +
        '<div class="sts-pill" id="sts-pill">' +
          '<div class="sts-pill-dot" id="sts-pill-dot"></div>' +
          '<span class="sts-pill-label">STS Gemini</span>' +
          '<span class="sts-pill-proj" id="sts-pill-proj"></span>' +
          '<div class="sts-pill-counts">' +
            '<span class="sts-c-done" id="sts-pill-done">0</span>' +
            '<span class="sts-c-total" id="sts-pill-total">0</span>' +
          '</div>' +
        '</div>' +
        '<!-- Expanded Panel -->' +
        '<div class="sts-panel" id="sts-panel" style="display:none;">' +
          '<!-- Header -->' +
          '<div class="sts-head">' +
            '<div class="sts-head-left">' +
              '<div class="sts-head-dot" id="sts-head-dot"></div>' +
              '<h3>STS Gemini</h3>' +
              '<span class="sts-head-proj" id="sts-head-proj" style="display:none;"></span>' +
              '<span class="sts-head-port" id="sts-head-port" style="display:none;"></span>' +
              '<span class="sts-head-ar" id="sts-head-ar" style="display:none;"></span>' +
            '</div>' +
            '<div class="sts-head-btns">' +
              '<button class="sts-hb" id="sts-settings-btn" title="Settings">&#x2699;</button>' +
              '<button class="sts-hb" id="sts-collapse-btn" title="Collapse">&#x2715;</button>' +
            '</div>' +
          '</div>' +
          '<!-- Connection bar -->' +
          '<div class="sts-conn-bar" id="sts-conn-bar" style="display:none;">' +
            '<span id="sts-conn-icon"></span>' +
            '<span id="sts-conn-msg">Disconnected</span>' +
          '</div>' +
          '<!-- Rate limit -->' +
          '<div class="sts-rate-limit" id="sts-rate-limit" style="display:none;">' +
            '<span class="sts-rate-icon">&#x26A0;</span>' +
            '<div class="sts-rate-info">' +
              '<div class="sts-rate-title">Rate Limited</div>' +
              '<div class="sts-rate-sub" id="sts-rate-sub">Resets at --</div>' +
            '</div>' +
            '<div class="sts-rate-countdown" id="sts-rate-countdown">??:??:??</div>' +
          '</div>' +
          '<!-- Settings -->' +
          '<div class="sts-settings" id="sts-settings">' +
            '<label>WS URL</label>' +
            '<input type="text" class="sts-url-input" id="sts-url-input" />' +
            '<button class="sts-url-save" id="sts-url-save">Save</button>' +
          '</div>' +
          '<!-- Stats -->' +
          '<div class="sts-stats">' +
            '<div class="sts-stat"><span class="sts-sv sts-c-pend" id="sts-n-queue">0</span><span class="sts-sl">Queue</span></div>' +
            '<div class="sts-stat"><span class="sts-sv sts-c-done" id="sts-n-typed">0</span><span class="sts-sl">Typed</span></div>' +
            '<div class="sts-stat"><span class="sts-sv sts-c-rdy" id="sts-n-done">0</span><span class="sts-sl">Done</span></div>' +
            '<div class="sts-stat"><span class="sts-sv sts-c-sent" id="sts-n-sent">0</span><span class="sts-sl">Sent</span></div>' +
          '</div>' +
          '<!-- Tabs -->' +
          '<div class="sts-tabs">' +
            '<button class="sts-tab active" data-tab="typing">Typing</button>' +
            '<button class="sts-tab" data-tab="sync">Sync</button>' +
          '</div>' +
          '<!-- Progress -->' +
          '<div class="sts-progress">' +
            '<div class="sts-prog-track"><div class="sts-prog-fill" id="sts-prog-fill"></div></div>' +
            '<span class="sts-prog-label" id="sts-prog-label">No scenes loaded</span>' +
          '</div>' +
          '<!-- List -->' +
          '<div class="sts-list" id="sts-list">' +
            '<div class="sts-empty"><div class="sts-empty-icon">&#x1F3A8;</div>No scenes loaded yet.</div>' +
          '</div>' +
          '<!-- Actions -->' +
          '<div class="sts-actions">' +
            '<button class="sts-btn sts-btn-primary" id="sts-action-btn">Start Typing</button>' +
            '<button class="sts-btn sts-btn-warn" id="sts-retry-btn" style="display:none;">Retry Failed</button>' +
            '<button class="sts-btn" id="sts-clear-btn" style="background:#374151;color:#9ca3af;font-size:11px;padding:6px 12px;">CLEAR</button>' +
          '</div>' +
        '</div>';
      document.body.appendChild(root);

      // Event handlers — draggable pill
      (function() {
        var pill = $id('sts-pill');
        var dragging = false, hasMoved = false, ox, oy;
        pill.addEventListener('mousedown', function(e) {
          dragging = true; hasMoved = false;
          ox = e.clientX - pill.getBoundingClientRect().left;
          oy = e.clientY - pill.getBoundingClientRect().top;
          e.preventDefault();
        });
        document.addEventListener('mousemove', function(e) {
          if (!dragging) return;
          hasMoved = true;
          pill.style.left = (e.clientX - ox) + 'px';
          pill.style.top = (e.clientY - oy) + 'px';
          pill.style.right = 'auto';
          pill.style.bottom = 'auto';
        });
        document.addEventListener('mouseup', function() {
          if (dragging && !hasMoved) {
            S.collapsed = false;
            localStorage.setItem('sts-gemini-collapsed', 'false');
            $id('sts-pill').style.display = 'none';
            $id('sts-panel').style.display = '';
            render();
          }
          dragging = false;
        });
      })();
      $id('sts-collapse-btn').addEventListener('click', function() {
        S.collapsed = true;
        localStorage.setItem('sts-gemini-collapsed', 'true');
        $id('sts-panel').style.display = 'none';
        $id('sts-pill').style.display = '';
        render();
      });
      $id('sts-settings-btn').addEventListener('click', function() {
        S.showSettings = !S.showSettings;
        $id('sts-settings').classList.toggle('open', S.showSettings);
        $id('sts-settings-btn').classList.toggle('active', S.showSettings);
        if (S.showSettings) $id('sts-url-input').value = S.wsUrl;
      });
      $id('sts-url-save').addEventListener('click', function() {
        var val = $id('sts-url-input').value.trim();
        if (val) {
          S.wsUrl = val;
          localStorage.setItem('sts-gemini-ws', val);
          localStorage.setItem('sts-gemini-ws-manual', val);
        } else {
          // Clear manual override → re-enable auto-discovery
          localStorage.removeItem('sts-gemini-ws-manual');
        }
        S.wsConnected = false;
        chrome.runtime.sendMessage({ action: 'STS_WS_RECONNECT', manualUrl: val || null });
        render();
      });
      // Tabs
      var tabs = root.querySelectorAll('.sts-tab');
      for (var ti = 0; ti < tabs.length; ti++) {
        tabs[ti].addEventListener('click', function() {
          root.querySelectorAll('.sts-tab').forEach(function(t) { t.classList.remove('active'); });
          this.classList.add('active');
          S.activeTab = this.dataset.tab;
          render();
        });
      }

      $id('sts-action-btn').addEventListener('click', function() {
        if (S.typing.active) { stopTyping(); } else { startTyping(); }
      });
      $id('sts-clear-btn').addEventListener('click', function() {
        if (S.typing.active) { stopTyping(); }
        S.typing.queue = [];
        S.scenes = {};
        S.projectId = null;
        S.typing.typedCount = 0;
        S.typing.currentIndex = -1;
        _capturedContainerIds = {};
        sceneContainerMap = {};
        // Remove all badges from DOM
        document.querySelectorAll('.sts-scene-badge').forEach(function(b) { b.remove(); });
        console.log('[STS] Cleared all jobs');
        render();
      });
      $id('sts-retry-btn').addEventListener('click', function() {
        // Reset all error/timed-out items to queued
        var retried = 0;
        S.typing.queue.forEach(function(q) {
          if (q.status === 'error') {
            q.status = 'queued';
            q.error = null;
            if (S.scenes[q.scene]) S.scenes[q.scene].status = 'pending';
            retried++;
          }
        });
        console.log('[STS] Retrying ' + retried + ' failed scenes');
        render();
        if (retried > 0 && !S.typing.active) startTyping();
      });

      // Per-scene retry buttons (delegated)
      $id('sts-panel').addEventListener('click', function(e) {
        var btn = e.target.closest('.sts-retry-scene-btn');
        if (!btn) return;
        var sceneKey = btn.getAttribute('data-scene');
        var item = S.typing.queue.find(function(q) { return String(q.scene) === sceneKey; });
        if (item && item.status === 'error') {
          item.status = 'queued';
          item.error = null;
          if (S.scenes[sceneKey]) S.scenes[sceneKey].status = 'pending';
          console.log('[STS] Retrying scene ' + sceneKey);
          render();
          if (!S.typing.active) startTyping();
        }
      });
      // Delegate thumbnail clicks for image overlay
      $id('sts-list').addEventListener('click', function(e) {
        var thumb = e.target.closest('.sts-row-thumb');
        if (!thumb || !thumb.src) return;
        e.stopPropagation();
        var overlay = document.getElementById('sts-img-overlay');
        if (overlay) overlay.remove();
        overlay = document.createElement('div');
        overlay.id = 'sts-img-overlay';
        overlay.innerHTML = '<img src="' + thumb.src + '" alt="Scene preview">';
        overlay.onclick = function() { overlay.remove(); };
        document.body.appendChild(overlay);
      });

      // Initial state
      if (!S.collapsed) {
        $id('sts-pill').style.display = 'none';
        $id('sts-panel').style.display = '';
      }
    }

    function render() {
      if (!document.getElementById('sts-sync')) injectUI();
      var tq = S.typing.queue;
      var total = tq.length, completed = 0, failed = 0;
      tq.forEach(function(q) { if (q.status === 'completed') completed++; if (q.status === 'error') failed++; });
      var pct = total > 0 ? Math.round(completed / total * 100) : 0;
      var wsOn = S.wsConnected;

      // Pill
      var pillDot = $id('sts-pill-dot');
      if (pillDot) pillDot.classList.toggle('on', wsOn);
      var pillProj = $id('sts-pill-proj');
      if (pillProj) pillProj.textContent = S.projectId || '';
      var pillDone = $id('sts-pill-done');
      if (pillDone) pillDone.textContent = completed;
      var pillTotal = $id('sts-pill-total');
      if (pillTotal) pillTotal.textContent = total;

      // Header
      var headDot = $id('sts-head-dot');
      if (headDot) headDot.classList.toggle('on', wsOn);
      var headProj = $id('sts-head-proj');
      if (headProj) { headProj.textContent = S.projectId || ''; headProj.style.display = S.projectId ? '' : 'none'; }
      try {
        var portMatch = S.wsUrl.match(/:(\d+)/);
        var headPort = $id('sts-head-port');
        if (headPort) { headPort.textContent = portMatch ? ':' + portMatch[1] : ''; headPort.style.display = portMatch ? '' : 'none'; }
      } catch(e) {}
      var headAr = $id('sts-head-ar');
      if (headAr) { headAr.textContent = S.aspectRatio || ''; headAr.style.display = S.aspectRatio ? '' : 'none'; }

      // Connection bar — always visible, reflects real-time WS state
      var connBar = $id('sts-conn-bar');
      if (connBar) {
        connBar.style.display = 'flex';
        var connIcon = $id('sts-conn-icon');
        var connMsg = $id('sts-conn-msg');
        if (wsOn) {
          connBar.classList.add('ok');
          if (connIcon) connIcon.textContent = '\u2713';
          if (connMsg) connMsg.textContent = 'Connected';
        } else {
          connBar.classList.remove('ok');
          if (connIcon) connIcon.textContent = '\u26A0';
          if (connMsg) connMsg.textContent = 'Disconnected';
        }
      }

      // Rate limit
      var rlEl = $id('sts-rate-limit');
      if (rlEl) {
        if (S.typing.rateLimited) {
          rlEl.style.display = 'flex';
          var rlSub = $id('sts-rate-sub');
          if (rlSub) rlSub.textContent = S.typing.rateLimitReset ? 'Resets at ' + S.typing.rateLimitReset.toLocaleTimeString() : 'Resets at unknown';
          var rlCd = $id('sts-rate-countdown');
          if (rlCd) rlCd.textContent = S.typing.rateLimitReset ? formatCountdown(S.typing.rateLimitReset) : '??:??:??';
        } else {
          rlEl.style.display = 'none';
        }
      }

      // Stats
      var queued = tq.filter(function(q) { return q.status === 'queued'; }).length;
      var typed = tq.filter(function(q) { return q.status === 'completed' || q.status === 'generating'; }).length;
      var sent = tq.filter(function(q) { return q.status === 'sent'; }).length;
      var nQueue = $id('sts-n-queue'); if (nQueue) nQueue.textContent = queued;
      var nTyped = $id('sts-n-typed'); if (nTyped) nTyped.textContent = typed;
      var nDone = $id('sts-n-done'); if (nDone) nDone.textContent = completed;
      var nSent = $id('sts-n-sent'); if (nSent) nSent.textContent = sent;

      // Progress
      var fill = $id('sts-prog-fill'); if (fill) fill.style.width = pct + '%';
      var label = $id('sts-prog-label');
      if (label) {
        if (S.typing.active) {
          var ci = S.typing.currentIndex;
          label.textContent = ci >= 0 ? 'Typing ' + (ci + 1) + '/' + total : 'Typing...';
        } else if (total > 0) {
          label.textContent = completed === total ? 'All done' : completed + '/' + total + ' completed';
        } else {
          label.textContent = 'No scenes loaded';
        }
      }

      // Action button
      var btn = $id('sts-action-btn');
      if (btn) {
        if (S.typing.active) {
          btn.textContent = 'Stop'; btn.className = 'sts-btn sts-btn-danger';
        } else if (S.typing.starting) {
          btn.textContent = 'Starting...'; btn.className = 'sts-btn sts-btn-primary'; btn.disabled = true;
        } else {
          btn.textContent = total > 0 ? 'Start Typing' : 'Waiting for Job'; btn.className = 'sts-btn sts-btn-primary'; btn.disabled = false;
        }
      }

      // Retry button — show when there are errors and not currently typing
      var retryBtn = $id('sts-retry-btn');
      if (retryBtn) {
        var hasErrors = tq.some(function(q) { return q.status === 'error'; });
        retryBtn.style.display = (hasErrors && !S.typing.active) ? '' : 'none';
      }

      // List
      var list = $id('sts-list');
      if (!list) return;

      if (S.activeTab === 'typing') {
        // ── Typing tab ──
        if (!tq.length) {
          list.innerHTML = '<div class="sts-empty"><div class="sts-empty-icon">&#x1F3A8;</div>No scenes loaded yet.</div>';
          return;
        }
        list.innerHTML = tq.map(function(item, si) {
          var pr = (item.displayPrompt || '').length > 46 ? item.displayPrompt.substring(0, 46) + '...' : item.displayPrompt || '';
          var sHTML = '', meta = '';
          var isCurrent = S.typing.active && si === S.typing.currentIndex;
          if (item.status === 'queued') { sHTML = '<div class="sts-d-q"></div>'; meta = 'queued'; }
          else if (item.status === 'typing') { sHTML = '<div class="sts-d-typing"></div>'; meta = 'typing...'; }
          else if (item.status === 'generating') { sHTML = '<div class="sts-d-gen"></div>'; meta = 'generating...'; }
          else if (item.status === 'completed') { sHTML = '<span class="sts-d-done">&#x2714;</span>'; meta = 'done'; }
          else if (item.status === 'error') { sHTML = '<span class="sts-d-err">&#x2718;</span>'; meta = 'error'; }
          var rowCls = 'sts-row' + (isCurrent ? ' highlight' : '') + (item.status === 'error' ? ' error-row' : '');
          var thumbHtml = item.imageUrl
            ? '<img class="sts-row-thumb" src="' + item.imageUrl + '" alt="">'
            : '<div class="sts-row-thumb sts-row-thumb-empty">' + item.scene + '</div>';
          var errHtml = item.error ? '<div class="sts-row-error">' + escHtml(item.error) + '</div>' : '';
          var retryHtml = item.status === 'error'
            ? '<button class="sts-retry-scene-btn" data-scene="' + item.scene + '" style="background:#f39c12;color:#0d1117;border:none;padding:2px 8px;border-radius:3px;font-size:10px;font-weight:700;cursor:pointer;margin-top:2px;">RETRY</button>'
            : '';
          var pidLabel = item.projectId ? '<span style="color:#00d4aa;font-size:9px;font-family:monospace;margin-right:4px;">' + item.projectId + '</span>' : '';
          return '<div class="' + rowCls + '">' +
            thumbHtml +
            '<div class="sts-row-num">' + item.scene + '</div>' +
            '<div class="sts-row-info">' +
              '<div class="sts-row-prompt">' + pidLabel + escHtml(pr) + '</div>' +
              '<div class="sts-row-meta">' + meta + '</div>' +
              errHtml + retryHtml +
            '</div>' +
            '<div class="sts-row-status">' + sHTML + '</div>' +
          '</div>';
        }).join('');
      } else {
        // ── Sync tab — shows image upload/save status per scene ──
        var sceneKeys = Object.keys(S.scenes).sort(function(a, b) {
          var na = parseInt(a.split('|').pop()); var nb = parseInt(b.split('|').pop());
          return (isNaN(na) ? 0 : na) - (isNaN(nb) ? 0 : nb);
        });
        if (!sceneKeys.length) {
          list.innerHTML = '<div class="sts-empty"><div class="sts-empty-icon">&#x1F4E1;</div>Waiting for generations...</div>';
          return;
        }
        list.innerHTML = sceneKeys.map(function(key) {
          var sc = S.scenes[key];
          var parts = key.split('|');
          var sceneNum = parts.length > 1 ? parts[1] : parts[0];
          var pid = sc.projectId || (parts.length > 1 ? parts[0] : '');
          var pr = (sc.prompt || '').length > 46 ? sc.prompt.substring(0, 46) + '...' : sc.prompt || '';
          var badgeMap = {
            pending: ['pending', 'pending'],
            generating: ['generating', 'generating...'],
            uploading: ['uploading', 'uploading...'],
            done: ['done', 'saved'],
            error: ['error', 'error']
          };
          var badge = badgeMap[sc.status] || ['pending', sc.status];
          var thumbHtml = sc.imageUrl
            ? '<img class="sts-row-thumb" src="' + sc.imageUrl + '" alt="">'
            : '<div class="sts-row-thumb sts-row-thumb-empty">' + sceneNum + '</div>';
          var pidLabel = pid ? '<span style="color:#00d4aa;font-size:9px;font-family:monospace;margin-right:4px;">' + pid + '</span>' : '';
          return '<div class="sts-row">' +
            thumbHtml +
            '<div class="sts-row-num">' + sceneNum + '</div>' +
            '<div class="sts-row-info">' +
              '<div class="sts-row-prompt">' + pidLabel + escHtml(pr) + '</div>' +
              '<div class="sts-row-meta">' + badge[1] + '</div>' +
            '</div>' +
            '<span class="sts-card-badge sts-badge-' + badge[0] + '">' + badge[1] + '</span>' +
          '</div>';
        }).join('');
      }
    }

    // ── Boot ─────────────────────────────────────────
    injectUI();
    render();
    console.log('STS Gemini Synchronizer initialized');
  }
})();
