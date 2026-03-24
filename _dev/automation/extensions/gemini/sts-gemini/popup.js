document.addEventListener('DOMContentLoaded', () => {
  const startBtn = document.getElementById('startBtn');
  const wsUrlInput = document.getElementById('wsUrl');
  const statusBadge = document.getElementById('statusBadge');
  const statusLabel = document.getElementById('statusLabel');
  const statusText = document.getElementById('statusText');

  function setRunning(running) {
    if (running) {
      startBtn.textContent = 'Stop Sync';
      startBtn.className = 'action-btn stop';
      statusBadge.className = 'status-badge online';
      statusLabel.textContent = 'Live';
      statusText.textContent = 'Running...';
    } else {
      startBtn.textContent = 'Start Sync';
      startBtn.className = 'action-btn start';
      statusBadge.className = 'status-badge offline';
      statusLabel.textContent = 'Offline';
    }
  }

  // Load saved URL
  chrome.storage.local.get(['stsWsUrl', 'stsRunning'], (data) => {
    if (data.stsWsUrl) wsUrlInput.value = data.stsWsUrl;
    if (data.stsRunning) {
      setRunning(true);
    }
  });

  startBtn.addEventListener('click', async () => {
    const wsUrl = wsUrlInput.value.trim();
    chrome.storage.local.set({ stsWsUrl: wsUrl });

    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab || !tab.url.includes('gemini.google.com')) {
      statusText.textContent = 'Open gemini.google.com first!';
      return;
    }

    chrome.storage.local.get(['stsRunning'], (data) => {
      if (data.stsRunning) {
        // Stop
        chrome.tabs.sendMessage(tab.id, { action: 'STS_STOP' });
        chrome.storage.local.set({ stsRunning: false });
        setRunning(false);
        statusText.textContent = 'Stopped';
      } else {
        // Start
        chrome.tabs.sendMessage(tab.id, { action: 'STS_START', wsUrl: wsUrl });
        chrome.storage.local.set({ stsRunning: true });
        setRunning(true);
        statusText.textContent = 'Starting...';
      }
    });
  });
});
