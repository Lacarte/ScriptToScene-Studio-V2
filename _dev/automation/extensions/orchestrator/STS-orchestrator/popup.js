// STS Orchestrator — Popup UI

const port = chrome.runtime.connect({ name: "sts-orchestrator-popup" });
const tabList = document.getElementById("tabList");
const searchInput = document.getElementById("searchInput");
const refreshBtn = document.getElementById("refreshBtn");
const reconnectBtn = document.getElementById("reconnectBtn");
const statusDot = document.getElementById("statusDot");
const statusText = document.getElementById("statusText");

let allTabs = [];

// ── Status ──────────────────────────────────────────────

port.onMessage.addListener((msg) => {
  if (msg.type === "STS_WS_STATUS") {
    statusDot.classList.toggle("connected", msg.connected);
    statusText.textContent = msg.connected ? "Connected" : "Disconnected";
  } else if (msg.type === "STS_TAB_LIST") {
    allTabs = msg.tabs;
    renderTabs();
  }
});

// ── Render tabs ─────────────────────────────────────────

function renderTabs() {
  const filter = searchInput.value.toLowerCase();
  const filtered = filter
    ? allTabs.filter(t =>
        (t.title && t.title.toLowerCase().includes(filter)) ||
        (t.url && t.url.toLowerCase().includes(filter))
      )
    : allTabs;

  if (!filtered.length) {
    tabList.innerHTML = '<li class="empty">No tabs found</li>';
    return;
  }

  tabList.innerHTML = filtered.map(t => {
    const faviconHtml = t.favIconUrl
      ? `<img class="tab-favicon" src="${escapeHtml(t.favIconUrl)}" onerror="this.style.display='none'">`
      : `<div class="tab-favicon" style="background:#333"></div>`;

    return `
      <li class="tab-item${t.active ? " active" : ""}" data-tab-id="${t.id}">
        ${faviconHtml}
        <div class="tab-info">
          <div class="tab-title">${escapeHtml(t.title || "Untitled")}</div>
          <div class="tab-url">${escapeHtml(shortUrl(t.url))}</div>
        </div>
        <span class="tab-id">#${t.id}</span>
      </li>
    `;
  }).join("");

  // Click to focus
  tabList.querySelectorAll(".tab-item").forEach(el => {
    el.addEventListener("click", () => {
      const tabId = parseInt(el.dataset.tabId);
      port.postMessage({ action: "STS_FOCUS_TAB", tabId });
    });
  });
}

function shortUrl(url) {
  if (!url) return "";
  try {
    const u = new URL(url);
    return u.hostname + u.pathname.slice(0, 40);
  } catch (e) {
    return url.slice(0, 50);
  }
}

function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

// ── Controls ────────────────────────────────────────────

searchInput.addEventListener("input", renderTabs);
refreshBtn.addEventListener("click", () => port.postMessage({ action: "STS_LIST_TABS" }));
reconnectBtn.addEventListener("click", () => port.postMessage({ action: "STS_WS_RECONNECT" }));

// Initial load
port.postMessage({ action: "STS_LIST_TABS" });
