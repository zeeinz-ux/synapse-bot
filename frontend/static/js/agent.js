/* ================================================================================
   JS: AI Agent Settings - Synapse Dashboard
   ================================================================================ */

(function () {
  "use strict";

  let GUILD_ID = window.CURRENT_GUILD_ID;

  if (!GUILD_ID || GUILD_ID === "undefined" || GUILD_ID === "") {
    console.error("[Agent] ❌ CRITICAL: window.CURRENT_GUILD_ID is undefined!");
    const pathMatch = window.location.pathname.match(/\/dashboard\/(\d+)\//);
    if (pathMatch && pathMatch[1]) {
      GUILD_ID = pathMatch[1];
      window.CURRENT_GUILD_ID = pathMatch[1];
      console.warn("[Agent] ⚠️ Fallback: extracted guild_id from URL:", GUILD_ID);
    } else {
      document.body.insertAdjacentHTML("afterbegin",
        `<div style="background:#ed4245;color:#fff;padding:1rem;text-align:center;font-weight:bold;">
          ⚠️ Error: Guild ID tidak terdeteksi. Refresh halaman atau hubungi admin.
        </div>`
      );
      return;
    }
  }

  const API_BASE = `/api/ai-agent`;
  const TOGGLE_URL = `/dashboard/${GUILD_ID}/ai-agent/toggle`;
  const SAVE_URL = `/dashboard/${GUILD_ID}/ai-agent/save`;

  const els = {
    toggle: document.getElementById("agent-toggle"),
    toggleLabel: document.getElementById("toggle-label"),
    mode: document.getElementById("agent-mode-select"),
    saveBtn: document.getElementById("save-btn"),
    toast: document.getElementById("toast"),
    toastMsg: document.getElementById("toast-message"),
    scanStatus: document.getElementById("scan-status-text"),
  };

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
        showToast(`AI Agent ${enabled ? "diaktifkan" : "dinonaktifkan"}.`, "success");
      } else {
        els.toggle.checked = !enabled;
        updateToggleVisuals();
        showToast(data.message || "Gagal menyimpan.", "error");
      }
    } catch (err) {
      console.error("[Agent] Toggle error:", err);
      els.toggle.checked = !enabled;
      updateToggleVisuals();
      showToast("Koneksi error. Coba lagi.", "error");
    }
  }

  async function handleSave() {
    const payload = {
      enabled: els.toggle ? els.toggle.checked : false,
      agent_mode: els.mode ? els.mode.value : "admin",
    };

    const originalText = els.saveBtn ? els.saveBtn.innerHTML : "Simpan";
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
      console.error("[Agent] Save error:", err);
      showToast("❌ Koneksi error. Coba lagi.", "error");
    } finally {
      if (els.saveBtn) { els.saveBtn.innerHTML = originalText; els.saveBtn.disabled = false; }
    }
  }

  function checkScanStatus() {
    if (!els.scanStatus) return;
    setTimeout(() => {
      els.scanStatus.textContent = "Gunakan /scan di Discord";
      els.scanStatus.style.color = "var(--text-muted)";
      els.scanStatus.style.fontWeight = "400";
    }, 800);
  }

  function init() {
    console.log("[Agent] ✅ Initializing with guild_id:", GUILD_ID);

    if (els.toggle) {
      els.toggle.addEventListener("change", handleToggle);
      updateToggleVisuals();
    }

    if (els.saveBtn) {
      els.saveBtn.addEventListener("click", handleSave);
    }

    checkScanStatus();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
