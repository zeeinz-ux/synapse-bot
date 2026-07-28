# Theme Toggle — Dark/Light Mode

## Status: Planning

---

## Overview

Tambahkan dark/light mode toggle dengan 3 opsi: **System** (auto deteksi), **Dark**, **Light**. Star animation (`stars.js`) jadi warna-warni di light mode. Preference disimpan di `localStorage`.

---

## Architecture

```
User clicks toggle (☀️/🌙/🖥️)
    ↓
theme.js:
  1. Set localStorage['synapse_theme'] = 'system' | 'dark' | 'light'
  2. Evaluate: if 'system' → window.matchMedia('prefers-color-scheme: light')
  3. Set <html data-theme="dark" | "light">
    ↓
CSS:
  [data-theme="light"] {
    --bg-deep: #f5f5f7;
    --text-primary: #1a1a1e;
    ...semua light vars override...
  }
    ↓
stars.js:
  Baca data-theme dari <html>
  Kalo "light" → pake warna pelangi
  Kalo "dark" → pake warna original (putih/emas/violet)
```

### Script Loading Order

```
<head>
  1. theme.js (inline, blocking — biar gak flicker)
  2. CSS files (pakai var yang udah diset data-theme)
</head>
<body>
  3. stars.js (defer — baca data-theme dari html)
  4. navbar.js / sidebar.js (toggle button handler)
</body>
```

---

## Phase Breakdown (6 phases)

### Phase 1: `theme.js` + HTML data-theme (2 files)
**Tujuan**: Theme engine dasar — inject theme.js inline di `<head>`, set `data-theme` di `<html>`.

**Files:**
| File | Action |
|------|--------|
| `frontend/static/js/theme.js` | **NEW** — Logic: baca localStorage → preferensi, fallback ke system prefers-color-scheme, set data-theme, listen system change |
| `frontend/pages/landing.html` | Inline `<script>` di `<head>` yang load theme.js + set data-theme |
| `frontend/pages/base.html` | Inline `<script>` di `<head>` yang load theme.js + set data-theme |

**Deliverable**: Buka landing.html → `<html data-theme="dark">` sesuai system. Ganti system ke light → auto update.

---

### Phase 2: Light mode CSS — Dashboard (2 files)
**Tujuan**: Semua halaman dashboard (extends `base.html`) punya light mode.

**Files:**
| File | Action |
|------|--------|
| `frontend/static/css/dashboard.css` | Tambah blok `[data-theme="light"]` — override semua var (bg-deep, bg-surface, text, border, accent, dll) |
| `frontend/static/css/sidebar.css` | Tambah blok `[data-theme="light"]` — override sidebar-bg, sidebar-border, text, hover, search, dll |

**Deliverable**: Dashboard page (settings, ai-chat, dll) bisa light mode saat `<html data-theme="light">`.

---

### Phase 3: Light mode CSS — Landing (2 files)
**Tujuan**: Landing page + navbar + footer bisa light mode.

**Files:**
| File | Action |
|------|--------|
| `frontend/static/css/landing.css` | Tambah blok `[data-theme="light"]` — override body-bg, sidebar-bg, glass-bg, gradient, hero-glow, dll |
| `frontend/static/css/navbar.css` | Tambah blok `[data-theme="light"]` — override navbar bg, border, dropdown, mobile menu |

**Deliverable**: Landing page + navbar bisa light mode.

---

### Phase 4: Light mode CSS — Remaining pages (5+ files)
**Tujuan**: Semua halaman dashboard kecil juga punya light mode vars.

**Files:**
| File | Action |
|------|--------|
| `frontend/static/css/agent.css` | Tambah `[data-theme="light"]` |
| `frontend/static/css/ai_chat.css` | Tambah `[data-theme="light"]` |
| `frontend/static/css/anti_spam.css` | Tambah `[data-theme="light"]` |
| `frontend/static/css/auto_responders.css` | Tambah `[data-theme="light"]` |
| `frontend/static/css/donation_settings.css` | Tambah `[data-theme="light"]` |
| `frontend/static/css/welcome_settings.css` | Tambah `[data-theme="light"]` |
| `frontend/static/css/photobox.css` | Tambah `[data-theme="light"]` |
| `frontend/static/css/landing.css` (footer.css vars) | Cek kalo ada var tambahan |

**Deliverable**: Semua halaman di web bisa light mode konsisten.

---

### Phase 5: Toggle Button UI (3 files)
**Tujuan**: User bisa ganti mode via tombol. 3 state: System / Dark / Light.

**Files:**
| File | Action |
|------|--------|
| `frontend/pages/partials/navbar.html` | Tambah toggle button di `nav-actions` (sebelah lang switcher). Mobile: tambah di mobile menu section |
| `frontend/pages/base.html` | Tambah toggle button di `sidebar-footer` (sebelah version info) |
| `frontend/static/css/navbar.css` | Style untuk theme toggle button (icon, active state, hover) |
| `frontend/static/css/sidebar.css` | Style untuk theme toggle di sidebar footer |

**Toggle behavior:**
```
Click → cycle: System → Dark → Light → System → ...
Ikon:  🖥️ → 🌙 → ☀️ → 🖥️ → ...
Label: "System" → "Dark" → "Light" → "System" → ...
```

**Deliverable**: Toggle berfungsi di landing page (navbar) + dashboard (sidebar). Preference persist.

---

### Phase 6: Stars Warna-warni (1 file)
**Tujuan**: Pas light mode, stars jadi pelangi. Pas dark mode, tetap putih/emas/violet.

**File:**
| File | Action |
|------|--------|
| `frontend/static/js/stars.js` | Inject deteksi `document.documentElement.dataset.theme`. Kalo "light" → pake array warmColors rainbow (merah, jingga, kuning, hijau, biru, ungu). Kalo "dark" → tetap pake warm (gold/amber) + violet |

**Deliverable**: Refresh landing page → stars warna-warni di light mode, normal di dark mode.

---

## Files Summary

| # | File | Phase | Action |
|---|------|-------|--------|
| 1 | `frontend/static/js/theme.js` | P1 | **NEW** |
| 2 | `frontend/pages/landing.html` | P1 | Edit `<head>` |
| 3 | `frontend/pages/base.html` | P1 | Edit `<head>` + P5 sidebar toggle |
| 4 | `frontend/static/css/dashboard.css` | P2 | Edit +light vars |
| 5 | `frontend/static/css/sidebar.css` | P2 + P5 | Edit +light vars + toggle style |
| 6 | `frontend/static/css/landing.css` | P3 | Edit +light vars |
| 7 | `frontend/static/css/navbar.css` | P3 + P5 | Edit +light vars + toggle style |
| 8 | `frontend/static/css/agent.css` | P4 | Edit +light vars |
| 9 | `frontend/static/css/ai_chat.css` | P4 | Edit +light vars |
| 10 | `frontend/static/css/anti_spam.css` | P4 | Edit +light vars |
| 11 | `frontend/static/css/auto_responders.css` | P4 | Edit +light vars |
| 12 | `frontend/static/css/donation_settings.css` | P4 | Edit +light vars |
| 13 | `frontend/static/css/welcome_settings.css` | P4 | Edit +light vars |
| 14 | `frontend/static/css/photobox.css` | P4 | Edit +light vars |
| 15 | `frontend/pages/partials/navbar.html` | P5 | Edit +toggle button |
| 16 | `frontend/static/js/stars.js` | P6 | Edit +light mode colors |

**Total: 16 files (1 new, 15 edits) — 6 phases**

---

## Phase Execution Order

```
Phase 1:  theme.js + data-theme di HTML  ──→  (engine core)
     ↓
Phase 2:  Dashboard CSS light vars       ──→  (dashboard bisa light)
     ↓
Phase 3:  Landing CSS light vars         ──→  (landing bisa light)
     ↓
Phase 4:  Remaining CSS light vars       ──→  (semua halaman light)
     ↓
Phase 5:  Toggle button UI               ──→  (user bisa milih)
     ↓
Phase 6:  Stars warna-warni              ──→  (eye candy light mode)
```

Setiap phase bisa di-commit & push sendiri biar gak overload.

---

## Progress Tracking

| Phase | Description | Status | Files |
|-------|-------------|--------|-------|
| P1 | theme.js + HTML data-theme | ❌ Not started | 3 |
| P2 | Dashboard CSS light vars | ❌ Not started | 2 |
| P3 | Landing CSS light vars | ❌ Not started | 2 |
| P4 | Remaining CSS light vars | ❌ Not started | 7 |
| P5 | Toggle button UI | ❌ Not started | 4 |
| P6 | Stars warna-warni | ❌ Not started | 1 |
