// ── STS Grok Automation — Service Worker ────────────────

// ── Side Panel Setup ────────────────────────────────────
async function setupSidePanel() {
  if (!chrome.sidePanel) return;
  await chrome.sidePanel.setOptions({
    path: "src/panel/panel.html",
    enabled: true,
  });
  await chrome.sidePanel.setPanelBehavior({
    openPanelOnActionClick: true,
  });
}

setupSidePanel();

chrome.runtime.onInstalled.addListener(() => {
  setupSidePanel();
  console.log("[STS Grok] Extension installed");
});

function waitForDownloadComplete(downloadId, timeoutMs = 10 * 60 * 1000) {
  return new Promise((resolve, reject) => {
    let finished = false;

    const cleanup = () => {
      chrome.downloads.onChanged.removeListener(handleChange);
      clearTimeout(timeoutId);
    };

    const finish = (error, result) => {
      if (finished) return;
      finished = true;
      cleanup();
      if (error) reject(error);
      else resolve(result);
    };

    const handleChange = (delta) => {
      if (delta.id !== downloadId || !delta.state?.current) return;
      if (delta.state.current === "complete") {
        finish(null, { downloadId, state: "complete" });
      } else if (delta.state.current === "interrupted") {
        const reason = delta.error?.current || "Download interrupted";
        finish(new Error(reason));
      }
    };

    const timeoutId = setTimeout(() => {
      finish(new Error("Download timed out"));
    }, timeoutMs);

    chrome.downloads.onChanged.addListener(handleChange);
    chrome.downloads.search({ id: downloadId }, (results) => {
      const item = results?.[0];
      if (!item?.id || finished) return;

      if (item.state === "complete") {
        finish(null, { downloadId, state: "complete" });
      } else if (item.state === "interrupted") {
        finish(new Error(item.error || "Download interrupted"));
      }
    });
  });
}

// ── Auto-open side panel on target pages ────────────────
function isAutoOpenUrl(url) {
  if (!url) return false;
  if (url === "about:blank") return true;
  try {
    const u = new URL(url);
    return u.hostname === "grok.com" && u.pathname.startsWith("/imagine");
  } catch {
    return false;
  }
}

chrome.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
  if (changeInfo.status !== "complete") return;
  if (!isAutoOpenUrl(tab.url)) return;

  try {
    await chrome.sidePanel.open({ tabId });
  } catch (e) {
    // May require user gesture on some Chrome versions
    console.log("[STS Grok] Auto-open side panel skipped:", e.message);
  }
});

// ── Auto-navigate to grok.com/imagine when job received ──
async function ensureGrokTab(options = {}) {
  const freshStart = !!options.freshStart;

  // Find existing grok.com tab
  const grokTabs = await chrome.tabs.query({ url: "*://grok.com/*" });
  if (grokTabs.length > 0) {
    const tab = grokTabs[0];

    if (!tab.url.includes("/imagine")) {
      await chrome.tabs.update(tab.id, { url: "https://grok.com/imagine", active: true });
    } else if (freshStart) {
      await chrome.tabs.update(tab.id, { active: true });
      await chrome.tabs.reload(tab.id, { bypassCache: true });
    } else {
      await chrome.tabs.update(tab.id, { active: true });
    }
    await chrome.windows.update(tab.windowId, { focused: true });
    return tab.id;
  }

  // No grok tab — reuse the active tab instead of opening a new one
  const [activeTab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (activeTab?.id) {
    await chrome.tabs.update(activeTab.id, { url: "https://grok.com/imagine" });
    return activeTab.id;
  }

  // Last resort — create one
  const newTab = await chrome.tabs.create({ url: "https://grok.com/imagine", active: true });
  return newTab.id;
}

// ── Message Router ──────────────────────────────────────

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  console.log("[STS Grok] Background received:", msg.type);

  switch (msg.type) {
    case "PING":
      sendResponse({ pong: true, from: "background" });
      break;

    case "ENSURE_GROK_TAB":
      ensureGrokTab({ freshStart: !!msg.freshStart })
        .then((tabId) => sendResponse({ success: true, tabId }))
        .catch((e) => sendResponse({ success: false, error: e.message }));
      return true; // async

    case "ANIMATE_PROGRESS":
      // Forward progress from content script to side panel
      // The side panel listens via chrome.runtime.onMessage
      break;

    case "DOWNLOAD_VIDEO":
      // Download a video URL to disk
      if (msg.url) {
        chrome.downloads.download(
          {
            url: msg.url,
            filename: msg.filename || `sts-video-${Date.now()}.mp4`,
            saveAs: false,
          },
          (downloadId) => {
            const lastError = chrome.runtime.lastError?.message;
            if (!downloadId || lastError) {
              sendResponse({
                success: false,
                downloadId,
                error: lastError || "Failed to start download",
              });
              return;
            }

            waitForDownloadComplete(downloadId)
              .then((result) => {
                sendResponse({
                  success: true,
                  downloadId,
                  state: result.state,
                });
              })
              .catch((error) => {
                sendResponse({
                  success: false,
                  downloadId,
                  error: error.message,
                });
              });
          }
        );
        return true; // async
      }
      sendResponse({ success: false, error: "No URL" });
      break;
  }

  return false;
});
