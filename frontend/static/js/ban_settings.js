document.addEventListener("DOMContentLoaded", () => {
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
  const banForm = document.getElementById("banForm");
  const btnSave = document.getElementById("btnSave");
  const toast = document.getElementById("toast");

  const styleSelector = document.getElementById("styleSelector");
  const embedSettingsCard = document.getElementById("embedSettingsCard");
  const bannerSettingsCard = document.getElementById("bannerSettingsCard");

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

  const bannerUploadZone = document.getElementById("bannerUploadZone");
  const bannerFileInput = document.getElementById("bannerFileInput");
  const bannerUploadPreview = document.getElementById("bannerUploadPreview");
  const bannerUploadPreviewImg = document.getElementById("bannerUploadPreviewImg");
  const bannerUploadRemove = document.getElementById("bannerUploadRemove");

  const uploadZone = document.getElementById("uploadZone");
  const fileInput = document.getElementById("fileInput");
  const uploadPreview = document.getElementById("uploadPreview");
  const uploadPreviewImg = document.getElementById("uploadPreviewImg");
  const uploadRemove = document.getElementById("uploadRemove");

  let uploadedFileData = "";
  let uploadedFileName = "";
  let uploadTarget = "";

  function resizeImage(file, maxWidth, quality) {
    if (maxWidth === void 0) maxWidth = 1200;
    if (quality === void 0) quality = 0.85;
    return new Promise((resolve, reject) => {
      const img = new Image();
      const reader = new FileReader();
      reader.onload = (e) => { img.src = e.target.result; };
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
        const resizedBase64 = canvas.toDataURL("image/jpeg", quality);
        resolve(resizedBase64);
      };
      img.onerror = (err) => reject(err);
      reader.readAsDataURL(file);
    });
  }

  function setActiveStyle(style) {
    document.querySelectorAll('.style-option input[name="style"]').forEach((radio) => {
      radio.checked = radio.value === style;
    });
    document.querySelectorAll(".style-option").forEach((opt) => {
      opt.classList.toggle("active", opt.dataset.style === style);
    });
    if (embedSettingsCard) embedSettingsCard.classList.toggle("visible", style === "embed");
    if (bannerSettingsCard) bannerSettingsCard.classList.toggle("visible", style === "banner");
  }

  if (styleSelector) {
    document.querySelectorAll(".style-option").forEach((option) => {
      option.addEventListener("click", () => { setActiveStyle(option.dataset.style); });
    });
    const initialStyleRadio = document.querySelector('.style-option input[name="style"]:checked');
    if (initialStyleRadio) setActiveStyle(initialStyleRadio.value);
    else setActiveStyle("embed");
  }

  if (toggleEmbed && embedPanel) {
    toggleEmbed.addEventListener("change", function () {
      embedPanel.classList.toggle("open", this.checked);
    });
  }

  if (toggleEnabled && statusBanner && statusText) {
    toggleEnabled.addEventListener("change", function () {
      if (this.checked) {
        statusBanner.className = "status-banner active";
        statusText.innerHTML = "Modul Ban sedang <strong>aktif</strong>.";
      } else {
        statusBanner.className = "status-banner inactive";
        statusText.innerHTML = "Modul Ban sedang <strong>nonaktif</strong>.";
      }
    });
  }

  function applyEmbedColor(hex) {
    document.documentElement.style.setProperty("--welcome-accent", hex);
    if (document.activeElement !== colorPicker && colorPicker) colorPicker.value = hex;
    if (document.activeElement !== colorHexInput && colorHexInput) colorHexInput.value = hex;
    if (embedPreviewBar) embedPreviewBar.style.background = hex;
  }

  if (colorPicker) colorPicker.addEventListener("input", function () { applyEmbedColor(this.value); });
  if (colorHexInput) {
    colorHexInput.addEventListener("input", function () {
      const v = this.value.startsWith("#") ? this.value : "#" + this.value;
      if (/^#[0-9A-Fa-f]{6}$/.test(v)) applyEmbedColor(v);
    });
  }

  function applyBannerColor(hex) {
    document.documentElement.style.setProperty("--banner-font-color", hex);
    if (document.activeElement !== bannerFontColorPicker && bannerFontColorPicker) bannerFontColorPicker.value = hex;
    if (document.activeElement !== bannerFontColorHex && bannerFontColorHex) bannerFontColorHex.value = hex;
  }

  if (bannerFontColorPicker) bannerFontColorPicker.addEventListener("input", function () { applyBannerColor(this.value); });
  if (bannerFontColorHex) {
    bannerFontColorHex.addEventListener("input", function () {
      const v = this.value.startsWith("#") ? this.value : "#" + this.value;
      if (/^#[0-9A-Fa-f]{6}$/.test(v)) applyBannerColor(v);
    });
  }

  if (embedTitleInput && embedPreviewTitle) {
    embedTitleInput.addEventListener("input", function () {
      embedPreviewTitle.textContent = this.value.trim() || "🚫 User Banned";
    });
  }

  if (bannerTextInput && koyaBannerTitle) {
    bannerTextInput.addEventListener("input", function () {
      koyaBannerTitle.textContent = (this.value.trim() || "BANNED").toUpperCase();
    });
  }

  if (bannerSubtextInput && koyaBannerSub) {
    bannerSubtextInput.addEventListener("input", function () {
      const val = this.value.trim() || "Member ke-171 • Hidden Hamlet";
      koyaBannerSub.textContent = val.replace("{count}", "171").replace("{server}", "Hidden Hamlet");
    });
  }

  if (toggleAvatarRing && koyaAvatarRing) {
    toggleAvatarRing.addEventListener("change", function () {
      koyaAvatarRing.classList.toggle("hidden", !this.checked);
    });
  }

  function updateBannerBgPreview(url) {
    if (koyaBannerBg && url) {
      koyaBannerBg.style.backgroundImage = "url(" + url + ")";
      koyaBannerBg.classList.remove("no-image");
    } else if (koyaBannerBg) {
      koyaBannerBg.style.backgroundImage = "";
      koyaBannerBg.classList.add("no-image");
    }
  }

  if (bannerBgUrlInput) {
    bannerBgUrlInput.addEventListener("input", function () { updateBannerBgPreview(this.value.trim()); });
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

  setupUploadZone(uploadZone, fileInput, uploadPreview, uploadPreviewImg, uploadRemove, (base64, filename) => {
    uploadedFileData = base64;
    uploadedFileName = filename;
    if (base64) uploadTarget = "embed_bg";
  });

  setupUploadZone(bannerUploadZone, bannerFileInput, bannerUploadPreview, bannerUploadPreviewImg, bannerUploadRemove, (base64, filename) => {
    uploadedFileData = base64;
    uploadedFileName = filename;
    if (base64) uploadTarget = "banner_bg";
    updateBannerBgPreview(base64);
  });

  function setupUploadZone(zone, input, preview, previewImg, removeBtn, onPreview) {
    if (!zone || !input) return;
    ["dragenter", "dragover", "dragleave", "drop"].forEach((eventName) => {
      zone.addEventListener(eventName, preventDefaults, false);
      document.body.addEventListener(eventName, preventDefaults, false);
    });
    function preventDefaults(e) { e.preventDefault(); e.stopPropagation(); }
    ["dragenter", "dragover"].forEach((eventName) => { zone.addEventListener(eventName, highlight, false); });
    ["dragleave", "drop"].forEach((eventName) => { zone.addEventListener(eventName, unhighlight, false); });
    function highlight() { zone.classList.add("dragover"); }
    function unhighlight() { zone.classList.remove("dragover"); }
    zone.addEventListener("drop", handleDrop, false);
    zone.addEventListener("click", function (e) { if (e.target.closest(".upload-remove")) return; input.click(); });
    function handleDrop(e) { const dt = e.dataTransfer; handleFiles(dt.files); }
    input.addEventListener("change", function () { handleFiles(this.files); });
    function handleFiles(files) {
      if (files.length > 0) {
        const file = files[0];
        if (!file.type.startsWith("image/")) { showToast("File harus berupa gambar (PNG, JPG, GIF).", "error"); return; }
        if (file.size > 5 * 1024 * 1024) { showToast("Ukuran file maksimal 5MB.", "error"); return; }
        previewFile(file);
      }
    }
    function previewFile(file) {
      const reader = new FileReader();
      reader.readAsDataURL(file);
      reader.onloadend = function () {
        const originalBase64 = reader.result;
        if (previewImg) previewImg.src = originalBase64;
        if (preview) preview.classList.add("active");
        zone.classList.add("has-file");
        resizeImage(file, 1200, 0.85).then((resizedBase64) => {
          uploadedFileData = resizedBase64;
          uploadedFileName = file.name;
          uploadTarget = zone.id === "bannerUploadZone" ? "banner_bg" : "embed_bg";
          const hiddenData = document.getElementById("uploaded_file_data");
          const hiddenName = document.getElementById("uploaded_file_name");
          const hiddenTarget = document.getElementById("upload_target");
          if (hiddenData) hiddenData.value = resizedBase64;
          if (hiddenName) hiddenName.value = file.name;
          if (hiddenTarget) hiddenTarget.value = uploadTarget;
          if (onPreview) onPreview(resizedBase64, file.name);
          showToast("📤 Gambar dipilih. Akan di-upload saat simpan.", "success");
        }).catch((err) => {
          showToast("❌ Gagal memproses gambar.", "error");
        });
      };
    }
    if (removeBtn) {
      removeBtn.addEventListener("click", function (e) {
        e.preventDefault();
        e.stopPropagation();
        if (preview) preview.classList.remove("active");
        if (previewImg) previewImg.src = "";
        if (input) input.value = "";
        zone.classList.remove("has-file");
        uploadedFileData = "";
        uploadedFileName = "";
        uploadTarget = "";
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

  function showToast(msg, type) {
    if (type === void 0) type = "success";
    if (!toast) return;
    document.getElementById("toastMsg").textContent = msg;
    document.getElementById("toastIcon").textContent = type === "success" ? "✅" : "❌";
    toast.className = "toast " + type;
    requestAnimationFrame(function () { return toast.classList.add("show"); });
    setTimeout(function () { return toast.classList.remove("show"); }, 4000);
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

  if (banForm) {
    banForm.addEventListener("submit", async function (e) {
      e.preventDefault();
      if (colorHexInput && colorPicker) {
        const hexVal = colorHexInput.value;
        if (/^#?[0-9A-Fa-f]{6}$/.test(hexVal)) colorPicker.value = hexVal.startsWith("#") ? hexVal : "#" + hexVal;
      }
      if (bannerFontColorHex && bannerFontColorPicker) {
        const hexVal = bannerFontColorHex.value;
        if (/^#?[0-9A-Fa-f]{6}$/.test(hexVal)) bannerFontColorPicker.value = hexVal.startsWith("#") ? hexVal : "#" + hexVal;
      }
      const channelSelect = document.getElementById("channel_id");
      if (channelSelect && !channelSelect.value) { showToast("Pilih channel tujuan terlebih dahulu.", "error"); return; }
      const messageText = document.getElementById("message_text");
      if (messageText && !messageText.value.trim()) { showToast("Teks pesan tidak boleh kosong.", "error"); return; }
      const guildId = document.querySelector('input[name="guild_id"]')?.value;
      if (!guildId) { showToast("Guild ID tidak ditemukan.", "error"); return; }
      const formData = new FormData(this);
      if (uploadedFileData) {
        formData.set("uploaded_file_data", uploadedFileData);
        formData.set("uploaded_file_name", uploadedFileName || "upload.png");
        formData.set("upload_target", uploadTarget);
      }
      if (btnSave) { btnSave.disabled = true; btnSave.classList.add("loading"); }
      try {
        const res = await fetch("/dashboard/" + guildId + "/welcome/ban/save", { method: "POST", body: formData });
        const result = await res.json();
        if (res.ok && result.success) {
          showToast(result.message || "✅ Tersimpan!", "success");
          uploadedFileData = "";
          uploadedFileName = "";
          uploadTarget = "";
          setTimeout(function () { window.location.reload(); }, 1500);
        } else {
          showToast(result.message || "❌ Gagal menyimpan.", "error");
        }
      } catch (err) {
        showToast("❌ Kesalahan jaringan. Periksa koneksi.", "error");
      } finally {
        if (btnSave) { btnSave.disabled = false; btnSave.classList.remove("loading"); }
      }
    });
  }
});
