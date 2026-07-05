/**
 * =====================================================
 * Auto Responders Page JavaScript - Synapse (FIXED)
 * =====================================================
 */

// ----------------------------------------------------------------
// Global error handler
// ----------------------------------------------------------------
window.addEventListener("error", function (event) {
  console.error("[Auto Responders] Uncaught error:", event.error);
  if (typeof showAlert === "function") {
    showAlert(
      "JS error: " + (event.error?.message || event.message || "unknown"),
      "error",
      6000,
    );
  }
});
window.addEventListener("unhandledrejection", function (event) {
  console.error("[Auto Responders] Unhandled promise rejection:", event.reason);
  if (typeof showAlert === "function") {
    const reason = event.reason?.message || String(event.reason);
    showAlert("Promise error: " + reason, "error", 6000);
  }
});

// ----------------------------------------------------------------
// Fetch wrapper with logging
// ----------------------------------------------------------------
(function () {
  const _origFetch = window.fetch.bind(window);
  window.fetch = async function (url, options = {}) {
    const method = (options.method || "GET").toUpperCase();
    const isOurApi =
      typeof url === "string" && url.includes("/api/auto-responders");
    if (isOurApi) {
      console.groupCollapsed(`[fetch] ${method} ${url}`);
      try {
        if (options.body) console.log("  body:", options.body);
      } catch (_) {}
    }
    let resp;
    try {
      resp = await _origFetch(url, options);
    } catch (err) {
      if (isOurApi) {
        console.error("  network error:", err);
        console.groupEnd();
      }
      throw err;
    }
    if (isOurApi) {
      console.log("  status:", resp.status);
      const cloned = resp.clone();
      try {
        const json = await cloned.json();
        console.log("  body:", json);
      } catch (_) {}
      console.groupEnd();
    }
    return resp;
  };
})();

const guildIdElement = document.getElementById("guild-id");
const guildId = guildIdElement ? guildIdElement.value : "";
let editingId = null;

// Track pending operations to prevent race conditions
const pendingOps = new Set();

// Initialize on DOM ready
document.addEventListener("DOMContentLoaded", function () {
  if (guildId) {
    loadAutoResponders();
    setupEventListeners();
  }
});

/**
 * Escape HTML entities including single quotes (for attribute safety)
 */
function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/**
 * Fetch channels and populate selects. Returns Promise that resolves
 * when channels are loaded.
 */
async function populateChannelSelects() {
  const sel = document.getElementById("ar-channels");
  const counter = document.getElementById("ar-channels-count");
  if (!sel) return;

  const loadingHtml = "<option disabled>⏳ Memuat channel…</option>";
  sel.innerHTML = loadingHtml;
  if (counter) counter.textContent = "Memuat…";

  try {
    const resp = await fetch(`/api/guilds/${guildId}/channels`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    const channels = data.channels || [];

    if (channels.length === 0) {
      sel.innerHTML =
        "<option disabled>⚠️ Belum ada channel terdaftar. Tunggu bot sync, atau tambahkan channel manual.</option>";
      if (counter) counter.textContent = "Channel belum tersedia — coba refresh beberapa saat lagi.";
      return;
    }

    channels.sort((a, b) => a.name.localeCompare(b.name));

    const optionsHtml = channels
      .map(
        (c) =>
          `<option value="${escapeHtml(c.id)}"># ${escapeHtml(c.name)}</option>`,
      )
      .join("");
    sel.innerHTML = optionsHtml;
    if (counter)
      counter.textContent = `${channels.length} channel — tahan Ctrl/Cmd untuk pilih banyak. Kosongkan = semua channel.`;
  } catch (err) {
    console.error("[Auto Responders] Failed to load channels:", err);
    sel.innerHTML = `<option disabled>❌ Gagal memuat channel: ${escapeHtml(String(err))}</option>`;
    if (counter) counter.textContent = "Gagal memuat channel.";
  }
}

/**
 * Load all auto responders from API.
 * Returns true on success, false on failure so callers can react.
 */
async function loadAutoResponders() {
  const listEl = document.getElementById("ar-list");
  const toggleEl = document.getElementById("global-toggle");

  if (!listEl) return false;

  try {
    const resp = await fetch(`/api/auto-responders/${guildId}`);
    const data = await resp.json();

    const responders = data.responders || [];
    const enabled = !!data.enabled;
    const ok =
      data.success === true || (Array.isArray(responders) && !data.error);

    if (ok) {
      if (toggleEl) {
        toggleEl.checked = enabled;
      }
      renderList(responders);
      return true;
    } else {
      const msg = data.message || data.error || "Unknown error";
      listEl.innerHTML = `<div class="empty">Error: ${escapeHtml(String(msg))}</div>`;
      return false;
    }
  } catch (e) {
    listEl.innerHTML = `<div class="empty">Gagal memuat data</div>`;
    console.error("[Auto Responders] Load error:", e);
    return false;
  }
}

/**
 * Render the list of auto responders
 */
function renderList(responders) {
  const listEl = document.getElementById("ar-list");
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

  listEl.innerHTML = responders
    .map((ar) => {
      const id = String(ar.id || "");
      const keywords = Array.isArray(ar.keyword)
        ? ar.keyword.join(", ")
        : ar.keyword || "";
      const count = Number(ar.trigger_count) || 0;
      return `
    <div class="ar-item" data-id="${escapeHtml(id)}" draggable="true">
      <div class="ar-item-header">
        <span class="ar-drag-handle" title="Seret untuk reorder">🟰</span>
        <span class="ar-keywords">${escapeHtml(String(keywords))}</span>
        <span class="ar-type-badge">${escapeHtml(String(ar.response_type || ""))}</span>
      </div>
      <div class="ar-response">${escapeHtml(String(ar.response_content || "(no response)"))}</div>
      <div class="ar-meta">
        <span class="stat-trigger">🎯 ${count}x dipicu</span>
        <span>Cooldown: ${Number(ar.cooldown_seconds) || 0}s</span>
        ${ar.case_sensitive ? "<span>Case Sensitive</span>" : ""}
        ${ar.regex_enabled ? "<span>Regex</span>" : ""}
        ${ar.match_whole_word ? "<span>Whole Word</span>" : ""}
        ${ar.mention_user ? "<span>Mention</span>" : ""}
        ${ar.delete_trigger ? "<span>Delete</span>" : ""}
      </div>
      <div class="ar-actions">
        <button class="ar-btn ar-btn-test"   data-action="test"   data-id="${escapeHtml(id)}" title="Test response">🧪 Test</button>
        <button class="ar-btn ar-btn-edit"   data-action="edit"   data-id="${escapeHtml(id)}">✏️ Edit</button>
        <button class="ar-btn ar-btn-toggle ${ar.enabled ? "" : "off"}" data-action="toggle" data-id="${escapeHtml(id)}" data-extra="${ar.enabled ? "false" : "true"}">
          ${ar.enabled ? "⏸️ Disable" : "▶️ Enable"}
        </button>
        <button class="ar-btn ar-btn-delete" data-action="delete" data-id="${escapeHtml(id)}">🗑️ Hapus</button>
      </div>
    </div>
  `;
    })
    .join("");

  // Re-bind drag events
  bindDragReorder();
}

/**
 * Setup event listeners for form interactions
 */
function setupEventListeners() {
  populateChannelSelects();

  // Search/filter
  const searchInput = document.getElementById("ar-search");
  if (searchInput) {
    searchInput.addEventListener("input", function () {
      filterList(this.value);
    });
  }

  // Image upload → base64
  const fileInput = document.getElementById("ar-response-image-upload");
  if (fileInput) {
    fileInput.addEventListener("change", function (e) {
      handleImageUpload(e.target.files[0]);
    });
  }
  document.getElementById("image-preview-clear")?.addEventListener("click", clearImageUpload);

  // Embed preview live
  ["ar-embed-title", "ar-embed-color", "ar-response-content", "ar-embed-thumbnail"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.addEventListener("input", updateEmbedPreview);
  });
  // Trigger preview on response type change too
  const responseTypeEl2 = document.getElementById("ar-response-type");
  if (responseTypeEl2) {
    const origHandler = responseTypeEl2._listeners ? null : null;
    responseTypeEl2.addEventListener("change", function (e) {
      updateEmbedPreview();
      // Toggle image preview
      const preview = document.getElementById("image-preview");
      if (e.target.value === "image") {
        const url = document.getElementById("ar-response-image-url")?.value;
        const dataUrl = document.getElementById("ar-response-image-url")?.dataset?.base64;
        if (url || dataUrl) showImagePreview(url || dataUrl);
      }
    });
  }

  const listEl = document.getElementById("ar-list");
  if (listEl) {
    listEl.addEventListener("click", function (event) {
      const btn = event.target.closest("button[data-action]");
      if (!btn) return;
      const action = btn.dataset.action;
      const id = btn.dataset.id;
      const extra = btn.dataset.extra;
      console.log("[Auto Responders] click", { action, id, extra });
      if (action === "edit") {
        editResponder(id);
      } else if (action === "toggle") {
        toggleResponder(id, extra === "true");
      } else if (action === "delete") {
        deleteResponder(id);
      } else if (action === "test") {
        testResponder(id);
      }
    });
  }

  // Global toggle with error revert
  const toggleEl = document.getElementById("global-toggle");
  if (toggleEl) {
    toggleEl.addEventListener("change", async function (e) {
      const originalChecked = e.target.checked;
      try {
        const resp = await fetch(`/api/auto-responders/${guildId}/toggle`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ enabled: originalChecked }),
        });
        const result = await resp.json();
        if (!result.success) {
          e.target.checked = !originalChecked;
          showAlert(result.message || "Gagal mengubah status fitur.", "error");
        }
      } catch (err) {
        e.target.checked = !originalChecked;
        showAlert("Error: " + err, "error");
        console.error("[Auto Responders] Toggle error:", err);
      }
    });
  }

  // Channel multi-select counter
  const chanSel = document.getElementById("ar-channels");
  const chanCount = document.getElementById("ar-channels-count");
  if (chanSel && chanCount) {
    const update = () => {
      const n = chanSel.selectedOptions.length;
      chanCount.textContent =
        n === 0
          ? "Tidak ada dipilih (berlaku untuk semua channel)"
          : `${n} channel dipilih`;
      chanCount.classList.toggle("has-selection", n > 0);
    };
    chanSel.addEventListener("change", update);
    update();
  }

  // Response type change
  const responseTypeEl = document.getElementById("ar-response-type");
  if (responseTypeEl) {
    responseTypeEl.addEventListener("change", function (e) {
      const type = e.target.value;
      const contentGroup = document.getElementById("response-content-group");
      const embedOptions = document.getElementById("embed-options");
      const imageOptions = document.getElementById("image-options");

      if (contentGroup) {
        contentGroup.style.display = type === "image" ? "none" : "block";
      }
      if (embedOptions) {
        embedOptions.style.display = type === "embed" ? "block" : "none";
      }
      if (imageOptions) {
        imageOptions.style.display = type === "image" ? "block" : "none";
      }
    });
  }

  // Form submit
  const form = document.getElementById("ar-form");
  if (form) {
    form.addEventListener("submit", async function (e) {
      e.preventDefault();
      await saveResponder();
    });
  }

  // Cancel edit button
  const cancelBtn = document.getElementById("cancel-edit");
  if (cancelBtn) {
    cancelBtn.addEventListener("click", function () {
      resetForm();
    });
  }
}

/**
 * Save responder to API
 */
async function saveResponder() {
  if (!validateForm()) return;

  const form = document.getElementById("ar-form");
  if (!form) return;

  const channelsSel = document.getElementById("ar-channels");

  // Use base64 data URL if uploaded
  const urlInput = document.getElementById("ar-response-image-url");
  let imageUrl = urlInput ? urlInput.value : "";
  if (urlInput && urlInput.dataset.base64) {
    imageUrl = urlInput.dataset.base64;
  }

  const data = {
    id: editingId || "",
    keyword: document.getElementById("ar-keyword").value,
    response_type: document.getElementById("ar-response-type").value,
    response_content: document.getElementById("ar-response-content").value,
    embed_title: document.getElementById("ar-embed-title").value,
    embed_color: document.getElementById("ar-embed-color").value,
    embed_thumbnail: document.getElementById("ar-embed-thumbnail").value,
    response_image_url: imageUrl,
    cooldown_seconds:
      parseInt(document.getElementById("ar-cooldown").value) || 10,
    case_sensitive: document.getElementById("ar-case-sensitive").checked,
    regex_enabled: document.getElementById("ar-regex").checked,
    match_whole_word: document.getElementById("ar-whole-word").checked,
    mention_user: document.getElementById("ar-mention-user").checked,
    delete_trigger: document.getElementById("ar-delete-trigger").checked,
    channel_ids: channelsSel
      ? Array.from(channelsSel.selectedOptions).map((o) => o.value)
      : [],
    enabled: true,
  };

  try {
    const resp = await fetch(`/api/auto-responders/${guildId}/save`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });

    const result = await resp.json();

    if (result.success) {
      const wasEditing = !!editingId;
      resetForm();
      const loadOk = await loadAutoResponders();
      if (!loadOk) {
        showAlert(
          "Data tersimpan, tapi gagal memperbarui tampilan. Refresh halaman.",
          "warning",
          5000,
        );
      } else {
        showAlert(
          wasEditing
            ? "Perubahan berhasil disimpan."
            : "Auto-responder baru berhasil dibuat.",
          "success",
        );
      }
    } else {
      showAlert(result.message || "Gagal menyimpan auto-responder.", "error");
    }
  } catch (e) {
    showAlert("Error saving: " + e, "error");
    console.error("[Auto Responders] Save error:", e);
  }
}

/**
 * Edit responder - populate form with existing data
 */
async function editResponder(id) {
  try {
    const resp = await fetch(`/api/auto-responders/${guildId}`);
    const data = await resp.json();

    const ar = (data.responders || []).find((r) => r.id === id);
    if (!ar) return;

    editingId = id;

    // Populate form fields
    document.getElementById("ar-id").value = id;
    document.getElementById("ar-keyword").value = Array.isArray(ar.keyword)
      ? ar.keyword.join(", ")
      : ar.keyword;
    document.getElementById("ar-response-type").value =
      ar.response_type || "text";
    document.getElementById("ar-response-content").value =
      ar.response_content || "";
    document.getElementById("ar-embed-title").value = ar.embed_title || "";
    document.getElementById("ar-embed-color").value =
      ar.embed_color || "#5865F2";
    document.getElementById("ar-embed-thumbnail").value =
      ar.embed_thumbnail || "";
    const imgUrl = ar.response_image_url || "";
    document.getElementById("ar-response-image-url").value = imgUrl.startsWith("data:") ? "(upload)" : imgUrl;
    if (imgUrl.startsWith("data:")) {
      document.getElementById("ar-response-image-url").dataset.base64 = imgUrl;
      showImagePreview(imgUrl);
    } else {
      delete document.getElementById("ar-response-image-url").dataset.base64;
      document.getElementById("image-preview").style.display = "none";
    }
    document.getElementById("ar-cooldown").value = ar.cooldown_seconds || 10;
    document.getElementById("ar-case-sensitive").checked =
      ar.case_sensitive || false;
    document.getElementById("ar-regex").checked = ar.regex_enabled || false;
    document.getElementById("ar-whole-word").checked =
      ar.match_whole_word || false;
    document.getElementById("ar-mention-user").checked =
      ar.mention_user || false;
    document.getElementById("ar-delete-trigger").checked =
      ar.delete_trigger || false;

    const chanSel = document.getElementById("ar-channels");

    function extractIds(value) {
      if (Array.isArray(value)) return value.map(String);
      if (value && typeof value === "object")
        return Object.keys(value).map(String);
      return [];
    }

    const channelIds = extractIds(
      ar.channel_ids ??
        (ar.channels && ar.channels.include) ??
        ar.include_channels,
    );

    function applySelection(sel, ids) {
      if (!sel) return;
      const idSet = new Set(ids.map(String));
      Array.from(sel.options).forEach((opt) => {
        opt.selected = idSet.has(String(opt.value));
      });
      sel.dispatchEvent(new Event("change"));
    }

    // Poll until channels are loaded (max 10 attempts, 300ms interval)
    let attempts = 0;
    const maxAttempts = 10;
    const pollInterval = 300;

    function tryApplySelection() {
      const isLoaded =
        chanSel &&
        chanSel.options.length > 1 &&
        !chanSel.options[0].disabled;
      if (isLoaded || attempts >= maxAttempts) {
        applySelection(chanSel, channelIds);
        return;
      }
      attempts++;
      setTimeout(tryApplySelection, pollInterval);
    }
    tryApplySelection();

    // Trigger change event to show/hide options
    const responseTypeEl = document.getElementById("ar-response-type");
    if (responseTypeEl) {
      responseTypeEl.dispatchEvent(new Event("change"));
    }

    // Update UI
    const cardTitle = document.querySelector(".form-card h2");
    if (cardTitle) cardTitle.textContent = "Edit Auto-Responder";

    const submitBtn = document.querySelector(
      '.form-card button[type="submit"]',
    );
    if (submitBtn) submitBtn.textContent = "💾 Update Auto-Responder";

    // Add cancel button if not exists
    if (!document.getElementById("cancel-edit")) {
      const cancelBtn = document.createElement("button");
      cancelBtn.type = "button";
      cancelBtn.id = "cancel-edit";
      cancelBtn.className = "btn btn-secondary";
      cancelBtn.textContent = "❌ Cancel";

      if (submitBtn) {
        submitBtn.after(cancelBtn);
        cancelBtn.addEventListener("click", resetForm);
      }
    }
  } catch (e) {
    showAlert("Error loading: " + e, "error");
    console.error("[Auto Responders] Edit error:", e);
  }
}

/**
 * Toggle responder enabled/disabled
 */
async function toggleResponder(id, enabled) {
  const button = document.querySelector(
    `.ar-item[data-id="${CSS.escape(id)}"] .ar-btn-toggle`,
  );
  const originalText = button ? button.textContent : null;
  const originalClass = button ? button.className : "";

  if (button) {
    button.disabled = true;
    button.textContent = enabled ? "⏸️ Disable" : "▶️ Enable";
  }

  try {
    const resp = await fetch(`/api/auto-responders/${guildId}/toggle`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: id, enable: enabled }),
    });
    const result = await resp.json();

    if (!result.success) {
      // Revert button state
      if (button) {
        button.textContent =
          originalText || (enabled ? "▶️ Enable" : "⏸️ Disable");
        button.className = originalClass;
      }
      showAlert(
        result.message || "Gagal mengubah status auto-responder.",
        "error",
      );
      return;
    }

    const loadOk = await loadAutoResponders();
    if (!loadOk) {
      showAlert(
        "Status diubah, tapi gagal memperbarui tampilan. Refresh halaman.",
        "warning",
        5000,
      );
    } else {
      showAlert(
        enabled
          ? "Auto-responder diaktifkan."
          : "Auto-responder dinonaktifkan.",
        "success",
      );
    }
  } catch (e) {
    if (button) {
      button.textContent =
        originalText || (enabled ? "▶️ Enable" : "⏸️ Disable");
      button.className = originalClass;
    }
    showAlert("Error: " + e, "error");
    console.error("[Auto Responders] Toggle error:", e);
  } finally {
    if (button) button.disabled = false;
  }
}

/**
 * Delete responder with optimistic UI update
 */
async function deleteResponder(id) {
  // Prevent duplicate delete operations
  const opKey = `delete-${id}`;
  if (pendingOps.has(opKey)) return;
  pendingOps.add(opKey);

  // Find the item element and name for confirmation
  const itemEl = document.querySelector(
    `.ar-item[data-id="${CSS.escape(id)}"]`,
  );
  const kwEl = itemEl?.querySelector(".ar-keywords");
  const arName = kwEl ? kwEl.textContent : id;

  const confirmed = await showConfirm(
    "Hapus Auto-Responder?",
    `Auto-responder untuk keyword "${arName}" akan dihapus permanen. Tindakan ini tidak bisa dibatalkan.`,
    "🗑️ Hapus",
    "Batal",
  );
  if (!confirmed) {
    pendingOps.delete(opKey);
    return;
  }

  // OPTIMISTIC DELETE: Remove from DOM immediately with animation
  let removedFromDom = false;
  if (itemEl) {
    itemEl.style.transition =
      "opacity 0.25s ease, transform 0.25s ease, max-height 0.3s ease";
    itemEl.style.opacity = "0";
    itemEl.style.transform = "translateX(20px)";
    itemEl.style.maxHeight = itemEl.offsetHeight + "px";

    // Force reflow
    void itemEl.offsetHeight;

    itemEl.style.maxHeight = "0";
    itemEl.style.marginBottom = "0";
    itemEl.style.paddingTop = "0";
    itemEl.style.paddingBottom = "0";
    itemEl.style.overflow = "hidden";

    setTimeout(() => {
      if (itemEl.parentNode) {
        itemEl.parentNode.removeChild(itemEl);
        removedFromDom = true;
      }
    }, 300);
  }

  try {
    const resp = await fetch(`/api/auto-responders/${guildId}/delete`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id }),
    });

    const result = await resp.json();

    if (result.success) {
      // Background refresh to ensure sync with server
      setTimeout(async () => {
        const loadOk = await loadAutoResponders();
        if (!loadOk && !removedFromDom) {
          showAlert(
            "Item dihapus, tapi gagal memperbarui tampilan. Refresh halaman.",
            "warning",
            5000,
          );
        }
      }, 500);

      showAlert(`Auto-responder "${arName}" berhasil dihapus.`, "success");
    } else {
      // REVERT: Server rejected, restore the item
      showAlert(result.message || "Gagal menghapus auto-responder.", "error");
      await loadAutoResponders(); // Full restore
    }
  } catch (e) {
    // REVERT: Network error, restore the item
    showAlert("Error: " + e, "error");
    console.error("[Auto Responders] Delete error:", e);
    await loadAutoResponders(); // Full restore
  } finally {
    pendingOps.delete(opKey);
  }
}

/**
 * Reset form to initial state
 */
function resetForm() {
  editingId = null;

  const form = document.getElementById("ar-form");
  if (form) form.reset();

  const cancelBtn = document.getElementById("cancel-edit");
  if (cancelBtn) cancelBtn.remove();

  const cardTitle = document.querySelector(".form-card h2");
  if (cardTitle) cardTitle.textContent = "Tambah Auto-Responder";

  const submitBtn = document.querySelector('.form-card button[type="submit"]');
  if (submitBtn) submitBtn.textContent = "➕ Tambah Auto-Responder";

  // Reset response type display
  const responseTypeEl = document.getElementById("ar-response-type");
  if (responseTypeEl) {
    responseTypeEl.value = "text";
    responseTypeEl.dispatchEvent(new Event("change"));
  }
}

// ----------------------------------------------------------------
// Drag Reorder
// ----------------------------------------------------------------

let _dragId = null;
let _dragOrderDirty = false;

function bindDragReorder() {
  const items = document.querySelectorAll(".ar-item[draggable='true']");
  items.forEach((el) => {
    el.removeEventListener("dragstart", _onDragStart);
    el.removeEventListener("dragend", _onDragEnd);
    el.removeEventListener("dragover", _onDragOver);
    el.removeEventListener("drop", _onDrop);
    el.addEventListener("dragstart", _onDragStart);
    el.addEventListener("dragend", _onDragEnd);
    el.addEventListener("dragover", _onDragOver);
    el.addEventListener("drop", _onDrop);
  });
}

function _onDragStart(e) {
  _dragId = this.dataset.id;
  this.classList.add("dragging");
  e.dataTransfer.effectAllowed = "move";
  e.dataTransfer.setData("text/plain", _dragId);
}

function _onDragEnd() {
  this.classList.remove("dragging");
  document.querySelectorAll(".ar-item.drag-over").forEach((el) => el.classList.remove("drag-over"));
}

function _onDragOver(e) {
  e.preventDefault();
  e.dataTransfer.dropEffect = "move";
  document.querySelectorAll(".ar-item.drag-over").forEach((el) => el.classList.remove("drag-over"));
  this.classList.add("drag-over");
}

function _onDrop(e) {
  e.preventDefault();
  this.classList.remove("drag-over");
  const fromId = _dragId;
  const toId = this.dataset.id;
  if (!fromId || fromId === toId) return;

  const list = document.getElementById("ar-list");
  const items = Array.from(list.querySelectorAll(".ar-item"));
  const fromIdx = items.findIndex((el) => el.dataset.id === fromId);
  const toIdx = items.findIndex((el) => el.dataset.id === toId);
  if (fromIdx === -1 || toIdx === -1) return;

  const fromEl = items[fromIdx];
  if (fromIdx < toIdx) {
    this.parentNode.insertBefore(fromEl, this.nextSibling);
  } else {
    this.parentNode.insertBefore(fromEl, this);
  }

  _dragOrderDirty = true;
  document.getElementById("reorder-hint").style.display = "flex";
}

document.getElementById("reorder-save")?.addEventListener("click", saveReorder);
document.getElementById("reorder-cancel")?.addEventListener("click", cancelReorder);

async function saveReorder() {
  const items = document.querySelectorAll(".ar-item");
  const orderData = [];
  items.forEach((el, idx) => {
    orderData.push({ id: el.dataset.id, order: idx });
  });

  const btn = document.getElementById("reorder-save");
  btn.disabled = true;
  btn.textContent = "⏳ Menyimpan...";

  try {
    const resp = await fetch(`/api/auto-responders/${guildId}/reorder`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ order: orderData }),
    });
    const result = await resp.json();
    if (result.success) {
      _dragOrderDirty = false;
      document.getElementById("reorder-hint").style.display = "none";
      showAlert("Urutan berhasil disimpan!", "success");
    } else {
      showAlert(result.message || "Gagal menyimpan urutan.", "error");
    }
  } catch (e) {
    showAlert("Error: " + e.message, "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "💾 Simpan Urutan";
  }
}

function cancelReorder() {
  document.getElementById("reorder-hint").style.display = "none";
  _dragOrderDirty = false;
  loadAutoResponders(); // reload original order
}

// ----------------------------------------------------------------
// Validasi, Search, Upload, Preview, Test
// ----------------------------------------------------------------

/**
 * Validate the form before save.
 * Returns true if valid, false otherwise (and shows alert).
 */
function validateForm() {
  const keyword = document.getElementById("ar-keyword")?.value?.trim();
  if (!keyword) {
    showAlert("Keyword tidak boleh kosong!", "error");
    document.getElementById("ar-keyword")?.focus();
    return false;
  }

  const regexEnabled = document.getElementById("ar-regex")?.checked;
  if (regexEnabled) {
    try {
      new RegExp(keyword);
    } catch (e) {
      showAlert("Regex pattern tidak valid: " + e.message, "error");
      return false;
    }
  }

  return true;
}

/**
 * Filter the responder list by keyword search term
 */
function filterList(term) {
  const items = document.querySelectorAll(".ar-item");
  const lower = term.toLowerCase().trim();
  let visible = 0;
  items.forEach((el) => {
    const keywords = el.querySelector(".ar-keywords")?.textContent?.toLowerCase() || "";
    const match = !lower || keywords.includes(lower);
    el.style.display = match ? "" : "none";
    if (match) visible++;
  });
  const count = document.getElementById("ar-count");
  if (count) count.textContent = `${visible}/${items.length}`;
}

/**
 * Handle image file upload → base64 data URL
 */
function handleImageUpload(file) {
  const MAX_SIZE = 400 * 1024; // 400KB
  if (!file) return;
  if (!file.type.startsWith("image/")) {
    showAlert("Hanya file gambar yang diizinkan.", "error");
    document.getElementById("ar-response-image-upload").value = "";
    return;
  }
  if (file.size > MAX_SIZE) {
    showAlert("Ukuran gambar maksimal 400KB.", "error");
    document.getElementById("ar-response-image-upload").value = "";
    return;
  }
  const reader = new FileReader();
  reader.onload = function (e) {
    const dataUrl = e.target.result;
    // Store as data URL in the url input's dataset
    const urlInput = document.getElementById("ar-response-image-url");
    if (urlInput) {
      urlInput.value = "(upload)";
      urlInput.dataset.base64 = dataUrl;
    }
    showImagePreview(dataUrl);
  };
  reader.onerror = function () {
    showAlert("Gagal membaca file.", "error");
  };
  reader.readAsDataURL(file);
}

function clearImageUpload() {
  const urlInput = document.getElementById("ar-response-image-url");
  if (urlInput) {
    urlInput.value = "";
    delete urlInput.dataset.base64;
  }
  document.getElementById("ar-response-image-upload").value = "";
  document.getElementById("image-preview").style.display = "none";
  document.getElementById("image-preview-img").src = "";
}

function showImagePreview(src) {
  const preview = document.getElementById("image-preview");
  const img = document.getElementById("image-preview-img");
  if (preview && img) {
    img.src = src;
    preview.style.display = "flex";
  }
}

/**
 * Live embed preview
 */
function updateEmbedPreview() {
  const type = document.getElementById("ar-response-type")?.value;
  const preview = document.getElementById("embed-preview");
  if (type !== "embed") {
    if (preview) preview.style.display = "none";
    return;
  }
  if (!preview) return;
  preview.style.display = "block";

  const title = document.getElementById("ar-embed-title")?.value || "Judul Embed";
  const desc = document.getElementById("ar-response-content")?.value || "Deskripsi response...";
  const color = document.getElementById("ar-embed-color")?.value || "#5865F2";
  const thumb = document.getElementById("ar-embed-thumbnail")?.value || "";

  document.getElementById("embed-preview-title").textContent = title;
  document.getElementById("embed-preview-desc").textContent = desc;
  document.getElementById("embed-preview-color").style.background = color;

  const thumbImg = document.getElementById("embed-preview-thumb");
  if (thumb) {
    thumbImg.src = thumb;
    thumbImg.style.display = "";
  } else {
    thumbImg.style.display = "none";
  }
}

/**
 * Open test response modal
 */
async function testResponder(id) {
  try {
    const resp = await fetch(`/api/auto-responders/${guildId}`);
    const data = await resp.json();
    const ar = (data.responders || []).find((r) => r.id === id);
    if (!ar) {
      showAlert("Auto-responder tidak ditemukan.", "error");
      return;
    }

    const overlay = document.createElement("div");
    overlay.className = "confirm-overlay";

    const card = document.createElement("div");
    card.className = "test-result-card";

    const header = document.createElement("h3");
    header.textContent = "🧪 Test Response";

    const kw = Array.isArray(ar.keyword) ? ar.keyword.join(", ") : ar.keyword || "";
    const type = ar.response_type || "text";
    const content = ar.response_content || "";
    const mention = ar.mention_user ? "@user " : "";

    const pre = document.createElement("pre");
    if (type === "text") {
      pre.textContent = `${mention}${content}`;
    } else if (type === "embed") {
      pre.textContent = `Embed:\nTitle: ${ar.embed_title || ""}\nDesc: ${content}\nColor: ${ar.embed_color || "#5865F2"}\nThumb: ${ar.embed_thumbnail || "-"}\n${mention ? "Mention: @user" : ""}`;
    } else if (type === "image") {
      const imgUrl = ar.response_image_url || "(upload)";
      pre.textContent = `Image Response:\n${mention}${imgUrl}`;
      if (ar.response_image_url && ar.response_image_url.startsWith("data:")) {
        const imgEl = document.createElement("img");
        imgEl.src = ar.response_image_url;
        imgEl.style.maxWidth = "100%";
        imgEl.style.maxHeight = "150px";
        imgEl.style.marginTop = "0.5rem";
        imgEl.style.borderRadius = "4px";
        card.appendChild(imgEl);
      }
    }

    const closeBtn = document.createElement("button");
    closeBtn.type = "button";
    closeBtn.className = "btn btn-secondary";
    closeBtn.textContent = "✕ Tutup";
    closeBtn.addEventListener("click", () => {
      if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
    });

    card.appendChild(header);
    card.appendChild(pre);
    card.appendChild(closeBtn);
    overlay.appendChild(card);
    document.body.appendChild(overlay);

    overlay.addEventListener("click", (e) => {
      if (e.target === overlay && overlay.parentNode) overlay.parentNode.removeChild(overlay);
    });
  } catch (e) {
    showAlert("Error: " + e.message, "error");
  }
}

// ----------------------------------------------------------------
// Toast & Modal utilities
// ----------------------------------------------------------------

function showAlert(message, type = "info", duration = 3000) {
  let container = document.getElementById("toast-container");
  if (!container) {
    container = document.createElement("div");
    container.id = "toast-container";
    container.className = "toast-container";
    document.body.appendChild(container);
  }

  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.setAttribute("role", type === "error" ? "alert" : "status");
  toast.setAttribute("aria-live", type === "error" ? "assertive" : "polite");

  const icon = document.createElement("span");
  icon.className = "toast-icon";
  icon.setAttribute("aria-hidden", "true");

  const msg = document.createElement("span");
  msg.className = "toast-message";
  msg.textContent = message;

  toast.appendChild(icon);
  toast.appendChild(msg);
  container.appendChild(toast);

  requestAnimationFrame(() => toast.classList.add("show"));

  toast.addEventListener("click", () => dismissToast(toast));

  if (duration > 0) {
    setTimeout(() => dismissToast(toast), duration);
  }

  return toast;
}

function dismissToast(toast) {
  if (!toast || !toast.parentNode) return;
  toast.classList.add("toast-out");
  setTimeout(
    () => toast.parentNode && toast.parentNode.removeChild(toast),
    250,
  );
}

function showConfirm(
  title,
  message,
  confirmText = "Confirm",
  cancelText = "Cancel",
) {
  return new Promise((resolve) => {
    const overlay = document.createElement("div");
    overlay.className = "confirm-overlay";

    const modal = document.createElement("div");
    modal.className = "confirm-modal";
    modal.setAttribute("role", "dialog");
    modal.setAttribute("aria-modal", "true");

    const h3 = document.createElement("h3");
    h3.textContent = title;
    const p = document.createElement("p");
    p.textContent = message;

    const actions = document.createElement("div");
    actions.className = "confirm-actions";

    const cancelBtn = document.createElement("button");
    cancelBtn.type = "button";
    cancelBtn.className = "btn-cancel";
    cancelBtn.textContent = cancelText;

    const confirmBtn = document.createElement("button");
    confirmBtn.type = "button";
    confirmBtn.className = "btn-confirm";
    confirmBtn.textContent = confirmText;

    actions.appendChild(cancelBtn);
    actions.appendChild(confirmBtn);
    modal.appendChild(h3);
    modal.appendChild(p);
    modal.appendChild(actions);
    overlay.appendChild(modal);
    document.body.appendChild(overlay);

    confirmBtn.focus();

    function cleanup(result) {
      if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
      document.removeEventListener("keydown", onKey);
      resolve(result);
    }

    cancelBtn.addEventListener("click", () => cleanup(false));
    confirmBtn.addEventListener("click", () => cleanup(true));
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) cleanup(false);
    });
    function onKey(e) {
      if (e.key === "Escape") cleanup(false);
      else if (e.key === "Enter") cleanup(true);
    }
    document.addEventListener("keydown", onKey);
  });
}

// Export functions for global access
window.editResponder = editResponder;
window.toggleResponder = toggleResponder;
window.deleteResponder = deleteResponder;
window.saveResponder = saveResponder;
window.resetForm = resetForm;
window.testResponder = testResponder;
