# 🤖 Discord Bot — Boost Tracker + Music Player

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

| Command           | Deskripsi                                                   |
| ----------------- | ----------------------------------------------------------- |
| `/play <query>`   | Putar lagu dari YouTube URL, Spotify URL, atau search query |
| `/pause`          | Pause lagu                                                  |
| `/resume`         | Lanjutkan lagu                                              |
| `/skip`           | Skip ke lagu berikutnya                                     |
| `/stop`           | Stop & keluar voice channel                                 |
| `/queue`          | Lihat antrian lagu                                          |
| `/nowplaying`     | Info lagu yang sedang diputar                               |
| `/volume <0-100>` | Atur volume bot                                             |

### Kualitas Audio

- **Codec**: MP3 320kbps
- **Sample Rate**: 48kHz
- **Channels**: Stereo (2.0)
- **Source**: YouTube (auto-search untuk Spotify)

---

## 📁 Struktur Project

```
discord-bot/
├── main.py                     # Entry point bot
├── cogs/
│   ├── __init__.py             # Package marker
│   ├── firebase_setup.py       # Setup Firebase (dual mode)
│   ├── general.py              # Ping, Stats, Help
│   ├── music.py                # Music Player (YouTube + Spotify)
│   ├── boost.py                # Boost Tracker
│   └── donation.py             # Donation Tracker
├── .env                        # Environment variables (JANGAN DI-COMMIT!)
├── .env.example                # Template .env
├── .gitignore                  # Melindungi file sensitif
├── requirements.txt            # Dependencies
├── serviceAccountKey.json      # Firebase key (VS Code only)
└── README.md                   # Dokumentasi ini
```

---

## 🚀 Quick Start

### 1. Clone Repository

```bash
git clone https://github.com/username/discord-bot.git
cd discord-bot
```

### 2. Install Dependencies

```bash
# Buat virtual environment
python -m venv venv

# Aktifkan venv
# Windows:
venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate

# Install packages
pip install -r requirements.txt
```

> ⚠️ **Note**: Music player butuh **FFmpeg** terinstall di sistem!
>
> - **Windows**: Download dari [ffmpeg.org](https://ffmpeg.org/download.html) dan tambah ke PATH
> - **Mac**: `brew install ffmpeg`
> - **Linux**: `sudo apt install ffmpeg`

### 3. Setup Environment Variables

#### Untuk VS Code (Lokal)

1. Copy `.env.example` jadi `.env`:

```bash
cp .env.example .env
```

2. Edit `.env`:

```env
# WAJIB
token_bot=your_discord_bot_token_here
FIREBASE_KEY=serviceAccountKey.json

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
| `token_bot`             | `your_discord_bot_token`                |
| `FIREBASE_KEY`          | Paste JSON service account **1 baris**  |
| `SPOTIFY_CLIENT_ID`     | `your_spotify_client_id` (opsional)     |
| `SPOTIFY_CLIENT_SECRET` | `your_spotify_client_secret` (opsional) |

> **Convert JSON ke 1 baris**:
>
> ```bash
> python -c "import json; print(json.dumps(json.load(open('serviceAccountKey.json'))))"
> ```

### 4. Setup Spotify API (Opsional)

1. Buka [Spotify Developer Dashboard](https://developer.spotify.com/dashboard/)
2. Create App → dapatkan **Client ID** & **Client Secret**
3. Masukkan ke `.env` atau Replit Secrets

---

## 🤖 Menjalankan Bot

### VS Code (Development)

```bash
python main.py
```

### Replit (Production/24-7)

1. Klik tombol **Run** ▶️
2. Bot akan otomatis jalan dengan web server di port 8080

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

---

## 📋 Daftar Slash Command

### 🌐 General

| Command  | Deskripsi            |
| -------- | -------------------- |
| `/ping`  | Cek latency bot      |
| `/stats` | Statistik bot        |
| `/help`  | Daftar semua command |

### 🎵 Music

| Command           | Deskripsi                           |
| ----------------- | ----------------------------------- |
| `/play <query>`   | Putar lagu (YouTube/Spotify/search) |
| `/pause`          | Pause lagu                          |
| `/resume`         | Lanjutkan lagu                      |
| `/skip`           | Skip lagu                           |
| `/stop`           | Stop & keluar VC                    |
| `/queue`          | Lihat antrian                       |
| `/nowplaying`     | Info lagu sekarang                  |
| `/volume <0-100>` | Atur volume                         |

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

# Atur volume

/volume level:75

# Lihat queue

/queue
```

---

## 🔒 Keamanan

### File yang WAJIB di-ignore:

- `.env`
- `serviceAccountKey.json`

### JANGAN PERNAH:

- ❌ Commit token/key ke GitHub
- ❌ Share screenshot `.env` atau Secrets

---

## 🛠️ Troubleshooting

| Error                       | Solusi                                                  |
| --------------------------- | ------------------------------------------------------- |
| `TOKEN_BOT tidak ditemukan` | Pastikan `.env` ada di root, `python-dotenv` terinstall |
| `FFmpeg not found`          | Install FFmpeg dan tambah ke PATH                       |
| `Spotify features disabled` | Tambahkan SPOTIFY_CLIENT_ID & SECRET                    |
| `Bot tidak join VC`         | Cek permission Connect & Speak                          |
| `Lagu tidak jernih`         | Cek FFmpeg options di `cogs/music.py`                   |

---

## 📦 Dependencies

```
discord.py>=2.3.0
firebase-admin>=6.2.0
flask>=2.3.0
python-dotenv>=1.0.0
yt-dlp>=2024.12.0
spotipy>=2.23.0
PyNaCl>=1.5.0
```

---

## 📝 Changelog

| Versi | Perubahan                                       |
| ----- | ----------------------------------------------- |
| v1.0  | Initial release — Boost & Donation              |
| v2.0  | **+ Music Player** (YouTube + Spotify, 320kbps) |
| v2.1  | Cogs system — modular architecture              |

---

## 👨‍💻 Developer

- **Discord**: `your_discord_username`
- **GitHub**: [github.com/username](https://github.com/username)

---

> **Note**: Bot menggunakan `discord.py` v2.x. Pastikan Python 3.8+ terinstall.
