# Landing Page — De-AI-Slop

Catatan perubahan yang udah dieksekusi vs yang masih pending.

## Ringkasan Status

| #   | Item                                           | Status       | Keterangan                                                                 |
| --- | ---------------------------------------------- | ------------ | -------------------------------------------------------------------------- |
| 1   | Sakura falling petals → Starfield              | **✅ Done**  | `stars.js` (canvas, 200 bintang + shooting star). `sakura.js/css` dihapus  |
| 2   | Emoji → SVG icon library                       | **✅ Done**  | Lucide CDN (`unpkg.com/lucide`), icon konsisten di semua section           |
| 3   | Hero badge "Bot Aktif & Siap Melayani"         | **✅ Done**  | Dihapus total                                                              |
| 4   | Gradient Discord blurple → palette personal    | **✅ Done**  | Opsi A: `#00d4ff` (cyan) → `#7c3aed` (violet)                             |
| 5   | Section pattern variasi                        | 🟡 Partial  | Steps jadi timeline, sisanya masih template-ish                            |
| 6   | Glassmorphism dikurangi                        | ❌ Pending  | Masih banyak pake glass (`--glass-bg`)                                     |
| 7   | Gradient text di title & stats                 | **✅ Done**  | Pake solid color semua                                                     |
| 8   | Em dash `—`                                    | **✅ Done**  | Ganti titik/koma/dot bullet `•`                                            |
| 9   | "How It Works 1-2-3" → timeline               | **✅ Done**  | Timeline vertikal pake connector line                                      |
| 10  | Tech stack badges                              | ❌ Pending  | Masih ada di About section                                                 |
| 11  | Scroll reveal intensity                        | ❌ Pending  | Masih sama kayak awal                                                      |
| 12  | `--hero-glow-a/b` update                       | **✅ Done**  | Ikut palette cyan/violet                                                   |
| 13  | Footer copyright personal                      | **✅ Done**  | `Dibuat oleh ZeenZ dengan ❤️`                                              |
| 14  | Guild marquee (ganti angka server)             | **✅ Done**  | RAF-driven, 3 copy, detail di `landing-guild-marquee.md`                   |
| 15  | Commands section update                        | **✅ Done**  | Sesuai bot asli: AI Chat, Voice Room, Auto Responder, Utility              |
| 16  | Discord logo SVG fix                           | **✅ Done**  | Eye cutouts ditambahin biar keliatan kaya Discord                          |
| 17  | Button ghost/glow reduction                    | ❌ Pending  | User minta balikin ke style awal (revert)                                  |
| 18  | CTA section solid gradient                     | ❌ Pending  | Masih glass card                                                            |
| 19  | FAQ minimal (border-bottom aja)                | ❌ Pending  | Masih glass accordion                                                      |
| 20  | About section solid bg                         | ❌ Pending  | Masih glass card                                                            |
| 21  | Section flow: CTA di akhir                     | **✅ Done**  | Urutan: Hero → Features → Steps → Commands → FAQ → About → **CTA** → Footer |

## Palette Akhir (Opsi A — Cyber/Neon)

```css
--accent: #00d4ff;
--accent-secondary: #7c3aed;
--accent-warm: #f59e0b;
--gradient-main: linear-gradient(135deg, #00d4ff, #7c3aed);
--hero-glow-a: rgba(0, 212, 255, 0.15);
--hero-glow-b: rgba(124, 58, 237, 0.08);
```

## Starfield (`frontend/static/js/stars.js`)

- Canvas-based, 200 bintang random, kelap-kelip perlahan
- Shooting star tiap 4-12 detik
- Gak ada DOM element, performa ringan
- File sakura.js/css dihapus

## Icon Library

- Lucide lewat CDN: `<script src="https://unpkg.com/lucide@latest">` + `lucide.createIcons()`
- Emoji di semua section diganti icon SVG stroke-based
- Konsisten: ukuran, warna (`currentColor`), stroke-width

## Struktur Halaman Sekarang

```
Hero (title + subtitle + guild marquee + buttons + stats)
  ↓
Features (5 card grid, Lucide icons)
  ↓
Steps (timeline vertikal)
  ↓
Commands (4 kategori, searchable, sesuai bot asli)
  ↓
FAQ (accordion)
  ↓
About (visi + developer + tech stack)
  ↓
CTA (ajakan invite)
  ↓
Footer
```

## Yang Masih Pending (masih bisa dikerjain)

Prioritas dari yang paling gampang:

1. **FAQ minimal** — hapus glass, pake border-bottom aja antar item
2. **About solid** — ganti `--glass-bg` ke `--sidebar-bg`
3. **Command cards solid** — ganti glass ke solid
4. **CTA solid gradient** — ganti glass ke gradient penuh
5. **Tech stack badges** — restyle atau hapus
6. **Kurangi scroll reveal** — jangan semua element kena `data-reveal`
