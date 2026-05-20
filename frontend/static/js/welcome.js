/**
 * welcome.js — Hidden Hamlet Welcome Settings Form Logic
 * Features: toggle embed panel, color picker sync, live preview,
 *           drag & drop upload, banner preview, form submit
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

  // Banner preview elements
  const bgImageUrlInput = document.getElementById("bg_image_url");
  const bannerImage = document.getElementById("bannerImage");
  const bannerPreview = document.getElementById("bannerPreview");
  const previewMessage = document.getElementById("previewMessage");

  // Upload zone elements
  const uploadZone = document.getElementById("uploadZone");
  const fileInput = document.getElementById("fileInput");
  const uploadPreview = document.getElementById("uploadPreview");
  const uploadPreviewImg = document.getElementById("uploadPreviewImg");
  const uploadRemove = document.getElementById("uploadRemove");

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

  // ── 5. Banner Preview Sync ──
  function updateBannerPreview(url) {
    if (bannerImage && url) {
      bannerImage.src = url;
      bannerImage.style.display = "block";
    } else if (bannerImage) {
      bannerImage.src = "/static/images/default-welcome-bg.png";
    }
  }

  // Sync URL input → banner preview
  if (bgImageUrlInput && bannerImage) {
    bgImageUrlInput.addEventListener("input", function () {
      updateBannerPreview(this.value.trim());
    });
  }

  // ── 6. Drag & Drop Upload ──
  if (uploadZone && fileInput) {
    // Prevent default drag behaviors
    ["dragenter", "dragover", "dragleave", "drop"].forEach((eventName) => {
      uploadZone.addEventListener(eventName, preventDefaults, false);
      document.body.addEventListener(eventName, preventDefaults, false);
    });

    function preventDefaults(e) {
      e.preventDefault();
      e.stopPropagation();
    }

    // Highlight drop zone on drag
    ["dragenter", "dragover"].forEach((eventName) => {
      uploadZone.addEventListener(eventName, highlight, false);
    });

    ["dragleave", "drop"].forEach((eventName) => {
      uploadZone.addEventListener(eventName, unhighlight, false);
    });

    function highlight() {
      uploadZone.classList.add("dragover");
    }

    function unhighlight() {
      uploadZone.classList.remove("dragover");
    }

    // Handle dropped files
    uploadZone.addEventListener("drop", handleDrop, false);

    function handleDrop(e) {
      const dt = e.dataTransfer;
      const files = dt.files;
      handleFiles(files);
    }

    // Handle file input change
    fileInput.addEventListener("change", function () {
      handleFiles(this.files);
    });

    function handleFiles(files) {
      if (files.length > 0) {
        const file = files[0];
        if (!file.type.startsWith("image/")) {
          showToast("File harus berupa gambar (PNG, JPG, GIF).", "error");
          return;
        }
        if (file.size > 5 * 1024 * 1024) {
          showToast("Ukuran file maksimal 5MB.", "error");
          return;
        }
        previewFile(file);
      }
    }

    function previewFile(file) {
      const reader = new FileReader();
      reader.readAsDataURL(file);
      reader.onloadend = function () {
        const base64 = reader.result;

        // Show preview in upload zone
        if (uploadPreviewImg) {
          uploadPreviewImg.src = base64;
        }
        if (uploadPreview) {
          uploadPreview.classList.add("active");
        }
        uploadZone.classList.add("has-file");

        // Update banner preview
        updateBannerPreview(base64);

        // Note: Base64 images won't work in Discord embed (too large)
        // User should upload to hosting and paste URL, or we need server-side upload
        console.log(
          "[WELCOME] 📤 File selected (base64 preview only — upload to hosting for Discord)",
        );
      };
    }

    // Remove uploaded file
    if (uploadRemove) {
      uploadRemove.addEventListener("click", function (e) {
        e.preventDefault();
        e.stopPropagation();

        if (uploadPreview) {
          uploadPreview.classList.remove("active");
        }
        if (uploadPreviewImg) {
          uploadPreviewImg.src = "";
        }
        if (fileInput) {
          fileInput.value = "";
        }
        uploadZone.classList.remove("has-file");

        // Reset banner to URL or default
        const urlValue = bgImageUrlInput ? bgImageUrlInput.value.trim() : "";
        updateBannerPreview(
          urlValue || "/static/images/default-welcome-bg.png",
        );
      });
    }
  }

  // ── 7. Toast Notification ──
  function showToast(msg, type = "success") {
    if (!toast) return;
    document.getElementById("toastMsg").textContent = msg;
    document.getElementById("toastIcon").textContent =
      type === "success" ? "✅" : "❌";
    toast.className = `toast ${type}`;
    requestAnimationFrame(() => toast.classList.add("show"));
    setTimeout(() => toast.classList.remove("show"), 4000);
  }

  // ── 8. Form Submit ──
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

      // Validate message text
      const messageText = document.getElementById("message_text");
      if (messageText && !messageText.value.trim()) {
        showToast("Teks pesan tidak boleh kosong.", "error");
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
