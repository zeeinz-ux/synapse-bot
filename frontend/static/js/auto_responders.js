/**
 * =====================================================
 * Auto Responders Page JavaScript - Hidden Hamlet
 * =====================================================
 */

const guildIdElement = document.getElementById('guild-id');
const guildId = guildIdElement ? guildIdElement.value : '';
let editingId = null;

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', function() {
  if (guildId) {
    loadAutoResponders();
    setupEventListeners();
  }
});

/**
 * Fetch the bot's channel cache and populate the include/exclude channel selects.
 * This bypasses the cross-process issue: the Flask process has no Discord
 * gateway, so we read the channels that the bot process already synced to
 * Firestore (collection bot_status/guild_channels).
 */
async function populateChannelSelects() {
  const includeSel = document.getElementById('ar-include-channels');
  const excludeSel = document.getElementById('ar-exclude-channels');
  const includeCounter = document.getElementById('ar-include-channels-count');
  const excludeCounter = document.getElementById('ar-exclude-channels-count');
  if (!includeSel || !excludeSel) return;

  // Show loading state
  const loadingHtml = '<option disabled>⏳ Memuat channel…</option>';
  includeSel.innerHTML = loadingHtml;
  excludeSel.innerHTML = loadingHtml;
  if (includeCounter) includeCounter.textContent = 'Memuat…';
  if (excludeCounter) excludeCounter.textContent = 'Memuat…';

  try {
    const resp = await fetch(`/api/guilds/${guildId}/channels`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    const channels = data.channels || [];

    if (channels.length === 0) {
      const emptyHtml = '<option disabled>⚠️ Belum ada channel terdaftar. Tunggu bot sync, atau tambahkan channel manual.</option>';
      includeSel.innerHTML = emptyHtml;
      excludeSel.innerHTML = emptyHtml;
      if (includeCounter) includeCounter.textContent = 'Channel belum tersedia — coba refresh beberapa saat lagi.';
      if (excludeCounter) excludeCounter.textContent = 'Channel belum tersedia — coba refresh beberapa saat lagi.';
      return;
    }

    // Sort alphabetically for easier scanning
    channels.sort((a, b) => a.name.localeCompare(b.name));

    const optionsHtml = channels
      .map((c) => `<option value="${c.id}"># ${escapeHtml(c.name)}</option>`)
      .join('');
    includeSel.innerHTML = optionsHtml;
    excludeSel.innerHTML = optionsHtml;
    if (includeCounter) includeCounter.textContent = `${channels.length} channel tersedia — tahan Ctrl/Cmd untuk pilih banyak`;
    if (excludeCounter) excludeCounter.textContent = `${channels.length} channel tersedia — tahan Ctrl/Cmd untuk pilih banyak`;
  } catch (err) {
    console.error('[Auto Responders] Failed to load channels:', err);
    const errHtml = `<option disabled>❌ Gagal memuat channel: ${escapeHtml(String(err))}</option>`;
    includeSel.innerHTML = errHtml;
    excludeSel.innerHTML = errHtml;
    if (includeCounter) includeCounter.textContent = 'Gagal memuat channel.';
    if (excludeCounter) excludeCounter.textContent = 'Gagal memuat channel.';
  }
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/**
 * Load all auto responders from API
 */
async function loadAutoResponders() {
  const listEl = document.getElementById('ar-list');
  const toggleEl = document.getElementById('global-toggle');

  if (!listEl) return;

  try {
    const resp = await fetch(`/api/auto-responders/${guildId}`);
    const data = await resp.json();

    if (data.success) {
      if (toggleEl) {
        toggleEl.checked = data.enabled;
      }
      renderList(data.responders || []);
    } else {
      listEl.innerHTML = `<div class="empty">Error: ${data.message}</div>`;
    }
  } catch (e) {
    listEl.innerHTML = `<div class="empty">Gagal memuat data</div>`;
    console.error('[Auto Responders] Load error:', e);
  }
}

/**
 * Render the list of auto responders
 */
function renderList(responders) {
  const listEl = document.getElementById('ar-list');
  if (!listEl) return;

  if (responders.length === 0) {
    listEl.innerHTML = `
      <div class="empty">
        <div class="empty-icon">📝</div>
        <p>Belum ada auto-responder</p>
        <p style="font-size: 0.75rem;">Buat yang pertama dengan form di samping!</p>
      </div>
    `;
    return;
  }

  listEl.innerHTML = responders.map(ar => `
    <div class="ar-item" data-id="${ar.id}">
      <div class="ar-item-header">
        <span class="ar-keywords">${Array.isArray(ar.keyword) ? ar.keyword.join(', ') : ar.keyword}</span>
        <span class="ar-type-badge">${ar.response_type}</span>
      </div>
      <div class="ar-response">${ar.response_content || '(no response)'}</div>
      <div class="ar-meta">
        <span>Cooldown: ${ar.cooldown_seconds}s</span>
        ${ar.case_sensitive ? '<span>Case Sensitive</span>' : ''}
        ${ar.regex_enabled ? '<span>Regex</span>' : ''}
        ${ar.match_whole_word ? '<span>Whole Word</span>' : ''}
        ${ar.mention_user ? '<span>Mention</span>' : ''}
        ${ar.delete_trigger ? '<span>Delete</span>' : ''}
      </div>
      <div class="ar-actions">
        <button class="ar-btn ar-btn-edit" onclick="editResponder('${ar.id}')">✏️ Edit</button>
        <button class="ar-btn ar-btn-toggle ${ar.enabled ? '' : 'off'}" onclick="toggleResponder('${ar.id}', ${!ar.enabled})">
          ${ar.enabled ? '⏸️ Disable' : '▶️ Enable'}
        </button>
        <button class="ar-btn ar-btn-delete" onclick="deleteResponder('${ar.id}')">🗑️ Hapus</button>
      </div>
    </div>
  `).join('');
}

/**
 * Setup event listeners for form interactions
 */
function setupEventListeners() {
  // Populate channel selects dynamically from the bot's channel cache.
  populateChannelSelects();

  // Global toggle
  const toggleEl = document.getElementById('global-toggle');
  if (toggleEl) {
    toggleEl.addEventListener('change', async function(e) {
      try {
        await fetch(`/api/auto-responders/${guildId}/toggle`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ enabled: e.target.checked })
        });
      } catch (err) {
        console.error('[Auto Responders] Toggle error:', err);
      }
    });
  }

  // Channel multi-select: update visible "N dipilih" counter
  ['ar-include-channels', 'ar-exclude-channels'].forEach((id) => {
    const sel = document.getElementById(id);
    const counter = document.getElementById(id + '-count');
    if (sel && counter) {
      const update = () => {
        const n = sel.selectedOptions.length;
        counter.textContent = n === 0
          ? 'Tidak ada dipilih (berlaku untuk semua channel)'
          : `${n} channel dipilih`;
        counter.classList.toggle('has-selection', n > 0);
      };
      sel.addEventListener('change', update);
      update();
    }
  });

  // Response type change
  const responseTypeEl = document.getElementById('ar-response-type');
  if (responseTypeEl) {
    responseTypeEl.addEventListener('change', function(e) {
      const type = e.target.value;
      const contentGroup = document.getElementById('response-content-group');
      const embedOptions = document.getElementById('embed-options');
      const imageOptions = document.getElementById('image-options');

      if (contentGroup) {
        contentGroup.style.display = type === 'image' ? 'none' : 'block';
      }
      if (embedOptions) {
        embedOptions.style.display = type === 'embed' ? 'block' : 'none';
      }
      if (imageOptions) {
        imageOptions.style.display = type === 'image' ? 'block' : 'none';
      }
    });
  }

  // Form submit
  const form = document.getElementById('ar-form');
  if (form) {
    form.addEventListener('submit', async function(e) {
      e.preventDefault();
      await saveResponder();
    });
  }

  // Cancel edit button
  const cancelBtn = document.getElementById('cancel-edit');
  if (cancelBtn) {
    cancelBtn.addEventListener('click', function() {
      resetForm();
    });
  }
}

/**
 * Save responder to API
 */
async function saveResponder() {
  const form = document.getElementById('ar-form');
  if (!form) return;

  const includeChannels = document.getElementById('ar-include-channels');
  const excludeChannels = document.getElementById('ar-exclude-channels');

  const data = {
    id: editingId || '',
    keyword: document.getElementById('ar-keyword').value,
    response_type: document.getElementById('ar-response-type').value,
    response_content: document.getElementById('ar-response-content').value,
    embed_title: document.getElementById('ar-embed-title').value,
    embed_color: document.getElementById('ar-embed-color').value,
    embed_thumbnail: document.getElementById('ar-embed-thumbnail').value,
    response_image_url: document.getElementById('ar-response-image-url').value,
    cooldown_seconds: parseInt(document.getElementById('ar-cooldown').value) || 10,
    case_sensitive: document.getElementById('ar-case-sensitive').checked,
    regex_enabled: document.getElementById('ar-regex').checked,
    match_whole_word: document.getElementById('ar-whole-word').checked,
    mention_user: document.getElementById('ar-mention-user').checked,
    delete_trigger: document.getElementById('ar-delete-trigger').checked,
    channel_ids: includeChannels ? Array.from(includeChannels.selectedOptions).map(o => o.value) : [],
    exclude_channels: excludeChannels ? Array.from(excludeChannels.selectedOptions).map(o => o.value) : [],
    enabled: true
  };

  try {
    const resp = await fetch(`/api/auto-responders/${guildId}/save`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });

    const result = await resp.json();

    if (result.success) {
      resetForm();
      await loadAutoResponders();
      showAlert('Auto-responder saved!', 'success');
    } else {
      showAlert('Error: ' + result.message, 'error');
    }
  } catch (e) {
    showAlert('Error saving: ' + e, 'error');
    console.error('[Auto Responders] Save error:', e);
  }
}

/**
 * Edit responder - populate form with existing data
 */
async function editResponder(id) {
  try {
    const resp = await fetch(`/api/auto-responders/${guildId}`);
    const data = await resp.json();

    const ar = (data.responders || []).find(r => r.id === id);
    if (!ar) return;

    editingId = id;

    // Populate form fields
    document.getElementById('ar-id').value = id;
    document.getElementById('ar-keyword').value = Array.isArray(ar.keyword) ? ar.keyword.join(', ') : ar.keyword;
    document.getElementById('ar-response-type').value = ar.response_type || 'text';
    document.getElementById('ar-response-content').value = ar.response_content || '';
    document.getElementById('ar-embed-title').value = ar.embed_title || '';
    document.getElementById('ar-embed-color').value = ar.embed_color || '#5865F2';
    document.getElementById('ar-embed-thumbnail').value = ar.embed_thumbnail || '';
    document.getElementById('ar-response-image-url').value = ar.response_image_url || '';
    document.getElementById('ar-cooldown').value = ar.cooldown_seconds || 10;
    document.getElementById('ar-case-sensitive').checked = ar.case_sensitive || false;
    document.getElementById('ar-regex').checked = ar.regex_enabled || false;
    document.getElementById('ar-whole-word').checked = ar.match_whole_word || false;
    document.getElementById('ar-mention-user').checked = ar.mention_user || false;
    document.getElementById('ar-delete-trigger').checked = ar.delete_trigger || false;

    // Trigger change event to show/hide options
    const responseTypeEl = document.getElementById('ar-response-type');
    if (responseTypeEl) {
      responseTypeEl.dispatchEvent(new Event('change'));
    }

    // Update UI
    const cardTitle = document.querySelector('.form-card h2');
    if (cardTitle) cardTitle.textContent = 'Edit Auto-Responder';

    const submitBtn = document.querySelector('.form-card button[type="submit"]');
    if (submitBtn) submitBtn.textContent = '💾 Update Auto-Responder';

    // Add cancel button if not exists
    if (!document.getElementById('cancel-edit')) {
      const cancelBtn = document.createElement('button');
      cancelBtn.type = 'button';
      cancelBtn.id = 'cancel-edit';
      cancelBtn.className = 'btn btn-secondary';
      cancelBtn.textContent = '❌ Cancel';

      if (submitBtn) {
        submitBtn.after(cancelBtn);
        cancelBtn.addEventListener('click', resetForm);
      }
    }

  } catch (e) {
    showAlert('Error loading: ' + e, 'error');
    console.error('[Auto Responders] Edit error:', e);
  }
}

/**
 * Toggle responder enabled/disabled
 */
async function toggleResponder(id, enabled) {
  try {
    const resp = await fetch(`/api/auto-responders/${guildId}`);
    const data = await resp.json();

    const ar = (data.responders || []).find(r => r.id === id);
    if (!ar) return;

    ar.enabled = enabled;

    await fetch(`/api/auto-responders/${guildId}/save`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(ar)
    });

    await loadAutoResponders();
  } catch (e) {
    showAlert('Error: ' + e, 'error');
    console.error('[Auto Responders] Toggle error:', e);
  }
}

/**
 * Delete responder
 */
async function deleteResponder(id) {
  if (!confirm('Yakin hapus auto-responder ini?')) return;

  try {
    const resp = await fetch(`/api/auto-responders/${guildId}/delete`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id })
    });

    const result = await resp.json();

    if (result.success) {
      await loadAutoResponders();
    } else {
      showAlert('Error: ' + result.message, 'error');
    }
  } catch (e) {
    showAlert('Error: ' + e, 'error');
    console.error('[Auto Responders] Delete error:', e);
  }
}

/**
 * Reset form to initial state
 */
function resetForm() {
  editingId = null;

  const form = document.getElementById('ar-form');
  if (form) form.reset();

  const cancelBtn = document.getElementById('cancel-edit');
  if (cancelBtn) cancelBtn.remove();

  const cardTitle = document.querySelector('.form-card h2');
  if (cardTitle) cardTitle.textContent = 'Tambah Auto-Responder';

  const submitBtn = document.querySelector('.form-card button[type="submit"]');
  if (submitBtn) submitBtn.textContent = '➕ Tambah Auto-Responder';

  // Reset response type display
  const responseTypeEl = document.getElementById('ar-response-type');
  if (responseTypeEl) {
    responseTypeEl.value = 'text';
    responseTypeEl.dispatchEvent(new Event('change'));
  }
}

/**
 * Show alert message
 */
function showAlert(message, type) {
  // Simple alert for now - can be replaced with toast notifications
  alert(message);
}

// Export functions for global access
window.editResponder = editResponder;
window.toggleResponder = toggleResponder;
window.deleteResponder = deleteResponder;
window.saveResponder = saveResponder;
window.resetForm = resetForm;