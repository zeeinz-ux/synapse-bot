(function(){
  var guildId = window.CURRENT_GUILD_ID;
  var fieldCount = 0;

  function val(id){ return (document.getElementById(id) || {}).value || ''; }
  function checked(id){ return (document.getElementById(id) || {}).checked || false; }

  function getEmbed(){
    var fields = [];
    document.querySelectorAll('.mb-field-item').forEach(function(el){
      fields.push({
        name: el.querySelector('.field-name').value || '\u200b',
        value: el.querySelector('.field-value').value || '\u200b',
        inline: el.querySelector('.field-inline').checked,
      });
    });
    return {
      title: val('mbTitle'),
      description: val('mbDesc'),
      color: (val('mbColor') || '5865f2').replace('#',''),
      author_name: val('mbAuthorName'),
      author_icon: val('mbAuthorIcon'),
      thumbnail: val('mbThumb'),
      image: val('mbImage'),
      footer_text: val('mbFooterText'),
      footer_icon: val('mbFooterIcon'),
      fields: fields,
    };
  }

  function renderPreview(){
    var e = getEmbed();
    var html = '';

    if(!e.title && !e.description && !e.author_name && !e.footer_text && e.fields.length === 0 && !e.thumbnail && !e.image){
      document.getElementById('mbPreviewInner').innerHTML = '<div class="mb-empty-preview">Isi form di samping untuk melihat preview</div>';
      return;
    }

    var color = e.color || '5865f2';
    var wrap = '<div class="mb-embed-preview" style="border-left-color:#' + color + '"><div class="embed-content">';

    if(e.author_name){
      wrap += '<div class="embed-author">';
      if(e.author_icon) wrap += '<img src="' + e.author_icon + '" loading="lazy">';
      wrap += e.author_name + '</div>';
    }

    if(e.thumbnail){
      wrap += '<div class="embed-thumb-wrap"><div class="embed-thumb" style="background-image:url(' + e.thumbnail + ')"></div></div>';
    }

    if(e.title) wrap += '<div class="embed-title">' + e.title + '</div>';
    if(e.description) wrap += '<div class="embed-desc">' + e.description.replace(/\n/g, '<br>') + '</div>';

    if(e.fields.length){
      wrap += '<div class="embed-fields">';
      for(var i=0; i<e.fields.length; i++){
        var f = e.fields[i];
        var ic = f.inline ? ' embed-field-inline' : '';
        wrap += '<div class="embed-field' + ic + '">'
          + '<div class="embed-field-name">' + f.name + '</div>'
          + '<div class="embed-field-value">' + f.value.replace(/\n/g, '<br>') + '</div>'
          + '</div>';
      }
      wrap += '</div>';
    }

    if(e.image) wrap += '<img class="embed-image" src="' + e.image + '" loading="lazy">';

    if(e.footer_text){
      wrap += '<div class="embed-footer">';
      if(e.footer_icon) wrap += '<img src="' + e.footer_icon + '" loading="lazy">';
      wrap += e.footer_text + '</div>';
    }

    wrap += '</div></div>';
    document.getElementById('mbPreviewInner').innerHTML = wrap;
  }

  function addField(name, value, inline){
    var idx = fieldCount++;
    var div = document.createElement('div');
    div.className = 'mb-field-item';
    div.innerHTML =
      '<div class="mb-field-item-header">'
      + '<span>Field #' + (idx + 1) + '</span>'
      + '<button type="button" class="btn-remove-field" data-idx="' + idx + '">✕</button>'
      + '</div>'
      + '<div class="mb-field">'
      + '<label>Name</label>'
      + '<input type="text" class="field-name" placeholder="Field name" value="' + (name || '') + '">'
      + '</div>'
      + '<div class="mb-field">'
      + '<label>Value</label>'
      + '<textarea class="field-value" rows="2" placeholder="Field value">' + (value || '') + '</textarea>'
      + '</div>'
      + '<div class="mb-field-row">'
      + '<input type="checkbox" class="field-inline" ' + (inline ? 'checked' : '') + '>'
      + '<label>Inline</label>'
      + '</div>';
    div.querySelector('.btn-remove-field').addEventListener('click', function(){
      div.remove();
      renderPreview();
    });
    var inputs = div.querySelectorAll('input, textarea');
    for(var i=0; i<inputs.length; i++){
      inputs[i].addEventListener('input', renderPreview);
    }
    document.getElementById('mbFieldsList').appendChild(div);
    renderPreview();
  }

  function clearFields(){
    document.getElementById('mbFieldsList').innerHTML = '';
    fieldCount = 0;
  }

  function loadEmbed(e){
    document.getElementById('mbTitle').value = e.title || '';
    document.getElementById('mbDesc').value = e.description || '';
    document.getElementById('mbColor').value = e.color || '5865f2';
    document.getElementById('mbColorPicker').value = '#' + (e.color || '5865f2');
    document.getElementById('mbAuthorName').value = e.author_name || '';
    document.getElementById('mbAuthorIcon').value = e.author_icon || '';
    document.getElementById('mbThumb').value = e.thumbnail || '';
    document.getElementById('mbImage').value = e.image || '';
    document.getElementById('mbFooterText').value = e.footer_text || '';
    document.getElementById('mbFooterIcon').value = e.footer_icon || '';
    clearFields();
    if(e.fields){
      for(var i=0; i<e.fields.length; i++){
        addField(e.fields[i].name, e.fields[i].value, e.fields[i].inline);
      }
    }
  }

  function resetForm(){
    document.getElementById('mbTitle').value = '';
    document.getElementById('mbDesc').value = '';
    document.getElementById('mbColor').value = '5865f2';
    document.getElementById('mbColorPicker').value = '#5865f2';
    document.getElementById('mbAuthorName').value = '';
    document.getElementById('mbAuthorIcon').value = '';
    document.getElementById('mbThumb').value = '';
    document.getElementById('mbImage').value = '';
    document.getElementById('mbFooterText').value = '';
    document.getElementById('mbFooterIcon').value = '';
    clearFields();
    renderPreview();
  }

  // --- Init ---
  document.addEventListener('DOMContentLoaded', function(){
    // Bind inputs to preview
    var allInputs = document.querySelectorAll('#mbEditorForm input, #mbEditorForm textarea, #mbEditorForm select');
    for(var i=0; i<allInputs.length; i++){
      allInputs[i].addEventListener('input', renderPreview);
    }

    document.getElementById('mbColorPicker').addEventListener('input', function(){
      document.getElementById('mbColor').value = this.value.replace('#','');
      renderPreview();
    });
    document.getElementById('mbColor').addEventListener('input', function(){
      document.getElementById('mbColorPicker').value = '#' + (this.value || '5865f2');
      renderPreview();
    });

    document.getElementById('mbAddField').addEventListener('click', function(){ addField('','',false); });

    document.getElementById('mbClearBtn').addEventListener('click', function(){
      if(confirm('Reset semua field?')) resetForm();
    });

    if(document.getElementById('mbAddField')) addField('','',false);
    renderPreview();

    // Load channels
    fetch('/api/message-builder/' + guildId + '/channels')
      .then(function(r){ return r.json(); })
      .then(function(d){
        if(!d.success || !d.channels.length) return;
        var sel = document.getElementById('mbChannel');
        for(var i=0; i<d.channels.length; i++){
          var opt = document.createElement('option');
          opt.value = d.channels[i].id;
          opt.textContent = '#' + d.channels[i].name;
          sel.appendChild(opt);
        }
      });

    // Send
    document.getElementById('mbSendBtn').addEventListener('click', function(){
      var channelId = document.getElementById('mbChannel').value;
      if(!channelId){ alert('Pilih channel dulu!'); return; }
      if(!confirm('Kirim embed ke channel terpilih?')) return;
      var btn = this;
      btn.textContent = '⏳ Mengirim...';
      btn.disabled = true;
      fetch('/api/message-builder/' + guildId + '/send', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({
          channel_id: channelId,
          embed: getEmbed(),
          content: val('mbContent'),
        }),
      })
      .then(function(r){ return r.json(); })
      .then(function(d){
        if(d.success){
          alert('✅ Embed berhasil dikirim!');
        } else {
          alert('❌ Gagal: ' + (d.message || 'unknown'));
        }
      })
      .catch(function(){ alert('❌ Gagal mengirim embed'); })
      .finally(function(){
        btn.textContent = '📤 Kirim';
        btn.disabled = false;
      });
    });

    // Save template
    document.getElementById('mbSaveBtn').addEventListener('click', function(){
      var name = prompt('Nama template:');
      if(!name) return;
      var btn = this;
      btn.textContent = '⏳ Menyimpan...';
      btn.disabled = true;
      fetch('/api/message-builder/' + guildId + '/templates', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({
          name: name,
          embed: getEmbed(),
          content: val('mbContent'),
        }),
      })
      .then(function(r){ return r.json(); })
      .then(function(d){
        if(d.success){
          alert('✅ Template "' + name + '" disimpan!');
        } else {
          alert('❌ Gagal: ' + (d.message || 'unknown'));
        }
      })
      .catch(function(){ alert('❌ Gagal menyimpan template'); })
      .finally(function(){
        btn.textContent = '💾 Simpan';
        btn.disabled = false;
      });
    });

    // Load templates modal
    var loadModal = document.getElementById('mbLoadModal');
    document.getElementById('mbLoadBtn').addEventListener('click', function(){
      var list = document.getElementById('mbTemplateList');
      list.innerHTML = '<div style="padding:1rem;text-align:center;color:#888;">Memuat...</div>';
      loadModal.classList.add('open');
      fetch('/api/message-builder/' + guildId + '/templates')
        .then(function(r){ return r.json(); })
        .then(function(d){
          if(!d.success || !d.templates.length){
            list.innerHTML = '<div style="padding:1rem;text-align:center;color:#888;">Belum ada template tersimpan</div>';
            return;
          }
          var html = '';
          for(var i=0; i<d.templates.length; i++){
            var t = d.templates[i];
            var date = t.updated_at ? new Date(t.updated_at * 1000).toLocaleDateString() : '';
            html += '<div class="template-item" data-id="' + t.id + '">'
              + '<div style="flex:1" class="template-load-btn">'
              + '<div class="template-item-name">' + (t.name || 'Untitled') + '</div>'
              + '<div class="template-item-date">' + date + '</div>'
              + '</div>'
              + '<button class="template-item-delete" title="Hapus">✕</button>'
              + '</div>';
          }
          list.innerHTML = html;

          list.querySelectorAll('.template-load-btn').forEach(function(el){
            el.addEventListener('click', function(){
              var id = this.parentElement.dataset.id;
              var tpl = d.templates.find(function(t){ return t.id === id; });
              if(tpl){
                loadEmbed(tpl.embed || {});
                document.getElementById('mbContent').value = tpl.content || '';
                loadModal.classList.remove('open');
              }
            });
          });
          list.querySelectorAll('.template-item-delete').forEach(function(btn){
            btn.addEventListener('click', function(e){
              e.stopPropagation();
              if(!confirm('Hapus template ini?')) return;
              var id = this.parentElement.dataset.id;
              var that = this;
              fetch('/api/message-builder/' + guildId + '/templates/' + id, { method: 'DELETE' })
                .then(function(r){ return r.json(); })
                .then(function(d2){
                  if(d2.success){
                    that.parentElement.remove();
                  }
                });
            });
          });
        })
        .catch(function(){
          list.innerHTML = '<div style="padding:1rem;text-align:center;color:#888;">Gagal memuat template</div>';
        });
    });
    document.getElementById('mbLoadClose').addEventListener('click', function(){ loadModal.classList.remove('open'); });
    loadModal.addEventListener('click', function(e){ if(e.target === loadModal) loadModal.classList.remove('open'); });
  });
})();
