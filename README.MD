# 🤖 Discord Bot — Boost Tracker + Music Player + Donation System

Bot Discord all-in-one dengan fitur tracking server boost, pencatatan donasi, dan **music player kualitas jernih** dari YouTube & Spotify. Support 24/7 via UptimeRobot.

---

## ✨ Fitur

| Fitur                       | Deskripsi                                                             |
| --------------------------- | --------------------------------------------------------------------- |
| 🚀 **Auto Boost Detection** | Deteksi otomatis member yang boost/unboost server                     |
| 💰 **Donasi Tracker**       | Catat donasi dengan `/donasi`                                         |
| 📊 **Cek Riwayat Boost**    | Cek status boost user dengan `/cekboost`                              |
| 🧪 **Simulasi Boost**       | Testing boost dengan `/testboost` (Admin only)                        |
| 🎵 **Music Player**         | Putar lagu dari **YouTube** & **Spotify** dengan kualitas **320kbps** |
| 🔥 **Firebase Firestore**   | Database real-time untuk menyimpan data                               |
| 🌐 **24/7 Uptime**          | Flask server untuk UptimeRobot ping                                   |
| 🔒 **Secure**               | Token & key disimpan di environment variables                         |
| 🔄 **Cogs System**          | Modular — tiap fitur di file terpisah                                 |

---

## 🎵 Music Player Features

| Command            | Deskripsi                                                   |
| ------------------ | ----------------------------------------------------------- |
| `/play <query>`    | Putar lagu dari YouTube URL, Spotify URL, atau search query |
| `/pause`           | Pause lagu                                                  |
| `/resume`          | Lanjutkan lagu                                              |
| `/skip`            | Skip ke lagu berikutnya                                     |
| `/stop`            | Stop & keluar voice channel                                 |
| `/queue`           | Lihat antrian lagu                                          |
| `/nowplaying`      | Info lagu yang sedang diputar                               |
| `/volume <0-1000>` | Atur volume bot (default 100)                               |
| `/loop <mode>`     | Atur loop: off / single / queue                             |
| `/shuffle`         | Acak antrian lagu                                           |
| `/autoplay`        | Toggle autoplay saat queue habis                            |
| `/playlist save`   | Simpan queue sebagai playlist                               |
| `/playlist load`   | Muat playlist ke queue                                      |
| `/playlist list`   | Lihat daftar playlist                                       |
| `/playlist delete` | Hapus playlist                                              |

### Kualitas Audio

- **Codec**: OPUS (via Lavalink)
- **Sample Rate**: 48kHz
- **Channels**: Stereo (2.0)
- **Source**: YouTube (auto-search untuk Spotify)

---

## 📁 Struktur Project

```
discord-bot/
├── main.py                     # Entry point bot + Flask keep-alive + Lavalink connect
├── .env                        # Environment variables (JANGAN DI-COMMIT!)
├── .env.example                # Template .env
├── .gitignore                  # Melindungi file sensitif
├── requirements.txt            # Dependencies
├── serviceAccountKey.json      # Firebase key (VS Code only, JANGAN DI-COMMIT!)
├── cogs/
│   ├── __init__.py             # Package init
│   ├── music.py                # Music Player (YouTube + Spotify + Playlist)
│   ├── general.py              # Ping, stats, help commands
│   ├── boost.py                # Boost Tracker
│   ├── donation.py             # Donation Tracker
│   └── firebase_setup.py       # Firebase Firestore init (dual mode)
└── lavalink/
    ├── Lavalink.jar            # Lavalink server v4.2.2
    ├── application.yml         # Lavalink config
    ├── plugins/                # Auto-downloaded plugins
    └── logs/                   # Lavalink logs
```

---

## 🚀 Quick Start

### 1. Clone Repository

```bash
git clone https://github.com/zeeinz-ux/my-discord-bot.git
cd my-discord-bot/discord-bot
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

#### Untuk VS Code (Lokal)

1. Copy `.env.example` jadi `.env`:

```bash
cp .env.example .env
```

2. Edit `.env`:

```env
# WAJIB
TOKEN_BOT=your_discord_bot_token_here
FIREBASE_KEY=serviceAccountKey.json

# Lavalink (lokal)
LAVALINK_HOST=127.0.0.1
LAVALINK_PORT=2333
LAVALINK_PASSWORD=youshallnotpass
LAVALINK_SECURE=false

# OPSIONAL (untuk Spotify)
SPOTIFY_CLIENT_ID=your_spotify_client_id
SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
```

3. Download `serviceAccountKey.json` dari [Firebase Console](https://console.firebase.google.com/)

#### Untuk Replit (Cloud/24-7)

1. Buka tab **Secrets** (ikon 🔒 di sidebar kiri)
2. Tambahkan key:

| Key                     | Value                                   |
| ----------------------- | --------------------------------------- |
| `TOKEN_BOT`             | `your_discord_bot_token`                |
| `FIREBASE_KEY`          | Paste JSON service account **1 baris**  |
| `LAVALINK_HOST`         | `127.0.0.1` (atau public node)          |
| `LAVALINK_PORT`         | `2333`                                  |
| `LAVALINK_PASSWORD`     | `youshallnotpass`                       |
| `LAVALINK_SECURE`       | `false`                                 |
| `SPOTIFY_CLIENT_ID`     | `your_spotify_client_id` (opsional)     |
| `SPOTIFY_CLIENT_SECRET` | `your_spotify_client_secret` (opsional) |

> **Convert JSON ke 1 baris**:
>
> ```bash
> python -c "import json; print(json.dumps(json.load(open('serviceAccountKey.json'))))"
> ```

### 4. Setup Lavalink (Lokal)

1. Pastikan **Java 17+** terinstall
2. Jalankan Lavalink:

```bash
cd lavalink
java -jar Lavalink.jar
# Tunggu "Lavalink is ready to accept connections."
# BIARKAN WINDOW INI TERBUKA
```

3. Di window baru, jalankan bot:

```bash
python main.py
```

### 5. Setup Spotify API (Opsional)

1. Buka [Spotify Developer Dashboard](https://developer.spotify.com/dashboard/)
2. Create App → dapatkan **Client ID** & **Client Secret**
3. Masukkan ke `.env` atau Replit Secrets

---

## 🤖 Menjalankan Bot

### VS Code (Development)

**Terminal 1 — Lavalink:**

```bash
cd lavalink
java -jar Lavalink.jar
```

**Terminal 2 — Bot:**

```bash
python main.py
```

Output yang diharapkan:

```
[LAVALINK] Node main ready! (Session ID: ...)
Bot logged in as Hidden Hamlet#1614 (ID: ...)
Connected to 1 guilds
Synced 18 slash commands
```

### Replit (Production/24-7)

1. Klik tombol **Run** ▶️
2. Bot akan otomatis jalan dengan web server di port 8080

> ⚠️ **Note**: Replit tidak support Lavalink Java jar. Gunakan public Lavalink node atau self-host di VPS terpisah untuk music feature.

---

## 🌐 Setup 24/7 dengan UptimeRobot

1. Daftar di [UptimeRobot](https://uptimerobot.com) (Free)
2. Klik **"Add New Monitor"**
3. Setting:

| Field               | Value                                    |
| ------------------- | ---------------------------------------- |
| Monitor Type        | HTTP(s)                                  |
| Friendly Name       | Discord Bot Keep Alive                   |
| URL                 | `https://nama-repl-username.replit.app/` |
| Monitoring Interval | Every 5 minutes                          |

> Replit akan sleep setelah idle, tapi UptimeRobot akan ping setiap 5 menit → bot tetap online!

---

## 📋 Daftar Slash Command

### 🌐 General

| Command  | Deskripsi            |
| -------- | -------------------- |
| `/ping`  | Cek latency bot      |
| `/stats` | Statistik bot        |
| `/help`  | Daftar semua command |

### 🎵 Music

| Command            | Deskripsi                           |
| ------------------ | ----------------------------------- |
| `/play <query>`    | Putar lagu (YouTube/Spotify/search) |
| `/pause`           | Pause lagu                          |
| `/resume`          | Lanjutkan lagu                      |
| `/skip`            | Skip lagu                           |
| `/stop`            | Stop & keluar VC                    |
| `/queue`           | Lihat antrian                       |
| `/nowplaying`      | Info lagu sekarang                  |
| `/volume <0-1000>` | Atur volume                         |
| `/loop <mode>`     | Atur loop: off/single/queue         |
| `/shuffle`         | Acak queue                          |
| `/autoplay`        | Toggle autoplay                     |
| `/playlist save`   | Simpan queue sebagai playlist       |
| `/playlist load`   | Muat playlist                       |
| `/playlist list`   | Lihat playlist                      |
| `/playlist delete` | Hapus playlist                      |

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

# Play dari Spotify URL

/play query:https://open.spotify.com/track/...

# Play playlist YouTube Mix

/play query:https://www.youtube.com/watch?v=...&list=RD...

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
- `lavalink/logs/` — Log Lavalink

### JANGAN PERNAH:

- ❌ Commit token/key ke GitHub
- ❌ Share screenshot `.env` atau Secrets
- ❌ Push `serviceAccountKey.json` ke repo publik

### Jika Token Terexpose:

1. Segera **reset token** di [Discord Developer Portal](https://discord.com/developers/applications)
2. Update `.env` / Replit Secrets dengan token baru
3. Restart bot

---

## 🔄 Workflow Development

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   VS Code   │────▶│   GitHub    │────▶│   Replit    │
│  (Dev/Test) │     │   (Repo)    │     │ (Production)│
└─────────────┘     └─────────────┘     └─────────────┘
      │                                           │
      └──────────── Import dari GitHub ───────────┘
```

1. **Edit & test** di VS Code
2. **Push** ke GitHub: `git push origin main`
3. **Pull** di Replit dari GitHub (tab Git → Pull)
4. **Run** di Replit untuk 24/7 uptime

### Git Commands

```bash
# Inisialisasi repo
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/zeeinz-ux/my-discord-bot.git
git push -u origin main

# Update
git add .
git commit -m "Update: deskripsi perubahan"
git push origin main

# Pull update dari GitHub
git pull origin main
```

---

## 🛠️ Troubleshooting

| Error                           | Penyebab                   | Solusi                                                           |
| ------------------------------- | -------------------------- | ---------------------------------------------------------------- |
| `TOKEN_BOT tidak ditemukan`     | `.env` tidak terbaca       | Pastikan `python-dotenv` terinstall, file `.env` ada di root     |
| `FIREBASE_KEY bukan JSON valid` | Format JSON salah          | VS Code: pastikan path file benar. Replit: pastikan JSON 1 baris |
| `Database tidak aktif`          | Firebase gagal konek       | Cek internet, validasi service account key                       |
| `Channel tidak ditemukan`       | Bot belum join server      | Invite bot ke server, cek channel ID                             |
| `Slash command tidak muncul`    | Belum di-sync              | Tunggu 1-5 menit, atau restart bot                               |
| `Module not found`              | Dependencies belum install | Jalankan `pip install -r requirements.txt`                       |
| `Permission denied`             | Bot tidak punya izin       | Cek role permission di server Discord                            |
| `Lavalink not connected`        | Lavalink belum jalan       | Jalankan `java -jar Lavalink.jar` dulu sebelum `python main.py`  |
| `/play hang/stuck`              | Search timeout             | Cek koneksi internet, coba query lain                            |
| `/skip spam embed`              | Race condition             | Pastikan pakai versi `music.py` terbaru                          |

---

## 📦 Dependencies

| Package        | Versi    | Fungsi                                 |
| -------------- | -------- | -------------------------------------- |
| discord.py     | >=2.4.0  | Library Discord bot                    |
| wavelink       | >=3.4.0  | Lavalink client untuk music            |
| firebase-admin | >=6.2.0  | Firebase Firestore integration         |
| flask          | >=2.3.0  | Fake web server untuk UptimeRobot      |
| python-dotenv  | >=1.0.0  | Load environment variables dari `.env` |
| requests       | >=2.34.0 | HTTP requests (Spotify API)            |
| PyNaCl         | >=1.5.0  | Voice encryption                       |

---

## 📝 Changelog

| Versi | Perubahan                                                             |
| ----- | --------------------------------------------------------------------- |
| v1.0  | Initial release — Boost tracking, donasi, Firebase integration        |
| v1.1  | Dual mode Firebase (file path & JSON string), improved error handling |
| v2.0  | **+ Music Player** (YouTube + Spotify via Lavalink)                   |
| v2.1  | Cogs system — modular architecture                                    |
| v2.2  | Playlist system (save/load/list/delete via Firebase)                  |
| v2.3  | Fix skip spam embed (lowercase reason), add search timeout            |

---

## 👨‍💻 Developer

- **Discord**: `!zeenz`
- **GitHub**: [github.com/zeeinz-ux](https://github.com/zeeinz-ux)
- **Replit**: [replit.com/@zeezeeinz](https://replit.com/@zeezeeinz)

---

## 📄 Lisensi

MIT License — Bebas modifikasi dan distribusi.

---

> **Note**: Bot ini menggunakan `discord.py` v2.4+ dan `wavelink` v3.5+. Pastikan Python versi 3.10+ terinstall.
>
> **Butuh bantuan?** Buka issue di GitHub atau hubungi developer via Discord.
