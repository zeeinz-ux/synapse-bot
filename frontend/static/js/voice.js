const guildIdEl = document.getElementById("guild-id");
const guildId = guildIdEl ? guildIdEl.value : "";

let config = {
  room_name_template: "",
  category_name: "",
};

document.addEventListener("DOMContentLoaded", async function () {
  if (!guildId) return;
  await loadCategories();
  await loadConfig();
  setupEventListeners();
});

async function loadCategories() {
  const sel = document.getElementById("category-name");
  if (!sel) return;
  try {
    const resp = await fetch(`/api/guilds/${guildId}/categories`);
    const data = await resp.json();
    if (data.success && data.categories) {
      data.categories.forEach((cat) => {
        const opt = document.createElement("option");
        opt.value = cat.name;
        opt.textContent = `📁 ${cat.name}`;
        sel.appendChild(opt);
      });
    }
  } catch (e) {
    console.error("[Voice] Load categories error:", e);
  }
}

async function loadConfig() {
  try {
    const resp = await fetch(`/api/voice/${guildId}/config`);
    const data = await resp.json();
    if (data.success) {
      config = data.config;
      applyConfig();
    }
  } catch (e) {
    console.error("[Voice] Load config error:", e);
  }
}

function applyConfig() {
  if (config.room_name_template) {
    document.getElementById("room-name-template").value = config.room_name_template;
  }
  if (config.category_name) {
    const sel = document.getElementById("category-name");
    if (sel && [...sel.options].some(o => o.value === config.category_name)) {
      sel.value = config.category_name;
    }
  }
}

function setupEventListeners() {
  document.getElementById("room-name-template")?.addEventListener("change", function (e) {
    config.room_name_template = e.target.value;
  });
  document.getElementById("category-name")?.addEventListener("change", function (e) {
    config.category_name = e.target.value;
  });
  document.getElementById("save-btn")?.addEventListener("click", saveConfig);
}

async function saveConfig() {
  const btn = document.getElementById("save-btn");
  btn.disabled = true;
  btn.textContent = "⏳ Menyimpan...";
  try {
    const resp = await fetch(`/api/voice/${guildId}/save`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(config),
    });
    const result = await resp.json();
    if (result.success) {
      showAlert("✅ Pengaturan voice berhasil disimpan!", "success");
    } else {
      showAlert(result.message || "Gagal menyimpan.", "error");
    }
  } catch (e) {
    showAlert("Error: " + e.message, "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "💾 Simpan Pengaturan";
  }
}

function escapeHtml(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

function showAlert(message, type, duration) {
  let container = document.getElementById("toast-container");
  if (!container) {
    container = document.createElement("div");
    container.id = "toast-container";
    container.className = "toast-container";
    document.body.appendChild(container);
  }
  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `<span class="toast-icon">${type === "success" ? "✅" : type === "error" ? "❌" : "ℹ️"}</span><span class="toast-message">${escapeHtml(message)}</span>`;
  container.appendChild(toast);
  requestAnimationFrame(() => toast.classList.add("show"));
  toast.addEventListener("click", () => { toast.classList.add("toast-out"); setTimeout(() => toast.remove(), 250); });
  const ms = duration || 3000;
  setTimeout(() => { toast.classList.add("toast-out"); setTimeout(() => toast.remove(), 250); }, ms);
}
