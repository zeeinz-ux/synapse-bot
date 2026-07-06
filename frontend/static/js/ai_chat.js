/* ================================================================================
   JS: AI Chat Settings v4.7 — Synapse Dashboard
   UPDATE: Triple API Tier Stack + Dedicated Channel Toggle
   ================================================================================ */

(function () {
  "use strict";

  const GUILD_ID = window.CURRENT_GUILD_ID;

  if (!GUILD_ID || GUILD_ID === "undefined" || GUILD_ID === "") {
    console.error("[AI Chat] ❌ CRITICAL: window.CURRENT_GUILD_ID is undefined!");
    const pathMatch = window.location.pathname.match(/\/dashboard\/(\d+)\//);
    if (pathMatch && pathMatch[1]) {
      window.CURRENT_GUILD_ID = pathMatch[1];
      console.warn("[AI Chat] ⚠️ Fallback: extracted guild_id from URL:", pathMatch[1]);
    } else {
      document.body.insertAdjacentHTML("afterbegin",
        `<div style="background:#ed4245;color:#fff;padding:1rem;text-align:center;font-weight:bold;">
          ⚠️ Error: Guild ID tidak terdeteksi. Refresh halaman atau hubungi admin.
        </div>`
      );
      return;
    }
  }

  const API_BASE = `/api/ai-chat`;
  const TOGGLE_URL = `/dashboard/${GUILD_ID}/ai-chat/toggle`;
  const SAVE_URL = `/dashboard/${GUILD_ID}/ai-chat/save`;

  const els = {
    toggle: document.getElementById("ai-toggle"),
    toggleLabel: document.getElementById("toggle-label"),
    channel: document.getElementById("channel-select"),
    dedicatedToggle: document.getElementById("dedicated-toggle"),
    dedicatedRow: document.getElementById("dedicated-toggle-row"),
    personality: document.getElementById("personality-select"),
    temperature: document.getElementById("temperature-slider"),
    tempValue: document.getElementById("temperature-value"),
    saveBtn: document.getElementById("save-btn"),
    historyContainer: document.getElementById("history-container"),
    toast: document.getElementById("toast"),
    toastMsg: document.getElementById("toast-message"),
    apiStatus: document.getElementById("ai-status-text"),
  };

  function show(el) { if (!el) return; el.style.display = ""; el.classList.remove("hidden"); }
  function hide(el) { if (!el) return; el.style.display = "none"; el.classList.add("hidden"); }

  async function init() {
    console.log("[AI Chat] ✅ Initializing v4.7 with guild_id:", GUILD_ID);
    await loadSettings();
    setupEventListeners();
    await loadHistory();
    checkApiStatus();
  }

  async function loadSettings() {
    try {
      const res = await fetch(`${API_BASE}/settings/${GUILD_ID}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
      const data = await res.json();

      if (!data.success) {
        showToast("⚠️ Gagal memuat pengaturan.", "error");
        return;
      }

      if (els.toggle) {
        els.toggle.checked = data.ai_chat_enabled || false;
        updateToggleVisuals();
      }

      const cfg = data.ai_chat || {};

      if (cfg.channel_id && els.channel) {
        els.channel.value = cfg.channel_id;
      }

      if (els.dedicatedToggle) {
        els.dedicatedToggle.checked = cfg.dedicated_ai_channel || false;
        updateDedicatedVisibility();
      }

      if (cfg.personality && els.personality) {
        els.personality.value = cfg.personality;
      }

      if (cfg.temperature !== undefined && cfg.temperature !== null && els.temperature) {
        els.temperature.value = cfg.temperature;
        if (els.tempValue) els.tempValue.textContent = cfg.temperature;
      }

      console.log("[AI Chat] ✅ Settings loaded:", data);
    } catch (err) {
      console.error("[AI Chat] Error load settings:", err);
      showToast("⚠️ Gagal memuat pengaturan. Cek koneksi.", "error");
    }
  }

  function updateDedicatedVisibility() {
    if (!els.dedicatedRow || !els.channel) return;
    if (els.channel.value) {
      show(els.dedicatedRow);
    } else {
      hide(els.dedicatedRow);
      if (els.dedicatedToggle) els.dedicatedToggle.checked = false;
    }
  }

  function setupEventListeners() {
    if (els.toggle) els.toggle.addEventListener("change", handleToggle);

    if (els.channel) {
      els.channel.addEventListener("change", updateDedicatedVisibility);
    }

    if (els.temperature) {
      els.temperature.addEventListener("input", (e) => {
        if (els.tempValue) els.tempValue.textContent = e.target.value;
      });
    }

    if (els.saveBtn) els.saveBtn.addEventListener("click", handleSaveSettings);
  }

  async function handleToggle() {
    const enabled = els.toggle.checked;
    updateToggleVisuals();

    try {
      const res = await fetch(TOGGLE_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled }),
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      if (data.success) {
        showToast(`AI Chat ${enabled ? "diaktifkan" : "dinonaktifkan"}.`, "success");
      } else {
        els.toggle.checked = !enabled;
        updateToggleVisuals();
        showToast(data.message || "Gagal menyimpan.", "error");
      }
    } catch (err) {
      console.error("[AI Chat] Toggle error:", err);
      els.toggle.checked = !enabled;
      updateToggleVisuals();
      showToast("Koneksi error. Coba lagi.", "error");
    }
  }

  function updateToggleVisuals() {
    if (!els.toggle || !els.toggleLabel) return;
    const enabled = els.toggle.checked;
    els.toggleLabel.textContent = enabled ? "Aktif" : "Nonaktif";
    els.toggleLabel.style.color = enabled ? "var(--accent-success)" : "var(--text-muted)";
    const card = els.toggle.closest(".card");
    if (!card) return;
    if (enabled) {
      card.style.borderColor = "var(--accent-primary)";
      card.style.background = "linear-gradient(135deg, #1e1e22 0%, #1a1a2e 100%)";
    } else {
      card.style.borderColor = "var(--border-color)";
      card.style.background = "var(--bg-card)";
    }
  }

  async function handleSaveSettings() {
    const payload = {
      personality: els.personality ? els.personality.value : "friendly",
      channel_id: els.channel ? els.channel.value : "",
      temperature: els.temperature ? parseFloat(els.temperature.value) : 0.75,
      dedicated_ai_channel: els.dedicatedToggle ? els.dedicatedToggle.checked : false,
    };

    const originalText = els.saveBtn ? els.saveBtn.innerHTML : "💾 Simpan Pengaturan";
    if (els.saveBtn) { els.saveBtn.innerHTML = "⏳ Menyimpan..."; els.saveBtn.disabled = true; }

    try {
      const res = await fetch(SAVE_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      if (data.success) {
        showToast("✅ Pengaturan berhasil disimpan!", "success");
      } else {
        showToast(data.message || "❌ Gagal menyimpan.", "error");
      }
    } catch (err) {
      console.error("[AI Chat] Save error:", err);
      showToast("❌ Koneksi error. Coba lagi.", "error");
    } finally {
      if (els.saveBtn) { els.saveBtn.innerHTML = originalText; els.saveBtn.disabled = false; }
    }
  }

  async function loadHistory() {
    if (!els.historyContainer) return;

    els.historyContainer.innerHTML = `
      <div class="loading-spinner">
        <div class="spinner"></div>
        <span>Memuat data...</span>
      </div>`;

    try {
      const res = await fetch(`${API_BASE}/history/${GUILD_ID}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      if (!data.success || !data.history || data.history.length === 0) {
        els.historyContainer.innerHTML = `
          <div class="empty-state">
            <div class="empty-icon">📝</div>
            <p>Belum ada riwayat chat.</p>
            <p class="text-muted">History akan muncul setelah user mulai chat dengan AI.</p>
          </div>`;
        return;
      }

      let html = '<div class="history-list">';
      data.history.forEach((item) => {
        const preview = item.preview || [];
        let messagesHtml = "";
        preview.forEach((msg) => {
          const roleClass = msg.role === "user" ? "user" : "assistant";
          const roleLabel = msg.role === "user" ? "User" : "AI";
          messagesHtml += `<div class="history-msg ${roleClass}"><strong>${roleLabel}:</strong> ${escapeHtml(msg.content)}</div>`;
        });
        html += `
          <div class="history-item">
            <div class="history-meta">
              <div class="history-avatar">#${item.user_id.slice(-4)}</div>
              <span class="history-user">User ${item.user_id.slice(-8)}</span>
              <span class="history-time">${item.total_messages} pesan • ${item.personality}</span>
            </div>
            ${messagesHtml}
          </div>`;
      });
      html += "</div>";
      els.historyContainer.innerHTML = html;
    } catch (err) {
      console.error("[AI Chat] History load error:", err);
      els.historyContainer.innerHTML = `
        <div class="empty-state">
          <div class="empty-icon">⚠️</div>
          <p>Gagal memuat riwayat chat.</p>
          <p class="text-muted">Coba refresh halaman.</p>
        </div>`;
    }
  }

  function checkApiStatus() {
    if (!els.apiStatus) return;
    setTimeout(() => {
      els.apiStatus.textContent = "Online";
      els.apiStatus.style.color = "var(--accent-success)";
      els.apiStatus.style.fontWeight = "600";
    }, 800);
  }

  function showToast(message, type) {
    if (!els.toast || !els.toastMsg) return;
    els.toastMsg.textContent = message;
    const colors = { success: "var(--accent-success)", error: "var(--accent-danger)", warning: "var(--accent-warning)" };
    els.toast.style.borderLeft = `4px solid ${colors[type] || colors.success}`;
    els.toast.classList.remove("hidden");
    els.toast.style.display = "flex";
    void els.toast.offsetWidth;
    els.toast.classList.add("show");
    setTimeout(() => {
      els.toast.classList.remove("show");
      setTimeout(() => { els.toast.classList.add("hidden"); els.toast.style.display = "none"; }, 300);
    }, 3000);
  }

  function escapeHtml(text) {
    if (!text) return "";
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
