const guildIdEl = document.getElementById("guild-id");
const guildId = guildIdEl ? guildIdEl.value : "";

let config = {
  enabled: false,
  ban_threshold: 3,
  kick_threshold: 3,
  channel_threshold: 3,
  role_threshold: 3,
  admin_threshold: 2,
  window_seconds: 10,
  lockdown_duration: 1800,
  whitelist_users: [],
  whitelist_roles: [],
  report_channel_id: "",
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
    console.error("[Anti Nuke] Load roles error:", e);
  }
}

async function loadChannels() {
  const sel = document.getElementById("report-channel");
  if (!sel) return;
  try {
    const resp = await fetch(`/api/guilds/${guildId}/channels`);
    const data = await resp.json();
    if (data.success && data.channels) {
      data.channels.sort((a, b) => a.name.localeCompare(b.name));
      data.channels.forEach((ch) => {
        const opt = document.createElement("option");
        opt.value = ch.id;
        opt.textContent = `# ${ch.name}`;
        sel.appendChild(opt);
      });
    }
  } catch (e) {
    console.error("[Anti Nuke] Load channels error:", e);
  }
}

async function loadConfig() {
  try {
    const resp = await fetch(`/api/anti-nuke/${guildId}/config`);
    const data = await resp.json();
    if (data.success) {
      config = data.config;
      applyConfig();
    }
  } catch (e) {
    console.error("[Anti Nuke] Load config error:", e);
  }
}

function applyConfig() {
  document.getElementById("global-toggle").checked = !!config.enabled;
  document.getElementById("ban-threshold").value = config.ban_threshold || 3;
  document.getElementById("kick-threshold").value = config.kick_threshold || 3;
  document.getElementById("channel-threshold").value = config.channel_threshold || 3;
  document.getElementById("role-threshold").value = config.role_threshold || 3;
  document.getElementById("admin-threshold").value = config.admin_threshold || 2;
  document.getElementById("window-seconds").value = config.window_seconds || 10;
  document.getElementById("lockdown-duration").value = (config.lockdown_duration || 1800) / 60;

  const chSel = document.getElementById("report-channel");
  if (chSel && config.report_channel_id) chSel.value = config.report_channel_id;

  renderUserTags(config.whitelist_users || []);
  renderRoleTags(config.whitelist_roles || []);
}

function setupEventListeners() {
  const globalToggle = document.getElementById("global-toggle");
  if (globalToggle) {
    globalToggle.addEventListener("change", function (e) {
      config.enabled = e.target.checked;
    });
  }

  const thresholdMap = {
    "ban-threshold": "ban_threshold",
    "kick-threshold": "kick_threshold",
    "channel-threshold": "channel_threshold",
    "role-threshold": "role_threshold",
    "admin-threshold": "admin_threshold",
  };
  Object.entries(thresholdMap).forEach(([elId, key]) => {
    const el = document.getElementById(elId);
    if (el) {
      el.addEventListener("change", function (e) {
        config[key] = parseInt(e.target.value) || 3;
      });
    }
  });

  document.getElementById("window-seconds")?.addEventListener("change", function (e) {
    config.window_seconds = parseInt(e.target.value) || 10;
  });
  document.getElementById("lockdown-duration")?.addEventListener("change", function (e) {
    config.lockdown_duration = (parseInt(e.target.value) || 30) * 60;
  });

  document.getElementById("report-channel")?.addEventListener("change", function (e) {
    config.report_channel_id = e.target.value;
  });

  document.getElementById("wl-user-add")?.addEventListener("click", addUser);
  document.getElementById("wl-user-input")?.addEventListener("keydown", function (e) {
    if (e.key === "Enter") { e.preventDefault(); addUser(); }
  });

  document.getElementById("wl-role-add")?.addEventListener("click", addRole);

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

async function saveConfig() {
  const btn = document.getElementById("save-btn");
  btn.disabled = true;
  btn.textContent = "⏳ Menyimpan...";

  try {
    const payload = {
      ...config,
      whitelist_users: config.whitelist_users || [],
      whitelist_roles: config.whitelist_roles || [],
    };

    const resp = await fetch(`/api/anti-nuke/${guildId}/save`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const result = await resp.json();

    if (result.success) {
      showAlert("✅ Pengaturan Anti-Nuke berhasil disimpan!", "success");
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
  const ms = duration || 3000;
  setTimeout(() => {
    toast.classList.add("toast-out");
    setTimeout(() => toast.remove(), 250);
  }, ms);
}