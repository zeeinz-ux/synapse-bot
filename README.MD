# 🤖 Hidden Hamlet — Discord Bot

<<<<<<< HEAD
Bot Discord all-in-one dengan fitur tracking server boost, pencatatan donasi, music player kualitas jernih dari YouTube & Spotify, **welcome announcement otomatis**, dan **web dashboard real-time**. Support 24/7 via UptimeRobot.
=======
Bot Discord all-in-one dengan fitur tracking server boost, pencatatan donasi, music player kualitas jernih dari YouTube & Spotify, **welcome announcement otomatis**, **web dashboard real-time dengan sidebar navigation**, dan **AI Chat** (coming soon). Support 24/7 via UptimeRobot.
>>>>>>> v3.6-sidebar

---

## ✨ Fitur

<<<<<<< HEAD
| Fitur                       | Deskripsi                                                             |
| --------------------------- | --------------------------------------------------------------------- |
| 🚀 **Auto Boost Detection** | Deteksi otomatis member yang boost/unboost server                     |
| 💰 **Donasi Tracker**       | Catat donasi dengan `/donasi`                                         |
| 📊 **Cek Riwayat Boost**    | Cek status boost user dengan `/cekboost`                              |
| 🧪 **Simulasi Boost**       | Testing boost dengan `/testboost` (Admin only)                        |
| 🎵 **Music Player**         | Putar lagu dari **YouTube** & **Spotify** dengan kualitas **320kbps** |
| 👋 **Welcome Announcement** | Sambut member baru otomatis dengan pesan kustom + embed               |
| 📊 **Web Dashboard**        | Status bot real-time + pengaturan welcome per server                  |
| 🔥 **Firebase Firestore**   | Database real-time untuk menyimpan data                               |
| 🌐 **24/7 Uptime**          | Flask server untuk UptimeRobot ping                                   |
| 🔒 **Secure**               | Token & key disimpan di environment variables                         |
| 🔄 **Cogs System**          | Modular — tiap fitur di file terpisah                                 |
=======
| Fitur | Deskripsi |
|-------|-----------|
| 🚀 **Auto Boost Detection** | Deteksi otomatis member yang boost/unboost server |
| 💰 **Donasi Tracker** | Catat donasi dengan `/donasi` |
| 📊 **Cek Riwayat Boost** | Cek status boost user dengan `/cekboost` |
| 🧪 **Simulasi Boost** | Testing boost dengan `/testboost` (Admin only) |
| 🎵 **Music Player** | Putar lagu dari **YouTube** & **Spotify** dengan kualitas **320kbps** |
| 👋 **Welcome Announcement** | Sambut member baru otomatis dengan pesan kustom + embed |
| 📊 **Web Dashboard** | Status bot real-time + pengaturan per server dengan sidebar navigation |
| 🧠 **AI Chat** | Chat bot AI powered by Google Gemini API (coming soon) |
| 🔥 **Firebase Firestore** | Database real-time untuk menyimpan data |
| 🌐 **24/7 Uptime** | Flask server untuk UptimeRobot ping |
| 🔒 **Secure** | Token & key disimpan di environment variables |
| 🔄 **Cogs System** | Modular — tiap fitur di file terpisah |

---

## 👋 Welcome Announcement (v3.5)

Kirim pesan sambutan otomatis saat member baru bergabung ke server.

### Konfigurasi via Web Dashboard

```
http://your-bot-url/dashboard/<guild_id>/welcome
```

### Fitur Welcome:

| Opsi | Deskripsi |
|------|-----------|
| **Toggle On/Off** | Aktifkan/nonaktifkan welcome message |
| **Channel Selection** | Pilih channel tujuan dari dropdown |
| **Custom Message** | Teks bebas dengan placeholder `{user}` dan `{server}` |
| **Embed Mode** | Kirim sebagai Discord embed dengan warna kustom |
| **Accent Color** | Picker warna untuk garis embed (hex) |
| **Embed Title** | Judul kustom untuk embed |
| **Background Image** | URL gambar banner di bawah embed |
| **Live Preview** | Preview real-time saat mengubah pengaturan |

### Placeholder:

| Placeholder | Hasil |
|-------------|-------|
| `{user}` | Mention user baru (`@username`) |
| `{server}` | Nama server Discord |

### Firestore Schema:

```json
{
  "welcome": {
    "enabled": true,
    "channel_id": "123456789012345678",
    "message_text": "Halo {user}, selamat datang di {server}! 🎉",
    "is_embed": true,
    "embed_color": "#5865F2",
    "embed_title": "👋 Selamat Datang!",
    "bg_image_url": "https://example.com/welcome-banner.png"
  }
}
```
>>>>>>> v3.6-sidebar

---

## 👋 Welcome Announcement (v3.5)

Kirim pesan sambutan otomatis saat member baru bergabung ke server.

### Konfigurasi via Web Dashboard

```
http://your-bot-url/dashboard/<guild_id>/welcome
```

### Fitur Welcome:

| Opsi                  | Deskripsi                                             |
| --------------------- | ----------------------------------------------------- |
| **Toggle On/Off**     | Aktifkan/nonaktifkan welcome message                  |
| **Channel Selection** | Pilih channel tujuan dari dropdown                    |
| **Custom Message**    | Teks bebas dengan placeholder `{user}` dan `{server}` |
| **Embed Mode**        | Kirim sebagai Discord embed dengan warna kustom       |
| **Accent Color**      | Picker warna untuk garis embed (hex)                  |
| **Embed Title**       | Judul kustom untuk embed                              |
| **Background Image**  | URL gambar banner di bawah embed                      |
| **Live Preview**      | Preview real-time saat mengubah pengaturan            |

### Placeholder:

| Placeholder | Hasil                           |
| ----------- | ------------------------------- |
| `{user}`    | Mention user baru (`@username`) |
| `{server}`  | Nama server Discord             |

### Firestore Schema:

```json
{
  "welcome": {
    "enabled": true,
    "channel_id": "123456789012345678",
    "message_text": "Halo {user}, selamat datang di {server}! 🎉",
    "is_embed": true,
    "embed_color": "#5865F2",
    "embed_title": "👋 Selamat Datang!",
    "bg_image_url": "https://example.com/welcome-banner.png"
  }
}
```

---

## 🎵 Music Player Features

| Command | Deskripsi |
|---------|-----------|
| `/play <query>` | Putar lagu dari YouTube URL, Spotify URL, atau search query |
| `/pause` | Pause lagu |
| `/resume` | Lanjutkan lagu |
| `/skip` | Skip ke lagu berikutnya |
| `/stop` | Stop & keluar voice channel |
| `/queue` | Lihat antrian lagu |
| `/nowplaying` | Info lagu yang sedang diputar |
| `/volume <0-1000>` | Atur volume bot (default 100) |
| `/loop <mode>` | Atur loop: off / single / queue |
| `/shuffle` | Acak antrian lagu |
| `/autoplay` | Toggle autoplay saat queue habis |
| `/seek <position>` | Skip ke posisi tertentu (format: 1:30 atau 90) |
| `/remove <index>` | Hapus lagu dari queue |
| `/move <from> <to>` | Pindah posisi lagu di queue |
| `/skipto <index>` | Skip ke lagu nomor tertentu |
| `/disconnect` | Keluar dari voice channel |
| `/clearqueue` | Kosongkan queue tanpa stop lagu |
| `/replay` | Putar ulang lagu dari awal |
| `/lyrics [query]` | Cari lirik lagu |
| `/playlist save <name>` | Simpan queue sebagai playlist |
| `/playlist load <name>` | Muat playlist ke queue |
| `/playlist list` | Lihat daftar playlist |
| `/playlist delete <name>` | Hapus playlist |

### Kualitas Audio

- **Codec**: OPUS (via Lavalink)
- **Sample Rate**: 48kHz
- **Channels**: Stereo (2.0)
- **Source**: YouTube (auto-search untuk Spotify)

---

## 📊 Web Dashboard (v3.6)

<<<<<<< HEAD
Akses status bot real-time dan pengaturan welcome per server:

| URL                             | Deskripsi                                |
| ------------------------------- | ---------------------------------------- |
| `/`                             | Landing page — links ke Dashboard & API  |
| `/dashboard`                    | Full status dashboard (auto-refresh 10s) |
| `/dashboard/<guild_id>/welcome` | Pengaturan welcome untuk server tertentu |
| `/api/stats`                    | JSON API untuk integrasi eksternal       |
=======
Dashboard dengan **sidebar navigation** untuk akses cepat semua fitur per server.

### URL Routes

| URL | Deskripsi |
|-----|-----------|
| `/` | Landing page — links ke Dashboard & API |
| `/dashboard` | Redirect ke server pertama |
| `/dashboard/<guild_id>/` | Main dashboard dengan stats real-time |
| `/dashboard/<guild_id>/welcome` | Pengaturan welcome untuk server tertentu |
| `/dashboard/<guild_id>/settings` | Bot settings (placeholder) |
| `/dashboard/<guild_id>/music` | Music player controls (placeholder) |
| `/dashboard/<guild_id>/boost` | Boost tracker riwayat (placeholder) |
| `/dashboard/<guild_id>/donation` | Donation riwayat (placeholder) |
| `/dashboard/<guild_id>/ai-chat` | AI Chat settings (placeholder — coming soon) |
| `/api/stats` | JSON API untuk integrasi eksternal |
>>>>>>> v3.6-sidebar

### Dashboard Menampilkan

- **Bot Status**: online/offline, uptime, username
- **Statistics**: jumlah server & total member
<<<<<<< HEAD
- **Server List**: Daftar server dengan link ke welcome settings
=======
- **Server Selector**: Dropdown pilih server (guild) aktif
>>>>>>> v3.6-sidebar
- **Lavalink**: connection status & node URI
- **Active Players**: guild yang sedang play music
  - Judul lagu, author, artwork
- **Progress bar** dengan position/duration
- **Queue size**, jumlah listener, status pause
- **Sidebar Navigation**: Akses cepat ke semua modul
  - General, Music, Announcements, Boost Tracker, Donation, Tools
- **Dark theme** dengan CSS :root variables
- **Responsive** layout (desktop, tablet, mobile)

---

## 🧠 AI Chat (Coming Soon)

Chat bot AI powered by **Google Gemini API** dengan penyimpanan di **Firebase Firestore**.

### Fitur yang Direncanakan:

| Fitur | Deskripsi |
|-------|-----------|
| **Personality Customization** | Atur gaya bicara AI: friendly, formal, tsundere, dll |
| **Chat History** | Simpan percakapan per user & per server di Firestore |
| **Context-Aware** | AI ingat percakapan sebelumnya dalam session |
| **Dashboard Settings** | Atur API key, model Gemini, max tokens, temperature |
| **Usage Stats** | Analytics penggunaan AI per server |
| **Commands** | `/chat`, `/reset`, `/personality` |

---

## 📁 Struktur Project (v3.6 — Frontend/Backend Separation)

```
<<<<<<< HEAD
my-discord-bot/
├── main.py                     # Entry point (bot + Flask thread + stats updater)
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
│   ├── welcome.py              # Welcome Announcement (on_member_join)
│   └── firebase_setup.py       # Firebase Firestore init (dual mode)
│
├── utils/                      # Shared helpers (DRY)
│   ├── __init__.py
│   ├── constants.py            # LAVALINK_NODES config
│   └── formatters.py           # format_duration(), format_uptime()
│
└── web/                        # Flask dashboard
    ├── __init__.py
    ├── web_app.py              # Flask app, routes, shared stats + welcome routes
    ├── static/
    │   └── css/
    │       ├── dashboard.css   # Dark theme with :root variables
    │       └── welcome_settings.css  # Welcome page custom styles
    └── templates/
        ├── dashboard.html      # Main dashboard Jinja2 template
        └── welcome_settings.html  # Welcome settings form
=======
discord-bot/
├── backend/                    # Python backend ONLY
│   ├── __init__.py             # Package marker
│   ├── main.py                 # Entry point: bot + Flask + stats updater
│   ├── .env                    # Environment variables (JANGAN DI-COMMIT!)
│   ├── .env.example            # Template environment variables
│   ├── serviceAccountKey.json  # Firebase private key (JANGAN DI-COMMIT!)
│   ├── cogs/                   # Discord bot cogs
│   │   ├── __init__.py
│   │   ├── music.py            # Music Player (Lavalink/Wavelink)
│   │   ├── spotify_down.py     # Spotify resolver utility (NOT a cog)
│   │   ├── general.py          # Ping, stats, help commands
│   │   ├── boost.py            # Boost Tracker
│   │   ├── donation.py         # Donation Tracker
│   │   ├── welcome.py          # Welcome Announcement
│   │   └── firebase_setup.py   # Firebase Firestore initialization
│   ├── utils/                  # Shared helpers
│   │   ├── __init__.py
│   │   ├── constants.py        # LAVALINK_NODES config
│   │   └── formatters.py       # format_duration(), format_uptime()
│   └── web/                    # Flask web server
│       ├── __init__.py
│       └── web_app.py          # Flask routes, dashboard, API
│
├── frontend/                   # HTML + CSS + JS ONLY
│   ├── static/
│   │   ├── css/
│   │   │   ├── dashboard.css       # Main dashboard styles
│   │   │   ├── sidebar.css         # Sidebar navigation styles
│   │   │   └── welcome_settings.css # Welcome page styles
│   │   └── js/
│   │       ├── sidebar.js          # Sidebar behavior (collapse, search, etc)
│   │       ├── welcome.js          # Welcome form handling
│   │       └── dashboard.js        # Dashboard auto-refresh
│   └── templates/
│       ├── base.html               # Base template with sidebar
│       ├── dashboard.html          # Main dashboard
│       ├── welcome_settings.html   # Welcome configuration
│       ├── music_settings.html     # Music player (placeholder)
│       ├── boost_settings.html     # Boost tracker (placeholder)
│       ├── donation_settings.html  # Donation tracker (placeholder)
│       ├── settings.html           # Bot settings (placeholder)
│       ├── message_builder.html    # Message builder (placeholder)
│       ├── templates.html          # Templates (placeholder)
│       ├── actions.html            # Auto actions (placeholder)
│       ├── auto_responders.html    # Auto responders (placeholder)
│       └── ai_chat.html            # AI Chat (placeholder)
│
├── .gitignore                  # Protect sensitive files
├── LICENSE
├── README.md                   # Dokumentasi ini
└── requirements.txt            # Python dependencies
>>>>>>> v3.6-sidebar
```

**Catatan**: `spotify_down.py` adalah utility module (bukan cog) yang digunakan oleh `music.py` untuk resolve Spotify URLs. Tidak muncul di sidebar dashboard.

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

Copy `.env.example` ke `backend/.env`:

```bash
cp backend/.env.example backend/.env
```

Edit `backend/.env`:

```env
# WAJIB
TOKEN_BOT=your_discord_bot_token_here

# OPSIONAL (untuk Spotify fallback ke Official API)
SPOTIFY_CLIENT_ID=your_spotify_client_id
SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
```

<<<<<<< HEAD
> **Note:** `SPOTIFY_CLIENT_ID` & `SECRET` opsional — bot tetap jalan pakai SpotifyDown API atau oEmbed fallback.

### 4. Jalankan Bot
=======
> **Note**: `SPOTIFY_CLIENT_ID` & `SECRET` opsional — bot tetap jalan pakai SpotifyDown API atau oEmbed fallback.

### 4. Setup Firebase

1. Download `serviceAccountKey.json` dari Firebase Console
2. Letakkan di `backend/serviceAccountKey.json`
3. Pastikan `FIREBASE_KEY=serviceAccountKey.json` di `backend/.env`

### 5. Jalankan Bot
>>>>>>> v3.6-sidebar

```bash
# DARI ROOT FOLDER (bukan dari dalam backend/)
python backend/main.py
```

Output yang diharapkan:

```
[FIREBASE] ✅ Berhasil terhubung ke Firestore!
[LAVALINK] ✅ Node 1 tersambung: https://lavalink.jirayu.net:13592
[STATUS] 🤖 Hidden Hamlet SEKARANG SUDAH ONLINE!
[STATUS] Terhubung ke 1 server Discord.
<<<<<<< HEAD
[COG] ✅ Total 5 cogs loaded!  (including welcome.py)
=======
[COG] ✅ Total 6 cogs loaded!
>>>>>>> v3.6-sidebar
[SYNC] ✅ 26 slash command(s) berhasil di-sync!
[DASHBOARD] 📊 Stats updater aktif (30s).
```

- Bot Discord aktif
- Flask server jalan di port 8080
- Dashboard: http://127.0.0.1:8080/dashboard
- Welcome Settings: http://127.0.0.1:8080/dashboard/GUILD_ID/welcome

---

## 🌐 Deploy ke Render (24/7)

### 1. Push ke GitHub

```bash
git add .
<<<<<<< HEAD
git commit -m "v3.5: Welcome Announcement feature"
=======
git commit -m "v3.6: Sidebar Navigation + Frontend/Backend Separation"
>>>>>>> v3.6-sidebar
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
   - **Start Command**: `python backend/main.py`
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

| Command | Deskripsi |
|---------|-----------|
| `/ping` | Cek latency bot |
| `/stats` | Statistik bot |
| `/help` | Daftar semua command |

### 🎵 Music

| Command | Deskripsi |
|---------|-----------|
| `/play <query>` | Putar lagu (YouTube/Spotify/search) |
| `/pause` | Pause lagu |
| `/resume` | Lanjutkan lagu |
| `/skip` | Skip lagu |
| `/stop` | Stop & keluar VC |
| `/queue` | Lihat antrian |
| `/nowplaying` | Info lagu sekarang |
| `/volume <0-1000>` | Atur volume |
| `/loop <mode>` | Atur loop: off/single/queue |
| `/shuffle` | Acak queue |
| `/autoplay` | Toggle autoplay |
| `/seek <position>` | Skip ke posisi (1:30 atau 90) |
| `/remove <index>` | Hapus dari queue |
| `/move <from> <to>` | Pindah posisi lagu |
| `/skipto <index>` | Skip ke nomor tertentu |
| `/disconnect` | Keluar VC |
| `/clearqueue` | Kosongkan queue |
| `/replay` | Ulang dari awal |
| `/lyrics [query]` | Cari lirik |
| `/playlist save <name>` | Simpan playlist |
| `/playlist load <name>` | Muat playlist |
| `/playlist list` | Lihat playlist |
| `/playlist delete <name>` | Hapus playlist |

### 🚀 Boost

| Command | Deskripsi | Permission |
|---------|-----------|------------|
| `/cekboost [@user]` | Cek riwayat boost | Everyone |
| `/testboost [@user]` | Simulasi boost | Administrator |

### 💰 Donation

| Command | Deskripsi |
|---------|-----------|
| `/donasi <nominal> <metode>` | Catat donasi |

---

## 🎵 Contoh Penggunaan Music

```markdown
# Play dari search query
/play query:alan walker faded

# Play dari YouTube URL
/play query:https://youtube.com/watch?v=...

# Play dari Spotify URL (track)
<<<<<<< HEAD

/play query:https://open.spotify.com/track/11dFghVXANMlKmJXsNCbNl

# Play dari Spotify URL (playlist)

=======
/play query:https://open.spotify.com/track/11dFghVXANMlKmJXsNCbNl

# Play dari Spotify URL (playlist)
>>>>>>> v3.6-sidebar
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

<<<<<<< HEAD
| Source                   | Kecepatan  | Reliability     | Auth                  |
| ------------------------ | ---------- | --------------- | --------------------- |
| **SpotifyDown API**      | ⚡ Fastest | ⚠️ Bisa down    | ❌ No auth            |
| **Spotify Official API** | ⚡ Fast    | ✅ Stable       | ✅ Client ID + Secret |
| **oEmbed**               | 🐢 Medium  | ✅ Always works | ❌ No auth            |
| **HTML Scrape**          | 🐢 Slow    | ⚠️ Fragile      | ❌ No auth            |
=======
| Source | Kecepatan | Reliability | Auth |
|--------|-----------|-------------|------|
| **SpotifyDown API** | ⚡ Fastest | ⚠️ Bisa down | ❌ No auth |
| **Spotify Official API** | ⚡ Fast | ✅ Stable | ✅ Client ID + Secret |
| **oEmbed** | 🐢 Medium | ✅ Always works | ❌ No auth |
| **HTML Scrape** | 🐢 Slow | ⚠️ Fragile | ❌ No auth |
>>>>>>> v3.6-sidebar

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

### Collection: `guild_settings`

```json
{
  "welcome": {
    "enabled": true,
    "channel_id": "123456789012345678",
    "message_text": "Halo {user}, selamat datang di {server}! 🎉",
    "is_embed": true,
    "embed_color": "#5865F2",
    "embed_title": "👋 Selamat Datang!",
    "bg_image_url": "https://example.com/welcome-banner.png"
  }
}
```

<<<<<<< HEAD
=======
### Collection: `ai_chat` (Coming Soon)

```json
{
  "user_id": "123456789",
  "guild_id": "987654321",
  "personality": "friendly",
  "history": [
    {
      "role": "user",
      "content": "Halo bot!",
      "timestamp": "2026-05-20T10:00:00Z"
    },
    {
      "role": "assistant",
      "content": "Halo! Ada yang bisa saya bantu?",
      "timestamp": "2026-05-20T10:00:01Z"
    }
  ],
  "created_at": "timestamp",
  "updated_at": "timestamp"
}
```

>>>>>>> v3.6-sidebar
---

## 🔒 Keamanan

### File yang WAJIB di-ignore (sudah di `.gitignore`):

- `backend/.env` — Berisi token bot
- `backend/serviceAccountKey.json` — Private key Firebase
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

<<<<<<< HEAD
| Error                        | Penyebab                   | Solusi                                                        |
| ---------------------------- | -------------------------- | ------------------------------------------------------------- |
| `TOKEN_BOT tidak ditemukan`  | `.env` tidak terbaca       | Pastikan `python-dotenv` terinstall, file `.env` ada di root  |
| `Module not found: wavelink` | Dependencies belum install | Jalankan `pip install -r requirements.txt`                    |
| `Lavalink not connected`     | Node tidak tersedia        | Cek koneksi internet, node mungkin down                       |
| `Slash command tidak muncul` | Belum di-sync              | Tunggu 1-5 menit, atau restart bot                            |
| `Permission denied`          | Bot tidak punya izin       | Cek role permission di server Discord                         |
| `/play hang/stuck`           | Search timeout             | Cek koneksi internet, coba query lain                         |
| `Dashboard 404`              | Route tidak terdaftar      | Cek `web/web_app.py`, pastikan `/dashboard` route ada         |
| `CSS tidak load`             | Path static salah          | Cek `static_folder` di Flask app                              |
| `Welcome page error 500`     | Jinja2 syntax error        | Pastikan `==` (comparison) bukan `=` (assignment) di template |
| `SpotifyDown API down`       | API tidak tersedia         | Fallback ke oEmbed/HTML scrape otomatis                       |
| `YouTube 403`                | Lavalink node ke-block     | Ganti node di `utils/constants.py`                            |
=======
| Error | Penyebab | Solusi |
|-------|----------|--------|
| `TOKEN_BOT tidak ditemukan` | `.env` tidak terbaca | Pastikan `python-dotenv` terinstall, file `backend/.env` ada |
| `Module not found: backend` | sys.path tidak include root | Pastikan `sys.path.insert(0, _project_root)` di `backend/main.py` |
| `Module not found: wavelink` | Dependencies belum install | Jalankan `pip install -r requirements.txt` |
| `Lavalink not connected` | Node tidak tersedia | Cek koneksi internet, node mungkin down |
| `Slash command tidak muncul` | Belum di-sync | Tunggu 1-5 menit, atau restart bot |
| `Permission denied` | Bot tidak punya izin | Cek role permission di server Discord |
| `/play hang/stuck` | Search timeout | Cek koneksi internet, coba query lain |
| `Dashboard 404` | Route tidak terdaftar | Cek `backend/web/web_app.py`, pastikan route ada |
| `Dashboard 500` | Jinja2 syntax error | Pastikan `==` (comparison) bukan `=` (assignment) di template |
| `CSS tidak load` | Path static salah | Cek `static_folder` di Flask app (`../../frontend/static`) |
| `TemplateNotFound` | Template tidak ada | Pastikan file `.html` ada di `frontend/templates/` |
| `Guild dropdown empty` | `guilds_list` tidak terkirim | Pastikan `main.py` kirim `guilds_list` ke `set_stats()` |
| `Sidebar tidak muncul` | `base.html` tidak di-extend | Cek `{% extends "base.html" %}` di child templates |
| `SpotifyDown API down` | API tidak tersedia | Fallback ke oEmbed/HTML scrape otomatis |
| `YouTube 403` | Lavalink node ke-block | Ganti node di `backend/utils/constants.py` |
| `spotify_down.py no setup` | Missing `setup()` function | Tambahkan `async def setup(bot): pass` di bottom file |
| **VS Code formatter error** | Prettier merusak Jinja2 | Matikan `formatOnSave` untuk HTML di VS Code settings |

### ⚠️ VS Code Formatter Warning

VS Code Prettier/formatter otomatis bisa merusak **Jinja2 template syntax** (`{% if %}`, `{{ variable }}`) saat save. **Matikan auto-format untuk file `.html`**:

1. Buka VS Code Settings (`Ctrl + ,`)
2. Cari `format on save`
3. Tambahkan ke `settings.json`:
   ```json
   {
     "[html]": {
       "editor.formatOnSave": false
     }
   }
   ```
4. Atau matikan **Auto Save** saat edit template files
>>>>>>> v3.6-sidebar

---

## 📦 Dependencies

<<<<<<< HEAD
| Package        | Versi   | Fungsi                           |
| -------------- | ------- | -------------------------------- |
| discord.py     | >=2.3.0 | Library Discord bot              |
| wavelink       | >=3.0.0 | Lavalink client untuk music      |
| firebase-admin | >=6.2.0 | Firebase Firestore integration   |
| flask          | >=2.3.0 | Web server untuk dashboard       |
| python-dotenv  | >=1.0.0 | Load environment variables       |
| aiohttp        | >=3.9.0 | Async HTTP untuk SpotifyDown API |
| PyNaCl         | >=1.5.0 | Voice encryption                 |
=======
| Package | Versi | Fungsi |
|---------|-------|--------|
| discord.py | >=2.3.0 | Library Discord bot |
| wavelink | >=3.0.0 | Lavalink client untuk music |
| firebase-admin | >=6.2.0 | Firebase Firestore integration |
| flask | >=2.3.0 | Web server untuk dashboard |
| python-dotenv | >=1.0.0 | Load environment variables |
| aiohttp | >=3.9.0 | Async HTTP untuk API calls |
| PyNaCl | >=1.5.0 | Voice encryption |
>>>>>>> v3.6-sidebar

---

## 🔄 Workflow Development

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   VS Code   │────▶│   GitHub    │────▶│   Render    │
│  (Dev/Test) │     │   (Repo)    │     │ (Production)│
└─────────────┘     └─────────────┘     └─────────────┘
```

1. **Edit & test** di VS Code (jalan dari root folder: `python backend/main.py`)
2. **Push** ke GitHub: `git push origin main`
3. **Render auto-deploy** dari GitHub

### Git Commands

```bash
# Update
git add .
git commit -m "v3.6: deskripsi perubahan"
git push origin main

# Pull update dari GitHub
git pull origin main
```

---

## 📝 Changelog

<<<<<<< HEAD
| Versi | Perubahan                                                                             |
| ----- | ------------------------------------------------------------------------------------- |
| v1.0  | Initial release — Boost tracking, donasi, Firebase integration                        |
| v2.0  | **+ Music Player** (YouTube + Spotify via Lavalink)                                   |
| v2.1  | Cogs system — modular architecture                                                    |
| v2.2  | Playlist system (save/load/list/delete via Firebase)                                  |
| v2.3  | Fix skip spam embed, add search timeout, auto-disconnect when alone                   |
| v3.0  | **+ Web Dashboard** — Real-time status, active players, progress bar                  |
| v3.1  | Refactor: extract utils (formatters, constants), separate web folder                  |
| v3.2  | **+ SpotifyDown API** integration with triple fallback                                |
| v3.3  | Async oEmbed/HTML scrape fallback, fix blocking I/O in `/lyrics`                      |
| v3.4  | Playlist embed + auto-play first track, update Lavalink nodes                         |
| v3.5  | **+ Welcome Announcement** — Auto welcome message with embed + web dashboard settings |
=======
| Versi | Perubahan |
|-------|-----------|
| v1.0 | Initial release — Boost tracking, donasi, Firebase integration |
| v2.0 | **+ Music Player** (YouTube + Spotify via Lavalink) |
| v2.1 | Cogs system — modular architecture |
| v2.2 | Playlist system (save/load/list/delete via Firebase) |
| v2.3 | Fix skip spam embed, add search timeout, auto-disconnect when alone |
| v3.0 | **+ Web Dashboard** — Real-time status, active players, progress bar |
| v3.1 | Refactor: extract utils (formatters, constants), separate web folder |
| v3.2 | **+ SpotifyDown API** integration with triple fallback |
| v3.3 | Async oEmbed/HTML scrape fallback, fix blocking I/O in `/lyrics` |
| v3.4 | Playlist embed + auto-play first track, update Lavalink nodes |
| v3.5 | **+ Welcome Announcement** — Auto welcome message with embed + web dashboard settings |
| **v3.6** | **+ Sidebar Navigation** — Frontend/backend separation, sidebar menu, placeholder pages, AI Chat menu |

---

## 🗺️ Roadmap

| Versi | Fitur | Status |
|-------|-------|--------|
| v3.7 | **Responsive Design** — Tablet, mobile, various screen sizes | Planned |
| v3.8 | **GitHub + Render Deployment** — Auto-deploy, CI/CD | Planned |
| v4.0 | **AI Chat** — Gemini API integration, personality, chat history | Planned |
| v4.1 | **Message Builder** — Drag-and-drop embed creator | Planned |
| v4.2 | **Auto Responders** — Keyword-based auto replies | Planned |
| v4.3 | **Actions** — Trigger-based automation | Planned |
>>>>>>> v3.6-sidebar

---

## 👨‍💻 Developer

- **Discord**: `zeeeinz`
- **GitHub**: [github.com/zeeinz-ux](https://github.com/zeeinz-ux)

---

> **Note**: Bot ini menggunakan `discord.py` v2.7+ dan `wavelink` v3.0+. Pastikan Python versi 3.10+ terinstall.
>
> **Butuh bantuan?** Buka issue di GitHub atau hubungi developer via Discord.
