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
  const includeSel = document.getElementById("ar-include-channels");
  const excludeSel = document.getElementById("ar-exclude-channels");
  const includeCounter = document.getElementById("ar-include-channels-count");
  const excludeCounter = document.getElementById("ar-exclude-channels-count");
  if (!includeSel || !excludeSel) return;

  const loadingHtml = "<option disabled>⏳ Memuat channel…</option>";
  includeSel.innerHTML = loadingHtml;
  excludeSel.innerHTML = loadingHtml;
  if (includeCounter) includeCounter.textContent = "Memuat…";
  if (excludeCounter) excludeCounter.textContent = "Memuat…";

  try {
    const resp = await fetch(`/api/guilds/${guildId}/channels`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    const channels = data.channels || [];

    if (channels.length === 0) {
      const emptyHtml =
        "<option disabled>⚠️ Belum ada channel terdaftar. Tunggu bot sync, atau tambahkan channel manual.</option>";
      includeSel.innerHTML = emptyHtml;
      excludeSel.innerHTML = emptyHtml;
      if (includeCounter)
        includeCounter.textContent =
          "Channel belum tersedia — coba refresh beberapa saat lagi.";
      if (excludeCounter)
        excludeCounter.textContent =
          "Channel belum tersedia — coba refresh beberapa saat lagi.";
      return;
    }

    channels.sort((a, b) => a.name.localeCompare(b.name));

    const optionsHtml = channels
      .map(
        (c) =>
          `<option value="${escapeHtml(c.id)}"># ${escapeHtml(c.name)}</option>`,
      )
      .join("");
    includeSel.innerHTML = optionsHtml;
    excludeSel.innerHTML = optionsHtml;
    if (includeCounter)
      includeCounter.textContent = `${channels.length} channel tersedia — tahan Ctrl/Cmd untuk pilih banyak`;
    if (excludeCounter)
      excludeCounter.textContent = `${channels.length} channel tersedia — tahan Ctrl/Cmd untuk pilih banyak`;
  } catch (err) {
    console.error("[Auto Responders] Failed to load channels:", err);
    const errHtml = `<option disabled>❌ Gagal memuat channel: ${escapeHtml(String(err))}</option>`;
    includeSel.innerHTML = errHtml;
    excludeSel.innerHTML = errHtml;
    if (includeCounter) includeCounter.textContent = "Gagal memuat channel.";
    if (excludeCounter) excludeCounter.textContent = "Gagal memuat channel.";
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
      return `
    <div class="ar-item" data-id="${escapeHtml(id)}">
      <div class="ar-item-header">
        <span class="ar-keywords">${escapeHtml(String(keywords))}</span>
        <span class="ar-type-badge">${escapeHtml(String(ar.response_type || ""))}</span>
      </div>
      <div class="ar-response">${escapeHtml(String(ar.response_content || "(no response)"))}</div>
      <div class="ar-meta">
        <span>Cooldown: ${Number(ar.cooldown_seconds) || 0}s</span>
        ${ar.case_sensitive ? "<span>Case Sensitive</span>" : ""}
        ${ar.regex_enabled ? "<span>Regex</span>" : ""}
        ${ar.match_whole_word ? "<span>Whole Word</span>" : ""}
        ${ar.mention_user ? "<span>Mention</span>" : ""}
        ${ar.delete_trigger ? "<span>Delete</span>" : ""}
      </div>
      <div class="ar-actions">
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
}

/**
 * Setup event listeners for form interactions
 */
function setupEventListeners() {
  populateChannelSelects();

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

  // Channel multi-select counters
  ["ar-include-channels", "ar-exclude-channels"].forEach((id) => {
    const sel = document.getElementById(id);
    const counter = document.getElementById(id + "-count");
    if (sel && counter) {
      const update = () => {
        const n = sel.selectedOptions.length;
        counter.textContent =
          n === 0
            ? "Tidak ada dipilih (berlaku untuk semua channel)"
            : `${n} channel dipilih`;
        counter.classList.toggle("has-selection", n > 0);
      };
      sel.addEventListener("change", update);
      update();
    }
  });

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
  const form = document.getElementById("ar-form");
  if (!form) return;

  const includeChannels = document.getElementById("ar-include-channels");
  const excludeChannels = document.getElementById("ar-exclude-channels");

  const data = {
    id: editingId || "",
    keyword: document.getElementById("ar-keyword").value,
    response_type: document.getElementById("ar-response-type").value,
    response_content: document.getElementById("ar-response-content").value,
    embed_title: document.getElementById("ar-embed-title").value,
    embed_color: document.getElementById("ar-embed-color").value,
    embed_thumbnail: document.getElementById("ar-embed-thumbnail").value,
    response_image_url: document.getElementById("ar-response-image-url").value,
    cooldown_seconds:
      parseInt(document.getElementById("ar-cooldown").value) || 10,
    case_sensitive: document.getElementById("ar-case-sensitive").checked,
    regex_enabled: document.getElementById("ar-regex").checked,
    match_whole_word: document.getElementById("ar-whole-word").checked,
    mention_user: document.getElementById("ar-mention-user").checked,
    delete_trigger: document.getElementById("ar-delete-trigger").checked,
    channel_ids: includeChannels
      ? Array.from(includeChannels.selectedOptions).map((o) => o.value)
      : [],
    exclude_channels: excludeChannels
      ? Array.from(excludeChannels.selectedOptions).map((o) => o.value)
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
    document.getElementById("ar-response-image-url").value =
      ar.response_image_url || "";
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

    const includeSel = document.getElementById("ar-include-channels");
    const excludeSel = document.getElementById("ar-exclude-channels");

    function extractIds(value) {
      if (Array.isArray(value)) return value.map(String);
      if (value && typeof value === "object")
        return Object.keys(value).map(String);
      return [];
    }

    const includeIds = extractIds(
      ar.channel_ids ??
        (ar.channels && ar.channels.include) ??
        ar.include_channels,
    );
    const excludeIds = extractIds(
      ar.exclude_channels ?? (ar.channels && ar.channels.exclude) ?? [],
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
        includeSel &&
        includeSel.options.length > 1 &&
        !includeSel.options[0].disabled;
      if (isLoaded || attempts >= maxAttempts) {
        applySelection(includeSel, includeIds);
        applySelection(excludeSel, excludeIds);
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
