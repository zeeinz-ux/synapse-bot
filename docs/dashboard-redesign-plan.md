# Dashboard Redesign Plan

## Current Flow (yang jalan sekarang)

```
/dashboard → redirect langsung ke /dashboard/{guild_id}/ (skip pilih server)
/dashboard/{guild_id}/ → render dashboard.html (statistik bot, server list kecil)
```

Masalah: user langsung dilempar ke server pertama tanpa milih, gak ada konteks server mana yang lagi di-setting.

---

## Target Flow

```
/dashboard → Landing Page (pilih server) → /dashboard/{guild_id}/ → Settings Server
```

---

## 1. Route Changes (`backend/web/web_app.py`)

### `/dashboard` — Server Selection Page (BARU)

Ubah dari redirect langsung jadi render pilihan server:

```python
@app.route("/dashboard")
@login_required
def dashboard():
    s = _get_filtered_stats()
    return render_template(
        "dashboard/select_server.html",
        s=s,
        user=session.get("user"),
        avatar_url=_discord_avatar_url(session.get("user")) if session.get("user") else "",
    )
```

- **Hapus** redirect ke `/{guild_id}/` — user harus milih dulu
- Pake template baru `dashboard/select_server.html`

### `/dashboard/<guild_id>/` — Server Settings Page (UBAH)

Template `dashboard/dashboard.html` → ganti jadi `dashboard/guild.html` (nama baru biar gak bingung).

**PENTING:** Di settings page, setiap halaman harus nampilin:

- Tombol **"arrow-left Kembali ke daftar server"** (pake Lucide `arrow-left`) di bagian atas halaman → `href="/dashboard"`
- Biar user gak bingung dan bisa ganti server kapan aja

| Elemen | Posisi |
|--------|--------|
| Guild Icon (bulat, 48-56px) | Kiri sidebar atau di atas page title |
| Guild Name (bold) | Samping/di bawah icon |
| Member count | Text kecil di bawah nama |

Ini dibutuhkan biar user sadar "oh gua lagi setting server X, bukan Y".

---

## 2. New Template: `select_server.html`

Halaman setelah login → `/dashboard`:

```
┌──────────────────────────────────────────┐
│  [Logo Synapse]     Dashboard            │
├──────────────────────────────────────────┤
│                                          │
│  Pilih Server                            │
│                                          │
│  ┌─────────────────────────────────┐    │
│  │ [icon] Hidden Hamlet             │    │
│  │      1,234 members               │    │
│  ├─────────────────────────────────┤    │
│  │ [icon] Server Keren             │    │
│  │      567 members                 │    │
│  ├─────────────────────────────────┤    │
│  │ [icon] Test Server              │    │
│  │      12 members                  │    │
│  └─────────────────────────────────┘    │
│                                          │
│  Info: Kamu bisa setting bot untuk       │
│  server yang kamu punya akses Admin/     │
│  Manage Guild.                           │
│                                          │
└──────────────────────────────────────────┘
```

### Data flow — ALL servers the user is in

Tampilin **semua** server tempat user masuk, bukan cuma yang punya akses admin.

Bedain 3 tipe server:

| Status | Icon Lucide | Kondisi | Akses |
|--------|-------------|---------|-------|
| **Available** | `shield-check` | Bot udah di server + user punya Admin/Manage Guild | Bisa setting config |
| **Locked** | `lock` | Bot udah di server + user **gak** punya Admin/Manage Guild | Cuma liat, gak bisa config |
| **Invite** | `plus-circle` | Bot **belom** di server | Tombol "Invite Bot" |

Data didapat dari 2 sumber yang digabung:

1. **User's guilds** — dari Discord OAuth2 (`/users/@me/guilds`), daftar semua server tempat user masuk
2. **Bot guilds** — dari `get_stats_snapshot().guilds_list`, daftar server tempat bot udah diinvite

Cara gabung:

```python
user_guilds = session["user_guilds"]  # semua server user (udah unfiltered)
bot_guild_ids = {g["id"] for g in bot_stats["guilds_list"]}

for g in user_guilds:
    g["bot_in"] = g["id"] in bot_guild_ids
    perms = int(g.get("permissions", 0))
    g["can_manage"] = (perms & 0x8) or (perms & 0x20)

    if g["bot_in"] and g["can_manage"]:
        g["card_type"] = "available"
        g["url"] = f"/dashboard/{g['id']}/"
    elif g["bot_in"] and not g["can_manage"]:
        g["card_type"] = "locked"
        g["url"] = None
    else:
        g["card_type"] = "invite"
        g["invite_url"] = f"https://discord.com/oauth2/authorize?client_id={CLIENT_ID}&scope=bot&permissions=8&guild_id={g['id']}"
```

### Server card elements
- Guild icon (Discord CDN)
- Guild name
- Member count (from bot data kalo available, fallback kosong)
- Status badge: `shield-check` Available / `lock` Locked / `plus-circle` Invite

### Layout — left-to-right grid

Susunan grid berurutan dari kiri ke kanan, wrap ke baris berikutnya:

```
┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│ Server 1  │ │ Server 2  │ │ Server 3  │ │ Server 4  │
│ shield Config │ │ shield Config │ │ plus Invite │ │  lock Locked │
└──────────┘ └──────────┘ └──────────┘ └──────────┘
┌──────────┐ ┌──────────┐ ┌──────────┐
│ Server 5  │ │ Server 6  │ │ Server 7  │
│ shield Config │ │ plus Invite │ │ shield Config │
└──────────┘ └──────────┘ └──────────┘
```

CSS:
```css
.server-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 1rem;
}
```

Naturally left-to-right, no centering, no fancy alignment.

### Status badge style

```css
.server-status {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.75rem;
  font-weight: 600;
  padding: 0.2rem 0.6rem;
  border-radius: 999px;
}

.server-status--available {
  color: #3ba55d;
  background: rgba(59, 165, 93, 0.1);
}

.server-status--locked {
  color: var(--text-muted);
  background: rgba(107, 107, 107, 0.1);
}

.server-status--invite {
  color: var(--accent);
  background: rgba(0, 212, 255, 0.08);
}
```

### Info bar
Di bawah grid, tampilkan info singkat:
```
(icon lightbulb) Kamu bisa mengatur bot di server yang bertanda shield-check.
   Kalo server belum ada bot-nya, klik plus-circle Invite dulu.
   Server lock cuma bisa dilihat — minta admin server untuk akses config.
```

---

## 3. Ubah `base.html` Sidebar Link

Saat ini link di sidebar langsung ke `/dashboard/{guild_id}/`. Ubah jadi:

| Dari | Jadi |
|------|------|
| `Dashboard` sidebar link | `href="/dashboard"` (select server page) |

Biar user bisa balik ke halaman pilih server kapan aja.

---

## 4. Server Context di Setiap Halaman Settings

Di `base.html`, tambahin **server header** di atas sidebar atau di main content:

```html
<!-- Di sidebar atau main content -->
<div class="guild-context">
  <img class="guild-context-icon" src="..." alt="..." width="48" height="48" />
  <div class="guild-context-info">
    <span class="guild-context-name">Hidden Hamlet</span>
    <span class="guild-context-members">1,234 members</span>
  </div>
</div>
```

**Atau** lebih simpel: di setiap halaman settings template (welcome.html, dsb), tambahin di atas konten utama:

```html
<div class="page-guild-header">
  <img src="..." class="page-guild-icon" />
  <div>
    <h2>Welcome Settings</h2>
    <span class="page-guild-name">Hidden Hamlet</span>
  </div>
</div>
```

Kirim data guild via `_render_page`:

```python
def _render_page(...):
    # ... existing code ...
    guild_info = {}
    for g in stats.get("guilds_list", []):
        if str(g["id"]) == str(guild_id):
            guild_info = g
            break
    return render_template(
        ...,
        guild_info=guild_info,  # <-- tambah ini
        **kwargs
    )
```

Guild icon URL helper di template:
```python
# Di context_processor atau filter
def guild_icon_url(guild):
    if guild.get("icon"):
        return f"https://cdn.discordapp.com/icons/{guild['id']}/{guild['icon']}.png"
    return ""
```

---

## 5. UX/UI Redesign Notes (Anti AI-slop)

### Yang dihindari:
- Gradient overload (terlalu banyak gradien warna-warni)
- Glassmorphism di card (udah dihilangkan)
- Shadow berlebihan
- Font weight 800 di semua teks
- Ikon Lucide yang gak perlu (setiap baris pake ikon)

### Yang diterapin:

| Elemen | Style |
|--------|-------|
| **Card** | `--sidebar-bg`, `border: 1px solid var(--sidebar-border)`, `border-radius: var(--radius-md)` |
| **Hover** | `border-color: var(--accent)` tipis, transform -2px |
| **Teks** | `--text-primary` untuk judul, `--text-secondary` untuk deskripsi |
| **Spacing** | Padding konsisten (1.25-1.5rem), gap 0.75-1rem |
| **Accent** | Dipakai minimal — hanya di hover state, border active, atau link |
| **Typography** | `font-weight: 600` untuk judul, `400`/`500` untuk body |

### Layout:
- Sidebar tetap di kiri (existing)
- Konten: `max-width: 1000px`, centered
- Server list: `grid-template-columns: repeat(auto-fill, minmax(320px, 1fr))`
- Settings page: 2 kolom (sidebar navigasi settings + konten utama) atau single column

---

## 6. Implementation Order

| Step | File | Apa |
|------|------|-----|
| 1 | `docs/dashboard-redesign-plan.md` | Plan ini (done) |
| 2 | `backend/web/web_app.py` | Ubah `/dashboard` route jadi pilih server; tambah `guild_info` di `_render_page`; ubah `/dashboard/<guild_id>/` pake template baru |
| 3 | `frontend/pages/dashboard/select_server.html` | Template baru: server selection grid |
| 4 | `frontend/pages/dashboard/guild.html` | Template baru: ganti `dashboard.html` untuk settings page |
| 5 | `frontend/pages/base.html` | Ubah sidebar link dashboard → `/dashboard`; tambah server context header |
| 6 | `frontend/static/css/select-server.css` | CSS untuk halaman pilih server |
| 7 | `frontend/static/css/guild.css` | CSS untuk halaman settings per-server |
| 8 | Semua halaman settings | Tambah server context header (guild icon + name) di tiap page |

---

## 7. Files affected

| File | Action |
|------|--------|
| `backend/web/web_app.py` | Edit route `/dashboard`, `/dashboard/<guild_id>/`, `_render_page`, `_discord_avatar_url` |
| `frontend/pages/dashboard/select_server.html` | **Create** |
| `frontend/pages/dashboard/guild.html` | **Create** (ambil konten dari `dashboard.html` yang lama) |
| `frontend/pages/dashboard/dashboard.html` | **Hapus** atau ganti isinya jadi redirect component |
| `frontend/pages/base.html` | Edit sidebar link + add guild context |
| `frontend/static/css/dashboard.css` | Edit (atau split jadi `select-server.css` + `guild.css`) |
| Semua `dashboard/*.html` | Tambah guild header di tiap page |

---

## Notes

- Data guild icon via Discord CDN: `https://cdn.discordapp.com/icons/{id}/{icon}.png`
- Fallback icon: initial huruf pertama dari nama guild
- **`_fetch_user_guilds` perlu diubah** biar gak filter admin/manage — semua server user ditampilkan
- Tapi guard di `_render_page` tetep jalan: hanya user dengan Admin/Manage yang bisa akses `/dashboard/{guild_id}/`
- Invite URL: `https://discord.com/oauth2/authorize?client_id={DISCORD_CLIENT_ID}&scope=bot&permissions=8&guild_id={guild_id}`
- Member count cuma available untuk guild yang botnya udah masuk (dari `get_stats_snapshot`)
