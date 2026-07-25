# Landing Page — Guild Marquee

## Tujuan

Ganti stat "Jumlah Server" (angka doang) di hero landing page jadi daftar avatar server Discord yang jalan horizontal (marquee), biar lebih real & engaging.

## Data

`/api/stats` udah ngembaliin `guilds_list`:

```json
{
  "guilds_list": [
    { "id": "123", "name": "Server Name", "member_count": 100, "icon": "https://cdn.discordapp.com/..." }
  ]
}
```

Dikumpulin tiap 30 detik di `main.py`, disimpen lewat Firestore.

## Perilaku

| Jumlah guild | Tampilan |
|-------------|----------|
| < 5 | Grid biasa (no animation) |
| ≥ 5 | Marquee horizontal, kanan → kiri |
| Hover | Animasi pause |

## Visual Mockup

### Posisi di halaman

Marquee ditempatin di hero section, **di bawah title/subtitle, di atas tombol invite & stats** — atau alternatifnya **menggantikan baris stats "Server / Members / Uptime"** (angka server doang diganti, members & uptime tetap).

### Gambaran hero section setelah jadi

```
┌──────────────────────────────────────────────┐
│              ● ONLINE (badge)                 │
│                                               │
│         ✨ SYNAPSE (title gradient)           │
│                                               │
│       subtitle text (secondary color)         │
│                                               │
│  ┌────────────────────────────────────────┐   │
│  │  ←──── GUILD MARQUEE ───────────────→  │   │
│  │  ┌──┐ ┌──┐ ┌──┐ ┌──┐ ┌──┐ ┌──┐       │   │
│  │  │██│ │██│ │██│ │██│ │██│ │██│  ...   │   │
│  │  └──┘ └──┘ └──┘ └──┘ └──┘ └──┘       │   │
│  │  Nama  Nama  Nama  Nama  Nama  Nama    │   │
│  │  ←──── arah baris 1 (kanan→kiri) ────  │   │
│  │                                        │   │
│  │  ──── arah baris 2 (kiri→kani) ────→  │   │
│  │  ┌──┐ ┌──┐ ┌──┐ ┌──┐ ┌──┐ ┌──┐       │   │
│  │  │██│ │██│ │██│ │██│ │██│ │██│  ...   │   │
│  │  └──┘ └──┘ └──┘ └──┘ └──┘ └──┘       │   │
│  │  Nama  Nama  Nama  Nama  Nama  Nama    │   │
│  │  ←──── GUILD MARQUEE ───────────────→  │   │
│  └────────────────────────────────────────┘   │
│              [fade]          [fade]            │
│                                               │
│         [🎯 Invite]   [🔐 Dashboard]         │
│                                               │
│  ───────────────────────────────────────      │
│  50K Members             99.9% Uptime          │
│                                               │
└──────────────────────────────────────────────┘
```

### Keterangan

| Elemen | Detail |
|--------|--------|
| **Background marquee** | `--glass-bg` (rgba 26,26,30,0.65), border `--glass-border`, backdrop-filter blur, border-radius |
| **Avatar** | Lingkaran 40×40px, border 2px `--sidebar-border` |
| **Nama server** | Font 0.75rem, `--text-secondary`, truncate 1 line, gap 6px dari avatar |
| **Fade edge** | `mask-image: linear-gradient(to right, transparent 0%, black 5%, black 95%, transparent 100%)` — ilang perlahan ke background gelap |
| **Arah baris 1** | Kanan → kiri (`translateX(-50%)`) |
| **Arah baris 2** | Kiri → kanan (`translateX(0)`) — zigzag biar dinamis |
| **Duplikat** | Item di-clone 1× biar seamless loop |
| **Hover** | `animation-play-state: paused` — biar user bisa liat detail |
| **Speed** | CSS custom property `--marquee-speed` (misal 30s-60s) tergantung jumlah guild |
| **Click** | Setiap item bisa diklik → redirect ke `https://discord.com/servers/...` (kalo ada discovery) atau fallback gak usah |

### Marquee item zoom (per avatar)

```
     ╭──────────╮
     │  ╭────╮  │
     │  │  ██│  │  ← 40×40px circle avatar
     │  │  ██│  │     border 2px
     │  ╰────╯  │
     │  Nama    │  ← truncated, ~12ch max
     │  Server  │
     ╰──────────╯
```

## Teknis

### Files affected

| File | Perubahan |
|------|-----------|
| `frontend/static/js/landing.js` | Di `loadStats()`, render `guilds_list` ke container marquee |
| `frontend/pages/landing.html` | Tambah `<div class="guild-marquee">` di hero section |
| `frontend/static/css/landing.css` | Tambah style marquee, keyframes, fade mask |

### CSS highlights

- `mask-image: linear-gradient(to right, transparent 0%, black 5%, black 95%, transparent 100%)`
- `@keyframes marquee-right { to { transform: translateX(-50%) } }`
- `@keyframes marquee-left { to { transform: translateX(0) } }`
- Duplicate content via JS, wrapper `width: fit-content`
- `animation-play-state: paused` on hover

### JS highlights

```js
const guilds = data.guilds_list || [];
if (guilds.length >= 5) {
  // render 2 rows, second row reversed
  // clone children for seamless loop
  // set css custom property --marquee-speed based on count
}
```

### Fallback

Kalo guilds_list kosong / error, fallback ke angka doang (kaya skrg).

## Gambaran Kasar DOM

```html
<div class="guild-marquee">
  <div class="marquee-row marquee-row--right">
    <div class="marquee-track">
      <div class="marquee-item">
        <img src="icon" loading="lazy" />
        <span>Server Name</span>
      </div>
      <!-- ... duplicated for loop ... -->
    </div>
  </div>
  <div class="marquee-row marquee-row--left">
    <!-- same, reversed & opposite direction -->
  </div>
</div>
```

## Catatan

- Icon Discord CDN bersifat permanen — gak perlu khawatir broken link
- Cache image: browser handle sendiri lewat `loading="lazy"`
- Kalo guild gak punya icon, fallback ke default Discord icon
