/**
 * welcome.js — Hidden Hamlet Welcome Settings Form Logic
 * Features: toggle embed panel, color picker sync, live preview, form submit
 */

document.addEventListener("DOMContentLoaded", () => {
  // ── Elements ──
  const toggleEmbed = document.getElementById("toggleEmbed");
  const embedPanel = document.getElementById("embedPanel");
  const toggleEnabled = document.getElementById("toggleEnabled");
  const statusBanner = document.getElementById("statusBanner");
  const statusText = document.getElementById("statusText");
  const colorPicker = document.getElementById("embed_color");
  const colorHexInput = document.getElementById("embed_color_text");
  const embedTitleInput = document.getElementById("embed_title");
  const previewTitle = document.getElementById("previewTitle");
  const welcomeForm = document.getElementById("welcomeForm");
  const btnSave = document.getElementById("btnSave");
  const toast = document.getElementById("toast");

  // ── 1. Embed Panel Toggle ──
  if (toggleEmbed && embedPanel) {
    toggleEmbed.addEventListener("change", function () {
      embedPanel.classList.toggle("open", this.checked);
    });
  }

  // ── 2. Status Banner Toggle ──
  if (toggleEnabled && statusBanner && statusText) {
    toggleEnabled.addEventListener("change", function () {
      if (this.checked) {
        statusBanner.className = "status-banner active";
        statusText.innerHTML = "Modul Welcome sedang <strong>aktif</strong>.";
      } else {
        statusBanner.className = "status-banner inactive";
        statusText.innerHTML =
          "Modul Welcome sedang <strong>nonaktif</strong>.";
      }
    });
  }

  // ── 3. Color Picker Sync ──
  function applyColor(hex) {
    document.documentElement.style.setProperty("--welcome-accent", hex);
    if (document.activeElement !== colorPicker && colorPicker) {
      colorPicker.value = hex;
    }
    if (document.activeElement !== colorHexInput && colorHexInput) {
      colorHexInput.value = hex;
    }
  }

  if (colorPicker) {
    colorPicker.addEventListener("input", function () {
      applyColor(this.value);
    });
  }

  if (colorHexInput) {
    colorHexInput.addEventListener("input", function () {
      const v = this.value.startsWith("#") ? this.value : "#" + this.value;
      if (/^#[0-9A-Fa-f]{6}$/.test(v)) {
        applyColor(v);
      }
    });
  }

  // ── 4. Live Preview Title ──
  if (embedTitleInput && previewTitle) {
    embedTitleInput.addEventListener("input", function () {
      previewTitle.textContent = this.value.trim() || "👋 Selamat Datang!";
    });
  }

  // ── 5. Toast Notification ──
  function showToast(msg, type = "success") {
    if (!toast) return;
    document.getElementById("toastMsg").textContent = msg;
    document.getElementById("toastIcon").textContent =
      type === "success" ? "✅" : "❌";
    toast.className = `toast ${type}`;
    requestAnimationFrame(() => toast.classList.add("show"));
    setTimeout(() => toast.classList.remove("show"), 4000);
  }

  // ── 6. Form Submit ──
  if (welcomeForm) {
    welcomeForm.addEventListener("submit", async function (e) {
      e.preventDefault();

      // Sync hex input ke color picker sebelum submit
      if (colorHexInput && colorPicker) {
        const hexVal = colorHexInput.value;
        if (/^#?[0-9A-Fa-f]{6}$/.test(hexVal)) {
          colorPicker.value = hexVal.startsWith("#") ? hexVal : "#" + hexVal;
        }
      }

      // Validate channel
      const channelSelect = document.getElementById("channel_id");
      if (channelSelect && !channelSelect.value) {
        showToast("Pilih channel tujuan terlebih dahulu.", "error");
        return;
      }

      const guildId = document.querySelector('input[name="guild_id"]')?.value;
      if (!guildId) {
        showToast("Guild ID tidak ditemukan.", "error");
        return;
      }

      // Loading state
      if (btnSave) {
        btnSave.disabled = true;
        btnSave.classList.add("loading");
      }

      try {
        const res = await fetch(`/dashboard/${guildId}/welcome/save`, {
          method: "POST",
          body: new FormData(this),
        });
        const result = await res.json();

        showToast(
          result.message || (res.ok ? "✅ Tersimpan!" : "❌ Gagal menyimpan."),
          res.ok && result.success ? "success" : "error",
        );
      } catch (err) {
        console.error("[WELCOME SAVE]", err);
        showToast("❌ Kesalahan jaringan. Periksa koneksi.", "error");
      } finally {
        if (btnSave) {
          btnSave.disabled = false;
          btnSave.classList.remove("loading");
        }
      }
    });
  }

  console.log("[WELCOME] ✅ Welcome JS loaded and initialized");
});
