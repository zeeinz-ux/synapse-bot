(function(){
  var guildId = window.CURRENT_GUILD_ID;
  var currentTab = 'message';

  var DEFAULT_ANNOUNCEMENTS = [
    {
      name: 'Selamat Datang',
      type: 'announcement',
      embed: { title: 'Selamat Datang {user}!', description: 'Halo {user}, selamat datang di **{server}**!\\nKamu member ke-{count}.\\n\\nBaca rules di <#channel_rules> dan perkenalan diri di <#channel_intro>.', color: '3ba55c' },
      content: '{user}',
    },
    {
      name: 'Selamat Tinggal',
      type: 'announcement',
      embed: { title: '{user} meninggalkan server', description: '{user} telah keluar dari **{server}**.\\nSekarang kita {count} member.', color: 'ed4245' },
      content: '',
    },
    {
      name: 'Terima Kasih Boost',
      type: 'announcement',
      embed: { title: 'Terima Kasih atas Boost!', description: '{user} telah melakukan **Boost** pada **{server}**! 🎉\\n\\nKita sekarang punya **{count} Boost**! Terima kasih banyak atas dukungannya! ❤️', color: '9B59B6' },
      content: '',
    },
    {
      name: 'Pemberitahuan Ban',
      type: 'announcement',
      embed: { title: '{user} telah di-ban', description: '{user} telah di-ban dari **{server}**.\\nMember tersisa: {count}.', color: 'ed4245' },
      content: '',
    },
  ];

  var DEFAULT_AUTO_RESPONSES = [
    {
      name: 'Info Server',
      type: 'auto_response',
      keywords: ['info', 'server', 'informasi'],
      response_type: 'embed',
      embed: { title: '📋 Info Server', description: '**{server}**\\n\\n📅 Dibuat: {created_at}\\n👑 Owner: <@!{owner_id}>\\n👥 Member: {member_count}\\n💬 Channel: {channel_count}', color: '5865f2' },
      content: '',
    },
    {
      name: 'Rules',
      type: 'auto_response',
      keywords: ['rules', 'aturan', 'peraturan'],
      response_type: 'embed',
      embed: { title: '📜 Rules Server', description: '1. **Hormati** sesama member\\n2. **No spam** di semua channel\\n3. **Gunakan channel** yang sesuai\\n4. **No NSFW** di luar channel NSFW\\n5. **Ikuti arahan** admin & moderator\\n\\nLanggar aturan = **sanksi** berupa warning/mute/kick/ban.', color: 'f0b232' },
      content: '',
    },
    {
      name: 'FAQ Bantuan',
      type: 'auto_response',
      keywords: ['help', 'bantuan', 'faq', 'command'],
      response_type: 'embed',
      embed: { title: '❓ Butuh Bantuan?', description: 'Gunakan `/help` untuk melihat semua command bot.\\nKunjungi <#channel_support> untuk bertanya ke admin.\\n\\n📚 **Command Populer:**\\n• `/ping` — Cek status bot\\n• `/stats` — Statistik server\\n• `/rank` — Level kamu', color: '5865f2' },
      content: '',
    },
    {
      name: 'Social Media',
      type: 'auto_response',
      keywords: ['sosial', 'social', 'media', 'instagram', 'twitter', 'youtube'],
      response_type: 'embed',
      embed: { title: '🌐 Social Media Kami', description: '📸 Instagram: [@server_ig](https://instagram.com/)\\n🐦 Twitter: [@server_twt](https://twitter.com/)\\n▶️ YouTube: [Server YT](https://youtube.com/)\\n💬 Discord: [Join Server](https://discord.gg/)', color: '5865f2' },
      content: '',
    },
  ];

  function isDefault(tpl){
    return tpl._default === true;
  }

  function findDefaults(type){
    if(type === 'announcement') return DEFAULT_ANNOUNCEMENTS;
    if(type === 'auto_response') return DEFAULT_AUTO_RESPONSES;
    return [];
  }

  function fmtRupiah(n){
    return 'Rp ' + Number(n).toLocaleString('id-ID');
  }

  function shortEmbedPreview(tpl){
    var e = tpl.embed || {};
    var html = '<div class="tpl-card-embed-preview" style="border-left-color:#' + (e.color || '5865f2') + '">';
    if(e.title) html += '<div class="ep-title">' + e.title + '</div>';
    if(e.description) html += '<div class="ep-desc">' + e.description.slice(0,120) + (e.description.length > 120 ? '…' : '') + '</div>';
    if(e.fields && e.fields.length) html += '<div class="ep-fields">📋 ' + e.fields.length + ' field(s)</div>';
    html += '</div>';
    return html;
  }

  function renderTab(type){
    currentTab = type;
    document.querySelectorAll('.tpl-tab').forEach(function(t){
      t.classList.toggle('active', t.dataset.type === type);
    });

    var grid = document.getElementById('tplGrid');
    grid.innerHTML = '<div class="tpl-empty"><h3>⏳ Memuat...</h3></div>';

    // Load user templates from API + merge defaults
    fetch('/api/templates/' + guildId)
      .then(function(r){ return r.json(); })
      .then(function(d){
        var userTemplates = (d.success && d.templates) ? d.templates.filter(function(t){ return t.type === type; }) : [];
        var defaults = findDefaults(type);
        var allTemplates = [];

        // Mark defaults
        defaults.forEach(function(dt){
          allTemplates.push(Object.assign({}, dt, { _default: true }));
        });
        userTemplates.forEach(function(ut){
          allTemplates.push(ut);
        });

        if(!allTemplates.length){
          grid.innerHTML = '<div class="tpl-empty"><h3>' + getEmptyIcon(type) + ' Belum Ada Template</h3><p>' + getEmptyDesc(type) + '</p></div>';
          return;
        }

        var html = '';
        for(var i=0; i<allTemplates.length; i++){
          var t = allTemplates[i];
          html += renderCard(t);
        }
        grid.innerHTML = html;

        // Bind card actions
        document.querySelectorAll('.tpl-card').forEach(function(card){
          var id = card.dataset.id;
          var isDef = card.dataset.default === 'true';
          var tpl = null;
          for(var j=0; j<allTemplates.length; j++){
            if(allTemplates[j].id === id || (isDef && allTemplates[j].name === card.dataset.name)){
              tpl = allTemplates[j];
              break;
            }
          }
          if(!tpl) return;

          // Delete
          var delBtn = card.querySelector('.btn-tpl-delete');
          if(delBtn){
            delBtn.addEventListener('click', function(){
              if(!confirm('Hapus template "' + tpl.name + '"?')) return;
              fetch('/api/templates/' + guildId + '/' + tpl.id, { method: 'DELETE' })
                .then(function(r){ return r.json(); })
                .then(function(d2){
                  if(d2.success) renderTab(currentTab);
                });
            });
          }

          // Send (message type only)
          var sendBtn = card.querySelector('.btn-tpl-send');
          if(sendBtn){
            sendBtn.addEventListener('click', function(){
              var ch = prompt('Masukkan ID channel tujuan:');
              if(!ch) return;
              sendBtn.textContent = '⏳...';
              fetch('/api/message-builder/' + guildId + '/send', {
                method: 'POST',
                headers: {'Content-Type':'application/json'},
                body: JSON.stringify({
                  channel_id: ch,
                  embed: tpl.embed || {},
                  content: tpl.content || '',
                }),
              })
              .then(function(r){ return r.json(); })
              .then(function(d2){
                if(d2.success) alert('✅ Embed dikirim!');
                else alert('❌ ' + (d2.message || 'Gagal'));
              })
              .catch(function(){ alert('❌ Gagal mengirim'); })
              .finally(function(){ sendBtn.textContent = '📤 Kirim'; });
            });
          }

          // Apply announcement
          var applyBtn = card.querySelector('.btn-tpl-apply');
          if(applyBtn){
            applyBtn.addEventListener('click', function(){
              showApplyModal(tpl);
            });
          }

          // Add auto-responder
          var arBtn = card.querySelector('.btn-tpl-add-ar');
          if(arBtn){
            arBtn.addEventListener('click', function(){
              arBtn.textContent = '⏳...';
              fetch('/api/templates/' + guildId + '/add-autoresponder', {
                method: 'POST',
                headers: {'Content-Type':'application/json'},
                body: JSON.stringify({
                  keywords: tpl.keywords || [tpl.name.toLowerCase()],
                  embed: tpl.embed || {},
                  content: tpl.content || '',
                }),
              })
              .then(function(r){ return r.json(); })
              .then(function(d2){
                if(d2.success) alert('✅ Auto-responder berhasil ditambahkan!');
                else alert('❌ ' + (d2.message || 'Gagal'));
              })
              .catch(function(){ alert('❌ Gagal menambah auto-responder'); })
              .finally(function(){ arBtn.textContent = '➕ Add AR'; });
            });
          }

          // Edit - save a copy as user template
          var editBtn = card.querySelector('.btn-tpl-edit');
          if(editBtn){
            editBtn.addEventListener('click', function(){
              if(isDef){
                // Save default as user template
                var name = prompt('Simpan sebagai template baru:', tpl.name);
                if(!name) return;
                editBtn.textContent = '⏳...';
                fetch('/api/templates/' + guildId, {
                  method: 'POST',
                  headers: {'Content-Type':'application/json'},
                  body: JSON.stringify({
                    name: name,
                    type: tpl.type,
                    embed: tpl.embed || {},
                    content: tpl.content || '',
                    keywords: tpl.keywords || [],
                    response_type: tpl.response_type || 'text',
                  }),
                })
                .then(function(r){ return r.json(); })
                .then(function(d2){
                  if(d2.success){ alert('✅ Template "' + name + '" disimpan!'); renderTab(currentTab); }
                  else alert('❌ ' + (d2.message || 'Gagal'));
                })
                .catch(function(){ alert('❌ Gagal menyimpan'); })
                .finally(function(){ editBtn.textContent = '✏️ Edit'; });
              }
            });
          }
        });
      })
      .catch(function(){
        grid.innerHTML = '<div class="tpl-empty"><h3>❌ Gagal Memuat</h3><p>Coba refresh halaman.</p></div>';
      });
  }

  function renderCard(t){
    var isDef = isDefault(t);
    var typeLabel = t.type === 'message' ? 'Message' : t.type === 'announcement' ? 'Announcement' : 'Auto Response';
    var typeBadge = 'badge-' + t.type;
    var hasEmbed = t.embed && (t.embed.title || t.embed.description);

    var html = '<div class="tpl-card" data-id="' + (t.id || '') + '" data-default="' + isDef + '" data-name="' + t.name + '">';
    html += '<div class="tpl-card-header">';
    html += '<span class="tpl-card-name">' + t.name + '</span>';
    html += '<div style="display:flex;gap:0.3rem;">';
    html += '<span class="tpl-card-badge ' + typeBadge + '">' + typeLabel + '</span>';
    if(isDef) html += '<span class="tpl-card-badge badge-default">Default</span>';
    html += '</div></div>';

    html += '<div class="tpl-card-body">';
    if(hasEmbed){
      html += shortEmbedPreview(t);
    } else if(t.content){
      html += '<div style="color:#b5bac1;font-size:0.85rem;">' + t.content.slice(0,100) + '</div>';
    } else if(t.keywords && t.keywords.length){
      html += '<div class="tpl-card-keywords">';
      for(var k=0; k<t.keywords.length; k++){
        html += '<span class="tpl-card-keyword">' + t.keywords[k] + '</span>';
      }
      html += '</div>';
    } else {
      html += '<div style="color:#555;font-size:0.85rem;">Tidak ada konten</div>';
    }
    html += '</div>';

    html += '<div class="tpl-card-actions">';
    if(t.type === 'message'){
      html += '<button class="btn-tpl btn-tpl-send">📤 Kirim</button>';
    }
    if(t.type === 'announcement'){
      html += '<button class="btn-tpl btn-tpl-apply">📌 Apply</button>';
    }
    if(t.type === 'auto_response'){
      html += '<button class="btn-tpl btn-tpl-add-ar">➕ Add AR</button>';
    }
    if(!isDef && t.id){
      html += '<button class="btn-tpl btn-tpl-delete">🗑 Hapus</button>';
    }
    if(isDef){
      html += '<button class="btn-tpl btn-tpl-edit">✏️ Edit</button>';
    }
    html += '</div></div>';

    return html;
  }

  function getEmptyIcon(type){
    if(type === 'message') return '💬';
    if(type === 'announcement') return '📢';
    return '🤖';
  }
  function getEmptyDesc(type){
    if(type === 'message') return 'Belum ada template message tersimpan. Gunakan Message Builder untuk membuatnya.';
    if(type === 'announcement') return 'Belum ada template announcement. Gunakan default di atas atau buat sendiri.';
    return 'Belum ada template auto-response. Gunakan default di atas atau buat sendiri.';
  }

  // --- Apply Modal ---
  function showApplyModal(tpl){
    var modal = document.getElementById('tplApplyModal');
    var list = document.getElementById('tplApplyList');
    list.innerHTML = '';
    var targets = [
      { id: 'welcome', icon: '👋', name: 'Welcome Message' },
      { id: 'leave', icon: '👋', name: 'Leave Message' },
      { id: 'ban', icon: '🔨', name: 'Ban Announcement' },
      { id: 'boost', icon: '🚀', name: 'Boost Announcement' },
    ];
    for(var i=0; i<targets.length; i++){
      var t = targets[i];
      var div = document.createElement('div');
      div.className = 'tpl-apply-item';
      div.innerHTML = '<span class="tpl-apply-icon">' + t.icon + '</span><span class="tpl-apply-name">' + t.name + '</span>';
      div.addEventListener('click', function(targetId){
        return function(){
          fetch('/api/templates/' + guildId + '/apply-announcement', {
            method: 'POST',
            headers: {'Content-Type':'application/json'},
            body: JSON.stringify({
              target: targetId,
              embed: tpl.embed || {},
              content: tpl.content || '',
            }),
          })
          .then(function(r){ return r.json(); })
          .then(function(d){
            if(d.success) alert('✅ Template diterapkan ke ' + targetId + '!');
            else alert('❌ ' + (d.message || 'Gagal'));
          })
          .catch(function(){ alert('❌ Gagal menerapkan template'); })
          .finally(function(){ modal.classList.remove('open'); });
        };
      }(t.id));
      list.appendChild(div);
    }
    modal.classList.add('open');
    document.getElementById('tplApplyCancel').addEventListener('click', function(){ modal.classList.remove('open'); });
    modal.addEventListener('click', function(e){ if(e.target === modal) modal.classList.remove('open'); });
  }

  // --- Init ---
  document.addEventListener('DOMContentLoaded', function(){
    document.querySelectorAll('.tpl-tab').forEach(function(tab){
      tab.addEventListener('click', function(){
        renderTab(this.dataset.type);
      });
    });
    renderTab('message');
  });
})();
