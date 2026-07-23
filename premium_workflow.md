# Premium Payment Workflow

## Overview

Sistem premium otomatis pake Saweria/Sociabuzz — bedain donasi vs premium lewat **nominal + pesan**.

Base price in **USD**, converted to local currency di masing-masing platform.

---

## Tier & Price

| Tier | USD | IDR (Saweria) | Durasi |
|------|-----|---------------|--------|
| **Monthly** | $3 | Rp 50.000 | 30 hari |
| **Yearly** | $25 | Rp 400.000 | 365 hari |

Deteksi tier lewat nominal:
- Rp 50.000 → premium **monthly**
- Rp 400.000 → premium **yearly**
- Nominal lain → **donasi biasa**

---

## Flow Pembayaran

```
User klik Beli Premium di Dashboard
  → Buka Sawiera/Sociabuzz
  → Bayar Rp 50.000 (monthly) / Rp 400.000 (yearly)
  → Tulis Discord User ID di pesan: "123456789012345678"
  → Webhook → Flask
     ↓
  Amount == 50000? → Monthly (30 hari)
  Amount == 400000? → Yearly (365 hari)
  Amount lainnya?   → Donasi biasa
     ↓
  Simpan premium_users[user_id] = {expiry: timestamp, tier: "monthly"|"yearly"}
  Kirim DM: "⭐ Premium aktif! Expiry: {date}"
```

---

## Aturan Deteksi

| Nominal | Pesan berisi angka? | Kategori | Aksi |
|---------|--------------------|----------|------|
| Rp 50.000 | Ya (user ID) | **Premium Monthly** | Expiry +30 hari |
| Rp 400.000 | Ya (user ID) | **Premium Yearly** | Expiry +365 hari |
| Rp 50.000/400.000 | Tidak/kosong | **Pending** | DM user minta ID |
| Nominal lain | — | **Donasi** | Existing flow |

---

## Data Model (Firestore)

```
guild_settings/{guild_id}/
  ├── premium_users/
  │   ├── "123456789012345678": {
  │   │     "expiry": 1735689600,      # Unix timestamp
  │   │     "tier": "monthly",
  │   │     "activated_at": 1700000000
  │   │   }
  │   └── "987654321098765432": {
  │         "expiry": 1767225600,
  │         "tier": "yearly",
  │         "activated_at": 1700000000
  │       }
  └── ...
```

---

## File yang Diubah

### 1. Webhook — `backend/web/web_app.py`
- Tambah deteksi amount == 50000 (monthly) / 400000 (yearly)
- Set `premium_users[user_id] = {expiry, tier}` di Firestore
- Kirim DM via control queue

### 2. Premium Check — `backend/cogs/voice_interface/voice_interface.py`
- `_check_premium()` cek: user_id in premium_users AND expiry > now

### 3. Expiry Cleanup — `backend/web/web_app.py` atau background task
- Hapus premium_users yang expired setiap 1 jam

### 4. Dashboard — `/dashboard/{guild_id}/premium`
- Tampilkan status premium (aktif sampai dd/mm/yyyy)
- Tombol "⭐ Beli Monthly $3" / "⭐ Beli Yearly $25"
- Convert ke IDR: Rp 50.000 / Rp 400.000

---

## Env Vars

| Variable | Default | Description |
|----------|---------|-------------|
| `PREMIUM_MONTHLY_IDR` | 50000 | Harga monthly dalam IDR |
| `PREMIUM_YEARLY_IDR` | 400000 | Harga yearly dalam IDR |
| `PREMIUM_MONTHLY_USD` | 3 | Display price USD |
| `PREMIUM_YEARLY_USD` | 25 | Display price USD |

---

## Security

- Validasi user ID ada di guild sebelum aktivasi
- Satu user bisa multiple purchase (extend expiry)
- Webhook signature kalau available