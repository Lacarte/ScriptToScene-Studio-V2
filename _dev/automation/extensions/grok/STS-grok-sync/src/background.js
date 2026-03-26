// STS Grok Sync — Service Worker (minimal)
// Only handles extension lifecycle and message forwarding

chrome.runtime.onInstalled.addListener(() => {
  console.log("[STS Grok Sync] Installed");
});

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === "PING") {
    sendResponse({ pong: true, from: "background" });
  }
  return false;
});
