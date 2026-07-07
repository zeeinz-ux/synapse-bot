const guildIdEl = document.getElementById("guild-id");
const guildId = guildIdEl ? guildIdEl.value : "";

let config = {
  enabled: true,
  filter_heuristic: true,
  filter_ai: true,
  filter_new_account: true,
  filter_image: true,
  whitelist_users: [],
  whitelist_roles: [],
  report_channel: "",
  custom_keywords: [],
  raid_protection: false,
  raid_threshold: 10,
  raid_window: 300,
  raid_action: "kick",
};

document.addEventListener("DOMContentLoaded", function () {
  if (!guildId) return;
  loadRoles();
  loadChannels();
  loadConfig();
  setupEventListeners();
});

async function loadRoles() {
  const select = document.getElementById("wl-role-select");
  if (!select) return;
  try {
    const resp = await fetch(`/api/actions/${guildId}/roles`);
    const data = await resp.json();
    if (data.success && data.roles) {
      data.roles.forEach((r) => {
        const opt = document.createElement("option");
        opt.value = r.id;
        opt.textContent = `${r.name} (${r.id})`;
        select.appendChild(opt);
      });
    }
  } catch (e) {
    console.error("[Anti Spam] Load roles error:", e);
  }
}

async function loadChannels() {
  const sel = document.getElementById("report-channel");
  if (!sel) return;
  try {
    const resp = await fetch(`/api/guilds/${guildId}/channels`);
    const data = await resp.json();
    if (data.success && data.channels) {
      data.channels.sort(function(a,b){ return a.name.localeCompare(b.name); });
      data.channels.forEach(function(ch){
        const opt = document.createElement("option");
        opt.value = ch.id;
        opt.textContent = `# ${ch.name}`;
        sel.appendChild(opt);
      });
    }
  } catch (e) {
    console.error("[Anti Spam] Load channels error:", e);
  }
}

async function loadConfig() {
  try {
    const resp = await fetch(`/api/anti-spam/${guildId}/config`);
    const data = await resp.json();
    if (data.success) {
      config = data.config;
      applyConfig();
    }
  } catch (e) {
    console.error("[Anti Spam] Load config error:", e);
  }
}

function applyConfig() {
  document.getElementById("global-toggle").checked = !!config.enabled;
  document.getElementById("filter-heuristic").checked = config.filter_heuristic !== false;
  document.getElementById("filter-ai").checked = config.filter_ai !== false;
  document.getElementById("filter-new-account").checked = config.filter_new_account !== false;
  document.getElementById("filter-image").checked = config.filter_image !== false;

  const chSel = document.getElementById("report-channel");
  if (chSel && config.report_channel) chSel.value = config.report_channel;

  document.getElementById("raid-toggle").checked = !!config.raid_protection;
  document.getElementById("raid-threshold").value = config.raid_threshold || 10;
  document.getElementById("raid-window").value = (config.raid_window || 300) / 60;
  document.getElementById("raid-action").value = config.raid_action || "kick";
  toggleRaidConfig(!!config.raid_protection);

  renderUserTags(config.whitelist_users || []);
  renderRoleTags(config.whitelist_roles || []);
  renderKeywordTags(config.custom_keywords || []);
}

function setupEventListeners() {
  const globalToggle = document.getElementById("global-toggle");
  if (globalToggle) {
    globalToggle.addEventListener("change", function (e) {
      config.enabled = e.target.checked;
      document.querySelectorAll(".filter-item input[type=checkbox]").forEach((cb) => {
        cb.disabled = !e.target.checked;
      });
    });
  }

  // Filter toggles
  const filterMap = {
    "filter-heuristic": "filter_heuristic",
    "filter-ai": "filter_ai",
    "filter-new-account": "filter_new_account",
    "filter-image": "filter_image",
  };
  Object.entries(filterMap).forEach(([elId, key]) => {
    const el = document.getElementById(elId);
    if (el) {
      el.addEventListener("change", function (e) {
        config[key] = e.target.checked;
      });
    }
  });

  // Report channel
  document.getElementById("report-channel")?.addEventListener("change", function (e) {
    config.report_channel = e.target.value;
  });

  // Add user
  document.getElementById("wl-user-add")?.addEventListener("click", addUser);
  document.getElementById("wl-user-input")?.addEventListener("keydown", function (e) {
    if (e.key === "Enter") { e.preventDefault(); addUser(); }
  });

  // Add role
  document.getElementById("wl-role-add")?.addEventListener("click", addRole);

  // Raid toggle
  document.getElementById("raid-toggle")?.addEventListener("change", function (e) {
    config.raid_protection = e.target.checked;
    toggleRaidConfig(e.target.checked);
  });
  document.getElementById("raid-threshold")?.addEventListener("change", function (e) {
    config.raid_threshold = parseInt(e.target.value) || 10;
  });
  document.getElementById("raid-window")?.addEventListener("change", function (e) {
    config.raid_window = (parseInt(e.target.value) || 5) * 60;
  });
  document.getElementById("raid-action")?.addEventListener("change", function (e) {
    config.raid_action = e.target.value;
  });

  // Keywords
  document.getElementById("kw-add")?.addEventListener("click", addKeyword);
  document.getElementById("kw-input")?.addEventListener("keydown", function (e) {
    if (e.key === "Enter") { e.preventDefault(); addKeyword(); }
  });

  // Save
  document.getElementById("save-btn")?.addEventListener("click", saveConfig);
}

function addUser() {
  const input = document.getElementById("wl-user-input");
  const id = input.value.trim();
  if (!id) return;
  if (!/^\d{17,19}$/.test(id)) {
    showAlert("User ID tidak valid. Masukkan ID Discord (17-19 digit angka).", "error");
    return;
  }
  if ((config.whitelist_users || []).includes(id)) {
    showAlert("User ID sudah ada di whitelist.", "warning");
    return;
  }
  config.whitelist_users = [...(config.whitelist_users || []), id];
  renderUserTags(config.whitelist_users);
  input.value = "";
  input.focus();
  showAlert("User ditambahkan ke whitelist. Jangan lupa simpan!", "success", 2000);
}

function addRole() {
  const select = document.getElementById("wl-role-select");
  const id = select.value;
  if (!id) return;
  if ((config.whitelist_roles || []).includes(id)) {
    showAlert("Role sudah ada di whitelist.", "warning");
    return;
  }
  config.whitelist_roles = [...(config.whitelist_roles || []), id];
  renderRoleTags(config.whitelist_roles);
  select.value = "";
  showAlert("Role ditambahkan ke whitelist. Jangan lupa simpan!", "success", 2000);
}

function removeUser(id) {
  config.whitelist_users = (config.whitelist_users || []).filter((u) => u !== id);
  renderUserTags(config.whitelist_users);
}

function removeRole(id) {
  config.whitelist_roles = (config.whitelist_roles || []).filter((r) => r !== id);
  renderRoleTags(config.whitelist_roles);
}

function renderUserTags(users) {
  const container = document.getElementById("wl-user-list");
  if (!container) return;
  if (!users || users.length === 0) {
    container.innerHTML = `<span class="empty-tag">Belum ada user di whitelist.</span>`;
    return;
  }
  container.innerHTML = users
    .map(
      (id) =>
        `<span class="tag"><span>${escapeHtml(id)}</span><button class="tag-remove" data-id="${escapeHtml(id)}" data-type="user">✕</button></span>`,
    )
    .join("");
  container.querySelectorAll(".tag-remove[data-type='user']").forEach((btn) => {
    btn.addEventListener("click", function () {
      removeUser(this.dataset.id);
    });
  });
}

function renderRoleTags(roles) {
  const container = document.getElementById("wl-role-list");
  if (!container) return;
  if (!roles || roles.length === 0) {
    container.innerHTML = `<span class="empty-tag">Belum ada role di whitelist.</span>`;
    return;
  }
  // Get role names from select options
  const roleMap = {};
  document.querySelectorAll("#wl-role-select option").forEach((opt) => {
    if (opt.value) roleMap[opt.value] = opt.textContent;
  });

  container.innerHTML = roles
    .map(
      (id) =>
        `<span class="tag"><span>${escapeHtml(roleMap[id] || id)}</span><button class="tag-remove" data-id="${escapeHtml(id)}" data-type="role">✕</button></span>`,
    )
    .join("");
  container.querySelectorAll(".tag-remove[data-type='role']").forEach((btn) => {
    btn.addEventListener("click", function () {
      removeRole(this.dataset.id);
    });
  });
}

function toggleRaidConfig(show) {
  const el = document.getElementById("raid-config");
  if (el) el.style.display = show ? "block" : "none";
}

function addKeyword() {
  const input = document.getElementById("kw-input");
  const kw = input.value.trim().toLowerCase();
  if (!kw) return;
  if (kw.length < 2) { showAlert("Keyword minimal 2 karakter.", "warning"); return; }
  if ((config.custom_keywords || []).includes(kw)) {
    showAlert("Keyword sudah ada.", "warning");
    return;
  }
  config.custom_keywords = [...(config.custom_keywords || []), kw];
  renderKeywordTags(config.custom_keywords);
  input.value = "";
  input.focus();
}

function removeKeyword(kw) {
  config.custom_keywords = (config.custom_keywords || []).filter((k) => k !== kw);
  renderKeywordTags(config.custom_keywords);
}

function renderKeywordTags(keywords) {
  const container = document.getElementById("kw-list");
  if (!container) return;
  if (!keywords || keywords.length === 0) {
    container.innerHTML = `<span class="empty-tag">Belum ada keyword custom.</span>`;
    return;
  }
  container.innerHTML = keywords
    .map(
      (kw) =>
        `<span class="tag"><span>${escapeHtml(kw)}</span><button class="tag-remove" data-kw="${escapeHtml(kw)}">✕</button></span>`,
    )
    .join("");
  container.querySelectorAll(".tag-remove").forEach((btn) => {
    btn.addEventListener("click", function () {
      removeKeyword(this.dataset.kw);
    });
  });
}

async function saveConfig() {
  const btn = document.getElementById("save-btn");
  btn.disabled = true;
  btn.textContent = "⏳ Menyimpan...";

  try {
    const payload = {
      ...config,
      whitelist_users: config.whitelist_users || [],
      whitelist_roles: config.whitelist_roles || [],
      custom_keywords: config.custom_keywords || [],
      raid_threshold: parseInt(config.raid_threshold) || 10,
      raid_window: parseInt(config.raid_window) || 300,
    };

    const resp = await fetch(`/api/anti-spam/${guildId}/save`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const result = await resp.json();

    if (result.success) {
      showAlert("✅ Pengaturan anti spam berhasil disimpan!", "success");
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
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
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
  toast.innerHTML = `<span class="toast-icon">${type === "success" ? "✅" : type === "error" ? "❌" : type === "warning" ? "⚠️" : "ℹ️"}</span><span class="toast-message">${escapeHtml(message)}</span>`;
  container.appendChild(toast);
  requestAnimationFrame(() => toast.classList.add("show"));
  toast.addEventListener("click", () => {
    toast.classList.add("toast-out");
    setTimeout(() => toast.remove(), 250);
  });
  if (duration === undefined || duration > 0) {
    const ms = duration || 3000;
    setTimeout(() => {
      toast.classList.add("toast-out");
      setTimeout(() => toast.remove(), 250);
    }, ms);
  }
}
