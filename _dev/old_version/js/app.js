/* ================================================================
   ScriptToScene Studio — App Core (navigation, toast, confirm, api)
   ================================================================ */

const $ = s => document.querySelector(s);
const $$ = s => document.querySelectorAll(s);
const esc = s => s ? s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;') : '';

// ---- Welcome Overlay (first visit) ----
const _welcomeQuotes = [
  // Productivity & Creativity
  '"The secret of getting ahead is getting started." — Mark Twain',
  '"Creativity is intelligence having fun." — Albert Einstein',
  '"Vision without execution is just hallucination." — Thomas Edison',
  '"The best way to predict the future is to create it." — Peter Drucker',
  '"Simplicity is the ultimate sophistication." — Leonardo da Vinci',
  '"Make it work, make it right, make it fast." — Kent Beck',
  '"Ideas are easy. Execution is everything." — John Doerr',

  // Curiosity
  '"The important thing is not to stop questioning. Curiosity has its own reason for existing." — Albert Einstein',
  '"I have no special talents. I am only passionately curious." — Albert Einstein',
  '"The cure for boredom is curiosity. There is no cure for curiosity." — Dorothy Parker',
  '"Be less curious about people and more curious about ideas." — Marie Curie',
  '"Millions saw the apple fall, but Newton asked why." — Bernard Baruch',
  '"The mind is not a vessel to be filled, but a fire to be kindled." — Plutarch',
  '"Judge a man by his questions rather than by his answers." — Voltaire',
  '"In all affairs it\'s a healthy thing now and then to hang a question mark on things you have long taken for granted." — Bertrand Russell',
  '"Research is formalized curiosity. It is poking and prying with a purpose." — Zora Neale Hurston',
  '"The world is full of magic things, patiently waiting for our senses to grow sharper." — W.B. Yeats',

  // Dark Psychology & Human Nature
  '"Man is not what he thinks he is, he is what he hides." — André Malraux',
  '"The most dangerous creature on earth is a false friend." — Confucius',
  '"People don\'t want to hear the truth because they don\'t want their illusions destroyed." — Friedrich Nietzsche',
  '"He who has a why to live can bear almost any how." — Friedrich Nietzsche',
  '"We are what we pretend to be, so we must be careful about what we pretend to be." — Kurt Vonnegut',
  '"The human race is governed by its imagination." — Napoleon Bonaparte',
  '"Every man is guilty of all the good he did not do." — Voltaire',
  '"Whoever fights monsters should see to it that in the process he does not become a monster." — Friedrich Nietzsche',
  '"The best way to keep a prisoner from escaping is to make sure he never knows he\'s in prison." — Fyodor Dostoevsky',
  '"A man who lies to himself is often the first to take offense." — Fyodor Dostoevsky',
  '"All cruelty springs from weakness." — Seneca',
  '"The most common way people give up their power is by thinking they don\'t have any." — Alice Walker',
  '"People will forget what you said, people will forget what you did, but people will never forget how you made them feel." — Maya Angelou',
  '"If you want to control someone, all you have to do is make them feel afraid." — Paulo Coelho',
  '"The masses have never thirsted after truth. Whoever can supply them with illusions is easily their master." — Gustave Le Bon',
  '"A person who has been punished is not less inclined to behave in a given way; at best, he learns how to avoid punishment." — B.F. Skinner',
  '"It is easier to fool people than to convince them they have been fooled." — (commonly attributed)',

  // Unknown Facts & Mind-Bending
  '"There are more possible iterations of a game of chess than there are atoms in the known universe."',
  '"Your brain uses 20% of your body\'s energy but is only 2% of your weight."',
  '"Octopuses have three hearts, blue blood, and can edit their own RNA."',
  '"A photon experiences zero time — from its perspective, emission and absorption happen simultaneously."',
  '"Honey never spoils. Archaeologists found 3,000-year-old honey in Egyptian tombs, still edible."',
  '"You share 60% of your DNA with a banana."',
  '"The human body contains enough iron to make a 3-inch nail."',
  '"Cleopatra lived closer in time to the Moon landing than to the construction of the Great Pyramid."',
  '"There are more stars in the universe than grains of sand on all of Earth\'s beaches."',
  '"A teaspoon of neutron star weighs about 6 billion tons."',
  '"Bananas are naturally radioactive — you\'d need to eat 10 million at once for radiation poisoning."',
  '"The total weight of all ants on Earth roughly equals the total weight of all humans."',
  '"Your body produces 25 million new cells each second. Every 13 seconds, you produce more cells than there are people in the US."',
  '"The Amazon rainforest produces 20% of the world\'s oxygen but consumes nearly all of it itself."',
  '"Sharks are older than trees. Sharks have existed for ~450 million years; trees for ~350 million."',
  '"Every atom in your body is billions of years old. Hydrogen, the most common element, was produced in the Big Bang 13.7 billion years ago."',
  '"The smell of rain has a name: petrichor. It\'s caused by a molecule called geosmin, which humans can detect at 5 parts per trillion."',

  // Science & Discovery
  '"The universe is under no obligation to make sense to you." — Neil deGrasse Tyson',
  '"Somewhere, something incredible is waiting to be known." — Carl Sagan',
  '"We are a way for the cosmos to know itself." — Carl Sagan',
  '"If you wish to make an apple pie from scratch, you must first invent the universe." — Carl Sagan',
  '"Not only is the universe stranger than we imagine, it is stranger than we can imagine." — Arthur Eddington',
  '"The good thing about science is that it\'s true whether or not you believe in it." — Neil deGrasse Tyson',
  '"Nothing in life is to be feared, it is only to be understood." — Marie Curie',
  '"An experiment is a question which science poses to Nature, and a measurement is the recording of Nature\'s answer." — Max Planck',
  '"The saddest aspect of life right now is that science gathers knowledge faster than society gathers wisdom." — Isaac Asimov',
  '"Two things are infinite: the universe and human stupidity; and I\'m not sure about the universe." — Albert Einstein',
  '"Science is not only a discipline of reason but also one of romance and passion." — Stephen Hawking',
  '"The most incomprehensible thing about the universe is that it is comprehensible." — Albert Einstein',
  '"We are all connected; to each other biologically, to the earth chemically, to the rest of the universe atomically." — Neil deGrasse Tyson',
  '"Look up at the stars and not down at your feet. Be curious." — Stephen Hawking',

  // Morality & Ethics
  '"The only thing necessary for the triumph of evil is for good men to do nothing." — Edmund Burke',
  '"In the end, we will remember not the words of our enemies, but the silence of our friends." — Martin Luther King Jr.',
  '"The measure of a man is what he does with power." — Plato',
  '"To see what is right and not do it is a want of courage." — Confucius',
  '"Nearly all men can stand adversity, but if you want to test a man\'s character, give him power." — Abraham Lincoln',
  '"Right is right, even if everyone is against it. Wrong is wrong, even if everyone is for it." — William Penn',
  '"The time is always right to do what is right." — Martin Luther King Jr.',
  '"Morality is not the doctrine of how we may make ourselves happy, but of how we may make ourselves worthy of happiness." — Immanuel Kant',
  '"The greatest threat to our planet is the belief that someone else will save it." — Robert Swan',
  '"An individual has not started living until he can rise above the narrow confines of his individualistic concerns to the broader concerns of all humanity." — Martin Luther King Jr.',
  '"He who is cruel to animals becomes hard also in his dealings with men." — Immanuel Kant',
  '"The true test of civilization is not the census, nor the size of cities, but the kind of man the country turns out." — Ralph Waldo Emerson',

  // Wisdom & Deep Meaning
  '"The only true wisdom is in knowing you know nothing." — Socrates',
  '"We suffer more often in imagination than in reality." — Seneca',
  '"No man ever steps in the same river twice, for it is not the same river and he is not the same man." — Heraclitus',
  '"The wound is the place where the Light enters you." — Rumi',
  '"He who knows others is wise; he who knows himself is enlightened." — Lao Tzu',
  '"The snake which cannot cast its skin has to die. As well the minds which are prevented from changing their opinions." — Friedrich Nietzsche',
  '"What you are is what you have been. What you\'ll be is what you do now." — Buddha',
  '"A society grows great when old men plant trees whose shade they know they shall never sit in." — Greek Proverb',
  '"The man who moves a mountain begins by carrying away small stones." — Confucius',
  '"When you realize nothing is lacking, the whole world belongs to you." — Lao Tzu',
  '"It is not that we have a short time to live, but that we waste a great deal of it." — Seneca',
  '"The mind is everything. What you think you become." — Buddha',
  '"Before you speak, let your words pass through three gates: Is it true? Is it necessary? Is it kind?" — Rumi',
  '"The soul becomes dyed with the color of its thoughts." — Marcus Aurelius',
  '"Knowing yourself is the beginning of all wisdom." — Aristotle',
  '"Between stimulus and response there is a space. In that space is our freedom and power to choose our response." — Viktor Frankl',
  '"The greatest glory in living lies not in never falling, but in rising every time we fall." — Nelson Mandela',
  '"Silence is a source of great strength." — Lao Tzu',
  '"Don\'t let yesterday take up too much of today." — Will Rogers',
  '"The obstacle is the way." — Marcus Aurelius',
  '"He who fears he will suffer, already suffers because he fears." — Michel de Montaigne',
  '"You can easily judge the character of a man by how he treats those who can do nothing for him." — Johann Wolfgang von Goethe',
  '"The only way to do great work is to love what you do." — Steve Jobs',
  '"Life shrinks or expands in proportion to one\'s courage." — Anaïs Nin',
  '"The unexamined life is not worth living." — Socrates',
];

function _initWelcome() {
  if (localStorage.getItem('sts-welcome-seen')) return;
  showWelcome();
}

function dismissWelcome() {
  const overlay = $('#welcome-overlay');
  if (!overlay) return;
  localStorage.setItem('sts-welcome-seen', '1');
  overlay.classList.add('dismissing');
  overlay.addEventListener('animationend', () => overlay.remove(), { once: true });
}

function showWelcome() {
  let overlay = $('#welcome-overlay');
  if (overlay) overlay.remove();
  const tpl = document.getElementById('welcome-template');
  if (!tpl) return;
  const clone = tpl.content.cloneNode(true);
  document.body.prepend(clone);
  overlay = $('#welcome-overlay');
  const q = overlay.querySelector('#welcome-quote');
  if (q) q.textContent = _welcomeQuotes[Math.floor(Math.random() * _welcomeQuotes.length)];
  overlay.style.display = 'flex';
}

document.addEventListener('DOMContentLoaded', _initWelcome);

// ---- Settings Manager (server JSON with .bak, localStorage only for sts-sidebar) ----
window.STS = {
  _cache: {},           // in-memory cache of all settings
  _defaults: {},        // from app-config.json
  _localKeys: new Set(),// keys that also mirror to localStorage
  _saveTimer: null,
  _dirty: false,

  /** Get a setting value. Sync — reads from memory cache. */
  get(key) {
    const v = this._cache[key];
    if (v !== undefined) return v;
    // Check localStorage for local-only keys
    const ls = localStorage.getItem(key);
    if (ls !== null) return ls === 'true' ? true : ls === 'false' ? false : (isNaN(ls) ? ls : +ls);
    return this._defaults[key] ?? null;
  },

  /** Set a setting value. Writes to memory + queues server save. */
  set(key, value) {
    this._cache[key] = value;
    if (this._localKeys.has(key)) localStorage.setItem(key, value);
    this._queueSave();
  },

  /** Queue a debounced save to server (300ms). */
  _queueSave() {
    this._dirty = true;
    clearTimeout(this._saveTimer);
    this._saveTimer = setTimeout(() => this._persist(), 300);
  },

  /** Persist all settings to server via PATCH. */
  async _persist() {
    if (!this._dirty) return;
    this._dirty = false;
    try {
      await fetch('/api/settings', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(this._cache),
      });
    } catch (_) { /* silent — next save will retry */ }
  },

  /** Reset all settings to defaults. */
  async reset() {
    this._cache = {};
    try { await fetch('/api/settings', { method: 'DELETE' }); } catch (_) {}
  },

  /** Load from server + app-config.json defaults. Returns a promise. */
  async init() {
    try {
      const [cfgRes, srvRes] = await Promise.all([
        fetch('/app-config.json').then(r => r.json()).catch(() => ({})),
        fetch('/api/settings').then(r => r.json()).catch(() => ({})),
      ]);
      this._defaults = cfgRes.defaults || {};
      (cfgRes.localStorage || []).forEach(k => this._localKeys.add(k));
      // Merge: defaults < server settings
      this._cache = { ...this._defaults, ...srvRes };
      // Mirror local keys to localStorage
      for (const k of this._localKeys) {
        const v = this._cache[k];
        if (v !== undefined) localStorage.setItem(k, v);
      }
    } catch (_) {
      this._defaults = {};
      this._cache = {};
    }
  }
};
window._stsReady = window.STS.init();

// ---- Shared State ----
window.STATE = {
  alignFile: null,
  alignResult: null,
  alignHistory: [],
  segmenterResult: null,
  segmenterAlignment: null,
  scenesSegData: null,
  scenesResult: null,
  assetsSceneData: null,
  assetStatuses: {},
  editorLoaded: false,
  captionData: null,
  captionAlignment: null,
};

// ---- Global Audio Registry ----
// Tracks all audio instances across modules so they can be stopped from one place.
window._stsAudioRegistry = {};

window.stsStopExportVideos = function (exceptVideo = null) {
  const list = document.getElementById('export-library-list');
  if (!list) return [];
  const stopped = [];
  list.querySelectorAll('video').forEach(video => {
    if (!video || video === exceptVideo) return;
    if (!video.paused) {
      video.pause();
      video.currentTime = 0;
      stopped.push('Export Library');
    } else if (video.currentTime > 0) {
      video.currentTime = 0;
    }
  });
  return stopped;
};

/**
 * Register an Audio element (or HTMLMediaElement) with a label.
 * @param {string} label  — e.g. "Captions", "Alignment", "TTS"
 * @param {HTMLMediaElement} audioEl
 */
window.stsAudioRegister = function (label, audioEl) {
  if (!audioEl) return;
  window._stsAudioRegistry[label] = audioEl;
  if (!audioEl.__stsExclusiveBound) {
    audioEl.__stsExclusiveBound = true;
    audioEl.addEventListener('play', () => {
      for (const [, otherEl] of Object.entries(window._stsAudioRegistry)) {
        if (!otherEl || otherEl === audioEl) continue;
        if (!otherEl.paused) {
          otherEl.pause();
          otherEl.currentTime = 0;
        }
      }
      if (typeof window.stsStopExportVideos === 'function') {
        window.stsStopExportVideos();
      }
      _stsAudioSyncIndicator();
    });
    audioEl.addEventListener('pause', _stsAudioSyncIndicator);
    audioEl.addEventListener('ended', _stsAudioSyncIndicator);
    audioEl.addEventListener('error', _stsAudioSyncIndicator);
  }
  _stsAudioSyncIndicator();
};

/** Unregister an audio element by label */
window.stsAudioUnregister = function (label) {
  delete window._stsAudioRegistry[label];
  _stsAudioSyncIndicator();
};

/** Stop all registered audio and return which ones were playing */
window.stsAudioStopAll = function (exceptExportVideo = null) {
  const stopped = [];
  for (const [label, el] of Object.entries(window._stsAudioRegistry)) {
    if (el && !el.paused) {
      el.pause();
      el.currentTime = 0;
      stopped.push(label);
    }
  }
  if (typeof window.stsStopExportVideos === 'function') {
    const exportStopped = window.stsStopExportVideos(exceptExportVideo);
    if (exportStopped.length) stopped.push(...exportStopped);
  }
  _stsAudioSyncIndicator();
  return stopped;
};

/** Get the label of the currently-playing audio (first found), or null */
window.stsAudioGetPlaying = function () {
  for (const [label, el] of Object.entries(window._stsAudioRegistry)) {
    if (el && !el.paused) return label;
  }
  return null;
};

// Update the sidebar audio indicator from the current registry state
function _stsAudioSyncIndicator() {
    const btn = document.getElementById('sidebar-audio-btn');
    if (!btn) return;
    const playing = window.stsAudioGetPlaying();
    const labelEl = btn.querySelector('.audio-source-label');
    if (playing) {
      btn.classList.add('audio-playing');
      btn.title = `Playing: ${playing} — click to stop`;
      if (labelEl) labelEl.textContent = playing;
    } else {
      btn.classList.remove('audio-playing');
      btn.title = 'No audio playing';
      if (labelEl) labelEl.textContent = '';
    }
}
document.addEventListener('DOMContentLoaded', _stsAudioSyncIndicator);

function stsAudioToggle() {
  const playing = window.stsAudioGetPlaying();
  if (playing) {
    window.stsAudioStopAll();
    toast(`Stopped: ${playing}`, 'info');
  } else {
    toast('No audio playing', 'info');
  }
}

// ---- Navigation ----
function hasStoredEditorProject() {
  const bridgeKeys = ['sts-staged-timeline', 'sts-editor-boot-project', 'sts-editor-scenes'];
  for (const key of bridgeKeys) {
    const raw = key === 'sts-staged-timeline'
      ? sessionStorage.getItem(key)
      : localStorage.getItem(key);
    if (!raw) continue;
    try {
      const data = JSON.parse(raw);
      if (data && Array.isArray(data.scenes) && data.scenes.length) {
        return true;
      }
    } catch (_) { /* ignore malformed bridge data */ }
  }

  return !!localStorage.getItem('sts-editor-last-saved-project-id');
}

function switchPage(page, editorSource = 'internal') {
  $$('.page').forEach(p => p.classList.remove('active'));
  document.getElementById('page-' + page).classList.add('active');
  $$('.nav-item[data-page]').forEach(n => {
    n.classList.toggle('active', n.dataset.page === page);
  });
  try { sessionStorage.setItem('sts-current-page', page); } catch (_) {}
  $$('#mobile-nav button[data-page]').forEach(b => {
    const isActive = b.dataset.page === page;
    b.style.color = isActive ? 'var(--accent)' : 'var(--text-muted)';
    b.classList.toggle('active', isActive);
  });
  if (page === 'editor') {
    try {
      sessionStorage.setItem('sts-editor-entry-source', editorSource || 'internal');
    } catch (_) {}
    $('#main-content').style.overflowY = 'hidden';
    if (!hasStoredEditorProject()) {
      _showProjectBrowser();
      return;
    }
    initEditorInline();
  } else {
    $('#main-content').style.overflowY = 'auto';
  }
  if (page === 'assets' && typeof loadAssetsHistory === 'function') {
    loadAssetsHistory();
  }
  if (page === 'export-library' && typeof loadExportLibrary === 'function') {
    loadExportLibrary();
  }
}

// Explicit editor entry from sidebar/mobile menu.
function openEditorFromMenu() {
  switchPage('editor', 'menu');
}

// ---------------------------------------------------------------------------
// Project Browser — shown when editor has no stored project
// ---------------------------------------------------------------------------

async function _showProjectBrowser() {
  const loadingEl = $('#editor-loading');
  if (!loadingEl) return;

  loadingEl.style.display = 'flex';
  const shell = $('#editor-shell');
  if (shell) shell.style.display = 'none';

  loadingEl.innerHTML = `
    <div style="text-align:center;padding:20px">
      <div style="width:28px;height:28px;border:2px solid rgba(255,255,255,0.08);border-top-color:var(--accent);border-radius:50%;animation:spin 0.8s linear infinite;margin:0 auto 12px"></div>
      <p style="color:var(--text-muted);font-size:12px">Scanning projects...</p>
    </div>`;

  try {
    const projects = await api('/api/projects');

    if (!projects || !projects.length) {
      loadingEl.innerHTML = `
        <div style="text-align:center">
          <svg width="40" height="40" fill="none" stroke="var(--text-muted)" stroke-width="1.5" viewBox="0 0 24 24" style="margin:0 auto 12px;opacity:0.4">
            <rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M9 21V9"/>
          </svg>
          <p style="color:var(--text-secondary);font-size:13px">No projects found</p>
          <p style="font-size:11px;margin-top:6px;color:var(--text-muted);opacity:0.7">Generate content in the Pipeline tab first</p>
        </div>`;
      return;
    }

    const cards = projects.map(p => {
      const hasAssets = p.has_assets && p.asset_count > 0;
      const statusDots = [
        `<span title="Scenes" style="width:7px;height:7px;border-radius:50%;background:${p.has_scenes ? 'var(--accent)' : 'rgba(255,255,255,0.1)'};display:inline-block"></span>`,
        `<span title="Assets (${p.asset_count})" style="width:7px;height:7px;border-radius:50%;background:${hasAssets ? '#60a5fa' : 'rgba(255,255,255,0.1)'};display:inline-block"></span>`,
        `<span title="Audio" style="width:7px;height:7px;border-radius:50%;background:${p.has_audio ? '#a78bfa' : 'rgba(255,255,255,0.1)'};display:inline-block"></span>`,
        `<span title="Editor Save" style="width:7px;height:7px;border-radius:50%;background:${p.has_editor ? '#FFB347' : 'rgba(255,255,255,0.1)'};display:inline-block"></span>`,
      ].join('');

      const preview = p.text_preview
        ? `<p style="font-size:10px;color:var(--text-muted);margin:6px 0 0;line-height:1.4;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical">${p.text_preview}</p>`
        : '';

      const dur = p.total_duration ? `${p.total_duration.toFixed(1)}s` : '';
      const meta = [
        p.scene_count ? `${p.scene_count} scenes` : '',
        dur,
        p.voice || '',
      ].filter(Boolean).join(' · ');

      const readyState = hasAssets ? 'ready' : p.has_scenes ? 'scenes only' : 'partial';
      const readyColor = hasAssets ? 'var(--accent)' : 'var(--text-muted)';

      return `
        <div class="project-card" data-project-id="${p.project_id}" style="
          background:var(--bg-surface);border:1px solid var(--border);border-radius:8px;
          padding:12px 14px;transition:border-color 0.15s, background 0.15s;
        " onmouseover="this.style.borderColor='rgba(78,205,196,0.3)'"
           onmouseout="this.style.borderColor='var(--border)'">
          <div style="display:flex;align-items:center;justify-content:space-between;gap:8px">
            <span style="font-family:var(--font-mono,'JetBrains Mono',monospace);font-size:12px;font-weight:600;color:var(--text)">${p.project_id}</span>
            <span style="font-size:9px;color:${readyColor};font-weight:600;text-transform:uppercase;letter-spacing:0.04em">${readyState}</span>
          </div>
          <div style="display:flex;align-items:center;gap:4px;margin-top:6px">${statusDots}
            <span style="font-size:9px;color:var(--text-muted);margin-left:6px">${meta}</span>
          </div>
          ${preview}
          <div class="project-card-steps" style="display:none;margin-top:8px"></div>
          <button class="project-build-btn" style="
            margin-top:10px;width:100%;padding:7px 0;border-radius:6px;border:none;
            background:var(--accent);color:#000;font-size:11px;font-weight:700;
            cursor:pointer;letter-spacing:0.03em;transition:opacity 0.15s;
          " onmouseover="this.style.opacity='0.85'" onmouseout="this.style.opacity='1'">Build, Assemble & Edit</button>
        </div>`;
    }).join('');

    loadingEl.innerHTML = `
      <div style="width:100%;max-width:520px;padding:20px">
        <div style="text-align:center;margin-bottom:16px">
          <p style="color:var(--text);font-size:14px;font-weight:600;margin-bottom:4px">Open a Project</p>
          <p style="color:var(--text-muted);font-size:11px">${projects.length} project${projects.length !== 1 ? 's' : ''} found</p>
        </div>
        <div style="display:flex;flex-direction:column;gap:8px;max-height:60vh;overflow-y:auto;padding-right:4px">
          ${cards}
        </div>
        <div style="text-align:center;margin-top:14px">
          <div style="display:flex;align-items:center;justify-content:center;gap:6px;font-size:9px;color:var(--text-muted);opacity:0.6">
            <span style="width:7px;height:7px;border-radius:50%;background:var(--accent);display:inline-block"></span> Scenes
            <span style="width:7px;height:7px;border-radius:50%;background:#60a5fa;display:inline-block;margin-left:6px"></span> Assets
            <span style="width:7px;height:7px;border-radius:50%;background:#a78bfa;display:inline-block;margin-left:6px"></span> Audio
            <span style="width:7px;height:7px;border-radius:50%;background:#FFB347;display:inline-block;margin-left:6px"></span> Saved
          </div>
        </div>
      </div>`;

    // Click handler for build buttons
    loadingEl.querySelectorAll('.project-build-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const card = btn.closest('.project-card');
        const pid = card.dataset.projectId;
        _buildAndOpenProject(pid, card);
      });
    });

  } catch (e) {
    console.error('Failed to load projects:', e);
    loadingEl.innerHTML = `
      <div style="text-align:center">
        <svg width="40" height="40" fill="none" stroke="var(--coral)" stroke-width="1.5" viewBox="0 0 24 24" style="margin:0 auto 12px;opacity:0.7">
          <circle cx="12" cy="12" r="10"/><path d="M12 8v4M12 16h.01"/>
        </svg>
        <p style="color:var(--coral);font-size:13px">Failed to load projects</p>
        <p style="font-size:11px;margin-top:6px;color:var(--text-muted)">${e.message || 'Check the server console'}</p>
      </div>`;
  }
}

async function _buildAndOpenProject(projectId, cardEl) {
  const btn = cardEl.querySelector('.project-build-btn');
  const stepsEl = cardEl.querySelector('.project-card-steps');

  // Disable button, show steps area
  btn.disabled = true;
  btn.textContent = 'Building...';
  btn.style.opacity = '0.5';
  btn.style.cursor = 'wait';
  stepsEl.style.display = 'block';
  cardEl.style.borderColor = 'var(--accent)';

  const _step = (label, status) => {
    const colors = { pending: 'var(--text-muted)', running: 'var(--accent)', done: 'var(--accent)', error: 'var(--coral)', skip: 'var(--text-muted)' };
    const icons = {
      pending: '<span style="opacity:0.3">&#9679;</span>',
      running: '<span style="display:inline-block;width:10px;height:10px;border:1.5px solid rgba(255,255,255,0.08);border-top-color:var(--accent);border-radius:50%;animation:spin 0.6s linear infinite"></span>',
      done: '<span style="color:var(--accent)">&#10003;</span>',
      error: '<span style="color:var(--coral)">&#10007;</span>',
      skip: '<span style="opacity:0.3">&#8212;</span>',
    };
    // Find or create the step row
    let row = stepsEl.querySelector(`[data-step="${label}"]`);
    if (!row) {
      row = document.createElement('div');
      row.dataset.step = label;
      row.style.cssText = 'display:flex;align-items:center;gap:6px;padding:2px 0;font-size:10px;';
      stepsEl.appendChild(row);
    }
    row.innerHTML = `<span style="width:14px;text-align:center;flex-shrink:0">${icons[status]}</span><span style="color:${colors[status]}">${label}</span>`;
  };

  try {
    // Step 1: Load scenes
    _step('Loading scenes', 'running');
    await new Promise(r => setTimeout(r, 80));

    const data = await api(`/api/projects/${encodeURIComponent(projectId)}/assemble`, {
      method: 'POST',
    });

    if (!data || data.error) {
      _step('Loading scenes', 'error');
      toast(data?.error || 'Failed to assemble project', 'error');
      btn.textContent = 'Retry';
      btn.disabled = false;
      btn.style.opacity = '1';
      btn.style.cursor = 'pointer';
      return;
    }

    _step('Loading scenes', 'done');

    // Step 2: Resolve assets
    _step('Resolving assets', 'running');
    await new Promise(r => setTimeout(r, 100));
    const mediaCount = (data.scenes || []).filter(s => s.mediaUrl || s.image_url).length;
    _step(`Resolving assets (${mediaCount}/${data.scene_count || 0})`, 'done');

    // Step 3: Audio track
    _step('Audio track', 'running');
    await new Promise(r => setTimeout(r, 80));
    const hasAudio = data.audio_tracks && data.audio_tracks.length > 0;
    _step('Audio track', hasAudio ? 'done' : 'skip');

    // Step 4: Captions
    _step('Captions', 'running');
    await new Promise(r => setTimeout(r, 80));
    const hasCaps = data.captions && data.captions.captions && data.captions.captions.length > 0;
    _step(`Captions${hasCaps ? ` (${data.captions.captions.length})` : ''}`, hasCaps ? 'done' : 'skip');

    // Step 5: Save project
    _step('Saving project', 'running');
    await new Promise(r => setTimeout(r, 80));
    _step('Saving project', 'done');

    // Step 6: Launch editor
    _step('Launching editor', 'running');

    // Store as boot project for the editor
    const bootData = {
      project_id: data.project_id,
      project_name: data.project_name || data.project_id,
      source_folder: data.source_folder || '',
      style: data.style || '',
      total_duration: data.total_duration || 0,
      scene_count: data.scene_count || 0,
      staged_at: data.saved_at || new Date().toISOString(),
      scenes: data.scenes || [],
      audio_tracks: data.audio_tracks || [],
      ...(data.audio ? { audio: data.audio } : {}),
      ...(data.captions ? { captions: data.captions, captionsEnabled: true } : {}),
    };

    try {
      sessionStorage.setItem('sts-staged-timeline', JSON.stringify(bootData));
      localStorage.setItem('sts-editor-boot-project', JSON.stringify(bootData));
      localStorage.setItem('sts-editor-scenes', JSON.stringify(bootData));
      if (bootData.source_folder) {
        localStorage.setItem('sts-editor-source-folder', bootData.source_folder);
      }
      localStorage.setItem('sts-editor-last-project-id', projectId);
      localStorage.setItem('sts-editor-last-saved-project-id', projectId);
    } catch (_) {}

    if (data.captions) {
      try {
        localStorage.setItem('sts-editor-captions', JSON.stringify(data.captions));
      } catch (_) {}
    }

    _step('Launching editor', 'done');
    await new Promise(r => setTimeout(r, 200));

    // Launch
    sessionStorage.setItem('sts-editor-entry-source', 'internal');
    STATE.editorLoaded = false;
    initEditorInline();

  } catch (e) {
    console.error('Failed to build project:', e);
    _step('Error', 'error');
    toast('Build failed: ' + (e.message || 'Unknown error'), 'error');
    btn.textContent = 'Retry';
    btn.disabled = false;
    btn.style.opacity = '1';
    btn.style.cursor = 'pointer';
  }
}

function restoreInitialPage() {
  let page = 'pipeline';
  try {
    page = sessionStorage.getItem('sts-current-page') || page;
  } catch (_) {}
  if (!document.getElementById('page-' + page)) page = 'pipeline';

  const editorSource = page === 'editor' && !hasStoredEditorProject()
    ? 'menu'
    : 'internal';

  switchPage(page, editorSource);
}

function toggleSidebar() {
  $('#sidebar').classList.toggle('collapsed');
  STS.set('sts-sidebar', $('#sidebar').classList.contains('collapsed'));
}

// Restore sidebar state (read localStorage directly — runs before STS.init resolves)
if (localStorage.getItem('sts-sidebar') === 'true') {
  $('#sidebar').classList.add('collapsed');
}

// ---- Toast ----
function toast(msg, type = 'success') {
  const el = document.createElement('div');
  const bg = { success: 'rgba(78,205,196,0.92)', error: 'rgba(255,107,107,0.92)', info: 'rgba(30,42,58,0.92)' };
  el.className = 'toast-item';
  el.style.background = bg[type] || bg.info;
  el.textContent = msg;
  $('#toast-wrap').appendChild(el);
  setTimeout(() => {
    el.style.opacity = '0'; el.style.transition = 'opacity 0.3s, transform 0.3s';
    el.style.transform = 'translateX(20px)';
    setTimeout(() => el.remove(), 300);
  }, 3500);
}

// ---- Confirm Dialog ----
function confirmDialog({ title, desc, message, confirmLabel } = {}) {
  return new Promise(resolve => {
    const modal = $('#confirm-modal');
    $('#confirm-title').textContent = title || 'Move to Trash?';
    $('#confirm-desc').textContent = desc || 'This action can be undone from the TRASH folder.';
    $('#confirm-message').textContent = message || '';
    $('#confirm-detail').style.display = message ? '' : 'none';
    $('#confirm-ok').textContent = confirmLabel || 'Move to Trash';
    modal.classList.remove('hidden');
    modal.style.display = 'flex';
    function cleanup(result) {
      modal.classList.add('hidden'); modal.style.display = '';
      $('#confirm-ok').removeEventListener('click', onOk);
      $('#confirm-cancel').removeEventListener('click', onCancel);
      document.removeEventListener('keydown', onKey);
      resolve(result);
    }
    function onOk() { cleanup(true); }
    function onCancel() { cleanup(false); }
    function onKey(e) { if (e.key === 'Escape') cleanup(false); else if (e.key === 'Enter') cleanup(true); }
    $('#confirm-ok').addEventListener('click', onOk);
    $('#confirm-cancel').addEventListener('click', onCancel);
    document.addEventListener('keydown', onKey);
  });
}

// ---- API Helper ----
async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.error || `HTTP ${res.status}`); }
  return res.json();
}

function _downloadFilenameFromDisposition(disposition) {
  if (!disposition) return '';
  const utf8Match = disposition.match(/filename\*\s*=\s*UTF-8''([^;]+)/i);
  if (utf8Match && utf8Match[1]) {
    try { return decodeURIComponent(utf8Match[1]); } catch (_) { return utf8Match[1]; }
  }
  const plainMatch = disposition.match(/filename\s*=\s*"?([^"]+)"?/i);
  return plainMatch && plainMatch[1] ? plainMatch[1] : '';
}

async function downloadFileFromApi(url, fallbackFilename = 'download.bin') {
  const res = await fetch(url);
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    throw new Error(d.error || `Download failed (${res.status})`);
  }
  const blob = await res.blob();
  const contentDisposition = res.headers.get('Content-Disposition') || '';
  const filename = _downloadFilenameFromDisposition(contentDisposition) || fallbackFilename;
  const objectUrl = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = objectUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
  return { filename, sizeBytes: blob.size };
}

async function downloadProjectZip(projectId) {
  if (!projectId) throw new Error('Missing project id');
  return downloadFileFromApi(`/api/editor/export-zip/${encodeURIComponent(projectId)}`, `${projectId}.zip`);
}

// ---- Settings (backed by STS server settings manager) ----
window.STS_SETTINGS = { normalize: true, clean: true };

/** Play the completion chime if sound is enabled */
window.playDoneSound = function () {
  if (!STS.get('sts-sound-enabled')) return;
  try { new Audio('/assets/sounds/effects/done.mp3').play(); } catch (_) {}
};

function settingsToggle(key, val) {
  STS_SETTINGS[key] = val;
  STS.set('sts-' + key, val);
}

// Restore toggles on load (after STS.init resolves)
document.addEventListener('DOMContentLoaded', () => {
  restoreInitialPage();

  window._stsReady.then(() => {
    STS_SETTINGS.normalize = STS.get('sts-normalize');
    STS_SETTINGS.clean = STS.get('sts-clean');

    const normEl = $('#setting-normalize');
    const cleanEl = $('#setting-clean');
    if (normEl) normEl.checked = STS_SETTINGS.normalize;
    if (cleanEl) cleanEl.checked = STS_SETTINGS.clean;

    const storageEl = $('#setting-editor-localstorage');
    const sessionStorageEl = $('#setting-editor-sessionstorage');
    if (storageEl) storageEl.checked = STS.get('sts-editor-storage');
    if (sessionStorageEl) sessionStorageEl.checked = STS.get('sts-editor-session-storage');

    const soundEl = $('#setting-sound-notifications');
    if (soundEl) soundEl.checked = STS.get('sts-sound-enabled');
  });
});

// ---- Settings: Clear All Projects ----
let _clearChallenge = '';
function _renderClearPreview(modules, totalItems) {
  const box = $('#settings-clear-preview');
  if (!box) return;
  const rows = (modules || []).map(m => {
    const count = Number(m.items || 0);
    const entries = Array.isArray(m.entries) ? m.entries : [];
    const list = entries.length
      ? `<div style="margin-top:4px;display:flex;flex-direction:column;gap:2px">${entries.map(name => `<span class="font-mono" style="font-size:10px;color:var(--text-muted)">${esc(name)}</span>`).join('')}</div>`
      : '<div style="margin-top:4px"><span class="font-mono" style="font-size:10px;color:var(--text-muted)">empty</span></div>';
    return `<div style="padding:6px 0;border-bottom:1px solid rgba(255,255,255,0.04)">
      <div style="display:flex;justify-content:space-between;gap:10px">
        <span style="font-size:11px;color:var(--text-secondary)">${esc(m.page)} � ${esc(m.module)}</span>
        <span class="font-mono" style="font-size:11px;color:${count > 0 ? '#ef4444' : 'var(--text-muted)'}">${count}</span>
      </div>
      ${list}
    </div>`;
  }).join('');
  box.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
      <span style="font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--text-muted);font-weight:700">Items that will be moved to TRASH</span>
      <span class="font-mono" style="font-size:11px;color:#ef4444;font-weight:700">${totalItems || 0} total</span>
    </div>
    ${rows || '<p style="font-size:11px;color:var(--text-muted);text-align:center;margin:0">Nothing to clear</p>'}
  `;
}

async function settingsClearAllProjects() {
  const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
  _clearChallenge = '';
  for (let i = 0; i < 6; i++) _clearChallenge += chars[Math.random() * chars.length | 0];
  $('#settings-clear-challenge').textContent = _clearChallenge;
  $('#settings-clear-input').value = '';
  $('#settings-clear-error').style.display = 'none';
  const preview = $('#settings-clear-preview');
  if (preview) preview.innerHTML = '<p class="font-mono" style="font-size:11px;color:var(--text-muted);margin:0;text-align:center">Loading modules to clear...</p>';
  const btn = $('#settings-clear-confirm-btn');
  btn.disabled = true;
  btn.style.opacity = '0.4';
  const dlg = $('#settings-clear-dialog');
  dlg.style.display = 'flex';
  try {
    const data = await api('/api/settings/clear-all-projects/preview');
    _renderClearPreview(data.modules || [], data.total_items || 0);
  } catch (e) {
    if (preview) preview.innerHTML = `<p style="font-size:11px;color:var(--coral);margin:0;text-align:center">Failed to load preview: ${esc(e.message || 'unknown error')}</p>`;
  }
  setTimeout(() => $('#settings-clear-input').focus(), 100);
}

function settingsClearDialogClose() {
  $('#settings-clear-dialog').style.display = 'none';
  _clearChallenge = '';
}

function settingsClearInputCheck() {
  const val = $('#settings-clear-input').value.toUpperCase().trim();
  const match = val === _clearChallenge;
  const btn = $('#settings-clear-confirm-btn');
  btn.disabled = !match;
  btn.style.opacity = match ? '1' : '0.4';
}

async function settingsClearConfirm() {
  const val = $('#settings-clear-input').value.toUpperCase().trim();
  if (val !== _clearChallenge) {
    $('#settings-clear-error').textContent = 'Characters do not match. Try again.';
    $('#settings-clear-error').style.display = 'block';
    return;
  }
  const btn = $('#settings-clear-confirm-btn');
  btn.disabled = true;
  btn.textContent = 'Clearing...';
  try {
    const resp = await fetch('/api/settings/clear-all-projects', { method: 'DELETE' });
    const data = await resp.json();
    settingsClearDialogClose();
    if (data.status === 'cleared') {
      // Reset all in-memory state
      STATE.alignFile = null;
      STATE.alignResult = null;
      STATE.alignHistory = [];
      STATE.segmenterResult = null;
      STATE.segmenterAlignment = null;
      STATE.scenesSegData = null;
      STATE.scenesResult = null;
      STATE.assetsSceneData = null;
      STATE.assetStatuses = {};
      STATE.captionData = null;
      STATE.captionAlignment = null;
      // Nuke all browser storage and reset server settings
      localStorage.clear();
      sessionStorage.clear();
      STS.reset();
      // Clear module badges
      ['tts', 'timing', 'segmenter', 'scenes', 'assets', 'pipeline'].forEach(m => setModuleBadge(m, ''));
      // Refresh ALL history lists across every module
      if (typeof loadScenesHistory === 'function') loadScenesHistory();
      if (typeof pipelineLoadHistory === 'function') pipelineLoadHistory();
      if (typeof loadAlignHistory === 'function') loadAlignHistory();
      if (typeof loadSegHistory === 'function') loadSegHistory();
      if (typeof loadCaptionsHistory === 'function') loadCaptionsHistory();
      if (typeof loadAssetsHistory === 'function') loadAssetsHistory();
      if (typeof loadExportLibrary === 'function') loadExportLibrary(true);
      // Clear visible results
      const scenesResults = document.getElementById('scenes-results');
      if (scenesResults) scenesResults.style.display = 'none';
      const assetsControls = document.getElementById('assets-controls');
      if (assetsControls) assetsControls.style.display = 'none';
      const assetsEmpty = document.getElementById('assets-empty');
      if (assetsEmpty) assetsEmpty.style.display = '';
      const exportsMsg = data.exports_deleted ? ` (${data.exports_deleted} export item${data.exports_deleted !== 1 ? 's' : ''} deleted)` : '';
      toast(`Cleared ${data.count} project item${data.count !== 1 ? 's' : ''}${exportsMsg}`, 'success');
      try { sessionStorage.setItem('sts-current-page', 'pipeline'); } catch (_) {}
      setTimeout(() => location.reload(), 600);
    } else {
      toast(data.error || 'Failed to clear projects', 'error');
    }
  } catch (e) {
    toast('Failed to clear projects: ' + e.message, 'error');
  } finally {
    btn.textContent = 'Delete All';
    btn.disabled = false;
  }
}

// Close dialog on Escape key
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && $('#settings-clear-dialog').style.display === 'flex') {
    settingsClearDialogClose();
  }
});

// ---- Auto-Forward (Continue to Next Step) ----
function showContinueBar(containerId, nextPage, label, setupFn) {
  const container = document.getElementById(containerId);
  if (!container) return;
  const existing = container.querySelector('.continue-bar');
  if (existing) existing.remove();
  const bar = document.createElement('div');
  bar.className = 'continue-bar';
  bar.style.cssText = 'display:flex;align-items:center;gap:12px;padding:12px 16px;margin-top:16px;background:rgba(78,205,196,0.06);border:1px solid rgba(78,205,196,0.2);border-radius:10px;animation:reveal 0.4s cubic-bezier(0.16,1,0.3,1)';
  bar.innerHTML = `<svg width="16" height="16" fill="none" stroke="var(--accent)" stroke-width="2" viewBox="0 0 24 24"><path d="M5 12h14"/><path d="M12 5l7 7-7 7"/></svg><span style="font-size:13px;color:var(--text-secondary)">Ready for next step</span>`;
  const btn = document.createElement('button');
  btn.style.cssText = 'margin-left:auto;padding:8px 20px;background:var(--accent);color:var(--bg-darkest);border:none;border-radius:8px;font-size:12px;font-weight:600;cursor:pointer;transition:opacity 0.15s';
  btn.textContent = label;
  btn.onmouseenter = () => btn.style.opacity = '0.85';
  btn.onmouseleave = () => btn.style.opacity = '1';
  btn.onclick = () => { if (setupFn) setupFn(); switchPage(nextPage); };
  bar.appendChild(btn);
  container.appendChild(bar);
}

// ---- Module Project Badge ----
function setModuleBadge(moduleId, text) {
  const el = document.getElementById('badge-' + moduleId);
  if (!el) return;
  if (text) {
    el.textContent = text;
    el.classList.add('visible');
  } else {
    el.textContent = '';
    el.classList.remove('visible');
  }
}

// ---- Time Ago ----
function timeAgo(ts) {
  if (!ts) return '';
  const diff = (Date.now() - new Date(ts).getTime()) / 1000;
  if (diff < 60) return 'just now';
  if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
  if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
  return Math.floor(diff / 86400) + 'd ago';
}




