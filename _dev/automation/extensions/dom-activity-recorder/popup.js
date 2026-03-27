const xpathInput = document.getElementById('xpath');

// Restore last used xpath from localStorage
const saved = localStorage.getItem('sar-last-xpath');
if (saved) xpathInput.value = saved;

document.getElementById('pick').addEventListener('click', () => {
  sendAction('PICK_ELEMENT');
});

document.getElementById('xpath-go').addEventListener('click', () => {
  const xpath = xpathInput.value.trim();
  if (!xpath) {
    showStatus('Enter an XPath or CSS selector', 'error');
    return;
  }
  // Save to localStorage
  localStorage.setItem('sar-last-xpath', xpath);
  sendAction('SELECT_BY_PATH', { path: xpath });
});

// Allow Enter key in xpath input
xpathInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') document.getElementById('xpath-go').click();
});

document.getElementById('stop').addEventListener('click', () => {
  sendAction('STOP_RECORDING');
});

document.getElementById('clear').addEventListener('click', () => {
  sendAction('CLEAR_DATA');
});

// Inject content script into tab if not already present, then send message
function ensureContentScript(tabId) {
  return new Promise((resolve) => {
    chrome.tabs.sendMessage(tabId, { action: '__PING__' }, (response) => {
      if (chrome.runtime.lastError) {
        chrome.scripting.insertCSS({ target: { tabId }, files: ['recorder.css'] }, () => {
          chrome.scripting.executeScript({ target: { tabId }, files: ['recorder.js'] }, () => {
            if (chrome.runtime.lastError) {
              resolve(false);
            } else {
              resolve(true);
            }
          });
        });
      } else {
        resolve(true);
      }
    });
  });
}

function sendAction(action, extra) {
  chrome.tabs.query({ active: true, currentWindow: true }, async (tabs) => {
    if (!tabs[0]) {
      showStatus('No active tab found.', 'error');
      return;
    }
    const tabId = tabs[0].id;

    const ready = await ensureContentScript(tabId);
    if (!ready) {
      showStatus('Cannot inject into this page (chrome:// or protected page).', 'error');
      return;
    }

    setTimeout(() => {
      chrome.tabs.sendMessage(tabId, Object.assign({ action: action }, extra || {}), (response) => {
        if (chrome.runtime.lastError) {
          showStatus('Failed to communicate with page. Try reloading.', 'error');
          return;
        }
        if (response && response.error) {
          showStatus(response.error, 'error');
        } else if (response && response.ok) {
          showStatus(response.message || 'Done', 'success');
          if (action !== 'STOP_RECORDING') {
            setTimeout(() => window.close(), 800);
          }
        } else {
          window.close();
        }
      });
    }, 100);
  });
}

function showStatus(msg, type) {
  const el = document.getElementById('status');
  el.textContent = msg;
  el.className = 'status ' + (type || '');
}
