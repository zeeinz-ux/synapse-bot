/* ============================================================
   Hidden Hamlet v4.6 — Queue Manager
   ============================================================ */

(function() {
  const GUILD_ID = window.CURRENT_GUILD_ID || (() => {
    const m = window.location.pathname.match(/\/guild\/(\d+)/);
    return m ? m[1] : null;
  })();

  const els = {
    total: document.getElementById('q-total'),
    duration: document.getElementById('q-duration'),
    btnShuffle: document.getElementById('btn-shuffle'),
    btnClear: document.getElementById('btn-clear'),
    inputUrl: document.getElementById('q-input-url'),
    inputSource: document.getElementById('q-input-source'),
    btnAdd: document.getElementById('btn-add'),
    list: document.getElementById('queue-list'),
    toast: document.getElementById('queue-toast'),
    toastMsg: document.getElementById('queue-toast-msg'),
  };

  let tracks = [];

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

  function render() {
    els.total.textContent = tracks.length;
    const totalSec = tracks.reduce((a, t) => a + (t.duration || 0), 0);
    els.duration.textContent = fmtTime(totalSec);

    if (tracks.length === 0) {
      els.list.innerHTML = `
        <div class="queue-empty">
          <div class="queue-empty-icon">🎶</div>
          <div class="queue-empty-text">Queue kosong. Tambahkan lagu untuk memulai.</div>
        </div>`;
      return;
    }

    els.list.innerHTML = tracks.map((t, i) => `
      <div class="queue-track" data-index="${i}">
        <div class="queue-track-num">${i + 1}</div>
        <img class="queue-track-thumb" src="${t.thumbnail || ''}" alt="" onerror="this.style.display='none'">
        <div class="queue-track-info">
          <div class="queue-track-title">${t.title || 'Unknown'}</div>
          <div class="queue-track-artist">${t.artist || 'Unknown Artist'}</div>
        </div>
        <div class="queue-track-dur">${fmtTime(t.duration)}</div>
        <div class="queue-track-btns">
          <button class="q-btn q-btn-icon" title="Move to top" onclick="window.moveToTop(${i})">⤴</button>
          <button class="q-btn q-btn-icon danger" title="Remove" onclick="window.removeTrack(${i})">❌</button>
        </div>
      </div>
    `).join('');
  }

  async function loadQueue() {
    if (!GUILD_ID) return;
    try {
      const data = await api(`queue?guild_id=${GUILD_ID}`);
      tracks = data.queue || [];
      render();
    } catch (e) {
      showToast(`Error loading queue: ${e.message}`);
    }
  }

  async function sendAction(action, payload = {}) {
    if (!GUILD_ID) return showToast('Guild ID not found');
    try {
      await api('queue', {
        method: 'POST',
        body: { guild_id: GUILD_ID, action, ...payload },
      });
      showToast(`Sent: ${action}`);
      loadQueue();
    } catch (e) {
      showToast(`Error: ${e.message}`);
    }
  }

  window.removeTrack = function(index) {
    sendAction('remove', { index });
  };

  window.moveToTop = function(index) {
    sendAction('move_top', { index });
  };

  els.btnAdd.addEventListener('click', () => {
    const url = els.inputUrl.value.trim();
    const source = els.inputSource.value;
    if (!url) return showToast('Enter a URL or query');
    sendAction('add', { query: url, source });
    els.inputUrl.value = '';
  });

  els.inputUrl.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') els.btnAdd.click();
  });

  els.btnClear.addEventListener('click', () => {
    if (confirm('Clear entire queue?')) sendAction('clear');
  });

  els.btnShuffle.addEventListener('click', () => sendAction('shuffle'));

  // Init
  loadQueue();
  setInterval(loadQueue, 5000);
})();
