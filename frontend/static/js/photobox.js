/**
 * Photobox — Multi-theme Photobooth Strip
 * Pilih tema & jumlah foto, ganti tema di tengah jalan, kirim via webhook.
 */
(function () {
  'use strict';

  const $ = (id) => document.getElementById(id);

  const states = {
    loading: $('pbStateLoading'),
    picker: $('pbStatePicker'),
    camera: $('pbStateCamera'),
    countdown: $('pbStateCountdown'),
    preview: $('pbStatePreview'),
    sending: $('pbStateSending'),
    success: $('pbStateSuccess'),
    error: $('pbStateError'),
  };

  const video = $('pbVideo');
  const canvas = $('pbCanvas');
  const countdownNum = $('pbCountdownNum');
  const countdownLabel = $('pbCountdownLabel');
  const errorText = $('pbErrorText');
  const stepLabel = $('pbStepLabel');
  const btnCaptureText = $('pbBtnCaptureText');
  const stepIndicator = $('pbStepIndicator');
  const frameDeco = $('pbFrameDeco');
  const frameLabel = $('pbFrameLabel');
  const floaties = $('pbFloaties');

  const pickerCards = document.querySelectorAll('.pb-picker-card');
  const themeBtns = document.querySelectorAll('.pb-theme-btn');
  const liveDots = document.querySelectorAll('.live-theme-dot');
  const btnStart = $('pbBtnStart');
  const btnCapture = $('pbBtnCapture');
  const btnRetake = $('pbBtnRetake');
  const btnSend = $('pbBtnSend');
  const btnRetry = $('pbBtnRetry');
  const btnAgain = $('pbBtnAgain');
  const btnBackPicker = $('pbBtnBackPicker');

  // ── State ──
  let mediaStream = null;
  let capturedFrames = [];
  let isProcessing = false;
  let currentStep = 1;
  let TOTAL_SHOTS = 3;
  let currentTheme = 'pink-love';

  // ═══════════════════════════════════════════════
  // THEMES
  // ═══════════════════════════════════════════════
  const THEMES = {
    'pink-love': {
      accent: '#ff6b9d',
      secondary: '#c8a8e9',
      stripBg: '#fff8fa',
      border: '#f0e0e8',
      text: '#ff6b9d',
      textMuted: '#b0a0b0',
      grad1: '#ff6b9d',
      grad2: '#c8a8e9',
      floaties: ['🌸', '⭐', '💖', '✨', '🫶', '🌟'],
      deco: ['💖', '✨', '🌸', '💕'],
      decoPos: [
        { top: '6px', left: '8px' },
        { top: '6px', right: '8px' },
        { bottom: '6px', left: '8px' },
        { bottom: '6px', right: '8px' },
      ],
      label: '✨ cuek — cantik — gemas ✨',
      betweenEmojis: ['💖', '✨', '⭐', '🫶', '🌸'],
      brand: '💖  Synapse Photobox  💖',
    },
    'sky-blue': {
      accent: '#4fc3f7',
      secondary: '#a8d8e9',
      stripBg: '#f0f8ff',
      border: '#d0e8f5',
      text: '#4fc3f7',
      textMuted: '#8ab4d0',
      grad1: '#4fc3f7',
      grad2: '#a8d8e9',
      floaties: ['☁️', '⭐', '🌸', '✨', '🌼', '🌟'],
      deco: ['⭐', '☁️', '🌸', '✨'],
      decoPos: [
        { top: '4px', left: '6px' },
        { top: '4px', right: '6px' },
        { bottom: '4px', left: '6px' },
        { bottom: '4px', right: '6px' },
      ],
      label: '✨ langit — bintang — bunga ✨',
      betweenEmojis: ['⭐', '🌸', '✨', '🌼', '☁️'],
      brand: '☁️  Synapse Photobox  ☁️',
    },
    'mint-night': {
      accent: '#69db7c',
      secondary: '#a8e9c8',
      stripBg: '#f5fff7',
      border: '#d0ead8',
      text: '#69db7c',
      textMuted: '#90b8a0',
      grad1: '#69db7c',
      grad2: '#a8e9c8',
      floaties: ['🍃', '🌿', '🌸', '✨', '🌙', '🌟'],
      deco: ['🌿', '🌙', '🍃', '✨'],
      decoPos: [
        { top: '4px', left: '6px' },
        { top: '4px', right: '6px' },
        { bottom: '4px', left: '6px' },
        { bottom: '4px', right: '6px' },
      ],
      label: '✨ segar — santai — damai ✨',
      betweenEmojis: ['🍃', '🌸', '✨', '🌙', '🌿'],
      brand: '🌿  Synapse Photobox  🌿',
    },
  };

  // ═══════════════════════════════════════════════
  // THEME SWITCHING
  // ═══════════════════════════════════════════════
  function applyTheme(themeId) {
    currentTheme = themeId;
    const t = THEMES[themeId];

    // Set data attribute on body (triggers CSS variables)
    document.body.setAttribute('data-theme', themeId);

    // Frame decorations
    frameDeco.innerHTML = '';
    t.deco.forEach((emoji, i) => {
      const el = document.createElement('span');
      el.className = 'frame-deco-item';
      el.textContent = emoji;
      el.style.top = t.decoPos[i].top;
      el.style.left = t.decoPos[i].left;
      el.style.right = t.decoPos[i].right || 'auto';
      el.style.bottom = t.decoPos[i].bottom || 'auto';
      el.style.animationDelay = (i * 0.3) + 's';
      frameDeco.appendChild(el);
    });

    // Frame label
    frameLabel.textContent = t.label;

    // Floating decorations
    floaties.innerHTML = '';
    t.floaties.forEach((emoji, i) => {
      const el = document.createElement('span');
      el.className = 'floaty';
      el.textContent = emoji;
      const positions = [
        { top: '8%', left: '5%' }, { top: '15%', right: '8%' },
        { top: '40%', left: '3%' }, { bottom: '30%', right: '5%' },
        { bottom: '15%', left: '10%' }, { top: '60%', right: '3%' },
      ];
      el.style.top = positions[i].top || 'auto';
      el.style.left = positions[i].left || 'auto';
      el.style.right = positions[i].right || 'auto';
      el.style.bottom = positions[i].bottom || 'auto';
      el.style.animationDelay = (i * 0.5) + 's';
      floaties.appendChild(el);
    });

    // Update active states
    themeBtns.forEach((btn) => {
      btn.classList.toggle('active', btn.dataset.theme === themeId);
    });
    liveDots.forEach((dot) => {
      dot.classList.toggle('active', dot.dataset.theme === themeId);
    });
  }

  // ═══════════════════════════════════════════════
  // STEP LABELS
  // ═══════════════════════════════════════════════
  const STEP_LABELS = {
    1: ['Pose terbaik!'],
    2: ['Pose pertama!', 'Pose terakhir!'],
    3: ['Pose pertama!', 'Pose kedua!', 'Pose terakhir!'],
    4: ['Pose #1!', 'Pose #2!', 'Pose #3!', 'Pose terakhir!'],
    5: ['Pose #1!', 'Pose #2!', 'Pose #3!', 'Pose #4!', 'Pose terakhir!'],
  };

  // ═══════════════════════════════════════════════
  // WEBHOOK
  // ═══════════════════════════════════════════════
  const params = new URLSearchParams(window.location.search);
  const webhookId = params.get('whid');
  const webhookToken = params.get('whtoken');
  const WEBHOOK_URL = webhookId && webhookToken
    ? `https://discord.com/api/webhooks/${webhookId}/${webhookToken}`
    : null;

  // ═══════════════════════════════════════════════
  // UTILITY
  // ═══════════════════════════════════════════════
  function showState(name) {
    Object.keys(states).forEach((key) => {
      states[key].classList.toggle('hidden', key !== name);
    });
  }

  function sleep(ms) {
    return new Promise((r) => setTimeout(r, ms));
  }

  function pad(n) {
    return String(n).padStart(2, '0');
  }

  function timestamp() {
    const d = new Date();
    return `photobooth-${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}-${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`;
  }

  function formatDate() {
    const d = new Date();
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'Mei', 'Jun', 'Jul', 'Agu', 'Sep', 'Okt', 'Nov', 'Des'];
    return `${pad(d.getDate())} ${months[d.getMonth()]} ${d.getFullYear()}`;
  }

  // ═══════════════════════════════════════════════
  // STEP INDICATOR
  // ═══════════════════════════════════════════════
  function buildStepIndicator(count) {
    stepIndicator.innerHTML = '';
    for (let i = 1; i <= count; i++) {
      if (i > 1) {
        const line = document.createElement('span');
        line.className = 'step-line';
        stepIndicator.appendChild(line);
      }
      const dot = document.createElement('span');
      dot.className = 'step-dot' + (i === 1 ? ' active' : '');
      dot.dataset.step = i;
      dot.textContent = i;
      stepIndicator.appendChild(dot);
    }
  }

  function updateStep(step) {
    currentStep = step;
    const dots = stepIndicator.querySelectorAll('.step-dot');
    dots.forEach((dot) => {
      const idx = parseInt(dot.dataset.step);
      dot.classList.toggle('active', idx === step);
      dot.classList.toggle('done', idx < step);
    });
    const labels = STEP_LABELS[TOTAL_SHOTS] || STEP_LABELS[3];
    stepLabel.textContent = labels[step - 1] || `Pose ke-${step}!`;
    btnCaptureText.textContent = `Ambil Foto ${step}`;
  }

  // ═══════════════════════════════════════════════
  // TEMPLATE PICKER
  // ═══════════════════════════════════════════════
  pickerCards.forEach((card) => {
    card.addEventListener('click', () => {
      pickerCards.forEach((c) => c.classList.remove('active'));
      card.classList.add('active');
    });
  });

  themeBtns.forEach((btn) => {
    btn.addEventListener('click', () => {
      applyTheme(btn.dataset.theme);
    });
  });

  btnStart.addEventListener('click', () => {
    const activeCard = document.querySelector('.pb-picker-card.active');
    if (!activeCard) return;
    TOTAL_SHOTS = parseInt(activeCard.dataset.count);
    capturedFrames = [];
    buildStepIndicator(TOTAL_SHOTS);
    updateStep(1);
    showState('camera');
  });

  // Live theme dots (camera page)
  liveDots.forEach((dot) => {
    dot.addEventListener('click', () => {
      applyTheme(dot.dataset.theme);
    });
  });

  // ═══════════════════════════════════════════════
  // CAMERA
  // ═══════════════════════════════════════════════
  async function startCamera() {
    showState('loading');

    if (!WEBHOOK_URL) {
      showError('Link photobox gak valid — coba ulang dari Discord ya!');
      return;
    }

    try {
      mediaStream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'user', width: { ideal: 640 }, height: { ideal: 480 } },
        audio: false,
      });
      video.srcObject = mediaStream;
      await video.play();
      applyTheme('pink-love');
      showState('picker');
    } catch (err) {
      console.error('[PHOTOBOX] Camera error:', err);
      if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
        showError('Izin kameranya diblokir! Coba izinin dulu di pengaturan browser.');
      } else if (err.name === 'NotFoundError') {
        showError('Kamera gak ketemu — pastiin perangkat lu punya kamera ya!');
      } else {
        showError('Gagal akses kamera: ' + err.message);
      }
    }
  }

  function stopCamera() {
    if (mediaStream) {
      mediaStream.getTracks().forEach((track) => track.stop());
      mediaStream = null;
    }
  }

  // ═══════════════════════════════════════════════
  // CAPTURE FRAME
  // ═══════════════════════════════════════════════
  function captureFrame() {
    const w = video.videoWidth;
    const h = video.videoHeight;
    const offscreen = document.createElement('canvas');
    offscreen.width = w;
    offscreen.height = h;
    const ctx = offscreen.getContext('2d');
    ctx.translate(w, 0);
    ctx.scale(-1, 1);
    ctx.drawImage(video, 0, 0, w, h);
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    return offscreen;
  }

  // ═══════════════════════════════════════════════
  // BUILD STRIP (theme-aware, aesthetic frame)
  // ═══════════════════════════════════════════════
  function buildStrip(frames) {
    const t = THEMES[currentTheme];

    const frameW = 230;
    const frameH = 172;
    const framePad = 10;
    const gap = 20;
    const paddingX = 20;
    const paddingY = 22;
    const headerH = 38;
    const footerH = 34;
    const outerRadius = 10;
    const innerRadius = 8;

    const totalPhotos = frames.length;
    const stripW = frameW + paddingX * 2;
    const stripH = headerH + totalPhotos * (frameH + framePad * 2) + (totalPhotos - 1) * gap + footerH + paddingY * 2;

    canvas.width = stripW;
    canvas.height = stripH;
    const ctx = canvas.getContext('2d');

    // ── Strip Background ──
    ctx.fillStyle = t.stripBg;
    ctx.beginPath();
    roundRect(ctx, 0, 0, stripW, stripH, outerRadius);
    ctx.fill();

    // ── Strip Border (double line) ──
    ctx.shadowColor = 'rgba(0,0,0,0.06)';
    ctx.shadowBlur = 6;
    ctx.strokeStyle = t.border;
    ctx.lineWidth = 2;
    ctx.beginPath();
    roundRect(ctx, 3, 3, stripW - 6, stripH - 6, outerRadius - 1);
    ctx.stroke();
    ctx.shadowBlur = 0;
    ctx.strokeStyle = t.grad2;
    ctx.setLineDash([4, 6]);
    ctx.lineWidth = 1;
    ctx.beginPath();
    roundRect(ctx, 8, 8, stripW - 16, stripH - 16, outerRadius - 4);
    ctx.stroke();
    ctx.setLineDash([]);

    // ── Header ──
    const gradH = ctx.createLinearGradient(paddingX, 0, paddingX + frameW, 0);
    gradH.addColorStop(0, 'transparent');
    gradH.addColorStop(0.05, t.grad1);
    gradH.addColorStop(0.5, t.grad2);
    gradH.addColorStop(0.95, t.grad1);
    gradH.addColorStop(1, 'transparent');
    ctx.fillStyle = gradH;
    ctx.fillRect(paddingX, paddingY + 2, frameW, 2);

    ctx.fillStyle = t.grad1;
    ctx.font = 'bold 13px Nunito, sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(t.brand, stripW / 2, paddingY + headerH / 2);

    // ── Photo Frames ──
    let y = paddingY + headerH;
    for (let i = 0; i < totalPhotos; i++) {
      const fx = paddingX;
      const fy = y;

      // Outer frame shadow
      ctx.shadowColor = 'rgba(0,0,0,0.10)';
      ctx.shadowBlur = 8;
      ctx.shadowOffsetY = 3;

      // White outer frame background
      ctx.fillStyle = '#ffffff';
      ctx.beginPath();
      roundRect(ctx, fx, fy, frameW, frameH + framePad * 2, outerRadius);
      ctx.fill();

      ctx.shadowBlur = 0;
      ctx.shadowOffsetY = 0;

      // Frame border
      ctx.strokeStyle = t.border;
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      roundRect(ctx, fx, fy, frameW, frameH + framePad * 2, outerRadius);
      ctx.stroke();

      // Inner frame accent border (colored)
      ctx.strokeStyle = t.grad1;
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      roundRect(ctx, fx + 3, fy + 3, frameW - 6, frameH + framePad * 2 - 6, outerRadius - 2);
      ctx.stroke();

      // Photo area (inside frame)
      const photoX = fx + framePad;
      const photoY = fy + framePad;
      const photoW = frameW - framePad * 2;
      const photoH = frameH;

      // Photo shadow
      ctx.shadowColor = 'rgba(0,0,0,0.08)';
      ctx.shadowBlur = 4;
      ctx.shadowOffsetY = 1;

      ctx.save();
      ctx.beginPath();
      roundRect(ctx, photoX, photoY, photoW, photoH, innerRadius);
      ctx.clip();
      ctx.drawImage(frames[i], 0, 0, frames[i].width, frames[i].height, photoX, photoY, photoW, photoH);
      ctx.restore();

      ctx.shadowBlur = 0;
      ctx.shadowOffsetY = 0;

      // Photo border
      ctx.strokeStyle = 'rgba(0,0,0,0.06)';
      ctx.lineWidth = 1;
      ctx.beginPath();
      roundRect(ctx, photoX, photoY, photoW, photoH, innerRadius);
      ctx.stroke();

      // ── Frame corner decorations ──
      ctx.font = '14px sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      const cornerEmoji = t.deco[0];
      ctx.fillText(cornerEmoji, fx + 12, fy + 14);
      ctx.fillText(cornerEmoji, fx + frameW - 12, fy + 14);

      // Small sticker badge on frame
      ctx.font = '10px sans-serif';
      ctx.fillStyle = t.grad1;
      ctx.beginPath();
      roundRect(ctx, fx + frameW - 36, fy + frameH + framePad * 2 - 18, 28, 14, 7);
      ctx.fill();
      ctx.fillStyle = '#fff';
      ctx.font = 'bold 8px Nunito, sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText('✨ cute', fx + frameW - 22, fy + frameH + framePad * 2 - 11);

      // Decorative element at bottom-left of frame
      ctx.font = '18px sans-serif';
      ctx.fillText(t.deco[i % t.deco.length], fx + 14, fy + frameH + framePad * 2 - 10);

      // ── Connector between frames ──
      if (i < totalPhotos - 1) {
        const connY = fy + frameH + framePad * 2 + gap / 2;
        ctx.fillStyle = t.grad2;
        ctx.beginPath();
        roundRect(ctx, stripW / 2 - 12, connY - 1, 24, 2, 1);
        ctx.fill();

        ctx.font = '15px sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(t.betweenEmojis[i % t.betweenEmojis.length], stripW / 2, connY);
      }

      y += frameH + framePad * 2 + gap;
    }

    // ── Divider before footer ──
    ctx.fillStyle = gradH;
    ctx.fillRect(paddingX, y - gap + 4, frameW, 2);

    // ── Footer ──
    ctx.fillStyle = t.textMuted;
    ctx.font = '11px Nunito, sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(`✦ ${formatDate()}  ·  ${totalPhotos} pose  ·  Synapse ✦`, stripW / 2, y + footerH / 2 + 2);

    // Small decorative dots in footer corners
    ctx.font = '10px sans-serif';
    ctx.fillText(t.deco[1] || '✨', paddingX + 6, y + footerH / 2 + 2);
    ctx.fillText(t.deco[1] || '✨', stripW - paddingX - 6, y + footerH / 2 + 2);
  }

  function roundRect(ctx, x, y, w, h, r) {
    ctx.moveTo(x + r, y);
    ctx.lineTo(x + w - r, y);
    ctx.quadraticCurveTo(x + w, y, x + w, y + r);
    ctx.lineTo(x + w, y + h - r);
    ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
    ctx.lineTo(x + r, y + h);
    ctx.quadraticCurveTo(x, y + h, x, y + h - r);
    ctx.lineTo(x, y + r);
    ctx.quadraticCurveTo(x, y, x + r, y);
    ctx.closePath();
  }

  // ═══════════════════════════════════════════════
  // COUNTDOWN
  // ═══════════════════════════════════════════════
  async function startCountdown() {
    if (isProcessing) return;
    if (capturedFrames.length >= TOTAL_SHOTS) return;

    isProcessing = true;
    showState('countdown');

    const steps = [
      { num: '3', label: 'siap-siap...', delay: 800 },
      { num: '2', label: 'senyum dong! 😊', delay: 800 },
      { num: '1', label: 'siap-siap... 📸', delay: 800 },
      { num: '📸', label: 'CHEESE! ✨', delay: 500 },
    ];

    for (const step of steps) {
      countdownNum.textContent = step.num;
      countdownLabel.textContent = step.label;
      countdownNum.style.animation = 'none';
      void countdownNum.offsetHeight;
      countdownNum.style.animation = 'countPop 0.6s ease-out';
      await sleep(step.delay);
    }

    const frame = captureFrame();
    capturedFrames.push(frame);
    isProcessing = false;

    if (capturedFrames.length < TOTAL_SHOTS) {
      updateStep(capturedFrames.length + 1);
      showState('camera');
    } else {
      updateStep(TOTAL_SHOTS);
      setTimeout(() => {
        buildStrip(capturedFrames);
        showState('preview');
      }, 400);
    }
  }

  // ═══════════════════════════════════════════════
  // SEND
  // ═══════════════════════════════════════════════
  async function sendPhoto() {
    showState('sending');

    try {
      const blob = await new Promise((resolve) =>
        canvas.toBlob(resolve, 'image/jpeg', 0.95)
      );

      const payload = new FormData();
      payload.append('file', blob, `${timestamp()}.jpg`);
      payload.append(
        'payload_json',
        JSON.stringify({ content: '📸 **Photobooth Strip — hasil jepretan!**' })
      );

      const resp = await fetch(WEBHOOK_URL, {
        method: 'POST',
        body: payload,
      });

      if (!resp.ok) {
        const errBody = await resp.text().catch(() => '');
        throw new Error(`Discord webhook error ${resp.status}: ${errBody.slice(0, 100)}`);
      }

      showState('success');
      stopCamera();
    } catch (err) {
      console.error('[PHOTOBOX] Send error:', err);
      showError('Gagal kirim foto: ' + err.message);
    }
  }

  // ═══════════════════════════════════════════════
  // ERROR
  // ═══════════════════════════════════════════════
  function showError(msg) {
    errorText.textContent = msg;
    showState('error');
    isProcessing = false;
  }

  // ═══════════════════════════════════════════════
  // EVENTS
  // ═══════════════════════════════════════════════
  btnCapture.addEventListener('click', startCountdown);
  btnRetake.addEventListener('click', () => {
    capturedFrames = [];
    buildStepIndicator(TOTAL_SHOTS);
    updateStep(1);
    showState('camera');
  });
  btnSend.addEventListener('click', sendPhoto);
  btnRetry.addEventListener('click', () => {
    stopCamera();
    startCamera();
  });
  btnAgain.addEventListener('click', () => {
    capturedFrames = [];
    buildStepIndicator(TOTAL_SHOTS);
    updateStep(1);
    if (!mediaStream) {
      startCamera();
    } else {
      showState('camera');
    }
  });
  btnBackPicker.addEventListener('click', () => {
    capturedFrames = [];
    showState('picker');
  });

  // ═══════════════════════════════════════════════
  // INIT
  // ═══════════════════════════════════════════════
  startCamera();
})();
