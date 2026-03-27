document.addEventListener('DOMContentLoaded', () => {
  const statusBadge = document.getElementById('statusBadge');
  const statusLabel = document.getElementById('statusLabel');
  const statusText = document.getElementById('statusText');

  function setStatus(connected) {
    if (connected) {
      statusBadge.className = 'status-badge online';
      statusLabel.textContent = 'Connected';
      statusText.textContent = 'Auto-connected to Flask WS';
    } else {
      statusBadge.className = 'status-badge offline';
      statusLabel.textContent = 'Reconnecting';
      statusText.textContent = 'Waiting for Flask on :5050...';
    }
  }

  // Query the content script for actual WS state
  async function checkStatus() {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab || !tab.url.includes('gemini.google.com')) {
      statusBadge.className = 'status-badge offline';
      statusLabel.textContent = 'Wrong page';
      statusText.textContent = 'Open gemini.google.com';
      return;
    }

    chrome.tabs.sendMessage(tab.id, { action: 'STS_STATUS' }, (response) => {
      if (chrome.runtime.lastError || !response) {
        setStatus(false);
      } else {
        setStatus(response.connected);
        if (response.projectId) {
          statusText.textContent = 'Project: ' + response.projectId + ' (' + response.sceneCount + ' scenes)';
        }
      }
    });
  }

  checkStatus();
  // Refresh every 2 seconds while popup is open
  setInterval(checkStatus, 2000);
});
