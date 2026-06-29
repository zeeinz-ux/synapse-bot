(function(){
  var guildId = window.CURRENT_GUILD_ID;
  var isStats = document.getElementById('statsGrid') !== null;

  if (isStats) {
    fetch('/api/boosts/' + guildId + '/stats')
      .then(function(r){ return r.json(); })
      .then(function(d){
        if(!d.success) return;
        document.getElementById('statTotal').textContent = d.total;
        document.getElementById('statActive').textContent = d.active;
        document.getElementById('statExpired').textContent = d.expired;
        document.getElementById('statTier').textContent = d.current_tier;
        document.getElementById('statBar').style.width = d.progress + '%';
        document.getElementById('statProgress').textContent = d.progress + '% menuju ' + d.next_tier + ' (' + d.next_at + ' boost)';

        var html = '';
        if(d.top_users && d.top_users.length){
          for(var i=0; i<d.top_users.length; i++){
            var u = d.top_users[i];
            var defaultIdx = (parseInt(u.user_id) >> 22) % 5;
            var avatar = 'https://cdn.discordapp.com/embed/avatars/' + defaultIdx + '.png';
            html += '<tr><td>' + (i+1) + '</td>'
              + '<td><img class="user-avatar" src="' + avatar + '" loading="lazy">'
              + '<code>' + u.user_id + '</code></td>'
              + '<td>' + u.count + 'x</td></tr>';
          }
        } else {
          html = '<tr><td colspan="3" class="loading">Belum ada data boost</td></tr>';
        }
        document.getElementById('topBody').innerHTML = html;
      })
      .catch(function(){
        document.getElementById('topBody').innerHTML = '<tr><td colspan="3" class="loading">Gagal memuat data</td></tr>';
      });
  } else {
    fetch('/api/boosts/' + guildId + '/history')
      .then(function(r){ return r.json(); })
      .then(function(d){
        if(!d.success) return;
        var countEl = document.getElementById('boostCount');
        if(countEl) countEl.textContent = d.count + ' event';
        var html = '';
        if(d.boosts && d.boosts.length){
          for(var i=0; i<d.boosts.length; i++){
            var b = d.boosts[i];
            var boosted = b.boosted_at ? b.boosted_at.slice(0,19).replace('T',' ') : '—';
            var unboosted = b.unboosted_at ? b.unboosted_at.slice(0,19).replace('T',' ') : '—';
            var statusClass = b.status === 'active' ? 'status-active' : 'status-expired';
            var statusLabel = b.status === 'active' ? 'Active' : 'Expired';
            var defaultIdx = (parseInt(b.user_id) >> 22) % 5;
            var avatar = 'https://cdn.discordapp.com/embed/avatars/' + defaultIdx + '.png';
            html += '<tr>'
              + '<td><img class="user-avatar" src="' + avatar + '" loading="lazy"><code>' + b.user_id + '</code></td>'
              + '<td>' + boosted + '</td>'
              + '<td><span class="' + statusClass + '">' + statusLabel + '</span></td>'
              + '<td>' + unboosted + '</td>'
              + '<td>' + (b.note || '—') + '</td></tr>';
          }
        } else {
          html = '<tr><td colspan="5" class="loading">Belum ada data boost</td></tr>';
        }
        document.getElementById('historyBody').innerHTML = html;
      })
      .catch(function(){
        document.getElementById('historyBody').innerHTML = '<tr><td colspan="5" class="loading">Gagal memuat data</td></tr>';
      });
  }
})();