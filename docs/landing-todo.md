# Landing Page — Yang Perlu Diubah

## 1. Blurple di CSS (navbar.css + footer.css) — 11 baris

Ganti semua `rgba(88, 101, 242` → `rgba(0, 212, 255` (cyan glow).

### navbar.css (7×)

| Baris | Sekarang | Jadi |
|-------|----------|------|
| 85 | `rgba(88,101,242,0.4)` (glow avatar) | `rgba(0,212,255,0.4)` |
| 118 | `rgba(88,101,242,0.3)` (glow invite) | `rgba(0,212,255,0.3)` |
| 124 | `rgba(88,101,242,0.5)` (glow invite hover) | `rgba(0,212,255,0.5)` |
| 151 | `rgba(88,101,242,0.1)` (btn-login hover bg) | `rgba(0,212,255,0.1)` |
| 286 | `rgba(88,101,242,0.1)` (lang-toggle hover bg) | `rgba(0,212,255,0.1)` |
| 343 | `rgba(88,101,242,0.12)` (lang-option active bg) | `rgba(0,212,255,0.12)` |
| 393 | `rgba(88,101,242,0.12)` (lang-option mobile active bg) | `rgba(0,212,255,0.12)` |

### footer.css (4×)

| Baris | Sekarang | Jadi |
|-------|----------|------|
| 86 | `rgba(88,101,242,0.1)` (btn hover bg) | `rgba(0,212,255,0.1)` |
| 91 | `rgba(88,101,242,0.3)` (btn-dashboard border) | `rgba(0,212,255,0.3)` |
| 105 | `rgba(88,101,242,0.3)` (btn-invite glow) | `rgba(0,212,255,0.3)` |
| 111 | `rgba(88,101,242,0.5)` (btn-invite hover glow) | `rgba(0,212,255,0.5)` |

---

## 2. 6 Item Pending (dari `landing-de-ai-slop.md`)

### 2.1 FAQ Minimal
- **Sekarang:** Glass accordion (`--glass-bg`)
- **Jadi:** Hapus glass bg, pake `border-bottom` aja antar item
- **File:** `frontend/static/css/landing.css` (cari `.faq-accordion`, `.faq-item`)

### 2.2 About Solid
- **Sekarang:** Glass card (`--glass-bg`)
- **Jadi:** Ganti `--glass-bg` ke `--sidebar-bg`
- **File:** `frontend/static/css/landing.css` (cari `.about` section)

### 2.3 Command Cards Solid
- **Sekarang:** Glass card
- **Jadi:** Ganti glass ke solid bg
- **File:** `frontend/static/css/landing.css` (cari `.commands-grid`, `.command-card`)

### 2.4 CTA Solid Gradient
- **Sekarang:** Glass card
- **Jadi:** Ganti glass ke gradient penuh (`--gradient-main`)
- **File:** `frontend/static/css/landing.css` (cari `.cta` section)

### 2.5 Tech Stack Badges
- **Sekarang:** Ada di About section
- **Jadi:** Restyle atau hapus
- **File:** `frontend/pages/index.html` & `frontend/static/css/landing.css`

### 2.6 Kurangi Scroll Reveal
- **Sekarang:** Semua element kena `data-reveal`
- **Jadi:** Hapus `data-reveal` dari element yang gak perlu
- **File:** `frontend/pages/index.html`
