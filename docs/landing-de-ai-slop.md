# Landing Page — De-AI-Slop Plan

## Daftar Isi

1. [Ringkasan Perubahan](#1-ringkasan-perubahan)
2. [Warna — Alternatif Palette](#2-warna--alternatif-palette)
3. [Background — Starfield](#3-background--starfield)
4. [Emoji → Icon Library](#4-emoji--icon-library)
5. [Hero Section — Breakdown](#5-hero-section)
6. [Features Section — Breakdown](#6-features-section)
7. [How It Works Section — Breakdown](#7-how-it-works-section)
8. [CTA Section — Breakdown](#8-cta-section)
9. [FAQ Section — Breakdown](#9-faq-section)
10. [Commands Section — Breakdown](#10-commands-section)
11. [About Section — Breakdown](#11-about-section)
12. [Navbar & Footer — Breakdown](#12-navbar--footer)
13. [Flow Keseluruhan](#13-flow-keseluruhan)

---

## 1. Ringkasan Perubahan

| #   | Item                                           | AI Slop? | Usulan                                                        |
| --- | ---------------------------------------------- | -------- | ------------------------------------------------------------- |
| 1   | Sakura falling petals                          | **🔥**   | Ganti → Starfield (bintang + shooting star canvas)            |
| 2   | Emoji icons di semua section                   | **🔥**   | Ganti pake SVG icon library (Lucide atau Font Awesome)        |
| 3   | Hero badge "Bot Aktif & Siap Melayani"         | **🔥**   | Hapus badge, ganti cara lain                                  |
| 4   | Gradient biru→ungu (`--gradient-main`)         | **🔥**   | Ganti palette ke warna yang lebih personal & gak khas Discord |
| 5   | Section pattern seragam (label→title→subtitle) | **🔥**   | Variasi layout tiap section biar gak template                 |
| 6   | Glassmorphism dipake di **SEMUA** komponen     | **🔥**   | Kurangi, beberapa section pake style berbeda                  |
| 7   | Gradient text di title & stats                 | 🟡       | Hapus, pake solid color                                       |
| 8   | Em dash `—` fallback                           | 🟡       | Ganti `-` doang atau angka 0                                  |
| 9   | "How It Works 1-2-3"                           | 🟡       | Ubah format, gak perlu numbering                              |
| 10  | Tech stack badges                              | 🟡       | Bisa dipertahankan tapi di-styling ulang                      |
| 11  | Scroll reveal animation (`data-reveal`) di semua section | 🟡 | Kurangi intensitasnya, jangan semua element kena reveal |
| 12  | `--hero-glow-a/b` masih Discord blurple+pink   | 🟡       | Ikut ganti palette warna                                      |
| 13  | Footer copyright generik                       | 🟢       | Tambah personal touch                                         |

---

## 2. Warna — Alternatif Palette

### Saat ini (AI slop)

```css
--accent: #5865f2; /* Discord blurple */
--accent-pink: #eb459e; /* Discord pink */
--accent-green: #3ba55d; /* Discord green */
--gradient: #5865f2 → #eb459e /* biru → ungu → pink = template banget */;
```

### Opsi A — Cyber / Neon (personal, gak khas Discord)

```css
--accent: #00d4ff; /* cyan terang */
--accent-secondary: #7c3aed; /* ungu violet */
--accent-warm: #f59e0b; /* amber */
--gradient-main: linear-gradient(135deg, #00d4ff, #7c3aed);
--gradient-text: linear-gradient(90deg, #00d4ff, #7c3aed);
--hero-glow-a: rgba(0, 212, 255, 0.15);
--hero-glow-b: rgba(124, 58, 237, 0.1);
```

| Warna            | Kesan                                |
| ---------------- | ------------------------------------ |
| Cyan `#00d4ff`   | Teknologi, modern, beda dari Discord |
| Violet `#7c3aed` | Kedalaman, kreatif                   |
| Amber `#f59e0b`  | Hangat, aksen                        |

### Opsi B — Ember / Warm (beda dari template dark mode biasa)

```css
--accent: #f97316; /* orange */
--accent-secondary: #dc2626; /* red */
--accent-warm: #fbbf24; /* kuning */
--gradient-main: linear-gradient(135deg, #f97316, #dc2626);
--gradient-text: linear-gradient(90deg, #f97316, #dc2626);
--hero-glow-a: rgba(249, 115, 22, 0.15);
--hero-glow-b: rgba(220, 38, 38, 0.08);
```

| Warna            | Kesan             |
| ---------------- | ----------------- |
| Orange `#f97316` | Energik, friendly |
| Red `#dc2626`    | Bold, semangat    |
| Kuning `#fbbf24` | Ceria, hangat     |

### Opsi C — Minimalist / Monokrom (paling anti-template)

```css
--accent: #e2e8f0; /* putih kebiruan */
--accent-secondary: #94a3b8; /* gray */
--accent-warm: #f8fafc; /* near white */
--gradient-main: linear-gradient(135deg, #e2e8f0, #94a3b8);
--gradient-text: linear-gradient(90deg, #e2e8f0, #94a3b8);
--hero-glow-a: rgba(255, 255, 255, 0.04);
--hero-glow-b: rgba(255, 255, 255, 0.02);
```

| Warna           | Kesan                 |
| --------------- | --------------------- |
| Putih `#e2e8f0` | Clean, profesional    |
| Gray `#94a3b8`  | Tenang, sophisticated |
| Transparan glow | Subtle, elegan        |

**Catatan**: `--hero-glow-a/b`, `--glass-border`, dan `--gradient-main/text` semua harus ikut berubah sesuai palette baru.

> **Saran**: Ambil Opsi A (cyan/violet) atau kustom campuran. Yang penting **bukan** `#5865f2` → `#eb459e`.

---

## 3. Background — Starfield (pengganti sakura)

### Saat ini

```
  ❀ sakura petals pink jatuh (120 elemen DOM, animasi JS)
```

### Usulan

```
  ✦ bintang kecil 200 titik, kelap-kelip perlahan
  🌠 shooting star kadang lewat (tiap ~4-12 detik)
  canvas-based, gak pakai DOM element
```

File baru: `frontend/static/js/stars.js`

Yang dihapus dari `landing.html`:
- `<link rel="stylesheet" href="css/sakura.css" />`
- `<div id="sakuraContainer" class="sakura-container"></div>`
- `<script src="js/sakura.js"></script>`

File yang didelete/arsip:
- `frontend/static/js/sakura.js`
- `frontend/static/css/sakura.css`

---

## 4. Emoji → Icon Library

### Masalah

Emoji 🤖👋📊💸⚡🎯🔐 di landing page adalah **salah satu tanda AI slop paling kuat** karena:

1. Emoji keliatan murahan & gak profesional di web (beda sama di Discord)
2. Semua AI template pake emoji karena gak perlu desain icon
3. Warna & style emoji gak konsisten antar platform/browser
4. Gak bisa di-custom (size, color, stroke weight)

### Usulan

Pake SVG icon library. Rekomendasi:

| Library                      | Kenapa                                                                        |
| ---------------------------- | ----------------------------------------------------------------------------- |
| **Lucide** (`lucide-static`) | Ringan, stroke-based, gampang di-custom warna & ukuran, cocok buat dark theme |
| **Heroicons**                | Dari Tailwind, solid & outline variant                                        |
| **Phosphor Icons**           | Banyak varian (bold/duotone/light), cocok buat efek gradient                  |

> Saran: **Lucide** — paling gampang diintegrasi, tinggal copy SVG langsung atau pake CDN.

### Mapping Emoji → Icon

| Lokasi                   | Emoji skrg     | Icon Lucide usulan                                      |
| ------------------------ | -------------- | ------------------------------------------------------- |
| Hero: tombol Invite      | 🎯             | `target` atau `plus-circle`                             |
| Hero: tombol Dashboard   | 🔐             | `layout-dashboard`                                      |
| Features: AI Chat        | 🤖             | `bot` atau `sparkles`                                   |
| Features: Welcome        | 👋             | `hand-wave` atau `image`                                |
| Features: Dashboard      | 📊             | `bar-chart-3`                                           |
| Features: Donation       | 💸             | `gift` atau `dollar-sign`                               |
| Features: Auto Responder | ⚡             | `zap` atau `webhook`                                    |
| Steps: Invite            | —              | `user-plus`                                             |
| Steps: Login             | —              | `log-in`                                                |
| Steps: Setup             | —              | `settings`                                              |
| Commands: AI Chat        | 🤖             | `bot`                                                   |
| Commands: Moderation     | 🛡️             | `shield`                                                |
| Commands: Utility        | ⚙️             | `wrench`                                                |
| CTA button               | 🎯             | `rocket` atau `sparkles`                                |
| Navbar mobile: menu      | 🏠 ❓ ⌨️ 👤 💬 | `home` `help-circle` `terminal` `user` `message-circle` |

### Cara integrasi

**Opsi A — Inline SVG** (paling ringan, gak perlu dependency):

```html
<svg
  width="20"
  height="20"
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  stroke-width="2"
>
  <path d="M12 2..." />
</svg>
```

Tinggal copy SVG path dari lucide.dev/icons/ lalu tempel.

**Opsi B — CDN Lucide**:

```html
<script src="https://unpkg.com/lucide@latest"></script>
```

Trus pake `<i data-lucide="bot" class="icon"></i>` + `lucide.createIcons()`.

> Saran: **Opsi A** biar gak dependen ke internet / CDN. File SVG-nya bisa disimpen di `frontend/static/icons/` atau langsung inline di HTML.

### Efek setelah ganti

```
Sebelum:  🤖 AI Chat Canggih
Sesudah:  (icon bot SVG) AI Chat Canggih
```

- Icon bisa dikasih `stroke: var(--accent)` biar warnanya konsisten sama theme
- Bisa dikasih `stroke-width: 1.5` atau `2` sesuai selera
- Ukuran konsisten (20×20 atau 24×24) di semua section

---

## 5. Hero Section

### Sekarang

```
┌──────────────────────────────────────────┐
│  ● Bot Aktif & Siap Melayani   ← BADGE   │
│                                          │
│  Bot Discord                             │
│  untuk Server Impian  ← gradient text    │
│  Kamu                                    │
│                                          │
│  Synapse hadir dengan AI Chat...         │
│                                          │
│  [🎯 Tambahkan ke Server] [🔐 Dashboard] │
│                                          │
│  ──── stats ────                         │
│  124         50K        99.9%            │
│  Server     Members    Uptime            │
│  (gradient) (gradient) (gradient)        │
└──────────────────────────────────────────┘
```

### AI slop di hero

1. **Badge** "Bot Aktif & Siap Melayani" + dot hijau pulsing = template AI nomor 1
2. **Gradient text** "Server Impian" = template AI nomor 2
3. **Stat numbers** juga gradient
4. **Subtitle** pake em dash `— semuanya dalam satu bot.`

### Usulan

```
┌──────────────────────────────────────────┐
│                                          │
│  ✦ Guild Marquee (opsional)              │
│  ←── detail: docs/landing-guild-marquee.md     │
│                                          │
│  𝓢𝓎𝓃𝒶𝓅𝓈ℯ                               │
│  Bot Discord untuk Server Impian Kamu    │
│        (solid color, no gradient)        │
│                                          │
│  [icon] Tambahkan ke Server   [icon] Dashboard │
│                                          │
│  ──── stats ────                         │
│  124         50K        99.9%            │
│  Server     Members    Uptime            │
│  (solid)    (solid)   (solid)            │
└──────────────────────────────────────────┘
```

### Perubahan spesifik

| Elemen                | Sekarang                           | Usulan                                                                                                                                                  |
| --------------------- | ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Badge                 | `● Bot Aktif & Siap Melayani`      | **Hapus.** Atau kalo mau dipertahankan, ganti jadi something personal, misal: `Dibuat oleh Hidden Hamlet` atau `v2.1.0` — tanpa dot hijau, tanpa glass |
| Title gradient        | `<span class="gradient-text">`     | **Hapus gradient.** Pake `color: var(--accent)` solid atau `color: var(--text-primary)` biasa                                                           |
| Stat numbers gradient | `background: var(--gradient-text)` | **Ganti** ke `color: var(--text-primary)` atau `color: var(--accent)` solid                                                                             |
| Em dash di subtitle   | `— semuanya dalam satu bot.`       | **Ganti** pake koma, titik, atau spasi aja                                                                                                              |
| Hero badge delete     | —                                  | Kalo badge dihapus, title naik & spacing lebih lega                                                                                                     |

### Kode yang diubah

- `landing.html` — hapus `<div class="hero-badge">`
- `landing.css` — `.stat-number` hapus gradient, pake `color: var(--text-primary)`
- `id.json` / `en.json` — hapus `hero.badge` key

---

## 6. Features Section

### Sekarang

```
┌──────────────────────────────────────────┐
│  FITUR UNGGULAN                          │
│  Semua yang kamu butuhkan,               │
│  sudah ada di sini.                      │
│                                          │
│  ┌──────┐ ┌──────┐ ┌──────┐             │
│  │  🤖  │ │  👋  │ │  📊  │             │
│  │ AI   │ │Welc..│ │Dash..│             │
│  │ Chat │ │System│ │board │             │
│  └──────┘ └──────┘ └──────┘             │
│  ┌──────┐ ┌──────┐                      │
│  │  💸  │ │  ⚡  │                      │
│  │Dona..│ │Auto..│                      │
│  └──────┘ └──────┘                      │
└──────────────────────────────────────────┘
```

### AI slop

- Pattern **label → title → subtitle** (sama persis kayak section lain)
- Feature cards **semua glassmorphism** + **emoji icon di background accent**
- Emoji icons 🤖👋📊💸⚡ — generic

### Usulan

```
┌──────────────────────────────────────────┐
│  APA YANG BISA SYNAPSE LAKUKAN?          │
│  (bedain label, gak pake label kecil,    │
│   langsung headline besar)               │
│                                          │
│  ┌─────────────────┐  ┌─────────────────┐│
│  │  [icon] AI Chat │  │  [icon] Welcome ││
│  │  powered by     │  │  Banner custom  ││
│  │  Gemini/Groq    │  │  via dashboard  ││
│  └─────────────────┘  └─────────────────┘│
│  ┌─────────────────┐  ┌─────────────────┐│
│  │  [icon] Dashbrd │  │  [icon] Donation││
│  │  real-time stats│  │  auto-track     ││
│  │  dark mode      │  │  boost server   ││
│  └─────────────────┘  └─────────────────┘│
│  ┌──────────────────────────────────────┐│
│  │  [icon] Auto Responder               ││
│  │  keyword trigger + auto-reply        ││
│  │  [full width, beda layout]           ││
│  └──────────────────────────────────────┘│
└──────────────────────────────────────────┘
```

### Perubahan spesifik

| Elemen        | Sekarang                            | Usulan                                                                                                                 |
| ------------- | ----------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| Section label | `FITUR UNGGULAN` (kecil, uppercase) | **Ganti** format heading lebih besar & beda, misal `APA YANG BISA SYNAPSE LAKUKAN?` tanpa `.section-label`          |
| Feature cards | 5 cards, semua sama persis          | **Variasi**: 4 card grid biasa + 1 card full-width di bawah (beda layout, lebih bold)                                  |
| Glassmorphism | Semua card `--glass-bg`             | **Kurangi**. Card bisa pake `background: var(--sidebar-bg)` (solid) dengan border tipis, tanpa `backdrop-filter: blur` |
| Emoji icons   | 🤖 👋 📊 💸 ⚡ di atas              | **Ganti** pake SVG icon library (Lucide), icon di kiri text horizontal, ukuran konsisten                               |

---

## 7. How It Works Section

### Sekarang

```
┌──────────────────────────────────────────┐
│  CARA KERJA                              │
│  Mulai dalam 3 langkah                   │
│                                          │
│  ┌──────┐ ┌──────┐ ┌──────┐             │
│  │  1   │ │  2   │ │  3   │             │
│  │Invite│ │Login │ │Atur &│             │
│  │ Bot  │ │Dash..│ │Nikmat│             │
│  └──────┘ └──────┘ └──────┘             │
└──────────────────────────────────────────┘
```

### AI slop

- "Mulai dalam 3 langkah" + numbering 1-2-3 = **template paling kentara**
- Sama persis pattern section: label→title→subtitle
- Step cards pake glassmorphism + gradient number

### Usulan

```
┌──────────────────────────────────────────┐
│  MULAI PAKE SYNAPSE                      │
│  (gak pake subtitle, langsung isi)       │
│                                          │
│  ┌─▶ Invite bot ke server kamu           │
│  │   Klik tombol, pilih server, beres    │
│  │                                       │
│  ├─▶ Login dashboard & atur setting      │
│  │   Semua ada di dashboard visual       │
│  │                                       │
│  └─▶ Nikmati fitur otomatis              │
│      Selesai, bot langsung jalan         │
│                                          │
│  (timeline vertikal, pake connector line │
│   bukan numbering 1-2-3)                 │
│  (gak pake glass, pake border kiri aja)  │
└──────────────────────────────────────────┘
```

### Perubahan spesifik

| Elemen     | Sekarang                           | Usulan                                                                       |
| ---------- | ---------------------------------- | ---------------------------------------------------------------------------- |
| Layout     | Grid 3 kolom                       | **Timeline vertikal** — 3 baris ke bawah dengan connector line/garis di kiri |
| Numbering  | `1`, `2`, `3` gradient             | **Hapus.** Pake arrow `▸` atau bullet `●` doang                              |
| Background | Glass                              | **Solid** `--sidebar-bg` atau border-left aja                                |
| Subtitle   | "Tidak perlu konfigurasi rumit..." | **Hapus.** Langsung ke step                                                  |
| Label | "CARA KERJA" | **Ganti** misal `MULAI` atau langsung judul besar                         |

---

## 8. CTA Section

### Sekarang

```
┌──────────────────────────────────────────┐
│  ┌────────────────────────────────────┐  │
│  │  Siap membawa server kamu          │  │
│  │  ke level berikutnya?              │  │
│  │                                    │  │
│  │  Bergabung dengan ratusan server...│  │
│  │                                    │  │
│  │  [Invite Sekarang] [Join Support]  │  │
│  └────────────────────────────────────┘  │
│  (glass card dengan border)              │
└──────────────────────────────────────────┘
```

### AI slop

- CTA card pake **glassmorphism LAGI** (sama kayak features, steps, FAQ, commands)
- Pattern: title → subtitle → 2 tombol = template
- "Siap membawa server kamu ke level berikutnya?" — super generik

### Usulan

```
┌──────────────────────────────────────────┐
│  ┌────────────────────────────────────┐  │
│  │  [icon] Coba Synapse Sekarang       │  │
│  │  Gratis, gak ribet                  │  │
│  │                                    │  │
│  │  [icon] Invite Sekarang             │  │
│  │                                    │  │
│  │  Punya pertanyaan? ⤵               │  │
│  │  Discord.gg/kwPr32AhGH             │  │
│  └────────────────────────────────────┘  │
│  (solid background, no glass,            │
│   panggah beda dari section lain)        │
└──────────────────────────────────────────┘
```

### Perubahan spesifik

| Elemen     | Sekarang                      | Usulan                                                                                                  |
| ---------- | ----------------------------- | ------------------------------------------------------------------------------------------------------- |
| Background | Glass                         | **Solid gradient** dari `--gradient-main` atau `--sidebar-bg` solid — biar beda dari semua section lain |
| Subtitle   | "Bergabung dengan ratusan..." | **Ganti** lebih pendek & to the point "Gratis, gak ribet"                                               |
| 2 tombol   | Invite + Support              | Bisa 1 tombol doang Invite, support jadi link kecil di bawah                                            |

---

## 9. FAQ Section

### Sekarang

```
┌──────────────────────────────────────────┐
│  FREQUENTLY ASKED QUESTIONS              │
│  Pertanyaan yang Sering Diajukan         │
│                                          │
│  ┌────────────────────────────────────┐  │
│  │ Apakah Synapse gratis?          ▼  │  │
│  └────────────────────────────────────┘  │
│  ┌────────────────────────────────────┐  │
│  │ Bagaimana cara mengundang...    ▼  │  │
│  └────────────────────────────────────┘  │
│  ┌────────────────────────────────────┐  │
│  │ Apakah fitur AI Chat-nya...     ▼  │  │
│  └────────────────────────────────────┘  │
└──────────────────────────────────────────┘
```

### AI slop

- Label "Frequently Asked Questions" + "Pertanyaan yang Sering Diajukan" (2 bahasa, mubazir)
- Accordion glassmorphism lagi
- Pattern section yang ke-5 dengan format yang sama

### Usulan

```
┌──────────────────────────────────────────┐
│  TANYA JAWAB                             │
│  (label aja, gak perlu subtitle)         │
│                                          │
│  Apakah Synapse gratis?                  │
│  ─────────────────────────────────────   │
│  Ya, Synapse sepenuhnya gratis untuk...  │
│  (expandable, tapi border-bottom aja)    │
│                                          │
│  Bagaimana cara mengundang bot?          │
│  ─────────────────────────────────────   │
│  (sama, format minimalis)                │
└──────────────────────────────────────────┘
```

### Perubahan spesifik

| Elemen               | Sekarang                                                         | Usulan                                                                        |
| -------------------- | ---------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| Background accordion | Glass                                                            | **No background.** Cuma border-bottom tipis doang antara item FAQ. Minimalis. |
| Label dobel          | "Frequently Asked Questions" + "Pertanyaan yang Sering Diajukan" | **Cukup 1.** "TANYA JAWAB" di ID, "FAQ" di EN                                 |
| Subtitle             | "Temukan jawaban..."                                             | **Hapus.** Langsung ke daftar FAQ                                             |

---

## 10. Commands Section

### Sekarang

```
┌──────────────────────────────────────────┐
│  DAFTAR PERINTAH                         │
│  Commands Reference                      │
│                                          │
│  🔍 [Cari perintah...]                   │
│                                          │
│  ┌──────┐ ┌──────┐ ┌──────┐             │
│  │ 🤖  │ │ 🛡️  │ │ ⚙️   │             │
│  │AI Chat│ │Moderasi││Utility│           │
│  │       │ │       │ │      │           │
│  │/ai..  │ │/kick  │ │/help │           │
│  │/ai..  │ │/ban   │ │/stats│           │
│  └──────┘ └──────┘ └──────┘             │
└──────────────────────────────────────────┘
```

### AI slop

- Pattern label→title→subtitle lagi
- Search bar dengan glassmorphism
- Command cards glassmorphism lagi

### Perubahan

Commands section is actually useful — jadi lebih ke **restyle** daripada ganti struktur:

| Elemen        | Sekarang                     | Usulan                                                          |
| ------------- | ---------------------------- | --------------------------------------------------------------- |
| Section label | "DAFTAR PERINTAH"            | **Ganti** misal `/commands` biar vibe-nya beda                  |
| Subtitle      | "Jelajahi semua perintah..." | **Hapus** atau digabung ke title                                |
| Glass card    | `--glass-bg`                 | **Ganti** solid `--sidebar-bg`, border tipis `--sidebar-border` |
| Search bar    | Glass                        | **Solid** juga, atau hapus blur effect                          |

---

## 11. About Section

### Sekarang

```
┌──────────────────────────────────────────┐
│  TENTANG KAMI                            │
│  About Synapse                           │
│                                          │
│  ┌────────────────────────────────────┐  │
│  │  [logo] Synapse                    │  │
│  │         Discord Bot                │  │
│  │                                    │  │
│  │  🎯 Visi        👤 Developer      │  │
│  │  Synapse dibangun... enthusiast... │  │
│  │                                    │  │
│  │  🛠️ Tech Stack                    │  │
│  │  [Python] [Discord.py] [Flask]     │  │
│  └────────────────────────────────────┘  │
└──────────────────────────────────────────┘
```

### AI slop

- Glass card lagi
- Tech stack badges — template
- Emoji di judul blok (🎯 👤 🛠️)
- Label dobel "TENTANG KAMI" + "About Synapse"

### Usulan

| Elemen      | Sekarang                         | Usulan                                       |
| ----------- | -------------------------------- | -------------------------------------------- |
| Glass       | `--glass-bg`                     | **Solid** `--sidebar-bg`                     |
| Tech badges | Pill dengan `--tag-bg`           | Mending dihapus atau diganti jadi text biasa |
| Emoji blok  | 🎯 👤 🛠️                         | Hapus, pake bold heading biasa               |
| Label dobel | "TENTANG KAMI" + "About Synapse" | Cukup 1                                      |

---

## 12. Navbar & Footer

### Navbar

| Elemen      | Sekarang                            | Usulan                                              |
| ----------- | ----------------------------------- | --------------------------------------------------- |
| Brand text  | `𝓢𝓎𝓃𝒶𝓅𝓈ℯ` font script               | Oke sih, personal. Tapi pastiin gak terlalu AI-vibe |
| Glass/Hover | Glass effect di beberapa tempat     | Minimalkan                                          |
| Mobile menu | Emoji 🏠 ❓ ⌨️ 👤 💬 di setiap link | Ganti pake SVG icon library atau hapus emoji        |

### Footer

| Elemen    | Sekarang                                 | Usulan                                                                                                                    |
| --------- | ---------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| Copyright | `© {year} Synapse. All rights reserved.` | **Generik.** Bisa ganti: `© {year} Dibuat oleh ZeenZ dengan ❤️` atau `© {year} Synapse — bot Discord untuk server impian` |

---

## 13. Flow Keseluruhan

### Susunan section sekarang

```
Hero
  ↓
Features
  ↓
How It Works
  ↓
CTA
  ↓
FAQ
  ↓
Commands
  ↓
About
  ↓
Footer
```

### Masalah flow

- **CTA muncul sebelum FAQ & Commands** — orang belum liat fitur detail udah disuruh invite
- **About di paling bawah** — ok, wajar
- **Commands sebelum About** — biasanya About lebih dulu dari commands

### Usulan flow

```
Hero (opsional: guild marquee)
  ↓
Features (apa yang bisa dilakukan)
  ↓
How It Works / Getting Started (ganti format timeline)
  ↓
Commands (referensi perintah)
  ↓
FAQ (pertanyaan umum)
  ↓
About (tentang bot & developer)
  ↓
CTA (ajakan action — pas di akhir, setelah semua informasi)
  ↓
Footer
```

### Alasan

- CTA di **bawah FAQ & About** — orang udah paham semua baru diajak invite
- Commands sebelum FAQ — biar orang liat fitur dulu, baru FAQ
- Flow lebih natural: **kenal fitur → liat commands → tanya jawab → tentang kami → action**

---

## Catatan Implementasi

### Prioritas eksekusi

| Urut | Item                                          | Effort        |
| ---- | --------------------------------------------- | ------------- |
| 1    | Emoji → SVG icon library                      | Ringan-Sedang |
| 2    | Starfield ganti sakura                        | Ringan        |
| 3    | Hapus sakura container + file .css/.js        | Ringan        |
| 4    | Hero badge hapus + gradient text hilangin     | Ringan        |
| 5    | Ganti palette warna (--accent, --hero-glow)   | Ringan        |
| 6    | Stat numbers solid color                      | Ringan        |
| 7    | CTA section pake solid gradient (bukan glass) | Ringan        |
| 8    | FAQ minimalis (no glass)                      | Ringan        |
| 9    | Footer copyright personal                     | Ringan        |
| 10   | Hapus em dash fallback                        | Ringan        |
| 11   | Kurangi scroll-reveal (gak semua element)     | Ringan        |
| 12   | Flow ulang susunan section                    | Sedang        |
| 13   | Features + Steps section layout variasi       | Berat         |
| 14   | Commands + About restyle solid                | Sedang        |

### Glassmorphism — komponen mana kena

| Komponen | Skrg | Usulan |
|----------|------|--------|
| Hero badge | Glass | Dihapus (badge dihapus) |
| Features card | Glass | **Solid** `--sidebar-bg` |
| Steps card | Glass | **Solid** `--sidebar-bg` |
| CTA card | Glass | **Solid** atau solid gradient |
| FAQ accordion | Glass | **No background** (border-bottom aja) |
| Command card | Glass | **Solid** `--sidebar-bg` |
| Search bar | Glass | **Solid** `--sidebar-bg` |
| About card | Glass | **Solid** `--sidebar-bg` |
| Button secondary | Glass | **Tetap** tapi dikurangi blur-nya |

### File yang kena

| File                               | Perubahan                                                       |
| ---------------------------------- | --------------------------------------------------------------- |
| `frontend/pages/landing.html`      | Emoji → icon, hero badge, section order, class, hapus sakura  |
| `frontend/static/css/landing.css`  | `:root` colors, glass removal, new section styles               |
| `frontend/static/css/sakura.css`   | Hapus file                                                     |
| `frontend/static/js/sakura.js`     | Hapus file                                                     |
| `frontend/static/js/stars.js`      | File baru                                                      |
| `frontend/static/icons/`           | Folder baru (kalau pake Opsi A inline SVG bisa dilewatin)       |
| `backend/web/translations/id.json` | Hapus `hero.badge`, update text                                |
| `backend/web/translations/en.json` | Sama                                                           |
