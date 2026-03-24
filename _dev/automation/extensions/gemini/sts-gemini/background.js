// STS Gemini — Background Service Worker
// Fetches images from Google CDN (has host_permissions)

chrome.runtime.onMessage.addListener(function(request, sender, sendResponse) {
  if (request.action === 'FETCH_IMAGE_BASE64') {
    var url = request.url;
    console.log('[STS BG] Fetching image:', url.substring(0, 80) + '...');

    // Try multiple strategies — Google CDN redirects and has varying CORS
    var strategies = [
      { credentials: 'omit', mode: 'cors', redirect: 'follow' },
      { credentials: 'omit', redirect: 'follow' },
      { credentials: 'include', redirect: 'follow' },
      {},  // bare fetch
    ];

    var attempt = 0;
    function tryNext() {
      if (attempt >= strategies.length) {
        console.error('[STS BG] All strategies failed for', url.substring(0, 60));
        sendResponse({ success: false, error: 'All fetch strategies failed' });
        return;
      }
      var opts = strategies[attempt];
      attempt++;
      console.log('[STS BG] Strategy', attempt, ':', JSON.stringify(opts));

      fetch(url, opts)
        .then(function(r) {
          console.log('[STS BG] Strategy', attempt, 'status:', r.status, 'type:', r.type);
          if (!r.ok) throw new Error('HTTP ' + r.status);
          return r.blob();
        })
        .then(function(blob) {
          console.log('[STS BG] Got blob:', blob.size, 'bytes, type:', blob.type);
          var reader = new FileReader();
          reader.onload = function() {
            var sizeKB = Math.round(blob.size / 1024);
            console.log('[STS BG] Success (' + sizeKB + ' KB) via strategy', attempt);
            sendResponse({ success: true, data: reader.result });
          };
          reader.onerror = function() {
            console.error('[STS BG] FileReader failed');
            tryNext();
          };
          reader.readAsDataURL(blob);
        })
        .catch(function(err) {
          console.warn('[STS BG] Strategy', attempt, 'failed:', err.message);
          tryNext();
        });
    }

    tryNext();
    return true; // Keep channel open
  }
});
