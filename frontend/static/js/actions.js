(function(){
  var guildId = window.CURRENT_GUILD_ID;
  var rolesCache = [];

  function qs(id){ return document.getElementById(id); }

  function loadRoles(){
    fetch('/api/actions/' + guildId + '/roles')
      .then(function(r){ return r.json(); })
      .then(function(d){
        if(!d.success) return;
        rolesCache = d.roles || [];
        var selects = document.querySelectorAll('.role-select');
        for(var i=0; i<selects.length; i++){
          populateRoles(selects[i]);
        }
      });
  }

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

  function populateRoles(sel){
    var currentVal = sel.value;
    sel.innerHTML = '<option value="">— Pilih role —</option>';
    for(var i=0; i<rolesCache.length; i++){
      var r = rolesCache[i];
      var opt = document.createElement('option');
      opt.value = r.id;
      opt.textContent = '@' + r.name;
      sel.appendChild(opt);
    }
    if(currentVal) sel.value = currentVal;
  }

  // --- Level Rewards ---
  function renderRewards(rewards){
    var container = qs('rewardsList');
    container.innerHTML = '';
    if(!rewards || !rewards.length){
      container.innerHTML = '<div style="color:#555;font-size:0.85rem;padding:0.5rem 0;">Belum ada reward.</div>';
      return;
    }
    for(var i=0; i<rewards.length; i++){
      addRewardRow(rewards[i].level, rewards[i].role_id);
    }
  }

  function addRewardRow(level, roleId){
    var container = qs('rewardsList');
    var emptyMsg = container.querySelector('div[style*="color:#555"]');
    if(emptyMsg) emptyMsg.remove();

    var div = document.createElement('div');
    div.className = 'reward-row';
    div.innerHTML =
      '<input type="number" class="reward-level" value="' + (level || '') + '" placeholder="Level" min="1">'
      + '<select class="role-select reward-role"></select>'
      + '<button type="button" class="btn-remove-reward">✕</button>';
    container.appendChild(div);

    populateRoles(div.querySelector('.reward-role'));
    if(roleId) div.querySelector('.reward-role').value = roleId;

    div.querySelector('.btn-remove-reward').addEventListener('click', function(){
      div.remove();
    });
  }

  function collectRewards(){
    var items = document.querySelectorAll('.reward-row');
    var rewards = [];
    for(var i=0; i<items.length; i++){
      var lvl = parseInt(items[i].querySelector('.reward-level').value);
      var rid = items[i].querySelector('.reward-role').value;
      if(lvl && rid) rewards.push({level: lvl, role_id: rid});
    }
    return rewards;
  }

  // --- Moderation ---
  function loadModerationConfig(data){
    if(!data) return;
    qs('modEnabled').checked = data.enabled !== false;
    setStrikeConfig('strike1', data.strike_1 || {action:'timeout',duration_hours:1});
    setStrikeConfig('strike2', data.strike_2 || {action:'kick'});
    setStrikeConfig('strike3', data.strike_3 || {action:'ban'});

    var chSel = qs('modReportChannel');
    if(data.report_channel) chSel.value = data.report_channel;

    setFilter('filterHeuristic', data.filter_heuristic !== false);
    setFilter('filterNewAccount', data.filter_new_account !== false);
    setFilter('filterAi', data.filter_ai !== false);
  }

  function setStrikeConfig(prefix, cfg){
    var actionSel = qs(prefix + 'Action');
    var durationRow = qs(prefix + 'Duration');
    if(actionSel){
      actionSel.value = cfg.action || 'ban';
      toggleDuration(actionSel, durationRow);
    }
    if(durationRow){
      durationRow.value = cfg.duration_hours || 1;
    }
  }

  function toggleDuration(actionSel, durationRow){
    if(!durationRow) return;
    durationRow.style.display = actionSel.value === 'timeout' ? '' : 'none';
  }

  function setFilter(id, enabled){
    var el = qs(id);
    if(el) el.classList.toggle('active', enabled);
  }

  function collectModeration(){
    function getStrike(prefix){
      var action = qs(prefix + 'Action').value;
      var cfg = {action: action};
      if(action === 'timeout'){
        cfg.duration_hours = parseInt(qs(prefix + 'Duration').value) || 1;
      }
      return cfg;
    }
    return {
      enabled: qs('modEnabled').checked,
      strike_1: getStrike('strike1'),
      strike_2: getStrike('strike2'),
      strike_3: getStrike('strike3'),
      report_channel: qs('modReportChannel').value,
      filter_heuristic: qs('filterHeuristic').classList.contains('active'),
      filter_new_account: qs('filterNewAccount').classList.contains('active'),
      filter_ai: qs('filterAi').classList.contains('active'),
    };
  }

  // --- Save helpers ---
  function saveLevelRewards(btn){
    var data = {
      enabled: qs('levelRewardEnabled').checked,
      rewards: collectRewards(),
      notify_channel: qs('levelNotifyChannel').value,
    };
    btn.textContent = '⏳ Menyimpan...';
    btn.disabled = true;
    fetch('/api/actions/' + guildId + '/level-rewards', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify(data),
    })
    .then(function(r){ return r.json(); })
    .then(function(d){
      if(d.success) alert('✅ Level rewards disimpan!');
      else alert('❌ ' + (d.message || 'Gagal'));
    })
    .catch(function(){ alert('❌ Gagal menyimpan'); })
    .finally(function(){ btn.textContent = '💾 Simpan'; btn.disabled = false; });
  }

  function saveModeration(btn){
    var data = collectModeration();
    btn.textContent = '⏳ Menyimpan...';
    btn.disabled = true;
    fetch('/api/actions/' + guildId + '/moderation', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify(data),
    })
    .then(function(r){ return r.json(); })
    .then(function(d){
      if(d.success) alert('✅ Konfigurasi moderasi disimpan!');
      else alert('❌ ' + (d.message || 'Gagal'));
    })
    .catch(function(){ alert('❌ Gagal menyimpan'); })
    .finally(function(){ btn.textContent = '💾 Simpan'; btn.disabled = false; });
  }

  // --- Init ---
  document.addEventListener('DOMContentLoaded', function(){
    loadRoles();
    loadChannels('levelNotifyChannel');
    setTimeout(function(){ loadChannels('modReportChannel'); }, 300);

    // Load level rewards
    fetch('/api/actions/' + guildId + '/level-rewards')
      .then(function(r){ return r.json(); })
      .then(function(d){
        if(!d.success) return;
        qs('levelRewardEnabled').checked = d.enabled;
        renderRewards(d.rewards);
        if(d.notify_channel){
          setTimeout(function(){
            qs('levelNotifyChannel').value = d.notify_channel;
          }, 500);
        }
      });

    // Load moderation config
    fetch('/api/actions/' + guildId + '/moderation')
      .then(function(r){ return r.json(); })
      .then(function(d){
        if(d.success) loadModerationConfig(d);
      });

    // Add reward
    qs('addRewardBtn').addEventListener('click', function(){
      var items = document.querySelectorAll('.reward-row');
      var nextLevel = items.length > 0 ? (parseInt(items[items.length-1].querySelector('.reward-level').value) || 0) + 5 : 5;
      addRewardRow(nextLevel, '');
      // populate roles for the new row
      var lastSel = document.querySelector('.reward-row:last-child .role-select');
      if(lastSel) populateRoles(lastSel);
    });

    // Strike action change → toggle duration
    document.querySelectorAll('.strike-action').forEach(function(sel){
      sel.addEventListener('change', function(){
        var prefix = this.id.replace('Action', '');
        toggleDuration(this, qs(prefix + 'Duration'));
      });
    });

    // Filter toggles
    document.querySelectorAll('.filter-tag').forEach(function(el){
      el.addEventListener('click', function(){
        this.classList.toggle('active');
      });
    });

    // Save buttons
    qs('saveLevelRewardsBtn').addEventListener('click', function(){ saveLevelRewards(this); });
    qs('saveModerationBtn').addEventListener('click', function(){ saveModeration(this); });
  });
})();
