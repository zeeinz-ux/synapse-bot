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
| ≥ 5 | Marquee 3 copy, 2 baris arah zigzag |
| Hover | Animasi pause via JS — lebih akurat drpd CSS `play-state` |

### Posisi di halaman

Marquee ditempatin di hero section, **di bawah subtitle, di atas tombol invite**. Stat server (angka) diganti jadi marquee visual. Members & Uptime tetap.

| Elemen | Detail |
|--------|--------|
| **Background marquee** | `--glass-bg` (rgba 26,26,30,0.65), border `--glass-border`, backdrop-filter blur, border-radius |
| **Avatar** | Lingkaran 40×40px, border 2px `--sidebar-border`. Fallback: initial letter kalo gak ada icon |
| **Nama server** | Font 0.75rem, `--text-secondary`, truncate 1 line (`max-width: 10ch`), gap 6px dari avatar |
| **Fade edge** | `mask-image` di `.marquee-row` — ilang perlahan ke background gelap |
| **Arah baris 1** | Kanan → kiri |
| **Arah baris 2** | Kiri → kanan (zigzag) |
| **Copy** | **3 copy** per baris (bukan 2) — biar pas reset ada overlap 1 set item yg tetap kelihatan, no visible jump |
| **Hover** | `mouseenter` → paused, `mouseleave` → resume (JS RAF-based, lebih responsif) |
| **Speed** | `max(40000, min(120000, guilds.length * 3000))` ms per siklus |
| **Click** | Skip — gada discovery link yg reliable |

## Teknis

### Files affected

| File | Perubahan |
|------|-----------|
| `frontend/static/js/landing.js` | `loadStats()` render `guilds_list`. `renderMarquee()` pake RAF, delta-time, 3 copy |
| `frontend/pages/landing.html` | `<div class="guild-marquee">` di hero, `#statItemServers` sbg fallback |
| `frontend/static/css/landing.css` | Style marquee, mask, grid fallback. **No keyframes** — semua animasi via JS RAF |

### CSS highlights

```css
.marquee-row {
  mask-image: linear-gradient(to right, transparent 0%, black 5%, black 95%, transparent 100%);
}
.marquee-track { width: fit-content; }
/* animation: none — RAF handles transform langsung */
```

### JS highlights

```js
// RAF-driven, no CSS keyframes
function tick(now) {
  if (lastTime && !paused) {
    elapsed += now - lastTime;
    const pct = (elapsed % (DURATION * 3)) / (DURATION * 3) * 100;
    rightTrack.style.transform = `translateX(-${pct / 3}%)`;
    leftTrack.style.transform  = `translateX(${pct / 3 - 33.33}%)`;
  }
  lastTime = now;
  rafId = requestAnimationFrame(tick);
}

// 3 copies per row, not 2
rightTrack.append(...items, ...dup1, ...dup2);
leftTrack.append(...reversed, ...dupRev1, ...dupRev2);
```

### Fallback

Kalo `guilds_list` kosong / error → container marquee `display: none`, stat server (`#statItemServers`) tetap kelihatan (seperti sebelum marquee).
