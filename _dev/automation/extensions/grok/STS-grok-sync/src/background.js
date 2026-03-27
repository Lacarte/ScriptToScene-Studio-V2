// STS Grok Sync — Service Worker
// Handles extension lifecycle, message forwarding, and tab activation

chrome.runtime.onInstalled.addListener(() => {
  console.log("[STS Grok Sync] Installed");
});

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === "PING") {
    sendResponse({ pong: true, from: "background" });
  } else if (msg.type === "ACTIVATE_TAB") {
    // Activate the tab that sent this message (content script's tab)
    if (sender.tab && sender.tab.id) {
      chrome.tabs.update(sender.tab.id, { active: true });
      chrome.windows.update(sender.tab.windowId, { focused: true });
      console.log("[STS Grok Sync] Tab activated:", sender.tab.id);
    }
    sendResponse({ ok: true });
  }
  return false;
});
