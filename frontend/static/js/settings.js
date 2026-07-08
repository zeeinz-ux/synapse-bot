(function(){
  var guildId = window.CURRENT_GUILD_ID;

  function qs(id){ return document.getElementById(id); }

  function showToast(msg, type){
    var t = document.createElement('div');
    t.textContent = msg;
    t.style.cssText = 'position:fixed;bottom:24px;right:24px;padding:12px 20px;border-radius:8px;font-size:0.85rem;font-weight:600;z-index:9999;transition:opacity 0.3s;color:#fff;' +
      (type === 'error' ? 'background:#ed4245;' : 'background:#3ba55c;');
    document.body.appendChild(t);
    setTimeout(function(){ t.style.opacity = '0'; setTimeout(function(){ t.remove(); }, 300); }, 2500);
  }

  function loadChannels(selId){
    fetch('/api/actions/' + guildId + '/channels')
      .then(function(r){ return r.json(); })
      .then(function(d){
        if(!d.success || !d.channels){
          console.warn('[SETTINGS] Gagal muat channels:', d && d.message || 'unknown');
          return;
        }
        var sel = qs(selId);
        if(!sel) return;
        sel.innerHTML = '<option value="">— Tidak ada —</option>';
        for(var i=0; i<d.channels.length; i++){
          var ch = d.channels[i];
          var opt = document.createElement('option');
          opt.value = ch.id;
          opt.textContent = '#' + ch.name;
          sel.appendChild(opt);
        }
      });
  }

  function loadFeatures(){
    fetch('/api/settings/' + guildId + '/features')
      .then(function(r){ return r.json(); })
      .then(function(d){
        if(!d.success){
          console.warn('[SETTINGS] Gagal muat fitur:', d.message || 'unknown');
          return;
        }
        var f = d.features || {};
        var labels = {
          welcome: '👋 Welcome',
          leave: '👋 Leave',
          ban: '🔨 Ban',
          boost_announce: '🚀 Boost',
          auto_responders: '🤖 Auto Responder',
          ai_chat: '🧠 AI Chat',
          level_rewards: '🎖 Level Rewards',
          moderation: '🛡 Moderasi',
        };
        var html = '';
        for(var key in labels){
          var status = f[key] ? 'on' : 'off';
          var label = f[key] ? 'Aktif' : 'Nonaktif';
          html += '<div class="set-feature-item">'
            + '<span class="set-feature-name">' + labels[key] + '</span>'
            + '<span class="set-feature-status ' + status + '">' + label + '</span>'
            + '</div>';
        }
        qs('featuresList').innerHTML = html;
      });
  }

  function loadGuildInfo(){
    fetch('/api/settings/' + guildId + '/info')
      .then(function(r){ return r.json(); })
      .then(function(d){
        if(!d.success || !d.guild){
          console.warn('[SETTINGS] Gagal muat info guild:', d && d.message || 'unknown');
          return;
        }
        var g = d.guild;
        qs('setServerName').textContent = g.name || 'Unknown';
        qs('setServerId').textContent = 'ID: ' + (g.id || '—');
        qs('setMemberCount').textContent = (g.member_count || 0).toLocaleString();
        // Try to get icon
        var iconEl = qs('setServerIcon');
        if (g.icon) {
          var iconUrl = g.icon.startsWith('http') ? g.icon : 'https://cdn.discordapp.com/icons/' + g.id + '/' + g.icon + '.png';
          iconEl.style.backgroundImage = 'url(' + iconUrl + ')';
          iconEl.classList.remove('no-icon');
        } else {
          iconEl.classList.add('no-icon');
          iconEl.textContent = (g.name || '?')[0].toUpperCase();
        }
      });
  }

  function loadConfig(){
    fetch('/api/settings/' + guildId + '/config')
      .then(function(r){ return r.json(); })
      .then(function(d){
        if(!d.success || !d.config){
          console.warn('[SETTINGS] Gagal muat config:', d && d.message || 'unknown');
          return;
        }
        var cfg = d.config;
        // Set log channel
        var sel = qs('logChannel');
        if(sel && cfg.log_channel){
          for(var i=0; i<sel.options.length; i++){
            if(sel.options[i].value === cfg.log_channel){
              sel.options[i].selected = true;
              break;
            }
          }
        }
        // Set bot language
        var langSel = qs('botLanguage');
        if(langSel && cfg.bot_language){
          langSel.value = cfg.bot_language;
        }
      });
  }

  // --- Init ---
  document.addEventListener('DOMContentLoaded', function(){
    loadGuildInfo();
    loadFeatures();
    loadChannels('logChannel');
    // Load config after channels have time to populate
    setTimeout(function(){ loadConfig(); }, 600);

    // Save logging
    qs('saveLoggingBtn').addEventListener('click', function(){
      var btn = this;
      var data = {
        log_channel: qs('logChannel').value,
        bot_language: qs('botLanguage').value,
      };
      btn.textContent = '⏳...';
      btn.disabled = true;
      fetch('/api/settings/' + guildId + '/save', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify(data),
      })
      .then(function(r){ return r.json(); })
      .then(function(d){
        if(d.success) showToast('✅ Disimpan!');
        else showToast('❌ ' + (d.message || 'Gagal'), 'error');
      })
      .catch(function(){ showToast('❌ Gagal menyimpan', 'error'); })
      .finally(function(){ btn.textContent = '💾 Simpan'; btn.disabled = false; });
    });

    // Reset buttons
    document.querySelectorAll('.btn-reset-feature').forEach(function(btn){
      btn.addEventListener('click', function(){
        var feature = this.dataset.feature;
        var name = this.dataset.name;
        if(!window.confirm('Reset ' + name + ' ke default?')) return;
        this.textContent = '⏳...';
        fetch('/api/settings/' + guildId + '/reset', {
          method: 'POST',
          headers: {'Content-Type':'application/json'},
          body: JSON.stringify({feature: feature}),
        })
        .then(function(r){ return r.json(); })
        .then(function(d){
          if(d.success){
            showToast('✅ ' + name + ' di-reset!');
            loadFeatures();
          } else showToast('❌ ' + (d.message || 'Gagal'), 'error');
        })
        .catch(function(){ showToast('❌ Gagal reset', 'error'); })
        .finally(function(){ btn.textContent = '↻ Reset'; });
      });
    });
  });
})();
