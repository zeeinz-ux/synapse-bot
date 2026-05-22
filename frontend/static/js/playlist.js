/* ============================================================
   Hidden Hamlet v4.6 — Playlist Manager (localStorage + Sync)
   ============================================================ */

(function() {
  const GUILD_ID = window.CURRENT_GUILD_ID || (() => {
    const m = window.location.pathname.match(/\/guild\/(\d+)/);
    return m ? m[1] : null;
  })();

  const STORAGE_KEY = GUILD_ID ? `hh_playlists_${GUILD_ID}` : 'hh_playlists_default';

  const els = {
    sidebarList: document.getElementById('pl-sidebar-list'),
    titleInput: document.getElementById('pl-title'),
    tracksContainer: document.getElementById('pl-tracks'),
    addRow: document.getElementById('pl-add-row'),
    newUrl: document.getElementById('pl-new-url'),
    btnNew: document.getElementById('btn-new-pl'),
    btnSave: document.getElementById('btn-save-pl'),
    btnLoadQueue: document.getElementById('btn-load-queue'),
    btnExport: document.getElementById('btn-export'),
    btnImportTrigger: document.getElementById('btn-import-trigger'),
    btnImportFile: document.getElementById('btn-import-file'),
    btnSync: document.getElementById('btn-sync-server'),
    toast: document.getElementById('pl-toast'),
    toastMsg: document.getElementById('pl-toast-msg'),
  };

  let playlists = [];
  let activeId = null;

  function showToast(msg) {
    els.toastMsg.textContent = msg;
    els.toast.classList.add('show');
    setTimeout(() => els.toast.classList.remove('show'), 2500);
  }

  function generateId(prefix = 'id') {
    return `${prefix}_${Math.random().toString(36).slice(2, 9)}_${Date.now().toString(36)}`;
  }

  function loadFromStorage() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return;
      const data = JSON.parse(raw);
      if (data && Array.isArray(data.playlists)) {
        playlists = data.playlists;
      }
    } catch (e) {
      console.error('Playlist load error', e);
      playlists = [];
    }
  }

  function saveToStorage() {
    const payload = {
      version: '1.0',
      guild_id: GUILD_ID || 'default',
      last_updated: new Date().toISOString(),
      playlists: playlists,
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
  }

  function fmtTime(sec) {
    if (!sec || isNaN(sec)) return '0:00';
    const m = Math.floor(sec / 60);
    const s = Math.floor(sec % 60);
    return `${m}:${s.toString().padStart(2, '0')}`;
  }

  function renderSidebar() {
    if (playlists.length === 0) {
      els.sidebarList.innerHTML = `<div style="padding:12px;color:var(--text-muted);font-size:0.8rem;text-align:center;">No playlists yet</div>`;
      return;
    }
    els.sidebarList.innerHTML = playlists.map(pl => `
      <div class="pl-item ${pl.id === activeId ? 'active' : ''}" data-id="${pl.id}">
        <div style="display:flex;align-items:center;gap:8px;overflow:hidden;">
          <span class="pl-item-name">${pl.name || 'Untitled'}</span>
          <span class="pl-item-count">${pl.tracks?.length || 0}</span>
        </div>
        <button class="pl-item-del" data-del="${pl.id}" title="Delete">🗑</button>
      </div>
    `).join('');

    // Bind clicks
    els.sidebarList.querySelectorAll('.pl-item').forEach(el => {
      el.addEventListener('click', (e) => {
        if (e.target.closest('.pl-item-del')) return;
        selectPlaylist(el.dataset.id);
      });
    });
    els.sidebarList.querySelectorAll('.pl-item-del').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        deletePlaylist(btn.dataset.del);
      });
    });
  }

  function renderMain() {
    const pl = playlists.find(p => p.id === activeId);
    if (!pl) {
      els.titleInput.value = 'Select a playlist';
      els.titleInput.readOnly = true;
      els.addRow.style.display = 'none';
      els.tracksContainer.innerHTML = `
        <div class="pl-empty">
          <div class="pl-empty-icon">🎵</div>
          <div>Select or create a playlist to manage tracks</div>
        </div>`;
      return;
    }

    els.titleInput.value = pl.name || 'Untitled';
    els.titleInput.readOnly = false;
    els.addRow.style.display = 'flex';

    const tracks = pl.tracks || [];
    if (tracks.length === 0) {
      els.tracksContainer.innerHTML = `
        <div class="pl-empty">
          <div class="pl-empty-icon">📭</div>
          <div>This playlist is empty. Add some tracks!</div>
        </div>`;
      return;
    }

    els.tracksContainer.innerHTML = tracks.map((t, i) => `
      <div class="pl-track">
        <div class="pl-track-num">${i + 1}</div>
        <div class="pl-track-info">
          <div class="pl-track-title">${t.title || 'Unknown'}</div>
          <div class="pl-track-artist">${t.artist || 'Unknown Artist'}</div>
        </div>
        <div class="pl-track-dur">${fmtTime(t.duration)}</div>
        <button class="pl-track-del" data-idx="${i}" title="Remove">❌</button>
      </div>
    `).join('');

    els.tracksContainer.querySelectorAll('.pl-track-del').forEach(btn => {
      btn.addEventListener('click', () => removeTrack(parseInt(btn.dataset.idx, 10)));
    });
  }

  function selectPlaylist(id) {
    activeId = id;
    renderSidebar();
    renderMain();
  }

  function createPlaylist() {
    const name = prompt('Playlist name:');
    if (!name || !name.trim()) return;
    const pl = {
      id: generateId('pl'),
      name: name.trim(),
      created_at: new Date().toISOString(),
      tracks: [],
    };
    playlists.push(pl);
    saveToStorage();
    selectPlaylist(pl.id);
    showToast('Playlist created');
  }

  function deletePlaylist(id) {
    if (!confirm('Delete this playlist?')) return;
    playlists = playlists.filter(p => p.id !== id);
    if (activeId === id) activeId = playlists.length ? playlists[0].id : null;
    saveToStorage();
    renderSidebar();
    renderMain();
    showToast('Playlist deleted');
  }

  function savePlaylist() {
    const pl = playlists.find(p => p.id === activeId);
    if (!pl) return;
    pl.name = els.titleInput.value.trim() || pl.name;
    saveToStorage();
    renderSidebar();
    showToast('Playlist saved');
  }

  function addTrack() {
    const url = els.newUrl.value.trim();
    if (!url) return showToast('Enter a URL or query');
    const pl = playlists.find(p => p.id === activeId);
    if (!pl) return;
    pl.tracks.push({
      id: generateId('tr'),
      title: url, // Will be resolved by backend later
      artist: 'Pending',
      duration: 0,
      source: 'unknown',
      url: url,
    });
    saveToStorage();
    els.newUrl.value = '';
    renderMain();
    renderSidebar();
    showToast('Track added (title will resolve on load)');
  }

  function removeTrack(index) {
    const pl = playlists.find(p => p.id === activeId);
    if (!pl) return;
    pl.tracks.splice(index, 1);
    saveToStorage();
    renderMain();
    renderSidebar();
    showToast('Track removed');
  }

  async function loadToQueue() {
    const pl = playlists.find(p => p.id === activeId);
    if (!pl || !pl.tracks?.length) return showToast('Playlist empty');
    if (!GUILD_ID) return showToast('Guild ID not found');

    try {
      const res = await fetch('/api/music/queue/bulk', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          guild_id: GUILD_ID,
          action: 'load_playlist',
          tracks: pl.tracks,
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      showToast(`Loaded ${pl.tracks.length} tracks to queue`);
    } catch (e) {
      showToast(`Error: ${e.message}`);
    }
  }

  function exportJSON() {
    const payload = {
      version: '1.0',
      guild_id: GUILD_ID || 'default',
      exported_at: new Date().toISOString(),
      playlists: playlists,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `hidden_hamlet_playlists_${GUILD_ID || 'export'}.json`;
    a.click();
    URL.revokeObjectURL(url);
    showToast('Exported to JSON');
  }

  function importJSON(file) {
    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const data = JSON.parse(e.target.result);
        if (!Array.isArray(data.playlists)) throw new Error('Invalid format');
        if (confirm(`Import ${data.playlists.length} playlists? This will merge with existing.`)) {
          // Merge by ID to avoid duplicates
          data.playlists.forEach(imported => {
            const existing = playlists.find(p => p.id === imported.id);
            if (existing) {
              existing.name = imported.name || existing.name;
              existing.tracks = imported.tracks || existing.tracks;
            } else {
              playlists.push(imported);
            }
          });
          saveToStorage();
          renderSidebar();
          if (!activeId && playlists.length) selectPlaylist(playlists[0].id);
          showToast('Import successful');
        }
      } catch (err) {
        showToast('Invalid JSON file');
      }
    };
    reader.readAsText(file);
  }

  async function syncToServer() {
    if (!GUILD_ID) return showToast('Guild ID not found');
    if (!playlists.length) return showToast('No playlists to sync');

    try {
      const res = await fetch('/api/music/playlists/sync', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          guild_id: GUILD_ID,
          playlists: playlists,
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      showToast('Synced to server');
    } catch (e) {
      showToast(`Sync error: ${e.message}`);
    }
  }

  // Event bindings
  els.btnNew.addEventListener('click', createPlaylist);
  els.btnSave.addEventListener('click', savePlaylist);
  els.btnLoadQueue.addEventListener('click', loadToQueue);
  els.btnExport.addEventListener('click', exportJSON);
  els.btnImportTrigger.addEventListener('click', () => els.btnImportFile.click());
  els.btnImportFile.addEventListener('change', (e) => {
    if (e.target.files[0]) importJSON(e.target.files[0]);
    e.target.value = '';
  });
  els.btnSync.addEventListener('click', syncToServer);
  els.newUrl.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') addTrack();
  });
  document.getElementById('btn-add-track').addEventListener('click', addTrack);

  // Init
  loadFromStorage();
  renderSidebar();
  renderMain();
  if (!activeId && playlists.length) selectPlaylist(playlists[0].id);
})();
