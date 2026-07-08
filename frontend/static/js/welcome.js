/**
 * welcome.js — Synapse Welcome Settings Form Logic v3.7.2
 * Features: style toggle (embed/banner), color picker sync, live preview,
 *           drag & drop upload with Catbox hosting + IMAGE RESIZE, banner preview, form submit
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
  const embedPreviewTitle = document.getElementById("embedPreviewTitle");
  const embedPreviewBar = document.getElementById("embedPreviewBar");
  const welcomeForm = document.getElementById("welcomeForm");
  const btnSave = document.getElementById("btnSave");
  const toast = document.getElementById("toast");

  // Style selector elements
  const styleSelector = document.getElementById("styleSelector");
  const embedSettingsCard = document.getElementById("embedSettingsCard");
  const bannerSettingsCard = document.getElementById("bannerSettingsCard");

  // Banner elements
  const bannerTextInput = document.getElementById("banner_text");
  const bannerSubtextInput = document.getElementById("banner_subtext");
  const bannerFontColorPicker = document.getElementById("banner_font_color");
  const bannerFontColorHex = document.getElementById("banner_font_color_text");
  const toggleAvatarRing = document.getElementById("toggleAvatarRing");
  const koyaBannerTitle = document.getElementById("koyaBannerTitle");
  const koyaBannerName = document.getElementById("koyaBannerName");
  const koyaBannerSub = document.getElementById("koyaBannerSub");
  const koyaAvatarRing = document.getElementById("koyaAvatarRing");
  const koyaBannerBg = document.getElementById("koyaBannerBg");
  const bannerBgUrlInput = document.getElementById("banner_bg_url");
  const bgUrlInput = document.getElementById("bg_image_url");
  const embedPreviewImage = document.getElementById("embedPreviewImage");

  // Banner upload elements
  const bannerUploadZone = document.getElementById("bannerUploadZone");
  const bannerFileInput = document.getElementById("bannerFileInput");
  const bannerUploadPreview = document.getElementById("bannerUploadPreview");
  const bannerUploadPreviewImg = document.getElementById(
    "bannerUploadPreviewImg",
  );
  const bannerUploadRemove = document.getElementById("bannerUploadRemove");

  // Embed upload elements
  const uploadZone = document.getElementById("uploadZone");
  const fileInput = document.getElementById("fileInput");
  const uploadPreview = document.getElementById("uploadPreview");
  const uploadPreviewImg = document.getElementById("uploadPreviewImg");
  const uploadRemove = document.getElementById("uploadRemove");

  // Hidden inputs for file upload
  let uploadedFileData = "";
  let uploadedFileName = "";
  let uploadTarget = ""; // "embed_bg" or "banner_bg"

  // ── 0. Image Resize Helper (NEW v3.7.2) ──
  function resizeImage(file, maxWidth = 1200, quality = 0.85) {
    return new Promise((resolve, reject) => {
      const img = new Image();
      const reader = new FileReader();

      reader.onload = (e) => {
        img.src = e.target.result;
      };
      reader.onerror = (err) => reject(err);

      img.onload = () => {
        let width = img.width;
        let height = img.height;

        if (width > maxWidth) {
          height = Math.round((height * maxWidth) / width);
          width = maxWidth;
        }

        const canvas = document.createElement("canvas");
        canvas.width = width;
        canvas.height = height;
        const ctx = canvas.getContext("2d");
        ctx.drawImage(img, 0, 0, width, height);

        // Convert to JPEG for smaller size
        const resizedBase64 = canvas.toDataURL("image/jpeg", quality);
        console.log(
          `[WELCOME] 🖼️ Resized: ${img.width}x${img.height} → ${width}x${height}, base64 length: ${resizedBase64.length}`,
        );

        console.log(`[WELCOME] 🖼️ Resized: ${img.width}x${img.height} → ${width}x${height}, base64 length: ${resizedBase64.length}`);
        resolve(resizedBase64);
      };

      img.onerror = (err) => reject(err);
      reader.readAsDataURL(file);
    });
  }

  // ── 1. Style Selector Toggle ──
  function setActiveStyle(style) {
    document
      .querySelectorAll('.style-option input[name="style"]')
      .forEach((radio) => {
        radio.checked = radio.value === style;
      });
    document.querySelectorAll(".style-option").forEach((opt) => {
      opt.classList.toggle("active", opt.dataset.style === style);
    });
    if (embedSettingsCard) {
      embedSettingsCard.classList.toggle("visible", style === "embed");
    }
    if (bannerSettingsCard) {
      bannerSettingsCard.classList.toggle("visible", style === "banner");
    }
    console.log(`[WELCOME] 🎨 Style switched to: ${style}`);
  }

  if (styleSelector) {
    document.querySelectorAll(".style-option").forEach((option) => {
      option.addEventListener("click", () => {
        setActiveStyle(option.dataset.style);
      });
    });
    const initialStyleRadio = document.querySelector(
      '.style-option input[name="style"]:checked',
    );
    if (initialStyleRadio) {
      setActiveStyle(initialStyleRadio.value);
    } else {
      setActiveStyle("embed");
    }
  }

  // ── 2. Embed Panel Toggle ──
  if (toggleEmbed && embedPanel) {
    toggleEmbed.addEventListener("change", function () {
      embedPanel.classList.toggle("open", this.checked);
    });
  }

  // ── 3. Status Banner Toggle ──
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

  // ── 4. Color Picker Sync (Embed) ──
  function applyEmbedColor(hex) {
    document.documentElement.style.setProperty("--welcome-accent", hex);
    if (document.activeElement !== colorPicker && colorPicker) {
      colorPicker.value = hex;
    }
    if (document.activeElement !== colorHexInput && colorHexInput) {
      colorHexInput.value = hex;
    }
    if (embedPreviewBar) {
      embedPreviewBar.style.background = hex;
    }
  }

  if (colorPicker) {
    colorPicker.addEventListener("input", function () {
      applyEmbedColor(this.value);
    });
  }

  if (colorHexInput) {
    colorHexInput.addEventListener("input", function () {
      const v = this.value.startsWith("#") ? this.value : "#" + this.value;
      if (/^#[0-9A-Fa-f]{6}$/.test(v)) {
        applyEmbedColor(v);
      }
    });
  }

  // ── 5. Banner Font Color Sync ──
  function applyBannerColor(hex) {
    document.documentElement.style.setProperty("--banner-font-color", hex);
    if (
      document.activeElement !== bannerFontColorPicker &&
      bannerFontColorPicker
    ) {
      bannerFontColorPicker.value = hex;
    }
    if (document.activeElement !== bannerFontColorHex && bannerFontColorHex) {
      bannerFontColorHex.value = hex;
    }
  }

  if (bannerFontColorPicker) {
    bannerFontColorPicker.addEventListener("input", function () {
      applyBannerColor(this.value);
    });
  }

  if (bannerFontColorHex) {
    bannerFontColorHex.addEventListener("input", function () {
      const v = this.value.startsWith("#") ? this.value : "#" + this.value;
      if (/^#[0-9A-Fa-f]{6}$/.test(v)) {
        applyBannerColor(v);
      }
    });
  }

  // ── 6. Live Preview Title (Embed) ──
  if (embedTitleInput && embedPreviewTitle) {
    embedTitleInput.addEventListener("input", function () {
      embedPreviewTitle.textContent = this.value.trim() || "👋 Selamat Datang!";
    });
  }

  // ── 7. Banner Text Live Preview ──
  if (bannerTextInput && koyaBannerTitle) {
    bannerTextInput.addEventListener("input", function () {
      koyaBannerTitle.textContent = (
        this.value.trim() || "WELCOME"
      ).toUpperCase();
    });
  }

  if (bannerSubtextInput && koyaBannerSub) {
    bannerSubtextInput.addEventListener("input", function () {
      const val = this.value.trim() || "Member ke-171 • Synapse";
      koyaBannerSub.textContent = val
        .replace("{count}", "171")
        .replace("{server}", "Synapse");
    });
  }

  // ── 8. Avatar Ring Toggle ──
  if (toggleAvatarRing && koyaAvatarRing) {
    toggleAvatarRing.addEventListener("change", function () {
      koyaAvatarRing.classList.toggle("hidden", !this.checked);
    });
  }

  // ── 9. Banner Background Preview ──
  function updateBannerBgPreview(url) {
    if (koyaBannerBg && url) {
      koyaBannerBg.style.backgroundImage = `url(${url})`;
      koyaBannerBg.classList.remove("no-image");
    } else if (koyaBannerBg) {
      koyaBannerBg.style.backgroundImage = "";
      koyaBannerBg.classList.add("no-image");
    }
  }

  if (bannerBgUrlInput) {
    bannerBgUrlInput.addEventListener("input", function () {
      updateBannerBgPreview(this.value.trim());
    });
  }

  function updateEmbedPreview(url) {
    if (!embedPreviewImage) return;
    if (url) {
      embedPreviewImage.classList.add("active");
      const img = embedPreviewImage.querySelector("img");
      if (img) img.src = url;
    } else {
      embedPreviewImage.classList.remove("active");
    }
  }

  if (bgUrlInput) {
    bgUrlInput.addEventListener("input", function () { updateEmbedPreview(this.value.trim()); });
    if (bgUrlInput.value.trim()) updateEmbedPreview(bgUrlInput.value.trim());
  }

  // ── 10. Drag & Drop Upload (Embed) ──
  setupUploadZone(
    uploadZone,
    fileInput,
    uploadPreview,
    uploadPreviewImg,
    uploadRemove,
    (base64, filename) => {
      uploadedFileData = base64;
      uploadedFileName = filename;
      uploadTarget = "embed_bg";
      console.log("[WELCOME] 📤 Embed file selected:", filename);
    },
  );

  // ── 11. Drag & Drop Upload (Banner) ──
  setupUploadZone(
    bannerUploadZone,
    bannerFileInput,
    bannerUploadPreview,
    bannerUploadPreviewImg,
    bannerUploadRemove,
    (base64, filename) => {
      uploadedFileData = base64;
      uploadedFileName = filename;
      uploadTarget = "banner_bg";
      updateBannerBgPreview(base64);
      console.log("[WELCOME] 📤 Banner file selected:", filename);
    },
  );

  // ── Upload Zone Setup Helper ──
  function setupUploadZone(
    zone,
    input,
    preview,
    previewImg,
    removeBtn,
    onPreview,
  ) {
    if (!zone || !input) return;

    ["dragenter", "dragover", "dragleave", "drop"].forEach((eventName) => {
      zone.addEventListener(eventName, preventDefaults, false);
      document.body.addEventListener(eventName, preventDefaults, false);
    });

    function preventDefaults(e) {
      e.preventDefault();
      e.stopPropagation();
    }

    ["dragenter", "dragover"].forEach((eventName) => {
      zone.addEventListener(eventName, highlight, false);
    });

    ["dragleave", "drop"].forEach((eventName) => {
      zone.addEventListener(eventName, unhighlight, false);
    });

    function highlight() {
      zone.classList.add("dragover");
    }

    function unhighlight() {
      zone.classList.remove("dragover");
    }

    zone.addEventListener("drop", handleDrop, false);

    zone.addEventListener("click", function (e) {
      if (e.target.closest(".upload-remove")) return;
      input.click();
    });

    function handleDrop(e) {
      const dt = e.dataTransfer;
      const files = dt.files;
      handleFiles(files);
    }

    input.addEventListener("change", function () {
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

    // ← FIX v3.7.2: Resize image via Canvas sebelum simpan base64
    function previewFile(file) {
      // 1. Baca asli untuk preview
      const reader = new FileReader();
      reader.readAsDataURL(file);
      reader.onloadend = function () {
        const originalBase64 = reader.result;

        // Tampilkan preview asli (biar user lihat)
        if (previewImg) {
          previewImg.src = originalBase64;
        }
        if (preview) {
          preview.classList.add("active");
        }
        zone.classList.add("has-file");

        // 2. Resize untuk upload (kecilkan base64 yang dikirim ke backend)
        resizeImage(file, 1200, 0.85)
          .then((resizedBase64) => {
            // Simpan yang resized untuk dikirim ke backend
            uploadedFileData = resizedBase64;
            uploadedFileName = file.name;
            uploadTarget =
              zone.id === "bannerUploadZone" ? "banner_bg" : "embed_bg";

            uploadTarget = (zone.id === "bannerUploadZone") ? "banner_bg" : "embed_bg";


            // ← FIX: Sync ke hidden inputs juga
            const hiddenData = document.getElementById("uploaded_file_data");
            const hiddenName = document.getElementById("uploaded_file_name");
            const hiddenTarget = document.getElementById("upload_target");
            if (hiddenData) hiddenData.value = resizedBase64;
            if (hiddenName) hiddenName.value = file.name;
            if (hiddenTarget) hiddenTarget.value = uploadTarget;

            if (onPreview) onPreview(resizedBase64, file.name);


            showToast(
              "📤 Gambar dipilih. Akan di-upload saat simpan.",
              "success",
            );

            showToast("📤 Gambar dipilih. Akan di-upload saat simpan.", "success");

          })
          .catch((err) => {
            console.error("[WELCOME] ❌ Error resizing image:", err);
            showToast("❌ Gagal memproses gambar.", "error");
          });
      };
    }

    if (removeBtn) {
      removeBtn.addEventListener("click", function (e) {
        e.preventDefault();
        e.stopPropagation();

        if (preview) {
          preview.classList.remove("active");
        }
        if (previewImg) {
          previewImg.src = "";
        }
        if (input) {
          input.value = "";
        }
        zone.classList.remove("has-file");

        uploadedFileData = "";
        uploadedFileName = "";
        uploadTarget = "";

        // ← FIX: Clear hidden inputs juga
        const hiddenData = document.getElementById("uploaded_file_data");
        const hiddenName = document.getElementById("uploaded_file_name");
        const hiddenTarget = document.getElementById("upload_target");
        if (hiddenData) hiddenData.value = "";
        if (hiddenName) hiddenName.value = "";
        if (hiddenTarget) hiddenTarget.value = "";

        if (onPreview) onPreview(null, "");
      });
    }
  }

  // ── 12. Toast Notification ──
  function showToast(msg, type = "success") {
    if (!toast) return;
    document.getElementById("toastMsg").textContent = msg;
    document.getElementById("toastIcon").textContent =
      type === "success" ? "✅" : "❌";
    toast.className = `toast ${type}`;
    requestAnimationFrame(() => toast.classList.add("show"));
    setTimeout(() => toast.classList.remove("show"), 4000);
  }

  // ── Gallery ──
  document.querySelectorAll(".gallery-toggle").forEach(function (btn) {
    btn.addEventListener("click", function () {
      const grid = document.getElementById(this.dataset.gallery);
      if (grid) grid.classList.toggle("open");
    });
  });
  document.querySelectorAll(".gallery-item").forEach(function (item) {
    item.addEventListener("click", function () {
      const input = document.getElementById(this.dataset.input);
      if (input) {
        input.value = this.src;
        input.dispatchEvent(new Event("input", { bubbles: true }));
        document.querySelectorAll(".gallery-grid").forEach(function (g) { g.classList.remove("open"); });
      }
    });
  });

  // ── Dynamic Gallery (from /api/gallery/images) ──
  document.querySelectorAll(".gallery-toggle-dynamic").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var grid = document.getElementById(this.dataset.grid + "Dynamic");
      if (!grid) return;
      if (grid.dataset.loaded) {
        grid.classList.toggle("open");
        return;
      }
      grid.dataset.loaded = "1";
      var inputTarget = this.dataset.input;
      fetch("/api/gallery/images")
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (!d.success || !d.images.length) {
            grid.innerHTML = '<div style="grid-column:1/-1;text-align:center;padding:1rem;color:var(--text-muted);font-size:0.8rem;">Belum ada gambar</div>';
            grid.classList.add("open");
            return;
          }
          var html = "";
          d.images.forEach(function (img) {
            html += '<img src="' + img.url + '" class="gallery-item" data-input="' + inputTarget + '" loading="lazy" style="cursor:pointer;border-radius:var(--r-md);aspect-ratio:16/9;object-fit:cover;width:100%;border:2px solid var(--border);transition:border-color 0.15s;" />';
          });
          grid.innerHTML = html;
          grid.querySelectorAll(".gallery-item").forEach(function (item) {
            item.addEventListener("click", function () {
              var input = document.getElementById(this.dataset.input);
              if (input) {
                input.value = this.src;
                input.dispatchEvent(new Event("input", { bubbles: true }));
                document.querySelectorAll(".gallery-grid").forEach(function (g) { g.classList.remove("open"); });
              }
            });
          });
          grid.classList.add("open");
        })
        .catch(function () {
          grid.innerHTML = '<div style="grid-column:1/-1;text-align:center;padding:1rem;color:var(--text-muted);font-size:0.8rem;">Gagal muat</div>';
          grid.classList.add("open");
        });
    });
  });

  // ── 13. Form Submit ──
  if (welcomeForm) {
    welcomeForm.addEventListener("submit", async function (e) {
      e.preventDefault();

      // Sync hex inputs ke color pickers
      if (colorHexInput && colorPicker) {
        const hexVal = colorHexInput.value;
        if (/^#?[0-9A-Fa-f]{6}$/.test(hexVal)) {
          colorPicker.value = hexVal.startsWith("#") ? hexVal : "#" + hexVal;
        }
      }
      if (bannerFontColorHex && bannerFontColorPicker) {
        const hexVal = bannerFontColorHex.value;
        if (/^#?[0-9A-Fa-f]{6}$/.test(hexVal)) {
          bannerFontColorPicker.value = hexVal.startsWith("#")
            ? hexVal
            : "#" + hexVal;
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

      // Build FormData with file upload info
      const formData = new FormData(this);

      // ← FIX v3.7.2: Pastikan hidden input values sudah sync ke FormData
      // (FormData otomatis ambil dari form elements, tapi kita append juga sebagai backup)
      if (uploadedFileData) {
        formData.set("uploaded_file_data", uploadedFileData);
        formData.set("uploaded_file_name", uploadedFileName || "upload.png");
        formData.set("upload_target", uploadTarget);
      }

      // Loading state
      if (btnSave) {
        btnSave.disabled = true;
        btnSave.classList.add("loading");
      }

      try {
        const res = await fetch(`/dashboard/${guildId}/welcome/save`, {
          method: "POST",
          body: formData,
        });
        const result = await res.json();

        if (res.ok && result.success) {
          showToast(result.message || "✅ Tersimpan!", "success");

          // Clear upload state after successful save
          uploadedFileData = "";
          uploadedFileName = "";
          uploadTarget = "";

          // Refresh page after 1.5s to show saved image
          setTimeout(() => {
            window.location.reload();
          }, 1500);
        } else {
          showToast(result.message || "❌ Gagal menyimpan.", "error");
        }
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


  console.log(
    "[WELCOME] ✅ Welcome JS v3.7.2 loaded — Image Resize + Catbox Upload",
  );

  console.log("[WELCOME] ✅ Welcome JS v3.7.2 loaded — Image Resize + Catbox Upload");
});
