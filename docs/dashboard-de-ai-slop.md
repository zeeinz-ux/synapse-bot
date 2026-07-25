# Dashboard — De-AI-Slop Plan

Menghilangkan tampilan AI-generic di dashboard, menyelaraskan dengan brand identity landing page (cyan `#00d4ff` + violet `#7c3aed`).

---

## Ringkasan Masalah

| # | Masalah | Saat Ini | Target |
|---|---------|----------|--------|
| 1 | **Warna accent** | `#5865f2` (Discord blurple) di SEMUA CSS dashboard | `#00d4ff` (cyan) + `#7c3aed` (violet) — sama kayak landing |
| 2 | **Icon** | Emoji di sidebar, nav labels, cards, buttons (`🌐` `📊` `👋` `🧠` dll) | Lucide SVG icons, konsisten dengan landing |
| 3 | **Sidebar active state** | `rgba(88, 101, 242, 0.15)` + blurple bar | Cyan glow + violet accent |
| 4 | **Btn-primary** | Solid blurple `#5865f2` | Gradient cyan→violet (sama kayak landing `.btn-primary`) |
| 5 | **Dashboard home hero** | Gradient blurple→pink `#5865f2 → #eb459e` | Gradient cyan→violet `#00d4ff → #7c3aed` |
| 6 | **Bot avatar** | Background blurple solid | Background gradient cyan→violet |
| 7 | **Tier badges (AI Chat)** | Blurple/yellow/green borders | Cyan/violet/warm sesuai brand |
| 8 | **CSS variable naming** | Campuran `--bg-primary`, `--bg-deep`, `--bg-surface` | Rapikan, satu sistem |

---

## Strategy per Phase

Setiap phase mencakup **HTML + CSS** untuk halaman tertentu. Urutan: dari yang paling sering dilihat (base/sidebar) ke halaman spesifik.

---

## Phase 0 — Translation Cleanup

**Goal:** Hapus emoji dari translation strings — emoji akan diganti dengan Lucide icon di HTML.

**Masalah:** 9 keys di `en.json` dan `id.json` punya emoji embedded di value string-nya. Sidebar render section header pake `{{ "base.section.general" | t }}` yang nilainya `"📊 General"`. Jadi meskipun HTML icon diganti Lucide, teksnya masih bawa emoji.

### Files & Perubahan

| File | Key | Before | After |
|------|-----|--------|-------|
| `backend/web/language/en.json` | `base.select_server` | `"🌐 Select Server"` | `"Select Server"` |
| `backend/web/language/id.json` | `base.select_server` | `"🌐 Pilih Server"` | `"Pilih Server"` |
| Both | `base.section.general` | `"📊 General"` | `"General"` |
| Both | `base.section.announcements` | `"📢 Announcements"` | `"Announcements"` |
| Both | `base.section.boost` | `"💎 Boost Tracker"` | `"Boost Tracker"` |
| Both | `base.section.donation` | `"💰 Donation Tracker"` | `"Donation Tracker"` |
| Both | `base.section.ai` | `"🤖 AI & Automation"` | `"AI & Automation"` |
| Both | `base.section.moderation` | `"🛡️ Moderation"` | `"Moderation"` |
| Both | `base.section.content` | `"📝 Content"` | `"Content"` |
| Both | `base.section.settings` | `"⚙️ Settings"` | `"Settings"` |

**Effort:** ✅ Rendah — 2 file, 9 key per file, ganti value aja.

**Relasi ke Phase 2:** Setelah emoji dihapus dari translations, sidebar section header tinggal pake Lucide icon dari HTML, bukan dari teks.

---

## Phase 1 — Foundation (CSS Variables)

**Goal:** Semua CSS variable accent diseragamkan dulu sebelum touch file lainnya.

### Files

| File | Yang Diubah |
|------|-------------|
| `frontend/static/css/dashboard.css` | `--accent-primary: #5865f2` → `#00d4ff`; `--accent-primary-hover: #4752c4` → `#7c3aed`; gradient hero blurple→pink → cyan→violet |
| `frontend/static/css/sidebar.css` | `--accent: #5865f2` → `#00d4ff`; `--active-bg` → rgba cyan; `--active-bar` → cyan |
| `frontend/static/css/ai_chat.css` | `--accent-primary` → `#00d4ff`; `--accent-primary-hover` → `#7c3aed` |
| `frontend/static/css/auto_responders.css` | Sama — ganti accent ke cyan/violet |
| `frontend/static/css/anti_spam.css` | Sama |
| `frontend/static/css/anti_nuke.css` | Sama |
| `frontend/static/css/actions.css` | Sama |
| `frontend/static/css/message_builder.css` | Sama |
| `frontend/static/css/settings.css` | Sama |
| `frontend/static/css/voice.css` | Sama |
| `frontend/static/css/boost_settings.css` | Sama |
| `frontend/static/css/boost_announce.css` | Sama |
| `frontend/static/css/donation_settings.css` | Sama |
| `frontend/static/css/welcome_settings.css` | Sama |
| `frontend/static/css/leave_settings.css` | Sama |
| `frontend/static/css/ban_settings.css` | Sama |
| `frontend/static/css/templates.css` | Sama |
| `frontend/static/css/photobox.css` | Sama |

**Effort:** Rendah — 17 file, tiap file cuma ganti beberapa baris CSS variable. Bisa batch pake replace-all.

**Hati-hati — hardcoded blurple (bukan CSS variable) perlu diganti manual:**
- `auto_responders.css:149` — `background: #5865f2;`
- `auto_responders.css:277` — toast info `rgba(88,101,242,0.5)` + `#5865f2`
- `anti_spam.css:114` — `color: #5865f2;`
- `dashboard.css:247` — toast info `rgba(88,101,242,0.5)` + `#5865f2`
- `welcome_settings.css:3` — `--welcome-accent: #5865f2` (rename variable)
- `welcome_settings.css:487` — `background: #4752c4;`
- `message_builder.html:50` — color picker default `value="#5865f2"`
- `message_builder.js:79,102,193,194,213,214,409` — default embed color `'5865f2'` (7×)
- `templates.js:38,54,62,83` — default template color `'5865f2'` (4×)

**Variable `--accent-pink: #eb459e`** di `dashboard.css:29` — dipake di gradient hero. Ganti gradientnya langsung, variablenya bisa dihapus atau dialihkan ke `--accent-warm`.

**Verifikasi:** Cari `#5865f2` dan `#4752c4` di semua file — harusnya gak ada sisa.

---

## Phase 2 — Base Layout (Sidebar + Topbar)

**Goal:** Sidebar dan layout dasar mencerminkan brand. Ini yang paling sering dilihat user.

### Files

| File | Yang Diubah |
|------|-------------|
| `frontend/pages/base.html` | Sidebar nav icons emoji → Lucide SVG; search icon → Lucide; logo brand refinement |
| `frontend/static/css/sidebar.css` | Active state blurple → cyan glow; bot avatar bg → gradient; search bar style; nav item hover color |

### Detail Perubahan `base.html`

**Sidebar Nav Icons (emoji → Lucide):**

| Section | Emoji | Lucide |
|---------|-------|--------|
| Dashboard | 🏠 | `layout-dashboard` |
| Join (Welcome) | 👋 | `hand` |
| Leave | 👋 | `door-open` |
| Ban | 🚫 | `ban` |
| Boost | 💎 | `gem` |
| Boost History | 📊 | `bar-chart-3` |
| Boost Stats | 📈 | `trending-up` |
| Donation | 💰 | `wallet` |
| Donation History | 💳 | `credit-card` |
| Donation Stats | 📈 | `trending-up` |
| AI Chat | 🧠 | `brain` |
| Auto Responders | 🤖 | `bot` |
| RAG Knowledge | 📚 | `library` |
| Voice Config | 🎛️ | `sliders` |
| Actions | ⚡ | `zap` |
| Anti Spam | 🛡️ | `shield` |
| Anti Nuke | 🚨 | `shield-alert` |
| Message Builder | ✏️ | `pencil` |
| Templates | 📄 | `files` |
| Settings | ⚙️ | `settings` |

**Effort:** Sedang — update sidebar icons + CSS active state.

---

## Phase 3 — Dashboard Home

**Goal:** Halaman pertama setelah login — harus kasih kesan brand yang kuat.

### Files

| File | Yang Diubah |
|------|-------------|
| `frontend/pages/dashboard/dashboard.html` | Hero gradient, stat card icons → Lucide, server grid style |
| `frontend/static/css/dashboard.css` | Color sync, icon style, hero layout refinement |

### Detail

**Gradient hero:**
```css
/* sebelum: blurple → pink */
background: linear-gradient(135deg, var(--accent-primary), var(--accent-pink));
/* sesudah: cyan → violet (sama kayak landing) */
background: linear-gradient(135deg, #00d4ff, #7c3aed);
```

**Stat card icons:**
- 📊 Servers → `server`
- 👥 Members → `users`

**Server card hover:** blurple → cyan

**Effort:** Rendah — 2 file.

---

## Phase 4 — AI Chat Settings

**Goal:** Halaman settings AI — tier stack diagram, form controls, toggle.

### Files

| File | Yang Diubah |
|------|-------------|
| `frontend/pages/dashboard/ai_chat.html` | Emoji → Lucide; page header icon; card icons; personality emoji (tetap); tier icons |
| `frontend/static/css/ai_chat.css` | Accent color toggle; btn-primary; tier badge borders |

### Detail

**Emoji → Lucide (AI Chat):**

| Lokasi | Emoji | Lucide |
|--------|-------|--------|
| Page header | 🧠 | `brain` |
| Card Status | ⚡ | `zap` |
| Card Personality | 🎭 | `theater` |
| Personality options | 😊 🧐 😤 😏 🦉 | **(tetap emoji)** |
| Save | 💾 | `save` |
| Card History | 📜 | `scroll-text` |
| Card Info | 📊 | `info` |

**Tier badge colors:**

| Tier | Sebelum | Sesudah |
|------|---------|---------|
| Tier 1 (Gemini) | Blurple `#5865f2` | Cyan `#00d4ff` |
| Tier 2 (Groq) | Yellow `#f0b232` | Warm `#f59e0b` |
| Tier 3 (Mistral) | Green `#3ba55d` | Violet `#7c3aed` |
| Tier 4 (Cohere) | Purple `#a855f7` | Cyan-violet mix |

**Effort:** Sedang.

---

## Phase 5 — Settings Pages (6 halaman)

**Goal:** Auto Responders, Anti Spam, Anti Nuke, Actions, Settings, Voice.

### Files

| File | Yang Diubah |
|------|-------------|
| `frontend/pages/dashboard/auto_responders.html` | Emoji → Lucide |
| `frontend/pages/dashboard/anti_spam.html` | Emoji → Lucide |
| `frontend/pages/dashboard/anti_nuke.html` | Emoji → Lucide |
| `frontend/pages/dashboard/actions.html` | Emoji → Lucide |
| `frontend/pages/dashboard/settings.html` | Emoji → Lucide |
| `frontend/pages/dashboard/voice.html` | Emoji → Lucide |
| `frontend/pages/dashboard/rag.html` | Emoji → Lucide |

**Effort:** Rendah — accent udah beres di Phase 1, tinggal icon.

---

## Phase 6 — Content + Announcement Pages (~9 halaman)

**Goal:** Message Builder, Templates, Welcome/Leave/Ban/Boost announce, Donation.

### Files

| File | Yang Diubah |
|------|-------------|
| `frontend/pages/dashboard/message_builder.html` | Emoji → Lucide |
| `frontend/static/js/message_builder.js` | Default embed color `#5865f2` → `#00d4ff` (7×) |
| `frontend/pages/dashboard/templates.html` | Emoji → Lucide |
| `frontend/static/js/templates.js` | Default template color `#5865f2` → `#00d4ff` (4×) |
| `frontend/pages/dashboard/welcome_settings.html` | Emoji → Lucide |
| `frontend/pages/dashboard/leave_settings.html` | Emoji → Lucide |
| `frontend/pages/dashboard/ban_settings.html` | Emoji → Lucide |
| `frontend/pages/dashboard/boost_announce.html` | Emoji → Lucide |
| `frontend/pages/dashboard/boost_settings.html` | Emoji → Lucide |
| `frontend/pages/dashboard/donation_settings.html` | Emoji → Lucide |

**Effort:** Sedang — banyak halaman, tapi pattern-nya sama.

---

## Ringkasan

| Phase | Fokus | Files | Effort |
|-------|-------|-------|--------|
| **0** | Translation — hapus emoji dari `en.json` & `id.json` | 2 file | ✅ Rendah |
| **1** | CSS variables — ganti `#5865f2` ke brand color | ~17 CSS | ✅ Rendah |
| **2** | Base layout — sidebar icons + active state | 2 file | ⚡ Sedang |
| **3** | Dashboard home — hero + stat cards | 2 file | ✅ Rendah |
| **4** | AI Chat settings — icons + tier colors | 2 file | ⚡ Sedang |
| **5** | 7 settings pages — emoji → Lucide | 7 file | ✅ Rendah |
| **6** | 8 content/announce pages — emoji → Lucide | 8 file | ⚡ Sedang |

**Rekomendasi eksekusi:** Phase 0 → 1 → 2 → 3 dulu. 4 phase pertama (0-3) udah cukup bikin dashboard keliatan beda dan nyambung sama landing. Setelah itu evaluasi apakah lanjut phase 4-6.

---

## Catatan Teknis

### Lucide CDN di Dashboard

Tambahin di `base.html` sebelum `</body>`:
```html
<script src="https://unpkg.com/lucide@latest"></script>
<script>lucide.createIcons()</script>
```

Cara pasang di Jinja2:
```html
<i data-lucide="zap" width="20" height="20"></i>
```

### CSS Variable Baru di `dashboard.css`

```css
--accent: #00d4ff;
--accent-hover: #00b8e0;
--accent-secondary: #7c3aed;
--gradient-main: linear-gradient(135deg, #00d4ff, #7c3aed);
```

### Cara Ganti Emoji ke Lucide

Emoji di HTML:
```html
<span class="nav-icon">🧠</span>
```

Jadi Lucide:
```html
<span class="nav-icon"><i data-lucide="brain" width="18" height="18"></i></span>
```

CSS untuk icon nav di `sidebar.css` — sesudah:
```css
.nav-icon {
  width: 20px;
  height: 20px;
  flex-shrink: 0;
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  justify-content: center;
}

.nav-item.active .nav-icon {
  color: var(--accent);
}
```
