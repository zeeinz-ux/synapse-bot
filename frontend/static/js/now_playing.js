/* ============================================================
   Hidden Hamlet v4.6 — Now Playing Controller
   ============================================================ */

(function() {
  const GUILD_ID = window.CURRENT_GUILD_ID || (() => {
    const m = window.location.pathname.match(/\/guild\/(\d+)/);
    return m ? m[1] : null;
  })();

  // DOM refs
  const els = {
    status: document.getElementById('np-status'),
    statusText: document.getElementById('np-status-text'),
    art: document.getElementById('np-art'),
    artPlaceholder: document.getElementById('np-art-placeholder'),
    title: document.getElementById('np-title'),
    artist: document.getElementById('np-artist'),
    progressBar: document.getElementById('np-progress-bar'),
    progressFill: document.getElementById('np-progress-fill'),
    currentTime: document.getElementById('np-current'),
    duration: document.getElementById('np-duration'),
    btnPlay: document.getElementById('btn-play'),
    btnPrev: document.getElementById('btn-prev'),
    btnNext: document.getElementById('btn-next'),
    btnStop: document.getElementById('btn-stop'),
    volume: document.getElementById('np-volume'),
    volValue: document.getElementById('np-vol-value'),
    channelSelect: document.getElementById('np-channel'),
    toggleAutojoin: document.getElementById('toggle-autojoin'),
    toggle247: document.getElementById('toggle-247'),
    toggleAnnounce: document.getElementById('toggle-announce'),
    defaultVol: document.getElementById('np-default-vol'),
    defaultVolValue: document.getElementById('np-default-vol-value'),
    btnDisconnect: document.getElementById('btn-disconnect'),
    btnClear: document.getElementById('btn-clear'),
    btnShuffle: document.getElementById('btn-shuffle'),
    btnLoop: document.getElementById('btn-loop'),
    toast: document.getElementById('np-toast'),
    toastMsg: document.getElementById('np-toast-msg'),
  };

  let pollInterval = null;
  let isPlaying = false;

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

  function updateStatus(connected, channelName) {
    if (connected) {
      els.status.className = 'np-status np-status-playing';
      els.statusText.textContent = `Playing in #${channelName || 'unknown'}`;
    } else {
      els.status.className = 'np-status np-status-idle';
      els.statusText.textContent = 'Idle — Not connected';
    }
  }

  function updatePlayer(data) {
    const track = data.track || {};
    isPlaying = data.playing || false;

    els.title.textContent = track.title || '—';
    els.artist.textContent = track.artist || '—';
    els.duration.textContent = fmtTime(track.duration);
    els.currentTime.textContent = fmtTime(data.position);

    const pct = track.duration ? (data.position / track.duration) * 100 : 0;
    els.progressFill.style.width = `${Math.min(pct, 100)}%`;

    els.btnPlay.textContent = isPlaying ? '⏸' : '▶';

    if (track.thumbnail) {
      els.art.src = track.thumbnail;
      els.art.style.display = 'block';
      els.artPlaceholder.style.display = 'none';
    } else {
      els.art.style.display = 'none';
      els.artPlaceholder.style.display = 'flex';
    }

    updateStatus(data.connected, data.channel_name);
  }

  async function loadStatus() {
    if (!GUILD_ID) return;
    try {
      const data = await api(`status?guild_id=${GUILD_ID}`);
      updatePlayer(data);
    } catch (e) {
      // silent fail on poll
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

  // Event bindings
  els.btnPlay.addEventListener('click', () => sendControl(isPlaying ? 'pause' : 'play'));
  els.btnPrev.addEventListener('click', () => sendControl('prev'));
  els.btnNext.addEventListener('click', () => sendControl('skip'));
  els.btnStop.addEventListener('click', () => sendControl('stop'));

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

  els.btnDisconnect.addEventListener('click', () => sendControl('disconnect'));
  els.btnClear.addEventListener('click', () => {
    if (confirm('Clear entire queue?')) sendControl('clear');
  });
  els.btnShuffle.addEventListener('click', () => sendControl('shuffle'));
  els.btnLoop.addEventListener('click', () => sendControl('loop'));

  // Progress bar seek
  els.progressBar.addEventListener('click', (e) => {
    const rect = els.progressBar.getBoundingClientRect();
    const pct = (e.clientX - rect.left) / rect.width;
    sendControl('seek', { position_pct: pct });
  });

  // Init
  loadChannels();
  loadStatus();
  pollInterval = setInterval(loadStatus, 3000);

  // Cleanup on page leave
  window.addEventListener('beforeunload', () => {
    if (pollInterval) clearInterval(pollInterval);
  });
})();
