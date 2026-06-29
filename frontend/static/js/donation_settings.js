(function(){
  var guildId = window.CURRENT_GUILD_ID;
  var isStats = document.getElementById('donationStatsGrid') !== null;

  function fmtRupiah(n){
    return 'Rp ' + Number(n).toLocaleString('id-ID');
  }

  function defaultAvatar(uid){
    var defaultIdx = (parseInt(uid) >> 22) % 5;
    return 'https://cdn.discordapp.com/embed/avatars/' + defaultIdx + '.png';
  }

  if (isStats) {
    fetch('/api/donations/' + guildId + '/stats')
      .then(function(r){ return r.json(); })
      .then(function(d){
        if(!d.success) return;
        document.getElementById('statTotalCount').textContent = d.total_count;
        document.getElementById('statTotalAmount').textContent = fmtRupiah(d.total_amount);
        document.getElementById('statAverage').textContent = fmtRupiah(d.average_amount);
        document.getElementById('statCompleted').textContent = d.completed_count;

        var html = '';
        if(d.top_donors && d.top_donors.length){
          for(var i=0; i<d.top_donors.length; i++){
            var u = d.top_donors[i];
            var rankClass = i === 0 ? 'gold' : i === 1 ? 'silver' : i === 2 ? 'bronze' : '';
            html += '<li>'
              + '<div class="donor-rank ' + rankClass + '">' + (i+1) + '</div>'
              + '<div class="donor-user"><img class="user-avatar" src="' + defaultAvatar(u.user_id) + '" loading="lazy">'
              + '<code>' + u.user_id + '</code></div>'
              + '<div class="donor-amount">' + fmtRupiah(u.total) + '</div>'
              + '</li>';
          }
        } else {
          html = '<li style="padding:1.25rem;text-align:center;color:#888;">Belum ada data donasi</li>';
        }
        document.getElementById('topDonorsBody').innerHTML = html;

        var methodHtml = '';
        if(d.method_breakdown && d.method_breakdown.length){
          for(var i=0; i<d.method_breakdown.length; i++){
            var m = d.method_breakdown[i];
            methodHtml += '<li><span class="method-name">' + m.method.toUpperCase() + '</span><span class="method-count">' + m.count + 'x</span></li>';
          }
        } else {
          methodHtml = '<li style="padding:1.25rem;text-align:center;color:#888;">Belum ada data</li>';
        }
        document.getElementById('methodBody').innerHTML = methodHtml;
      })
      .catch(function(){
        document.getElementById('topDonorsBody').innerHTML = '<li style="padding:1.25rem;text-align:center;color:#888;">Gagal memuat data</li>';
        document.getElementById('methodBody').innerHTML = '<li style="padding:1.25rem;text-align:center;color:#888;">Gagal memuat data</li>';
      });
  } else {
    fetch('/api/donations/' + guildId + '/history')
      .then(function(r){ return r.json(); })
      .then(function(d){
        if(!d.success) return;
        var countEl = document.getElementById('donationCount');
        if(countEl) countEl.textContent = d.count + ' transaksi';
        var html = '';
        if(d.donations && d.donations.length){
          for(var i=0; i<d.donations.length; i++){
            var tx = d.donations[i];
            var created = tx.created_at ? tx.created_at.slice(0,19).replace('T',' ') : '—';
            var statusClass = tx.status === 'completed' ? 'status-completed' : 'status-pending';
            var statusLabel = tx.status === 'completed' ? 'Completed' : 'Pending';
            html += '<tr>'
              + '<td><code>' + tx.id.slice(0,8) + '…</code></td>'
              + '<td><img class="user-avatar" src="' + defaultAvatar(tx.user_id) + '" loading="lazy"><code>' + tx.user_id + '</code></td>'
              + '<td class="amount-col">' + fmtRupiah(tx.amount) + '</td>'
              + '<td>' + (tx.payment_method || '—').toUpperCase() + '</td>'
              + '<td><span class="' + statusClass + '">' + statusLabel + '</span></td>'
              + '<td>' + created + '</td>'
              + '<td>' + (tx.note || '—') + '</td></tr>';
          }
        } else {
          html = '<tr><td colspan="7" class="loading">Belum ada data donasi</td></tr>';
        }
        document.getElementById('donationHistoryBody').innerHTML = html;
      })
      .catch(function(){
        document.getElementById('donationHistoryBody').innerHTML = '<tr><td colspan="7" class="loading">Gagal memuat data</td></tr>';
      });
  }
})();
