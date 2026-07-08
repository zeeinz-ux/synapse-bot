(function(){
  var guildId = window.CURRENT_GUILD_ID;
  var fieldCount = 0;

  // ── Discord character limits ──
  var CHAR_LIMITS = {
    mbTitle: 256,
    mbDesc: 4096,
    mbFooterText: 2048,
  };
  var FIELD_NAME_LIMIT = 256;
  var FIELD_VALUE_LIMIT = 1024;

  function val(id){ return (document.getElementById(id) || {}).value || ''; }
  function checked(id){ return (document.getElementById(id) || {}).checked || false; }

  // ── Character counter ──
  function updateCharCount(input){
    var id = input && input.id;
    if(!id || !CHAR_LIMITS[id]) return;
    var counter = document.querySelector('.mb-char-count[data-for="' + id + '"]');
    if(!counter) return;
    var len = input.value.length;
    var limit = CHAR_LIMITS[id];
    counter.textContent = len + '/' + limit;
    counter.classList.toggle('over', len > limit);
  }

  function updateFieldCharCount(el){
    var nameInput = el.querySelector('.field-name');
    var valueInput = el.querySelector('.field-value');
    var nc = el.querySelector('.field-char-name');
    var vc = el.querySelector('.field-char-value');
    if(nc && nameInput){
      var nl = nameInput.value.length;
      nc.textContent = nl + '/' + FIELD_NAME_LIMIT;
      nc.classList.toggle('over', nl > FIELD_NAME_LIMIT);
    }
    if(vc && valueInput){
      var vl = valueInput.value.length;
      vc.textContent = vl + '/' + FIELD_VALUE_LIMIT;
      vc.classList.toggle('over', vl > FIELD_VALUE_LIMIT);
    }
  }

  // ── Validation before send ──
  function hasCharLimitErrors(){
    var errors = [];
    // Main fields
    var mainIds = ['mbTitle', 'mbDesc', 'mbFooterText'];
    for(var i=0; i<mainIds.length; i++){
      var inp = document.getElementById(mainIds[i]);
      if(inp && inp.value.length > CHAR_LIMITS[mainIds[i]]){
        errors.push(mainIds[i]);
      }
    }
    // Field items
    document.querySelectorAll('.mb-field-item').forEach(function(el){
      var n = el.querySelector('.field-name');
      var v = el.querySelector('.field-value');
      if(n && n.value.length > FIELD_NAME_LIMIT) errors.push('field-name');
      if(v && v.value.length > FIELD_VALUE_LIMIT) errors.push('field-value');
    });
    return errors.length > 0;
  }

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

  function esc(str){
    var d = document.createElement('div');
    d.textContent = str || '';
    return d.innerHTML;
  }

  function renderPreview(){
    var e = getEmbed();
    if(!e.title && !e.description && !e.author_name && !e.footer_text && e.fields.length === 0 && !e.thumbnail && !e.image){
      document.getElementById('mbPreviewInner').innerHTML = '<div class="mb-empty-preview">Isi form di samping untuk melihat preview</div>';
      return;
    }
    var color = e.color || '5865f2';
    var wrap = '<div class="mb-embed-preview" style="border-left-color:#' + color + '"><div class="embed-content">';
    if(e.author_name){
      wrap += '<div class="embed-author">';
      if(e.author_icon) wrap += '<img src="' + esc(e.author_icon) + '" loading="lazy">';
      wrap += esc(e.author_name) + '</div>';
    }
    if(e.thumbnail){
      wrap += '<div class="embed-thumb-wrap"><div class="embed-thumb" style="background-image:url(' + esc(e.thumbnail) + ')"></div></div>';
    }
    if(e.title) wrap += '<div class="embed-title">' + esc(e.title) + '</div>';
    if(e.description) wrap += '<div class="embed-desc">' + esc(e.description).replace(/\n/g, '<br>') + '</div>';
    if(e.fields.length){
      wrap += '<div class="embed-fields">';
      for(var i=0; i<e.fields.length; i++){
        var f = e.fields[i];
        var ic = f.inline ? ' embed-field-inline' : '';
        wrap += '<div class="embed-field' + ic + '">'
          + '<div class="embed-field-name">' + esc(f.name) + '</div>'
          + '<div class="embed-field-value">' + esc(f.value).replace(/\n/g, '<br>') + '</div>'
          + '</div>';
      }
      wrap += '</div>';
    }
    if(e.image) wrap += '<img class="embed-image" src="' + esc(e.image) + '" loading="lazy">';
    if(e.footer_text){
      wrap += '<div class="embed-footer">';
      if(e.footer_icon) wrap += '<img src="' + esc(e.footer_icon) + '" loading="lazy">';
      wrap += esc(e.footer_text) + '</div>';
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
      + '<div class="btn-group">'
      + '<button type="button" class="btn-reorder-field btn-move-up" title="Naik">&#9650;</button>'
      + '<button type="button" class="btn-reorder-field btn-move-down" title="Turun">&#9660;</button>'
      + '<button type="button" class="btn-remove-field" title="Hapus">&#10005;</button>'
      + '</div>'
      + '</div>'
      + '<div class="mb-field">'
      + '<label>Name <span class="mb-char-count field-char-name">0/' + FIELD_NAME_LIMIT + '</span></label>'
      + '<input type="text" class="field-name" placeholder="Field name" maxlength="' + FIELD_NAME_LIMIT + '" value="' + esc(name) + '">'
      + '</div>'
      + '<div class="mb-field">'
      + '<label>Value <span class="mb-char-count field-char-value">0/' + FIELD_VALUE_LIMIT + '</span></label>'
      + '<textarea class="field-value" rows="2" placeholder="Field value" maxlength="' + FIELD_VALUE_LIMIT + '">' + esc(value) + '</textarea>'
      + '</div>'
      + '<div class="mb-field-row">'
      + '<input type="checkbox" class="field-inline" ' + (inline ? 'checked' : '') + '>'
      + '<label>Inline</label>'
      + '</div>';
    div.querySelector('.btn-remove-field').addEventListener('click', function(){
      div.remove();
      renderPreview();
    });
    div.querySelector('.btn-move-up').addEventListener('click', function(){
      var prev = div.previousElementSibling;
      if(prev){ div.parentElement.insertBefore(div, prev); renderPreview(); }
    });
    div.querySelector('.btn-move-down').addEventListener('click', function(){
      var next = div.nextElementSibling;
      if(next){ div.parentElement.insertBefore(next, div); renderPreview(); }
    });
    var inputs = div.querySelectorAll('input, textarea');
    for(var i=0; i<inputs.length; i++){
      inputs[i].addEventListener('input', function(){
        updateFieldCharCount(this.closest('.mb-field-item'));
        renderPreview();
      });
    }
    document.getElementById('mbFieldsList').appendChild(div);
    updateFieldCharCount(div);
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
    renderPreview();
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

  // ── Image upload helpers ──
  function resizeImage(file, maxWidth, quality){
    if(maxWidth === void 0) maxWidth = 1200;
    if(quality === void 0) quality = 0.85;
    return new Promise(function(resolve, reject){
      var img = new Image();
      var reader = new FileReader();
      reader.onload = function(e){ img.src = e.target.result; };
      reader.onerror = function(err){ reject(err); };
      img.onload = function(){
        var width = img.width;
        var height = img.height;
        if(width > maxWidth){
          height = Math.round((height * maxWidth) / width);
          width = maxWidth;
        }
        var canvas = document.createElement("canvas");
        canvas.width = width;
        canvas.height = height;
        var ctx = canvas.getContext("2d");
        ctx.drawImage(img, 0, 0, width, height);
        resolve(canvas.toDataURL("image/jpeg", quality));
      };
      img.onerror = function(err){ reject(err); };
      reader.readAsDataURL(file);
    });
  }

  function loadGalleryImages(targetId){
    var grid = document.getElementById('mbGalleryGrid');
    grid.innerHTML = '<div class="gallery-empty">Memuat gambar...</div>';
    fetch('/api/gallery/images')
      .then(function(r){ return r.json(); })
      .then(function(d){
        if(!d.success || !d.images.length){
          grid.innerHTML = '<div class="gallery-empty">'
            + (d.success ? 'Belum ada gambar tersimpan' : 'Gagal memuat gambar: ' + (d.message || 'unknown'))
            + '</div>';
          return;
        }
        var html = '';
        for(var i=0; i<d.images.length; i++){
          var img = d.images[i];
          html += '<div class="gallery-item" data-url="' + esc(img.url) + '">'
            + '<img src="' + esc(img.url) + '" loading="lazy">'
            + '<div class="gallery-item-label">' + esc(img.label) + '</div>'
            + '</div>';
        }
        grid.innerHTML = html;
        grid.querySelectorAll('.gallery-item').forEach(function(el){
          el.addEventListener('click', function(){
            document.getElementById(targetId).value = this.dataset.url;
            document.getElementById('mbGalleryModal').classList.remove('open');
            renderPreview();
          });
        });
      })
      .catch(function(){
        grid.innerHTML = '<div class="gallery-empty">Gagal memuat gambar</div>';
      });
  }

  function setupUploadZone(targetId){
    var zone = document.getElementById('mbGalleryUploadZone');
    var input = document.getElementById('mbGalleryFileInput');
    var preview = document.getElementById('mbGalleryUploadPreview');
    var previewImg = document.getElementById('mbGalleryUploadPreviewImg');
    var status = document.getElementById('mbGalleryUploadStatus');
    if(!zone || !input) return;

    function preventDefaults(e){ e.preventDefault(); e.stopPropagation(); }
    function highlight(){ zone.classList.add('dragover'); }
    function unhighlight(){ zone.classList.remove('dragover'); }

    ['dragenter','dragover'].forEach(function(ev){ zone.addEventListener(ev, highlight, false); });
    ['dragleave','drop'].forEach(function(ev){ zone.addEventListener(ev, unhighlight, false); });
    ['dragenter','dragover','dragleave','drop'].forEach(function(ev){
      zone.addEventListener(ev, preventDefaults, false);
    });

    zone.addEventListener('drop', function(e){
      handleFiles(e.dataTransfer.files, targetId);
    }, false);
    zone.addEventListener('click', function(){ input.click(); });
    input.addEventListener('change', function(){
      handleFiles(this.files, targetId);
    });

    function handleFiles(files, tid){
      if(!files.length) return;
      var file = files[0];
      if(!file.type.startsWith('image/')){
        status.textContent = 'File harus gambar!';
        status.className = 'mb-upload-status error';
        return;
      }
      if(file.size > 5 * 1024 * 1024){
        status.textContent = 'Maks 5MB!';
        status.className = 'mb-upload-status error';
        return;
      }
      zone.classList.add('has-file');
      status.textContent = 'Memproses...';
      status.className = 'mb-upload-status uploading';
      var reader = new FileReader();
      reader.onload = function(e){
        previewImg.src = e.target.result;
        resizeImage(file, 1200, 0.85).then(function(resized){
          status.textContent = 'Mengupload...';
          fetch('/api/gallery/upload', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
              data_url: resized,
              filename: file.name,
            }),
          })
          .then(function(r){ return r.json(); })
          .then(function(d){
            if(d.success){
              status.textContent = 'Upload berhasil!';
              status.className = 'mb-upload-status done';
              setTimeout(function(){
                zone.classList.remove('has-file');
                previewImg.src = '';
                status.textContent = '';
                status.className = 'mb-upload-status';
                input.value = '';
                loadGalleryImages(tid);
              }, 800);
            } else {
              status.textContent = 'Gagal: ' + (d.message || 'unknown');
              status.className = 'mb-upload-status error';
            }
          })
          .catch(function(){
            status.textContent = 'Gagal upload';
            status.className = 'mb-upload-status error';
          });
        });
      };
      reader.readAsDataURL(file);
    }
  }

  // ── Image gallery ──
  function openGallery(targetId){
    var modal = document.getElementById('mbGalleryModal');
    modal.classList.add('open');
    setupUploadZone(targetId);
    loadGalleryImages(targetId);
  }

  // ── Collapsible: Media & Footer ──
  function initCollapsible(){
    var toggle = document.getElementById('mbMediaToggle');
    var body = document.getElementById('mbMediaBody');
    var arrow = document.getElementById('mbMediaArrow');
    if(!toggle || !body) return;
    // Start collapsed
    body.classList.add('hidden');
    arrow.classList.add('collapsed');
    toggle.addEventListener('click', function(){
      body.classList.toggle('hidden');
      arrow.classList.toggle('collapsed');
    });
  }

  // --- Init ---
  document.addEventListener('DOMContentLoaded', function(){
    // Bind inputs to preview + char count
    var allInputs = document.querySelectorAll('#mbEditorForm input, #mbEditorForm textarea, #mbEditorForm select');
    for(var i=0; i<allInputs.length; i++){
      allInputs[i].addEventListener('input', function(){
        updateCharCount(this);
        renderPreview();
      });
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

    // Init char counters for main fields
    var mainIds = ['mbTitle', 'mbDesc', 'mbFooterText'];
    for(var i=0; i<mainIds.length; i++){
      var inp = document.getElementById(mainIds[i]);
      if(inp) updateCharCount(inp);
    }

    initCollapsible();
    if(document.getElementById('mbAddField')) addField('','',false);
    renderPreview();

    // Load channels
    fetch('/api/message-builder/' + guildId + '/channels')
      .then(function(r){ return r.json(); })
      .then(function(d){
        if(!d.success || !d.channels.length){
          console.warn('[MB] Gagal muat channels:', d && d.message || 'unknown');
          return;
        }
        var sel = document.getElementById('mbChannel');
        for(var i=0; i<d.channels.length; i++){
          var opt = document.createElement('option');
          opt.value = d.channels[i].id;
          opt.textContent = '#' + d.channels[i].name;
          sel.appendChild(opt);
        }
      })
      .catch(function(){
        console.warn('[MB] Network error saat muat channels');
      });

    // Gallery pick buttons
    document.querySelectorAll('.btn-pick-image').forEach(function(btn){
      btn.addEventListener('click', function(){
        openGallery(this.dataset.target);
      });
    });
    document.getElementById('mbGalleryClose').addEventListener('click', function(){
      document.getElementById('mbGalleryModal').classList.remove('open');
    });
    document.getElementById('mbGalleryModal').addEventListener('click', function(e){
      if(e.target === this) this.classList.remove('open');
    });

    // Send
    document.getElementById('mbSendBtn').addEventListener('click', function(){
      var channelId = document.getElementById('mbChannel').value;
      if(!channelId){ alert('Pilih channel dulu!'); return; }
      if(hasCharLimitErrors()){
        if(!confirm('Ada field yang melebihi batas karakter Discord. Tetap kirim?')) return;
      }
      if(!confirm('Kirim embed ke channel terpilih?')) return;
      var btn = this;
      btn.textContent = 'Mengirim...';
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
          alert('Embed berhasil dikirim!');
        } else {
          alert('Gagal: ' + (d.message || 'unknown'));
        }
      })
      .catch(function(){ alert('Gagal mengirim embed'); })
      .finally(function(){
        btn.textContent = 'Kirim';
        btn.disabled = false;
      });
    });

    // Save template
    document.getElementById('mbSaveBtn').addEventListener('click', function(){
      var name = prompt('Nama template:');
      if(!name) return;
      var btn = this;
      btn.textContent = 'Menyimpan...';
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
          alert('Template "' + name + '" disimpan!');
        } else {
          alert('Gagal: ' + (d.message || 'unknown'));
        }
      })
      .catch(function(){ alert('Gagal menyimpan template'); })
      .finally(function(){
        btn.textContent = 'Simpan';
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
            list.innerHTML = '<div style="padding:1rem;text-align:center;color:#888;">'
              + (d.success ? 'Belum ada template tersimpan' : 'Gagal memuat template: ' + (d.message || 'unknown'))
              + '</div>';
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
              + '<button class="template-item-delete" title="Hapus">&#10005;</button>'
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
                  } else {
                    alert('Gagal hapus: ' + (d2.message || 'unknown'));
                  }
                })
                .catch(function(){
                  alert('Gagal menghapus template');
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
