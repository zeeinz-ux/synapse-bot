# 🤖 Hidden Hamlet — Discord Bot

Bot Discord all-in-one dengan fitur tracking server boost, pencatatan donasi, music player kualitas jernih dari YouTube & Spotify, dan **web dashboard real-time**. Support 24/7 via UptimeRobot.

---

## ✨ Fitur

| Fitur                       | Deskripsi                                                             |
| --------------------------- | --------------------------------------------------------------------- |
| 🚀 **Auto Boost Detection** | Deteksi otomatis member yang boost/unboost server                     |
| 💰 **Donasi Tracker**       | Catat donasi dengan `/donasi`                                         |
| 📊 **Cek Riwayat Boost**    | Cek status boost user dengan `/cekboost`                              |
| 🧪 **Simulasi Boost**       | Testing boost dengan `/testboost` (Admin only)                        |
| 🎵 **Music Player**         | Putar lagu dari **YouTube** & **Spotify** dengan kualitas **320kbps** |
| 📊 **Web Dashboard**        | Status bot real-time di browser (auto-refresh)                        |
| 🔥 **Firebase Firestore**   | Database real-time untuk menyimpan data                               |
| 🌐 **24/7 Uptime**          | Flask server untuk UptimeRobot ping                                   |
| 🔒 **Secure**               | Token & key disimpan di environment variables                         |
| 🔄 **Cogs System**          | Modular — tiap fitur di file terpisah                                 |

---

## 🎵 Music Player Features

| Command                   | Deskripsi                                                   |
| ------------------------- | ----------------------------------------------------------- |
| `/play <query>`           | Putar lagu dari YouTube URL, Spotify URL, atau search query |
| `/pause`                  | Pause lagu                                                  |
| `/resume`                 | Lanjutkan lagu                                              |
| `/skip`                   | Skip ke lagu berikutnya                                     |
| `/stop`                   | Stop & keluar voice channel                                 |
| `/queue`                  | Lihat antrian lagu                                          |
| `/nowplaying`             | Info lagu yang sedang diputar                               |
| `/volume <0-1000>`        | Atur volume bot (default 100)                               |
| `/loop <mode>`            | Atur loop: off / single / queue                             |
| `/shuffle`                | Acak antrian lagu                                           |
| `/autoplay`               | Toggle autoplay saat queue habis                            |
| `/seek <position>`        | Skip ke posisi tertentu (format: 1:30 atau 90)              |
| `/remove <index>`         | Hapus lagu dari queue                                       |
| `/move <from> <to>`       | Pindah posisi lagu di queue                                 |
| `/skipto <index>`         | Skip ke lagu nomor tertentu                                 |
| `/disconnect`             | Keluar dari voice channel                                   |
| `/clearqueue`             | Kosongkan queue tanpa stop lagu                             |
| `/replay`                 | Putar ulang lagu dari awal                                  |
| `/lyrics [query]`         | Cari lirik lagu                                             |
| `/playlist save <name>`   | Simpan queue sebagai playlist                               |
| `/playlist load <name>`   | Muat playlist ke queue                                      |
| `/playlist list`          | Lihat daftar playlist                                       |
| `/playlist delete <name>` | Hapus playlist                                              |

### Kualitas Audio

- **Codec**: OPUS (via Lavalink)
- **Sample Rate**: 48kHz
- **Channels**: Stereo (2.0)
- **Source**: YouTube (auto-search untuk Spotify)

---

## 📊 Web Dashboard

Akses status bot real-time di browser:

| URL          | Deskripsi                                |
| ------------ | ---------------------------------------- |
| `/`          | Landing page — links ke Dashboard & API  |
| `/dashboard` | Full status dashboard (auto-refresh 10s) |
| `/api/stats` | JSON API untuk integrasi eksternal       |

### Dashboard Menampilkan

- **Bot Status**: online/offline, uptime, username
- **Statistics**: jumlah server & total member
- **Lavalink**: connection status & node URI
- **Active Players**: guild yang sedang play music
  - Judul lagu, author, artwork
- **Progress bar** dengan position/duration
- **Queue size**, jumlah listener, status pause
- **Dark theme** dengan CSS :root variables
- **Responsive** mobile layout

---

## 📁 Struktur Project

```
my-discord-bot/
├── main.py                     # Entry point bot + Flask thread + stats updater
├── requirements.txt            # Dependencies
├── .env                        # Environment variables (JANGAN DI-COMMIT!)
├── .env.example                # Template .env
├── .gitignore                  # Melindungi file sensitif & backup
├── README.md                   # Dokumentasi ini
├── LICENSE
│
├── cogs/                       # Discord bot cogs
│   ├── __init__.py
│   ├── music.py                # Music Player (YouTube + Spotify + Playlist)
│   ├── spotify_down.py         # SpotifyDown API resolver + fallback
│   ├── general.py              # Ping, stats, help commands
│   ├── boost.py                # Boost Tracker
│   ├── donation.py             # Donation Tracker
│   └── firebase_setup.py       # Firebase Firestore init (dual mode)
│
├── utils/                      # Shared helpers (DRY)
│   ├── __init__.py
│   ├── constants.py            # LAVALINK_NODES config
│   └── formatters.py           # format_duration(), format_uptime()
│
└── web/                        # Flask dashboard
    ├── __init__.py
    ├── web_app.py              # Flask app, routes, shared stats
    ├── static/
    │   └── css/
    │       └── dashboard.css   # Dark theme with :root variables
    └── templates/
        └── dashboard.html      # Jinja2 template
```

---

## 🚀 Quick Start

### 1. Clone Repository

```bash
git clone https://github.com/zeeinz-ux/my-discord-bot.git
cd my-discord-bot
```

### 2. Install Dependencies

```bash
# Buat virtual environment (recommended)
python -m venv venv

# Aktifkan venv
# Windows:
venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate

# Install packages
pip install -r requirements.txt
```

### 3. Setup Environment Variables

Copy `.env.example` jadi `.env`:

```bash
cp .env.example .env
```

Edit `.env`:

```env
# WAJIB
TOKEN_BOT=your_discord_bot_token_here

# OPSIONAL (untuk Spotify fallback ke Official API)
SPOTIFY_CLIENT_ID=your_spotify_client_id
SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
```

> **Note:** `SPOTIFY_CLIENT_ID` & `SECRET` opsional — bot tetap jalan pakai SpotifyDown API atau oEmbed fallback.

### 4. Jalankan Bot

```bash
python main.py
```

Output yang diharapkan:

```
[LAVALINK] ✅ Node 1 tersambung: https://lavalink.jirayu.net:13592
[STATUS] 🤖 Hidden Hamlet SEKARANG SUDAH ONLINE!
[STATUS] Terhubung ke 1 server Discord.
[COG] ✅ Total 4 cogs loaded!
[SYNC] ✅ 18 slash command(s) berhasil di-sync!
[DASHBOARD] 📊 Stats updater aktif (30s).
```

- Bot Discord aktif
- Flask server jalan di port 8080
- Dashboard: http://127.0.0.1:8080/dashboard

---

## 🌐 Deploy ke Render (24/7)

### 1. Push ke GitHub

```bash
git add .
git commit -m "Initial deploy"
git push origin main
```

### 2. Setup Render

1. Daftar/login di [Render](https://render.com)
2. **New** → **Web Service**
3. Connect GitHub repo `zeeinz-ux/my-discord-bot`
4. Settings:
   - **Name**: `my-discord-bot`
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python main.py`
   - **Plan**: Free
5. Tambah **Environment Variables**:
   - `TOKEN_BOT` = your_discord_token
   - `SPOTIFY_CLIENT_ID` = (opsional)
   - `SPOTIFY_CLIENT_SECRET` = (opsional)
6. Klik **Create Web Service**

### 3. Setup UptimeRobot

1. Daftar di [UptimeRobot](https://uptimerobot.com)
2. **Add New Monitor**:
   - **Monitor Type**: HTTP(s)
   - **Friendly Name**: Discord Bot Keep Alive
   - **URL**: `https://my-discord-bot-gdew.onrender.com/`
   - **Interval**: Every 5 minutes

> Render free tier sleep setelah 15 menit idle. UptimeRobot ping setiap 5 menit → bot tetap online!

---

## 📋 Daftar Slash Command

### 🌐 General

| Command  | Deskripsi            |
| -------- | -------------------- |
| `/ping`  | Cek latency bot      |
| `/stats` | Statistik bot        |
| `/help`  | Daftar semua command |

### 🎵 Music

| Command                   | Deskripsi                           |
| ------------------------- | ----------------------------------- |
| `/play <query>`           | Putar lagu (YouTube/Spotify/search) |
| `/pause`                  | Pause lagu                          |
| `/resume`                 | Lanjutkan lagu                      |
| `/skip`                   | Skip lagu                           |
| `/stop`                   | Stop & keluar VC                    |
| `/queue`                  | Lihat antrian                       |
| `/nowplaying`             | Info lagu sekarang                  |
| `/volume <0-1000>`        | Atur volume                         |
| `/loop <mode>`            | Atur loop: off/single/queue         |
| `/shuffle`                | Acak queue                          |
| `/autoplay`               | Toggle autoplay                     |
| `/seek <position>`        | Skip ke posisi (1:30 atau 90)       |
| `/remove <index>`         | Hapus dari queue                    |
| `/move <from> <to>`       | Pindah posisi lagu                  |
| `/skipto <index>`         | Skip ke nomor tertentu              |
| `/disconnect`             | Keluar VC                           |
| `/clearqueue`             | Kosongkan queue                     |
| `/replay`                 | Ulang dari awal                     |
| `/lyrics [query]`         | Cari lirik                          |
| `/playlist save <name>`   | Simpan playlist                     |
| `/playlist load <name>`   | Muat playlist                       |
| `/playlist list`          | Lihat playlist                      |
| `/playlist delete <name>` | Hapus playlist                      |

### 🚀 Boost

| Command              | Deskripsi         | Permission    |
| -------------------- | ----------------- | ------------- |
| `/cekboost [@user]`  | Cek riwayat boost | Everyone      |
| `/testboost [@user]` | Simulasi boost    | Administrator |

### 💰 Donation

| Command                      | Deskripsi    |
| ---------------------------- | ------------ |
| `/donasi <nominal> <metode>` | Catat donasi |

---

## 🎵 Contoh Penggunaan Music

```markdown
# Play dari search query
/play query:alan walker faded

# Play dari YouTube URL
/play query:https://youtube.com/watch?v=...

# Play dari Spotify URL (track)
/play query:https://open.spotify.com/track/11dFghVXANMlKmJXsNCbNl

# Play dari Spotify URL (playlist)
/play query:https://open.spotify.com/playlist/1OdeBqfZNHjcS3PgbXhqZc

# Atur volume
/volume level:75

# Lihat queue
/queue

# Skip lagu
/skip

# Simpan playlist
/playlist save name:Rock Favorites
```

---

## 🔥 Spotify Integration

Bot menggunakan **multi-strategy resolver** untuk Spotify URLs:

| Source | Kecepatan | Reliability | Auth |
|--------|-----------|-------------|------|
| **SpotifyDown API** | ⚡ Fastest | ⚠️ Bisa down | ❌ No auth |
| **Spotify Official API** | ⚡ Fast | ✅ Stable | ✅ Client ID + Secret |
| **oEmbed** | 🐢 Medium | ✅ Always works | ❌ No auth |
| **HTML Scrape** | 🐢 Slow | ⚠️ Fragile | ❌ No auth |

**Fallback chain:**
```
SpotifyDown API → Spotify Official → oEmbed → HTML Scrape → ytsearch
```

### SpotifyDown API
- **Endpoint**: `api.spotifydown.com`
- **Features**: Track list, album list, YouTube ID mapping
- **Limitation**: Unofficial, bisa mati sewaktu-waktu

### Spotify Official API (Fallback)
- **Butuh**: `SPOTIFY_CLIENT_ID` & `SPOTIFY_CLIENT_SECRET`
- **Features**: Full metadata, track list, album tracks
- **Rate limit**: 1 request/second

### oEmbed / HTML Scrape (Last Resort)
- **No auth required**
- **Returns**: Title, artist, thumbnail only
- **Limitation**: Single track per URL (no playlist track list)

---

## 🔥 Firebase Firestore Structure

### Collection: `transactions`

```json
{
  "user_id": "123456789",
  "guild_id": "987654321",
  "type": "donation",
  "amount": 50000,
  "payment_method": "QRIS",
  "status": "pending",
  "created_at": "timestamp"
}
```

### Collection: `boosts`

```json
{
  "user_id": "123456789",
  "guild_id": "987654321",
  "type": "server_boost",
  "boosted_at": "timestamp",
  "unboosted_at": "timestamp",
  "status": "active | expired"
}
```

### Collection: `playlists`

```json
{
  "guild_id": "987654321",
  "user_id": "123456789",
  "name": "Rock Favorites",
  "tracks": [
    {
      "title": "Song Name",
      "uri": "https://youtube.com/watch?v=...",
      "author": "Artist",
      "artwork": "https://...",
      "length": 240000
    }
  ],
  "created_at": "timestamp"
}
```

---

## 🔒 Keamanan

### File yang WAJIB di-ignore (sudah di `.gitignore`):

- `.env` — Berisi token bot
- `serviceAccountKey.json` — Private key Firebase
- `__pycache__/` — Python cache
- `*-backup.py` — Backup files
- `lavalink/` — Lavalink server files

### JANGAN PERNAH:

- ❌ Commit token/key ke GitHub
- ❌ Share screenshot `.env` atau Secrets
- ❌ Push `serviceAccountKey.json` ke repo publik

### Jika Token Terexpose:

1. Segera **reset token** di [Discord Developer Portal](https://discord.com/developers/applications)
2. Update `.env` / Render env vars dengan token baru
3. Restart bot

---

## 🛠️ Troubleshooting

| Error                        | Penyebab                   | Solusi                                                       |
| ---------------------------- | -------------------------- | ------------------------------------------------------------ |
| `TOKEN_BOT tidak ditemukan`  | `.env` tidak terbaca       | Pastikan `python-dotenv` terinstall, file `.env` ada di root |
| `Module not found: wavelink` | Dependencies belum install | Jalankan `pip install -r requirements.txt`                   |
| `Lavalink not connected`     | Node tidak tersedia        | Cek koneksi internet, node mungkin down                      |
| `Slash command tidak muncul` | Belum di-sync              | Tunggu 1-5 menit, atau restart bot                           |
| `Permission denied`          | Bot tidak punya izin       | Cek role permission di server Discord                        |
| `/play hang/stuck`           | Search timeout             | Cek koneksi internet, coba query lain                        |
| `Dashboard 404`              | Route tidak terdaftar      | Cek `web/web_app.py`, pastikan `/dashboard` route ada        |
| `CSS tidak load`             | Path static salah          | Cek `static_folder` di Flask app                             |
| `SpotifyDown API down`       | API tidak tersedia         | Fallback ke oEmbed/HTML scrape otomatis                      |
| `YouTube 403`                | Lavalink node ke-block     | Ganti node di `utils/constants.py`                           |

---

## 📦 Dependencies

| Package        | Versi      | Fungsi                              |
| -------------- | ---------- | ----------------------------------- |
| discord.py     | >=2.3.0    | Library Discord bot                 |
| wavelink       | >=3.0.0    | Lavalink client untuk music         |
| firebase-admin | >=6.2.0    | Firebase Firestore integration      |
| flask          | >=2.3.0    | Web server untuk dashboard          |
| python-dotenv  | >=1.0.0    | Load environment variables          |
| aiohttp        | >=3.9.0    | Async HTTP untuk SpotifyDown API    |
| PyNaCl         | >=1.5.0    | Voice encryption                    |

---

## 🔄 Workflow Development

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   VS Code   │────▶│   GitHub    │────▶│   Render    │
│  (Dev/Test) │     │   (Repo)    │     │ (Production)│
└─────────────┘     └─────────────┘     └─────────────┘
```

1. **Edit & test** di VS Code
2. **Push** ke GitHub: `git push origin main`
3. **Render auto-deploy** dari GitHub

### Git Commands

```bash
# Update
git add .
git commit -m "Update: deskripsi perubahan"
git push origin main

# Pull update dari GitHub
git pull origin main
```

---

## 📝 Changelog

| Versi | Perubahan                                                            |
| ----- | -------------------------------------------------------------------- |
| v1.0  | Initial release — Boost tracking, donasi, Firebase integration       |
| v2.0  | **+ Music Player** (YouTube + Spotify via Lavalink)                  |
| v2.1  | Cogs system — modular architecture                                   |
| v2.2  | Playlist system (save/load/list/delete via Firebase)                 |
| v2.3  | Fix skip spam embed, add search timeout, auto-disconnect when alone  |
| v3.0  | **+ Web Dashboard** — Real-time status, active players, progress bar |
| v3.1  | Refactor: extract utils (formatters, constants), separate web folder |
| v3.2  | **+ SpotifyDown API** integration with triple fallback               |
| v3.3  | Async oEmbed/HTML scrape fallback, fix blocking I/O in `/lyrics`     |
| v3.4  | Playlist embed + auto-play first track, update Lavalink nodes        |

---

## 👨‍💻 Developer

- **Discord**: `zeeeinz`
- **GitHub**: [github.com/zeeinz-ux](https://github.com/zeeinz-ux)

---

> **Note**: Bot ini menggunakan `discord.py` v2.7+ dan `wavelink` v3.0+. Pastikan Python versi 3.10+ terinstall.
>
> **Butuh bantuan?** Buka issue di GitHub atau hubungi developer via Discord.
