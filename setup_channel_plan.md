# Server Setup — Channel Structure

## 📁 General

| Channel               | Type | Permission                                                                                                                                               |
| --------------------- | ---- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `#‼️・welcome`        | Text | @everyone read only gak bisa kirim chat                                                                                                                  |
| `#👋・leave`          | Text | @adminonly read                                                                                                                                          |
| `#⚡・support-server` | Text | @everyone read only (ini tinggal setting aja arahin kesini bagi yang boost atau donasi itu cuma munculin embed nya doang kok) |
| `#🚨・report-spam`    | Text | @everyone send (lapor spam udah bekerja di anti spam ai itu) (read only)                                                                                 |

## 📊 SERVER STATS (Voice — gembok, cuma admin bisa join)

| Channel         | Note                                   |
| --------------- | -------------------------------------- |
| `📊 ALL MEMBER` | @everyone connect: False → icon gembok |
| `📊 MEMBER`     | @everyone connect: False               |
| `📊 BOTS`       | @everyone connect: False               |

## 🎮 Music/Hiburan

| Channel                | Type |
| ---------------------- | ---- |
| `#📸・gallery`         | Text |
| `#🎥・share-streaming` | Text |
| `#🔁・share-content`   | Text |
| `#🤡・funny`           | Text |
| `#📌・ping-test`       | Text |
| `#🎶・req-music`       | Text |

## 💬 Create Voice

| Channel              | Type  | Note                                           |
| -------------------- | ----- | ---------------------------------------------- |
| `#✨・interface`     | Text  | Panel kontrol voice room (button only)         |
| `#💬・talk`          | Text  | Chat buat voice                                |
| `⌛ Lobby`           | Voice | Pure lobby biasa                               |
| `😴 AFK 💤`          | Voice | AFK channel (>1hr idle → dipindah sini)        |
| `➕ Create Caffee'`  | Voice | Join → auto-create temp room di 🎮 Game        |

## 🎮 Game

| Channel        | Type  | Note                          |
| -------------- | ----- | ----------------------------- |
| `🗣️ Caffee`   | Voice | Permanent voice chat (paten)  |

## 🎵 Music

| Channel    | Type  |
| ---------- | ----- |
| `🔊 Music` | Voice |

## 🎬 Streaming

| Channel     | Type  |
| ----------- | ----- |
| `🎬 Stream` | Voice |

---

**Total**: ~21 channel (12 text + 9 voice)
**Requirements**: Manage Channels + Move Members permission
