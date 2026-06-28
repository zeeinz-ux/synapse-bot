/* ============================================================
   Hidden Hamlet v4.6 — Now Playing Controller
   Real-time sync with diff-based DOM updates
   ============================================================ */

(function() {
  const GUILD_ID = window.CURRENT_GUILD_ID || (() => {
    const m = window.location.pathname.match(/\/guild\/(\d+)/);
    return m ? m[1] : null;
  })();

  // DOM refs
  const els = {
    status:       document.getElementById('np-status'),
    statusText:   document.getElementById('np-status-text'),
    art:          document.getElementById('np-art'),
    artPlaceholder: document.getElementById('np-art-placeholder'),
    title:        document.getElementById('np-title'),
    artist:       document.getElementById('np-artist'),
    progressFill: document.getElementById('np-progress-fill'),
    currentTime:  document.getElementById('np-current'),
    duration:     document.getElementById('np-duration'),
    btnPlay:      document.getElementById('btn-play'),
    btnPrev:      document.getElementById('btn-prev'),
    btnNext:      document.getElementById('btn-next'),
    btnStop:      document.getElementById('btn-stop'),
    volume:       document.getElementById('np-volume'),
    volValue:     document.getElementById('np-vol-value'),
    channelSelect: document.getElementById('np-channel'),
    toggleAutojoin: document.getElementById('toggle-autojoin'),
    toggle247:    document.getElementById('toggle-247'),
    toggleAnnounce: document.getElementById('toggle-announce'),
    defaultVol:   document.getElementById('np-default-vol'),
    defaultVolValue: document.getElementById('np-default-vol-value'),
    btnDisconnect: document.getElementById('btn-disconnect'),
    btnClear:     document.getElementById('btn-clear'),
    btnShuffle:   document.getElementById('btn-shuffle'),
    btnLoop:      document.getElementById('btn-loop'),
    toast:        document.getElementById('np-toast'),
    toastMsg:     document.getElementById('np-toast-msg'),
    disconnected: document.getElementById('np-disconnected'),
    controls:     document.getElementById('np-controls-panel'),
    progressBar:  document.getElementById('np-progress-bar'),
  };

  // State
  let pollInterval = null;
  let isPlaying = false;
  let _consecutiveErrors = 0;
  let _prevTrackKey = '';
  let _prevConnected = null;
  let _prevPositionSec = -1;
  let _prevPlaying = null;

  function showToast(msg) {
    els.toastMsg.textContent = msg;
    els.toast.classList.add('show');
    setTimeout(() => els.toast.classList.remove('show'), 2500);
  }

  async function api(endpoint, opts = {}) {
    const url = `/api/music/${endpoint}`;
    const res = await fetch(url, {
      headers: { 'Content-Type': 'application/json' },
      ...opts,
      body: opts.body ? JSON.stringify(opts.body) : undefined,
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json().catch(() => ({}));
  }

  function fmtTime(sec) {
    if (!sec || isNaN(sec)) return '0:00';
    const m = Math.floor(sec / 60);
    const s = Math.floor(sec % 60);
    return `${m}:${s.toString().padStart(2, '0')}`;
  }

  // ── Diff-based DOM update (no flicker) ──
  function updatePlayer(data) {
    const connected = data.connected === true;
    const track = data.track || {};
    const trackKey = track.title + '|' + track.artist + '|' + track.duration;

    // --- Connection status (only on change) ---
    if (connected !== _prevConnected) {
      _prevConnected = connected;
      showDisconnected(!connected);
      if (connected) {
        els.status.className = 'np-status np-status-playing';
        els.statusText.textContent = `Playing in #${data.channel_name || 'unknown'}`;
        els.controls.style.display = '';
      } else {
        els.status.className = 'np-status np-status-idle';
        els.statusText.textContent = 'Idle — Not connected';
        els.controls.style.display = 'none';
      }
    }

    if (!connected) {
      isPlaying = false;
      return;
    }

    // --- Track metadata (only when track changes) ---
    if (trackKey !== _prevTrackKey) {
      _prevTrackKey = trackKey;
      _prevPositionSec = -1; // force progress update below

      if (track.title) {
        els.title.textContent = track.title;
      }
      if (track.artist) {
        els.artist.textContent = track.artist;
      }
      els.duration.textContent = fmtTime(track.duration);

      if (track.thumbnail) {
        if (els.art.src !== track.thumbnail) {
          els.art.src = track.thumbnail;
        }
        els.art.style.display = 'block';
        els.artPlaceholder.style.display = 'none';
      } else {
        els.art.style.display = 'none';
        els.artPlaceholder.style.display = 'flex';
      }
    }

    // --- Play state (only on change) ---
    const playing = data.playing === true;
    if (playing !== _prevPlaying) {
      _prevPlaying = playing;
      isPlaying = playing;
      els.btnPlay.textContent = playing ? '⏸' : '▶';
    }

    // --- Progress bar (always update — moves every poll) ---
    const posSec = data.position || 0;
    const durSec = track.duration || 0;
    const pct = durSec ? (posSec / durSec) * 100 : 0;
    els.progressFill.style.width = `${Math.min(pct, 100)}%`;
    els.currentTime.textContent = fmtTime(posSec);
    _prevPositionSec = posSec;
  }

  // ── Disconnected overlay ──
  function showDisconnected(offline) {
    if (offline) {
      els.disconnected.style.display = 'flex';
    } else {
      els.disconnected.style.display = 'none';
    }
  }

  async function loadStatus() {
    if (!GUILD_ID) return;
    try {
      const data = await api(`status?guild_id=${GUILD_ID}`);
      _consecutiveErrors = 0;
      updatePlayer(data);
    } catch (e) {
      _consecutiveErrors++;
      if (_consecutiveErrors >= 3) {
        showDisconnected(true);
        if (_prevConnected !== false) {
          _prevConnected = false;
          els.status.className = 'np-status np-status-idle';
          els.statusText.textContent = 'Bot disconnected';
          els.controls.style.display = 'none';
        }
      }
    }
  }

  async function loadChannels() {
    if (!GUILD_ID) return;
    try {
      const data = await api(`channels?guild_id=${GUILD_ID}`);
      const channels = data.channels || [];
      els.channelSelect.innerHTML = '<option value="">— Select Channel —</option>' +
        channels.map(c => `<option value="${c.id}">${c.name}</option>`).join('');
    } catch (e) {
      console.error('Failed to load channels', e);
    }
  }

  async function sendControl(action, payload = {}) {
    if (!GUILD_ID) return showToast('Guild ID not found');
    try {
      await api('control', {
        method: 'POST',
        body: { guild_id: GUILD_ID, action, ...payload },
      });
      showToast(`Sent: ${action}`);
      loadStatus();
    } catch (e) {
      showToast(`Error: ${e.message}`);
    }
  }

  // ── Cooldown map to prevent double-clicks ──
  const _cooldowns = {};

  function _withCooldown(el, action, handler) {
    el.addEventListener('click', (e) => {
      if (_cooldowns[action]) return;
      _cooldowns[action] = true;
      el.style.opacity = '0.6';
      handler(e);
      setTimeout(() => { _cooldowns[action] = false; el.style.opacity = ''; }, 1000);
    });
  }

  // Optimistic toggle for play/pause
  function _togglePlayBtn() {
    isPlaying = !isPlaying;
    els.btnPlay.textContent = isPlaying ? '⏸' : '▶';
  }

  _withCooldown(els.btnPlay, 'playtoggle', () => {
    const action = isPlaying ? 'pause' : 'play';
    _togglePlayBtn();
    sendControl(action);
  });
  _withCooldown(els.btnPrev, 'prev', () => sendControl('prev'));
  _withCooldown(els.btnNext, 'skip', () => sendControl('skip'));
  _withCooldown(els.btnStop, 'stop', () => sendControl('stop'));

  els.volume.addEventListener('input', (e) => {
    const val = e.target.value;
    els.volValue.textContent = `${val}%`;
  });
  els.volume.addEventListener('change', (e) => {
    sendControl('volume', { volume: parseInt(e.target.value, 10) });
  });

  els.defaultVol.addEventListener('input', (e) => {
    els.defaultVolValue.textContent = `${e.target.value}%`;
  });

  els.channelSelect.addEventListener('change', (e) => {
    if (e.target.value) sendControl('join', { channel_id: e.target.value });
  });

  function bindToggle(el, settingKey) {
    el.addEventListener('click', () => {
      const active = el.classList.toggle('active');
      sendControl('setting', { key: settingKey, value: active });
    });
  }
  bindToggle(els.toggleAutojoin, 'autojoin');
  bindToggle(els.toggle247, '247_mode');
  bindToggle(els.toggleAnnounce, 'announce');

  _withCooldown(els.btnDisconnect, 'disconnect', () => sendControl('disconnect'));
  els.btnClear.addEventListener('click', () => {
    if (confirm('Clear entire queue?')) {
      sendControl('clear');
      els.btnClear.style.opacity = '0.6';
      setTimeout(() => els.btnClear.style.opacity = '', 1000);
    }
  });
  _withCooldown(els.btnShuffle, 'shuffle', () => sendControl('shuffle'));
  _withCooldown(els.btnLoop, 'loop', () => sendControl('loop'));

  // Progress bar seek
  els.progressBar.addEventListener('click', (e) => {
    const rect = els.progressBar.getBoundingClientRect();
    const pct = (e.clientX - rect.left) / rect.width;
    sendControl('seek', { position_pct: pct });
  });

  // ── Init ──
  loadChannels();
  loadStatus();
  pollInterval = setInterval(loadStatus, 3000);

  // Cleanup on page leave
  window.addEventListener('beforeunload', () => {
    if (pollInterval) clearInterval(pollInterval);
  });
})();
