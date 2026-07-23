# Voice Interface — `#✨・interface`

## Overview

Sistem voice management via text channel `#✨・interface`. User bisa kontrol voice room mereka sendiri pake buttons/select menus.

## Temporary Voice System

| Channel | Type | Fungsi |
|---------|------|--------|
| `➕ Create Caffee'` | Voice | Join → auto-create voice room di kategori **Game** (`🗣 Caffee`) |
| `⌛ Lobby` | Voice | Lobby biasa, waiting area |
| `😴 AFK 💤` | Voice | AFK channel (>1 jam idle → dipindah sini otomatis) |

Flow:
1. User join `➕ Create Caffee'` → bot auto-create voice room baru di kategori Game
2. Nama room: `「🔊」{username}'s Room`
3. Pas semua orang leave → auto-delete room
4. Owner room bisa kontrol room via `#✨・interface`

## Interface Features (via `#✨・interface`)

Tiap fitur pake button/select. Pesan di-embed dengan tombol:

```
╔══════════════════════════════════════════╗
║        🎛️ Voice Room Controls           ║
║                                          ║
║ Room: 「🔊」Budi's Room                  ║
║ Members: 3/10                            ║
║ Privacy: 🔓 Public                       ║
║ Chat: 💬 Open                            ║
║ Region: 🇸🇬 Singapore                    ║
║                                          ║
║ [✏️ Rename] [🔒 Lock] [👁️ Visible]     ║
║ [👥 Limit] [🚪 Waiting] [💬 Chat]       ║
║ [✅ Trust] [❌ Untrust] [🚫 Block]      ║
║ [🔇 Kick] [🌐 Region] [🗑️ Delete]      ║
║                                          ║
║ ⭐ PREMIUM:                              ║
║ [📥 Claim] [📤 Transfer]                ║
╚══════════════════════════════════════════╝
```

### Fitur List

| Fitur | Tipe | Deskripsi |
|-------|------|-----------|
| **Rename** | Modal (text input) | Ubah nama voice room |
| **Limit** | Select (1/2/5/10/20/unlimited) | Batas maksimal member |
| **Privacy** | Toggle button | Visible / Invisible (hide from channel list) |
| **Lock** | Toggle button | Lock (gembok) / Unlock — deny/allow @everyone connect |
| **Chat** | Toggle button | Open / Close chat untuk room ini (bikin text channel temp atau pake thread) |
| **Waiting Room** | Toggle button | Aktifkan waiting room — orang join masuk waiting dulu, di-approve owner |
| **Trust** | Select (pilih member) | Kasih akses khusus ke user tertentu |
| **Untrust** | Select (pilih member) | Cabut akses user |
| **Invite** | Modal (text input user ID) | Invite specific user ke room |
| **Kick** | Select (pilih member di room) | Kick user dari room |
| **Delete** | Button (confirm) | Hapus voice room (owner only) |
| **Claim** ⭐ | Button (premium) | Ambil alih room yang owner-nya offline >5 menit |
| **Transfer** ⭐ | Select (pilih member) | Transfer kepemilikan room ke user lain |
| **Block** | Modal (text input user ID) | Block user — gabisa join room ini |
| **Unblock** | Select (pilih blocked user) | Unblock user |
| **Region** | Select (region list) | Ganti region voice |

## Permission System

| Level | Bisa apa |
|-------|----------|
| **Owner** (pembuat room) | Semua fitur termasuk Delete |
| **Premium Owner** | Claim + Transfer |
| **Trusted** | Invite, kick (anggota biasa) |
| **Untrusted/Blocked** | Gak bisa join |

## Premium Check

- Claim: owner room offline >5 menit → siapapun bisa claim jadi owner baru
- Transfer: pindahin owner ke user lain (premium feature)
- Premium status check via Firestore (`guild_settings/{guild_id}/premium_users`)

## Room Lifecycle

1. Join `➕ Create Caffee'` → room dibuat
2. Owner keluar → room tetep ada 5 menit (grace period buat claim)
3. Owner keluar >5 menit + masih ada member → siapapun bisa Claim
4. Semua orang leave → room auto-delete
5. Owner pencet Delete → room langsung dihapus

## Implementation Notes

- Gunain `discord.VoiceChannel` + overwrites untuk lock/unlock
- Gunain `discord.ui.View` dengan persistent buttons
- State disimpen di memory (dict per guild → per room)
- Waiting room: set user jadi `speak: False` sampe di-approve