(function(){
  var guildId = window.CURRENT_GUILD_ID;
  var isStats = document.getElementById('donationStatsGrid') !== null;
  var isSettings = document.getElementById('donationSettingsCard') !== null;

  function fmtRupiah(n){
    return 'Rp ' + Number(n).toLocaleString('id-ID');
  }

  function userAvatar(tx){
    if(tx.avatar_url) return tx.avatar_url;
    var defaultIdx = (parseInt(tx.user_id) >> 22) % 5;
    return 'https://cdn.discordapp.com/embed/avatars/' + defaultIdx + '.png';
  }
  function userName(tx){
    return tx.username || tx.user_id;
  }

  /* ---- Inline note edit ---- */
  function makeNoteCell(tx){
    var note = tx.note || '';
    return '<span class="note-display" data-tx="' + tx.id + '">'
      + '<span class="note-text">' + (note || '—') + '</span>'
      + '<button class="btn-note-edit" data-tx="' + tx.id + '" title="Edit catatan">✏️</button>'
      + '</span>';
  }

  function bindNoteEdits(){
    document.querySelectorAll('.btn-note-edit').forEach(function(btn){
      btn.addEventListener('click', function(){
        var txId = this.dataset.tx;
        var cell = this.closest('.note-display');
        var textEl = cell.querySelector('.note-text');
        var current = textEl.textContent === '—' ? '' : textEl.textContent;
        var input = document.createElement('input');
        input.type = 'text';
        input.className = 'note-input';
        input.value = current;
        input.placeholder = 'Tambah catatan...';
        cell.innerHTML = '';
        cell.appendChild(input);
        input.focus();
        input.select();

        function save(){
          var val = input.value.trim();
          fetch('/api/donations/' + guildId + '/note', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({id: txId, note: val})
          })
          .then(function(r){ return r.json(); })
          .then(function(res){
            if(res.success) location.reload();
            else alert('Gagal: ' + (res.message || 'unknown'));
          })
          .catch(function(){ alert('Network error'); });
        }

        input.addEventListener('keydown', function(e){
          if(e.key === 'Enter') { e.preventDefault(); save(); }
          if(e.key === 'Escape') location.reload();
        });
        input.addEventListener('blur', save);
      });
    });
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
              + '<div class="donor-user"><img class="user-avatar" src="' + userAvatar(u) + '" loading="lazy">'
              + '<span class="donor-name">' + userName(u) + '</span></div>'
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
            var confirmBtn = tx.status === 'completed'
              ? '<span class="status-completed">✔️</span>'
              : '<button class="btn-confirm-donation" data-tx="' + tx.id + '">✔️ Confirm</button>';
            html += '<tr>'
              + '<td><code>' + tx.id.slice(0,8) + '…</code></td>'
              + '<td><img class="user-avatar" src="' + userAvatar(tx) + '" loading="lazy"><span class="user-name-cell">' + userName(tx) + '</span></td>'
              + '<td class="amount-col">' + fmtRupiah(tx.amount) + '</td>'
              + '<td>' + (tx.payment_method || '—').toUpperCase() + '</td>'
              + '<td><span class="' + statusClass + '">' + statusLabel + '</span></td>'
              + '<td>' + created + '</td>'
              + '<td class="action-col">' + confirmBtn + '</td>'
              + '<td>' + makeNoteCell(tx) + '</td></tr>';
          }
        } else {
          html = '<tr><td colspan="8" class="loading">Belum ada data donasi</td></tr>';
        }
        document.getElementById('donationHistoryBody').innerHTML = html;

        // Bind confirm buttons
        document.querySelectorAll('.btn-confirm-donation').forEach(function(btn){
          btn.addEventListener('click', function(){
            var txId = this.dataset.tx;
            if(!confirm('Konfirmasi donasi ' + txId.slice(0,8) + '…?')) return;
            var self = this;
            self.disabled = true;
            self.textContent = '⏳...';
            fetch('/api/donations/' + guildId + '/confirm', {
              method: 'POST',
              headers: {'Content-Type': 'application/json'},
              body: JSON.stringify({id: txId})
            })
            .then(function(r){ return r.json(); })
            .then(function(res){
              if(res.success){
                location.reload();
              } else {
                alert('Gagal: ' + (res.message || 'unknown'));
                self.disabled = false;
                self.textContent = '✔️ Confirm';
              }
            })
            .catch(function(){
              alert('Network error');
              self.disabled = false;
              self.textContent = '✔️ Confirm';
            });
          });
        });

        bindNoteEdits();
      })
      .catch(function(){
        var el = document.getElementById('donationHistoryBody');
        if(el) el.innerHTML = '<tr><td colspan="8" class="loading">Gagal memuat data</td></tr>';
      });
  }

  /* ---- Settings Page ---- */
  if (isSettings) {
    // Load channels
    fetch('/api/guilds/' + guildId + '/channels')
      .then(function(r){ return r.json(); })
      .then(function(d){
        var sel = document.getElementById('donation-channel');
        if(!sel) return;
        var html = '<option value="">— Tidak ada (nonaktif) —</option>';
        if(d.channels && d.channels.length){
          d.channels.sort(function(a,b){ return a.name.localeCompare(b.name); });
          d.channels.forEach(function(ch){
            html += '<option value="' + ch.id + '"># ' + ch.name + '</option>';
          });
        }
        sel.innerHTML = html;

        // Load config setelah channel ready
        fetch('/api/donations/' + guildId + '/settings')
          .then(function(r){ return r.json(); })
          .then(function(cfg){
            if(!cfg.success) return;
            var c = cfg.config || {};
            document.getElementById('donation-enabled').checked = c.enabled !== false;
            if(c.channel_id) sel.value = c.channel_id;
            document.getElementById('donation-min-amount').value = c.min_amount || 0;
            var whInput = document.getElementById('donation-webhook-url');
            if(whInput) whInput.value = c.webhook_url || '';
            var tyInput = document.getElementById('donation-thank-you');
            if(tyInput) tyInput.value = c.thank_you_message || tyInput.placeholder;
            updateDonationStatus(c.enabled !== false);
          });
      });

    // Toggle → update status banner
    document.getElementById('donation-enabled').addEventListener('change', function(e){
      updateDonationStatus(e.target.checked);
    });

    function updateDonationStatus(enabled){
      var banner = document.getElementById('donationStatusBanner');
      var text = document.getElementById('donationStatusText');
      if(!banner || !text) return;
      if(enabled){
        banner.className = 'status-banner active';
        text.innerHTML = 'Fitur donasi sedang <strong>aktif</strong>.';
      } else {
        banner.className = 'status-banner inactive';
        text.innerHTML = 'Fitur donasi sedang <strong>nonaktif</strong>.';
      }
    }

    // Save settings (form submit)
    document.getElementById('donationSettingsForm').addEventListener('submit', function(e){
      e.preventDefault();
      var btn = document.getElementById('donation-save-settings');
      btn.disabled = true;
      btn.classList.add('loading');
      fetch('/api/donations/' + guildId + '/settings', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          enabled: document.getElementById('donation-enabled').checked,
          channel_id: document.getElementById('donation-channel').value,
          min_amount: parseInt(document.getElementById('donation-min-amount').value) || 0,
          webhook_url: (document.getElementById('donation-webhook-url')?.value || '').trim(),
          thank_you_message: (document.getElementById('donation-thank-you')?.value || '').trim()
        })
      })
      .then(function(r){ return r.json(); })
      .then(function(res){
        if(res.success) showToast('✅ Pengaturan disimpan!', 'success');
        else showToast('❌ ' + (res.message || 'Gagal menyimpan'), 'error');
      })
      .catch(function(){ showToast('❌ Network error', 'error'); })
      .finally(function(){
        btn.disabled = false;
        btn.classList.remove('loading');
      });
    });
  }

  function showToast(msg, type){
    var toast = document.getElementById('toast');
    if(!toast) return;
    var icon = document.getElementById('toastIcon');
    var msgEl = document.getElementById('toastMsg');
    if(icon) icon.textContent = type === 'success' ? '✅' : '❌';
    if(msgEl) msgEl.textContent = msg;
    toast.className = 'toast ' + (type || 'success');
    requestAnimationFrame(function(){ toast.classList.add('show'); });
    setTimeout(function(){ toast.classList.remove('show'); }, 4000);
  }

  // Copy webhook URL buttons
  document.querySelectorAll('.btn-copy').forEach(function(btn){
    btn.addEventListener('click', function(){
      var targetId = this.dataset.target;
      var codeEl = document.getElementById(targetId);
      if(!codeEl) return;
      var text = codeEl.textContent.trim();
      if(navigator.clipboard && navigator.clipboard.writeText){
        navigator.clipboard.writeText(text).then(function(){
          btn.textContent = '✅ Copied!';
          btn.classList.add('copied');
          setTimeout(function(){
            btn.textContent = '📋 Copy';
            btn.classList.remove('copied');
          }, 2000);
        }).catch(function(){
          fallbackCopy(text, btn);
        });
      } else {
        fallbackCopy(text, btn);
      }
    });
  });
  function fallbackCopy(text, btn){
    var ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed'; ta.style.left = '-9999px';
    document.body.appendChild(ta);
    ta.select();
    try {
      document.execCommand('copy');
      btn.textContent = '✅ Copied!';
      btn.classList.add('copied');
      setTimeout(function(){
        btn.textContent = '📋 Copy';
        btn.classList.remove('copied');
      }, 2000);
    } catch(e) {}
    document.body.removeChild(ta);
  }
})();
