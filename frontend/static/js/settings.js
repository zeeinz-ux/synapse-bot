(function(){
  var guildId = window.CURRENT_GUILD_ID;

  function qs(id){ return document.getElementById(id); }

  function loadChannels(selId){
    fetch('/api/actions/' + guildId + '/channels')
      .then(function(r){ return r.json(); })
      .then(function(d){
        if(!d.success || !d.channels) return;
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
        if(!d.success) return;
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
        if(!d.success || !d.guild) return;
        var g = d.guild;
        qs('setServerName').textContent = g.name || 'Unknown';
        qs('setServerId').textContent = 'ID: ' + (g.id || '—');
        qs('setMemberCount').textContent = (g.member_count || 0).toLocaleString();
        // Try to get icon
        var iconUrl = g.icon ? 'https://cdn.discordapp.com/icons/' + g.id + '/' + g.icon + '.png' : null;
        if(iconUrl){
          qs('setServerIcon').style.backgroundImage = 'url(' + iconUrl + ')';
        }
      });
  }

  function loadSettings(){
    fetch('/api/settings/' + guildId + '/features')
      .then(function(r){ return r.json(); })
      .then(function(d){
        if(!d.success) return;
      });

    // Load stored log channel
    fetch('/api/settings/' + guildId + '/features')
      .then(function(){ /* no-op, firebase already has it */ });
  }

  // --- Init ---
  document.addEventListener('DOMContentLoaded', function(){
    loadGuildInfo();
    loadFeatures();
    loadChannels('logChannel');
    setTimeout(function(){
      // Try to load existing log_channel value after channels loaded
    }, 500);

    // Save logging
    qs('saveLoggingBtn').addEventListener('click', function(){
      var btn = this;
      var data = {
        log_channel: qs('logChannel').value,
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
        if(d.success) alert('✅ Disimpan!');
        else alert('❌ ' + (d.message || 'Gagal'));
      })
      .catch(function(){ alert('❌ Gagal menyimpan'); })
      .finally(function(){ btn.textContent = '💾 Simpan'; btn.disabled = false; });
    });

    // Reset buttons
    document.querySelectorAll('.btn-reset-feature').forEach(function(btn){
      btn.addEventListener('click', function(){
        var feature = this.dataset.feature;
        var name = this.dataset.name;
        if(!confirm('Reset ' + name + ' ke default?')) return;
        this.textContent = '⏳...';
        fetch('/api/settings/' + guildId + '/reset', {
          method: 'POST',
          headers: {'Content-Type':'application/json'},
          body: JSON.stringify({feature: feature}),
        })
        .then(function(r){ return r.json(); })
        .then(function(d){
          if(d.success){
            alert('✅ ' + name + ' di-reset!');
            loadFeatures();
          } else alert('❌ ' + (d.message || 'Gagal'));
        })
        .catch(function(){ alert('❌ Gagal reset'); })
        .finally(function(){ btn.textContent = '↻ Reset'; });
      });
    });
  });
})();
