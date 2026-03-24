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
    } else if (request.action === 'STS_STOP') {
      console.log('[STS Gemini] STOP received');
      if (window.__stsGeminiState) {
        window.__stsGeminiState.typing.stopRequested = true;
        if (window.__stsGeminiState.ws) {
          try { window.__stsGeminiState.ws.close(); } catch(e) {}
        }
      }
      var panel = document.getElementById('sts-gemini-panel');
      if (panel) panel.remove();
      window.__stsGeminiActive = false;
      chrome.storage.local.set({ stsRunning: false });
      sendResponse({ ok: true });
    }
  });

  // Always auto-start on Gemini — connect WS and show panel
  chrome.storage.local.get(['stsWsUrl'], function(data) {
    console.log('[STS Gemini] Auto-starting on page load');
    setTimeout(function() {
      initSync(data.stsWsUrl || null);
    }, 2000);
  });

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
      ws: null,
      wsConnected: false,
      wsReconnectTimer: null,
      activeTab: 'queue', // 'queue' or 'sync'
      syncHistory: [], // { projectId, scene, status, timestamp, sizeKB, imageUrl }
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

    // ── WebSocket ─────────────────────────────────────
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
          S.ws.send(JSON.stringify({ type: 'EXTENSION_READY', source: 'sts-gemini-ext' }));
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
          var pid = msg.projectId;
          var jobAspect = msg.aspectRatio || '';
          var scenes = msg.scenes || [];
          console.log('[STS WS] IMAGE_JOB:', pid, '-', scenes.length, 'scenes', 'aspect:', jobAspect);

          // Always clear queue on new IMAGE_JOB — every job is a fresh request
          console.log('[STS WS] New job, clearing queue');
          S.typing.queue = [];
          S.typing.active = false;
          S.typing.starting = false;
          S.typing.currentIndex = -1;
          S.projectId = pid;
          S.aspectRatio = jobAspect;

          for (var si = 0; si < scenes.length; si++) {
            var sc = scenes[si];
            var k = String(sc.scene);
            var scAspect = sc.aspectRatio || jobAspect || '';
            var arSuffix = scAspect ? ' aspect ratio ' + scAspect : '';
            S.typing.queue.push({
              projectId: pid, scene: k, displayPrompt: sc.prompt,
              aspectRatio: scAspect,
              fullPrompt: sc.prompt + arSuffix + ' [' + pid + '|' + sc.scene + ']',
              selected: true, status: 'queued', error: null,
            });
          }
          render();
          if (msg.autoType && !S.typing.active && !S.typing.starting) {
            console.log('[STS WS] Auto-starting typing');
            setTimeout(function() { startTyping(); }, 2000);
          }
          break;
        }
        case 'PONG': break;
        case 'NAVIGATE': {
          var url = msg.url;
          if (url) {
            console.log('[STS WS] NAVIGATE received, redirecting to:', url);
            // Small delay to let any final renders complete
            setTimeout(function() {
              window.location.href = url;
            }, 1500);
          }
          break;
        }
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

    function waitForImageGeneration(timeoutMs, knownUrls) {
      timeoutMs = timeoutMs || 120000;
      knownUrls = knownUrls || {};
      return new Promise(function(resolve) {
        var start = Date.now();
        var seenLoading = false;
        var stableCount = 0;
        var requiredStable = 5;
        console.log('Waiting for image (timeout: ' + (timeoutMs / 1000) + 's)...');

        var checkInterval = setInterval(function() {
          var generating = isGeminiGenerating();
          if (generating) {
            if (!seenLoading) { seenLoading = true; console.log('Generation started'); }
            stableCount = 0;
          } else {
            if (seenLoading) {
              stableCount++;
              var showMore = document.querySelector('button[aria-label*="Show more"]');
              var regenerate = document.querySelector('button[aria-label*="Regenerate"]');
              var modifyResponse = document.querySelector('button[aria-label*="Modify response"]');
              if (showMore || regenerate || modifyResponse) {
                console.log('Completion buttons detected');
                stableCount = requiredStable;
              }
            } else {
              if (Date.now() - start > 15000) {
                var dlBtn = document.querySelector('mat-icon[fonticon="download"]');
                if (dlBtn) { seenLoading = true; stableCount = requiredStable; }
              }
            }
          }

          if (seenLoading && stableCount >= requiredStable) {
            clearInterval(checkInterval);
            console.log('[IMAGE] Generation stable. Searching for image...');

            // Helper: find first NEW image URL not in knownUrls
            function findNewImage(imgs) {
              for (var i = imgs.length - 1; i >= 0; i--) {
                var src = imgs[i].src;
                if (src && src.indexOf('http') === 0 && !knownUrls[src]) {
                  return src;
                }
              }
              return null;
            }

            // Strategy 1: single-image button > img (exact Gemini DOM path)
            var singleImgs = document.querySelectorAll('single-image button.image-button img');
            console.log('[IMAGE] single-image button img:', singleImgs.length);
            var newUrl1 = findNewImage(singleImgs);
            if (newUrl1) {
              console.log('[IMAGE] Found NEW (single-image):', newUrl1.substring(0, 80) + '...');
              resolve(newUrl1); return;
            }

            // Strategy 2: generated-image img.image.loaded
            var genImgs = document.querySelectorAll('generated-image img.image.loaded');
            console.log('[IMAGE] generated-image img.loaded:', genImgs.length);
            var newUrl2 = findNewImage(genImgs);
            if (newUrl2) {
              console.log('[IMAGE] Found NEW (generated-image):', newUrl2.substring(0, 80) + '...');
              resolve(newUrl2); return;
            }

            // Strategy 3: any img with Gemini CDN URL pattern
            var allImgs = document.querySelectorAll('img');
            for (var i = allImgs.length - 1; i >= 0; i--) {
              if (allImgs[i].src && allImgs[i].src.indexOf('lh3.googleusercontent.com/gg') !== -1) {
                console.log('[IMAGE] Found (CDN fallback):', allImgs[i].src.substring(0, 80) + '...');
                resolve(allImgs[i].src); return;
              }
            }

            console.warn('[IMAGE] Generation complete but no image found. Dumping all img srcs:');
            document.querySelectorAll('img').forEach(function(img, idx) {
              if (img.src && img.src.indexOf('data:') !== 0) {
                console.log('[IMAGE]   img[' + idx + '] class="' + img.className + '" src="' + img.src.substring(0, 60) + '..."');
              }
            });
            resolve(null); return;
          }

          if (Date.now() - start > timeoutMs) {
            clearInterval(checkInterval); console.error('Timed out'); resolve(null);
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
      document.querySelectorAll('generated-image img.image.loaded').forEach(function(img) {
        if (img.src) seenImageUrls[img.src] = true;
      });

      var idx = 0;
      var completedProjects = {}; // Track which projects have been signaled complete
      function processNext() {
        if (S.typing.stopRequested || idx >= tq.length) {
          S.typing.active = false; S.typing.currentIndex = -1; render();
          var completed = 0, failed = 0;
          tq.forEach(function(q) { if (q.status === 'completed') completed++; if (q.status === 'error') failed++; });
          console.log('=== Done: ' + completed + ' ok, ' + failed + ' failed ===');
          // Send JOB_COMPLETE for each project whose scenes are all done
          _checkProjectCompletions(completedProjects);
          return;
        }
        var item = tq[idx];
        if (!item.selected || item.status === 'completed') { idx++; processNext(); return; }

        S.typing.currentIndex = idx; item.status = 'typing'; render();
        sendWS({ type: 'STATUS_UPDATE', projectId: item.projectId, scene: parseInt(item.scene), status: 'typing' });

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
            item.status = 'generating'; render();
            sendWS({ type: 'STATUS_UPDATE', projectId: item.projectId, scene: parseInt(item.scene), status: 'generating' });
            return waitForImageGeneration(120000, seenImageUrls);
          })
          .then(function(imageUrl) {
            if (S.typing.stopRequested) { item.status = 'queued'; return null; }
            if (imageUrl && !seenImageUrls[imageUrl]) {
              seenImageUrls[imageUrl] = true;
              return fetchImageAsBase64(imageUrl).then(function(b64) {
                if (b64) {
                  sendWS({ type: 'IMAGE_UPLOAD', projectId: item.projectId, scene: parseInt(item.scene),
                    image: { data: b64, source_url: imageUrl } });
                  item.status = 'completed'; item.imageUrl = imageUrl; S.typing.typedCount++;
                  var sizeKB = Math.round(b64.length * 3 / 4 / 1024);
                  S.syncHistory.push({
                    projectId: item.projectId, scene: item.scene, status: 'uploaded',
                    timestamp: new Date().toLocaleTimeString(), sizeKB: sizeKB, imageUrl: imageUrl,
                  });
                  console.log('[' + item.projectId + '] Scene ' + item.scene + ' completed (' + sizeKB + ' KB)');
                  // Check if this project is now complete
                  _checkProjectCompletions(completedProjects);
                } else {
                  item.status = 'error'; item.error = 'Fetch failed';
                  S.syncHistory.push({
                    projectId: item.projectId, scene: item.scene, status: 'failed',
                    timestamp: new Date().toLocaleTimeString(), sizeKB: 0, imageUrl: null,
                  });
                }
              });
            } else if (!imageUrl) {
              item.status = 'error'; item.error = 'Timed out';
            } else { item.status = 'error'; item.error = 'Duplicate'; }
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

    function _checkProjectCompletions(sent) {
      // Group queue items by projectId and send JOB_COMPLETE for fully done projects
      var projects = {};
      S.typing.queue.forEach(function(q) {
        if (!projects[q.projectId]) projects[q.projectId] = { total: 0, done: 0 };
        projects[q.projectId].total++;
        if (q.status === 'completed') projects[q.projectId].done++;
      });
      for (var pid in projects) {
        if (projects[pid].done === projects[pid].total && !sent[pid]) {
          sent[pid] = true;
          sendWS({ type: 'JOB_COMPLETE', projectId: pid });
          console.log('[JOB_COMPLETE] All scenes done for', pid);
        }
      }
    }

    // ── UI Overlay ───────────────────────────────────
    function injectPanelStyles() {
      if (document.getElementById('sts-gemini-styles')) return;
      var style = document.createElement('style');
      style.id = 'sts-gemini-styles';
      style.textContent =
        '@import url("https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,400;9..40,500;9..40,700&family=JetBrains+Mono:wght@400;600&display=swap");' +
        '#sts-gemini-panel{--sts-bg:#0c0e14;--sts-sf:#12151e;--sts-el:#1a1e2a;--sts-bd:#1f2536;--sts-t1:#e2e8f0;--sts-t2:#64748b;--sts-tm:#475569;--sts-ac:#2dd4bf;--sts-ad:#2dd4bf33;--sts-dn:#f87171;--sts-dd:#f8717133;--sts-ok:#34d399;--sts-od:#34d39933;--sts-am:#fbbf24;}' +
        '#sts-gemini-panel *,#sts-gemini-panel *::before,#sts-gemini-panel *::after{box-sizing:border-box;}' +
        '#sts-gemini-panel{position:fixed;top:0;right:0;z-index:99999;font-family:"DM Sans",sans-serif;font-size:12px;color:var(--sts-t1);}' +
        /* Collapsed pill */
        '#sts-gemini-panel.sts-c{top:14px;right:14px;background:var(--sts-bg);border:1px solid var(--sts-bd);border-radius:100px;padding:10px 18px;cursor:pointer;display:flex;align-items:center;gap:10px;box-shadow:0 4px 24px rgba(0,0,0,0.5),0 0 0 1px rgba(45,212,191,0.06);backdrop-filter:blur(20px) saturate(1.5);transition:transform .15s,box-shadow .15s;}' +
        '#sts-gemini-panel.sts-c:hover{transform:translateY(-2px);box-shadow:0 6px 28px rgba(0,0,0,0.6),0 0 20px rgba(45,212,191,0.08);}' +
        '.sts-pd{width:7px;height:7px;border-radius:50%;flex-shrink:0;}' +
        '.sts-pt{font-weight:700;font-size:12px;letter-spacing:-.2px;}' +
        '.sts-pc{font-family:"JetBrains Mono",monospace;font-size:11px;color:var(--sts-tm);}' +
        /* Expanded */
        '#sts-gemini-panel.sts-e{background:var(--sts-bg);border-left:1.5px solid rgba(255,255,255,0.10);border-radius:0;width:420px;height:100vh;overflow:hidden;display:flex;flex-direction:column;box-shadow:0 24px 80px rgba(0,0,0,0.55),0 0 0 1px rgba(255,255,255,0.03) inset;backdrop-filter:blur(24px) saturate(1.4);animation:sts-sl .3s cubic-bezier(.16,1,.3,1);}' +
        '@keyframes sts-sl{from{opacity:0;transform:translateX(20px)}to{opacity:1;transform:translateX(0)}}' +
        /* Header */
        '.sts-hd{padding:16px 20px 14px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--sts-bd);background:linear-gradient(180deg,rgba(45,212,191,0.06) 0%,transparent 100%);flex-shrink:0;position:relative;}' +
        '.sts-hd::after{content:"";position:absolute;bottom:0;left:16px;right:16px;height:1px;background:linear-gradient(90deg,transparent,var(--sts-ad),transparent);}' +
        '.sts-hl{display:flex;align-items:center;gap:10px;}' +
        '.sts-lg{width:26px;height:26px;border-radius:7px;background:linear-gradient(135deg,var(--sts-ac),#06b6d4);display:flex;align-items:center;justify-content:center;font-family:"JetBrains Mono",monospace;font-weight:600;font-size:9px;color:#0c0e14;letter-spacing:-.5px;flex-shrink:0;box-shadow:0 0 14px var(--sts-ad);}' +
        '.sts-ti{font-weight:700;font-size:13px;letter-spacing:-.3px;}' +
        '.sts-wb{display:inline-flex;align-items:center;gap:5px;padding:2px 8px 2px 6px;border-radius:100px;font-family:"JetBrains Mono",monospace;font-size:9px;font-weight:600;letter-spacing:.4px;text-transform:uppercase;}' +
        '.sts-wb.on{background:var(--sts-od);color:var(--sts-ok);border:1px solid rgba(52,211,153,.15);}' +
        '.sts-wb.off{background:var(--sts-dd);color:var(--sts-dn);border:1px solid rgba(248,113,113,.15);}' +
        '.sts-wd{width:5px;height:5px;border-radius:50%;}' +
        '.sts-wb.on .sts-wd{background:var(--sts-ok);box-shadow:0 0 6px var(--sts-ok);animation:sts-p 2s ease-in-out infinite;}' +
        '.sts-wb.off .sts-wd{background:var(--sts-dn);box-shadow:0 0 6px var(--sts-dn);}' +
        '@keyframes sts-p{0%,100%{opacity:1}50%{opacity:.4}}' +
        '.sts-ha{display:flex;gap:2px;}' +
        '.sts-ib{background:none;border:1px solid transparent;color:var(--sts-tm);cursor:pointer;font-size:14px;padding:4px 6px;border-radius:6px;transition:all .15s;line-height:1;}' +
        '.sts-ib:hover{color:var(--sts-t1);background:var(--sts-el);border-color:var(--sts-bd);}' +
        /* Rate limit */
        '.sts-rl{padding:10px 16px;background:rgba(248,113,113,.08);border-bottom:1px solid rgba(248,113,113,.12);display:flex;align-items:center;gap:10px;flex-shrink:0;}' +
        '.sts-ri{font-size:18px;flex-shrink:0;filter:drop-shadow(0 0 4px rgba(248,113,113,.4));}' +
        '.sts-rf{flex:1;}' +
        '.sts-rt{color:var(--sts-dn);font-weight:700;font-size:11px;letter-spacing:.3px;text-transform:uppercase;}' +
        '.sts-rs{color:#f8717199;font-size:10px;margin-top:1px;}' +
        '.sts-rc{font-family:"JetBrains Mono",monospace;font-size:18px;font-weight:600;color:#fff;background:rgba(248,113,113,.15);border:1px solid rgba(248,113,113,.2);padding:4px 12px;border-radius:8px;min-width:86px;text-align:center;letter-spacing:1px;}' +
        /* Project */
        '.sts-pj{padding:6px 16px;font-family:"JetBrains Mono",monospace;font-size:10px;color:var(--sts-tm);border-bottom:1px solid var(--sts-bd);letter-spacing:.3px;flex-shrink:0;}' +
        '.sts-pj b{color:var(--sts-t2);font-weight:600;}' +
        /* Stats */
        '.sts-ss{padding:12px 16px 14px;flex-shrink:0;}' +
        '.sts-sr{display:flex;gap:16px;margin-bottom:10px;}' +
        '.sts-st{display:flex;align-items:baseline;gap:4px;}' +
        '.sts-sn{font-family:"JetBrains Mono",monospace;font-weight:600;font-size:14px;}' +
        '.sts-sl{font-size:10px;color:var(--sts-tm);text-transform:uppercase;letter-spacing:.5px;}' +
        '.sts-pk{height:4px;background:var(--sts-el);border-radius:4px;overflow:hidden;margin-bottom:12px;}' +
        '.sts-pf{height:100%;border-radius:4px;background:linear-gradient(90deg,var(--sts-ac),#06b6d4);transition:width .4s cubic-bezier(.4,0,.2,1);position:relative;}' +
        '.sts-pf::after{content:"";position:absolute;inset:0;background:linear-gradient(90deg,transparent,rgba(255,255,255,.15) 50%,transparent);animation:sts-sh 2s ease-in-out infinite;}' +
        '@keyframes sts-sh{0%{transform:translateX(-100%)}100%{transform:translateX(100%)}}' +
        '.sts-ab{width:100%;padding:10px;border:none;border-radius:10px;font-family:"DM Sans",sans-serif;font-size:12px;font-weight:700;cursor:pointer;letter-spacing:.2px;transition:all .15s;overflow:hidden;}' +
        '.sts-ab:active{transform:scale(.98);}' +
        '.sts-ab.go{background:linear-gradient(135deg,#2dd4bf,#06b6d4);color:#0c0e14;box-shadow:0 2px 12px var(--sts-ad);}' +
        '.sts-ab.go:hover{box-shadow:0 4px 20px var(--sts-ad);}' +
        '.sts-ab.ht{background:linear-gradient(135deg,#f87171,#ef4444);color:#fff;box-shadow:0 2px 12px var(--sts-dd);}' +
        '.sts-ab.ht:hover{box-shadow:0 4px 20px var(--sts-dd);}' +
        /* Project header in scene list */
        '.sts-ph{padding:8px 14px;background:linear-gradient(90deg,rgba(45,212,191,.06),transparent);border-bottom:1px solid var(--sts-bd);border-top:1px solid var(--sts-bd);display:flex;align-items:center;justify-content:space-between;gap:8px;position:sticky;top:0;z-index:1;backdrop-filter:blur(8px);}' +
        '.sts-ph+.sts-ph{border-top:none;}' +
        /* Scene list */
        '.sts-scl{overflow-y:auto;border-top:1px solid var(--sts-bd);flex:1;min-height:0;}' +
        '.sts-scl::-webkit-scrollbar{width:4px;}' +
        '.sts-scl::-webkit-scrollbar-track{background:transparent;}' +
        '.sts-scl::-webkit-scrollbar-thumb{background:var(--sts-bd);border-radius:4px;}' +
        '.sts-si{padding:8px 12px 8px 14px;border-left:3px solid transparent;transition:background .12s,border-color .12s;display:flex;align-items:flex-start;gap:8px;}' +
        '.sts-si:hover{background:rgba(255,255,255,.02);}' +
        '.sts-si.act{background:rgba(45,212,191,.04);}' +
        '.sts-snu{font-family:"JetBrains Mono",monospace;font-weight:600;font-size:11px;min-width:24px;padding-top:1px;}' +
        '.sts-sb{flex:1;min-width:0;}' +
        '.sts-sp{color:#94a3b8;font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;display:flex;align-items:center;gap:6px;}' +
        '.sts-spin{width:12px;height:12px;border:2px solid var(--sts-bd);border-top-color:var(--sts-ac);border-radius:50%;flex-shrink:0;animation:sts-rot .8s linear infinite;}' +
        '.sts-spin.gen{border-top-color:var(--sts-am);}' +
        '@keyframes sts-rot{to{transform:rotate(360deg)}}' +
        '.sts-se{color:var(--sts-dn);font-size:10px;margin-top:3px;opacity:.85;}' +
        '.sts-sci{font-size:11px;flex-shrink:0;padding-top:1px;}' +
        '.sts-em{padding:20px 16px;color:var(--sts-tm);text-align:center;font-size:11px;}' +
        '.sts-retry{background:none;border:1px solid var(--sts-bd);color:var(--sts-tm);font-size:9px;font-family:"JetBrains Mono",monospace;font-weight:600;padding:3px 8px;border-radius:5px;cursor:pointer;flex-shrink:0;transition:all .15s;text-transform:uppercase;letter-spacing:.5px;}' +
        '.sts-retry:hover{color:var(--sts-ac);border-color:var(--sts-ac);background:var(--sts-ad);}' +
        /* Thumbnail */
        '.sts-th{width:32px;height:32px;border-radius:6px;object-fit:cover;border:1px solid var(--sts-bd);flex-shrink:0;cursor:pointer;transition:border-color .15s,box-shadow .15s;}' +
        '.sts-th:hover{border-color:var(--sts-ac);box-shadow:0 0 8px var(--sts-ad);}' +
        '.sts-th-empty{width:32px;height:32px;border-radius:6px;background:var(--sts-el);border:1px solid var(--sts-bd);flex-shrink:0;display:flex;align-items:center;justify-content:center;font-size:12px;color:var(--sts-tm);}' +
        /* Image overlay */
        '#sts-img-overlay{position:fixed;inset:0;z-index:999999;background:rgba(0,0,0,.85);backdrop-filter:blur(8px);display:flex;align-items:center;justify-content:center;cursor:pointer;animation:sts-fo .2s ease-out;}' +
        '@keyframes sts-fo{from{opacity:0}to{opacity:1}}' +
        '#sts-img-overlay img{max-width:90vw;max-height:90vh;border-radius:12px;box-shadow:0 8px 40px rgba(0,0,0,.6);border:1px solid rgba(255,255,255,.1);}' +
        /* Settings */
        '.sts-cfg{padding:12px 16px;border-top:1px solid var(--sts-bd);flex-shrink:0;}' +
        '.sts-cfg label{font-family:"JetBrains Mono",monospace;font-size:9px;color:var(--sts-tm);letter-spacing:.8px;text-transform:uppercase;display:block;margin-bottom:5px;}' +
        '.sts-cfg input{width:100%;background:#161a26;border:1px solid var(--sts-bd);border-radius:8px;padding:8px 10px;color:var(--sts-t1);font-family:"JetBrains Mono",monospace;font-size:11px;outline:none;transition:border-color .2s,box-shadow .2s;box-sizing:border-box;}' +
        '.sts-cfg input:focus{border-color:var(--sts-ac);box-shadow:0 0 0 3px rgba(45,212,191,.08);}' +
        '.sts-cfb{margin-top:8px;background:var(--sts-el);border:1px solid var(--sts-bd);color:var(--sts-t2);padding:6px 14px;border-radius:8px;font-family:"DM Sans",sans-serif;font-size:11px;font-weight:600;cursor:pointer;transition:all .15s;}' +
        '.sts-cfb:hover{background:#1f2536;color:var(--sts-t1);border-color:var(--sts-ac);}' +
        /* Tabs */
        '.sts-tabs{display:flex;border-bottom:1px solid var(--sts-bd);flex-shrink:0;}' +
        '.sts-tab{flex:1;padding:8px 0;text-align:center;font-family:"JetBrains Mono",monospace;font-size:10px;font-weight:600;letter-spacing:.5px;text-transform:uppercase;color:var(--sts-tm);cursor:pointer;border-bottom:2px solid transparent;transition:all .15s;}' +
        '.sts-tab:hover{color:var(--sts-t2);background:rgba(255,255,255,.02);}' +
        '.sts-tab.active{color:var(--sts-ac);border-bottom-color:var(--sts-ac);}' +
        '.sts-tab .sts-badge{display:inline-block;background:var(--sts-ad);color:var(--sts-ac);padding:1px 6px;border-radius:100px;font-size:9px;margin-left:4px;}' +
        /* Sync list */
        '.sts-sync-item{padding:8px 14px;border-bottom:1px solid rgba(255,255,255,.03);display:flex;align-items:center;gap:10px;transition:background .12s;}' +
        '.sts-sync-item:hover{background:rgba(255,255,255,.02);}' +
        '.sts-sync-icon{font-size:14px;flex-shrink:0;}' +
        '.sts-sync-info{flex:1;min-width:0;}' +
        '.sts-sync-title{font-size:11px;font-weight:600;color:var(--sts-t1);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}' +
        '.sts-sync-meta{font-family:"JetBrains Mono",monospace;font-size:9px;color:var(--sts-tm);margin-top:2px;display:flex;gap:8px;}' +
        '.sts-sync-status{font-family:"JetBrains Mono",monospace;font-size:9px;font-weight:600;padding:2px 6px;border-radius:4px;}' +
        '.sts-sync-status.ok{color:var(--sts-ok);background:var(--sts-od);}' +
        '.sts-sync-status.fail{color:var(--sts-dn);background:var(--sts-dd);}';
      document.head.appendChild(style);
    }

    function render() {
      injectPanelStyles();
      var panel = document.getElementById('sts-gemini-panel');
      if (!panel) { panel = document.createElement('div'); panel.id = 'sts-gemini-panel'; document.body.appendChild(panel); }
      var tq = S.typing.queue;
      var total = tq.length, completed = 0, failed = 0;
      tq.forEach(function(q) { if (q.status === 'completed') completed++; if (q.status === 'error') failed++; });
      var pct = total > 0 ? Math.round(completed / total * 100) : 0;
      var wsOn = S.wsConnected;
      var wsLabel = wsOn ? 'Live' : 'Off';
      var wsCls = wsOn ? 'sts-wb on' : 'sts-wb off';

      // ── Collapsed pill ──
      if (S.collapsed) {
        panel.className = 'sts-c';
        var dotBg = wsOn ? 'var(--sts-ok)' : 'var(--sts-dn)';
        var dotSh = wsOn ? '0 0 6px var(--sts-ok)' : '0 0 6px var(--sts-dn)';
        panel.innerHTML =
          '<span class="sts-pd" style="background:' + dotBg + ';box-shadow:' + dotSh + ';"></span>' +
          '<span class="sts-pt">STS Gemini</span>' +
          '<span class="sts-pc">' + completed + '/' + total + '</span>';
        panel.onclick = function() { S.collapsed = false; localStorage.setItem('sts-gemini-collapsed', 'false'); render(); };
        return;
      }

      // ── Expanded panel ──
      panel.className = 'sts-e';
      panel.onclick = null;

      var headerHtml =
        '<div class="sts-hd">' +
          '<div class="sts-hl">' +
            '<div class="sts-lg">STS</div>' +
            '<span class="sts-ti">STS Gemini</span>' +
            '<span class="' + wsCls + '"><span class="sts-wd"></span>' + wsLabel + '</span>' +
          '</div>' +
          '<div class="sts-ha">' +
            '<button id="sts-settings-toggle" class="sts-ib" title="Settings">\u2699</button>' +
            '<button id="sts-collapse-btn" class="sts-ib" title="Minimize">\u2212</button>' +
          '</div>' +
        '</div>';

      var rateLimitHtml = '';
      if (S.typing.rateLimited) {
        var countdown = S.typing.rateLimitReset ? formatCountdown(S.typing.rateLimitReset) : '??:??:??';
        var resetStr = S.typing.rateLimitReset ? S.typing.rateLimitReset.toLocaleTimeString() : 'unknown';
        rateLimitHtml =
          '<div class="sts-rl">' +
            '<span class="sts-ri">\u26A0</span>' +
            '<div class="sts-rf">' +
              '<div class="sts-rt">Rate Limited</div>' +
              '<div class="sts-rs">Resets at ' + resetStr + '</div>' +
            '</div>' +
            '<div class="sts-rc">' + countdown + '</div>' +
          '</div>';
      }

      // Collect unique projects from queue
      var projectIds = [];
      tq.forEach(function(q) {
        if (projectIds.indexOf(q.projectId) === -1) projectIds.push(q.projectId);
      });
      var projectCountLabel = projectIds.length > 1 ? projectIds.length + ' projects' : (projectIds[0] || 'No project');
      var projectHtml = projectIds.length > 0
        ? '<div class="sts-pj">Queue \u2022 <b>' + projectCountLabel + '</b></div>'
        : '';

      var btnLabel = S.typing.active ? 'Stop' : 'Start Typing';
      var btnCls = S.typing.active ? 'sts-ab ht' : 'sts-ab go';
      var btnId = S.typing.active ? 'sts-stop-btn' : 'sts-start-btn';

      var statsHtml =
        '<div class="sts-ss">' +
          '<div class="sts-sr">' +
            '<div class="sts-st"><span class="sts-sn" style="color:var(--sts-ok);">' + completed + '</span><span class="sts-sl">done</span></div>' +
            '<div class="sts-st"><span class="sts-sn" style="color:var(--sts-dn);">' + failed + '</span><span class="sts-sl">err</span></div>' +
            '<div class="sts-st"><span class="sts-sn" style="color:var(--sts-t2);">' + total + '</span><span class="sts-sl">total</span></div>' +
          '</div>' +
          '<div class="sts-pk"><div class="sts-pf" style="width:' + pct + '%;"></div></div>' +
          '<button id="' + btnId + '" class="' + btnCls + '">' + btnLabel + '</button>' +
        '</div>';

      // Tab switcher
      var syncCount = S.syncHistory.length;
      var tabsHtml =
        '<div class="sts-tabs">' +
          '<div class="sts-tab' + (S.activeTab === 'queue' ? ' active' : '') + '" data-tab="queue">Queue</div>' +
          '<div class="sts-tab' + (S.activeTab === 'sync' ? ' active' : '') + '" data-tab="sync">Sync' + (syncCount > 0 ? '<span class="sts-badge">' + syncCount + '</span>' : '') + '</div>' +
        '</div>';

      var scenesHtml = '';
      var stColors = { queued:'var(--sts-tm)', typing:'var(--sts-am)', generating:'#38bdf8', completed:'var(--sts-ok)', error:'var(--sts-dn)' };
      var stIcons = { queued:'\u23F3', typing:'\u270D\uFE0F', generating:'\u2728', completed:'\u2713', error:'\u2717' };

      // Group scenes by project and render with project headers
      var lastPid = null;
      tq.forEach(function(item, si) {
        // Project header when projectId changes
        if (item.projectId !== lastPid) {
          lastPid = item.projectId;
          var pDone = 0, pTotal = 0, pErr = 0;
          tq.forEach(function(q) {
            if (q.projectId === lastPid) { pTotal++; if (q.status === 'completed') pDone++; if (q.status === 'error') pErr++; }
          });
          var pPct = pTotal > 0 ? Math.round(pDone / pTotal * 100) : 0;
          var arTag = item.aspectRatio ? '<span style="color:var(--sts-ac);background:var(--sts-ad);padding:1px 6px;border-radius:4px;font-size:9px;margin-left:6px;">' + item.aspectRatio + '</span>' : '';
          var pStatusColor = pDone === pTotal ? 'var(--sts-ok)' : pErr > 0 ? 'var(--sts-am)' : 'var(--sts-t2)';
          scenesHtml +=
            '<div class="sts-ph">' +
              '<div style="display:flex;align-items:center;gap:6px;flex:1;min-width:0;">' +
                '<span style="color:' + pStatusColor + ';font-size:11px;">\u25A0</span>' +
                '<span style="font-weight:700;font-size:11px;color:var(--sts-t1);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">' + (item.projectId || 'unknown') + '</span>' +
                arTag +
              '</div>' +
              '<span style="font-family:\'JetBrains Mono\',monospace;font-size:10px;color:var(--sts-tm);">' + pDone + '/' + pTotal + '</span>' +
            '</div>';
        }

        var sColor = stColors[item.status] || 'var(--sts-tm)';
        var sIcon = stIcons[item.status] || '\u23F3';
        var isActive = si === S.typing.currentIndex;
        var short = item.displayPrompt.substring(0, 55) + (item.displayPrompt.length > 55 ? '\u2026' : '');
        var errHtml = item.error ? '<div class="sts-se">' + item.error + '</div>' : '';
        var thumbHtml = item.imageUrl
          ? '<img class="sts-th" src="' + item.imageUrl + '" data-scene="' + item.scene + '" alt="Scene ' + item.scene + '">'
          : '<div class="sts-th-empty">' + sIcon + '</div>';
        var retryHtml = (item.status === 'error' || item.status === 'completed') && !S.typing.active
          ? '<button class="sts-retry" data-retry="' + si + '">\u21BB</button>'
          : '';
        scenesHtml +=
          '<div class="sts-si' + (isActive ? ' act' : '') + '" style="border-left-color:' + (isActive ? sColor : 'transparent') + ';">' +
            thumbHtml +
            '<span class="sts-snu" style="color:' + sColor + ';">#' + item.scene + '</span>' +
            '<div class="sts-sb">' +
              '<div class="sts-sp">' + (item.status === 'typing' ? '<span class="sts-spin"></span>' : item.status === 'generating' ? '<span class="sts-spin gen"></span>' : '') + short + '</div>' +
              errHtml +
            '</div>' +
            retryHtml +
          '</div>';
      });
      // Sync tab content
      var syncHtml = '';
      if (S.activeTab === 'sync') {
        if (S.syncHistory.length === 0) {
          syncHtml = '<div class="sts-em">No images synced yet</div>';
        } else {
          // Show newest first
          for (var hi = S.syncHistory.length - 1; hi >= 0; hi--) {
            var h = S.syncHistory[hi];
            var isOk = h.status === 'uploaded';
            var statusCls = isOk ? 'ok' : 'fail';
            var statusLabel = isOk ? '\u2713 Sent' : '\u2717 Failed';
            var thumbSyncHtml = h.imageUrl
              ? '<img class="sts-th" src="' + h.imageUrl + '" alt="Scene ' + h.scene + '">'
              : '<div class="sts-th-empty">' + (isOk ? '\u2713' : '\u2717') + '</div>';
            syncHtml +=
              '<div class="sts-sync-item">' +
                thumbSyncHtml +
                '<div class="sts-sync-info">' +
                  '<div class="sts-sync-title">' + h.projectId + ' \u2014 Scene #' + h.scene + '</div>' +
                  '<div class="sts-sync-meta">' +
                    '<span>' + h.timestamp + '</span>' +
                    (h.sizeKB > 0 ? '<span>' + h.sizeKB + ' KB</span>' : '') +
                  '</div>' +
                '</div>' +
                '<span class="sts-sync-status ' + statusCls + '">' + statusLabel + '</span>' +
              '</div>';
          }
        }
      }

      var contentHtml = S.activeTab === 'queue'
        ? '<div class="sts-scl">' + (scenesHtml || '<div class="sts-em">No scenes loaded</div>') + '</div>'
        : '<div class="sts-scl">' + syncHtml + '</div>';

      var settingsHtml = '';
      if (S.showSettings) {
        settingsHtml =
          '<div class="sts-cfg">' +
            '<label>WebSocket Endpoint</label>' +
            '<input id="sts-ws-url" type="text" value="' + S.wsUrl + '" spellcheck="false">' +
            '<button id="sts-ws-save" class="sts-cfb">Save &amp; Reconnect</button>' +
          '</div>';
      }

      panel.innerHTML = headerHtml + rateLimitHtml + projectHtml + statsHtml + tabsHtml + contentHtml + settingsHtml;

      setTimeout(function() {
        var collapseBtn = document.getElementById('sts-collapse-btn');
        if (collapseBtn) collapseBtn.onclick = function(e) { e.stopPropagation(); S.collapsed = true; localStorage.setItem('sts-gemini-collapsed', 'true'); render(); };
        var settingsToggle = document.getElementById('sts-settings-toggle');
        if (settingsToggle) settingsToggle.onclick = function(e) { e.stopPropagation(); S.showSettings = !S.showSettings; render(); };
        // Tab switching
        document.querySelectorAll('#sts-gemini-panel .sts-tab').forEach(function(tab) {
          tab.onclick = function(e) { e.stopPropagation(); S.activeTab = tab.getAttribute('data-tab'); render(); };
        });
        var startBtn = document.getElementById('sts-start-btn');
        if (startBtn) startBtn.onclick = function(e) { e.stopPropagation(); startTyping(); };
        var stopBtn = document.getElementById('sts-stop-btn');
        if (stopBtn) stopBtn.onclick = function(e) { e.stopPropagation(); stopTyping(); };
        // Retry buttons
        document.querySelectorAll('#sts-gemini-panel .sts-retry').forEach(function(btn) {
          btn.onclick = function(e) {
            e.stopPropagation();
            var idx = parseInt(btn.getAttribute('data-retry'));
            var item = S.typing.queue[idx];
            if (item) {
              console.log('[RETRY] Re-queuing scene', item.scene);
              item.status = 'queued';
              item.error = null;
              item.imageUrl = null;
              render();
              // Auto-start if not already running
              if (!S.typing.active && !S.typing.starting) {
                setTimeout(function() { startTyping(); }, 500);
              }
            }
          };
        });
        // Thumbnail click → fullscreen overlay
        var thumbs = document.querySelectorAll('#sts-gemini-panel .sts-th');
        thumbs.forEach(function(th) {
          th.onclick = function(e) {
            e.stopPropagation();
            var overlay = document.getElementById('sts-img-overlay');
            if (overlay) overlay.remove();
            overlay = document.createElement('div');
            overlay.id = 'sts-img-overlay';
            overlay.innerHTML = '<img src="' + th.src + '" alt="Scene preview">';
            overlay.onclick = function() { overlay.remove(); };
            document.body.appendChild(overlay);
          };
        });

        var saveBtn = document.getElementById('sts-ws-save');
        if (saveBtn) saveBtn.onclick = function(e) {
          e.stopPropagation();
          var urlInput = document.getElementById('sts-ws-url');
          if (urlInput && urlInput.value) {
            S.wsUrl = urlInput.value; localStorage.setItem('sts-gemini-ws', S.wsUrl);
            if (S.ws) { try { S.ws.close(); } catch(ex) {} }
            S.ws = null; S.wsConnected = false; connectWS(); render();
          }
        };
      }, 50);
    }

    // ── Boot ─────────────────────────────────────────
    render();
    connectWS();
    console.log('STS Gemini Synchronizer initialized');
  }
})();
