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
      deco: ['💖', '💖', '💖', '💖'],
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
      deco: ['☁️', '⭐', '🌸', '✨'],
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
      deco: ['🍃', '🌙', '🌸', '✨'],
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
  // BUILD STRIP (theme-aware)
  // ═══════════════════════════════════════════════
  function buildStrip(frames) {
    const t = THEMES[currentTheme];

    const photoW = 240;
    const photoH = 180;
    const gap = 12;
    const paddingX = 20;
    const paddingY = 24;
    const headerH = 40;
    const footerH = 36;
    const cornerRadius = 10;

    const totalPhotos = frames.length;
    const stripW = photoW + paddingX * 2;
    const stripH = headerH + totalPhotos * photoH + (totalPhotos - 1) * gap + footerH + paddingY * 2;

    canvas.width = stripW;
    canvas.height = stripH;
    const ctx = canvas.getContext('2d');

    // Background
    ctx.fillStyle = t.stripBg;
    ctx.beginPath();
    roundRect(ctx, 0, 0, stripW, stripH, 12);
    ctx.fill();

    // Subtle border
    ctx.shadowColor = 'rgba(0,0,0,0.08)';
    ctx.shadowBlur = 4;
    ctx.strokeStyle = t.border;
    ctx.lineWidth = 2;
    ctx.beginPath();
    roundRect(ctx, 2, 2, stripW - 4, stripH - 4, 11);
    ctx.stroke();
    ctx.shadowBlur = 0;

    // Top decorative line
    const grad = ctx.createLinearGradient(0, 0, stripW, 0);
    grad.addColorStop(0, 'transparent');
    grad.addColorStop(0.2, t.grad1);
    grad.addColorStop(0.5, t.grad2);
    grad.addColorStop(0.8, t.grad1);
    grad.addColorStop(1, 'transparent');
    ctx.fillStyle = grad;
    ctx.fillRect(paddingX, paddingY - 2, photoW, 3);

    // Header
    ctx.fillStyle = t.grad1;
    ctx.font = 'bold 14px Nunito, sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(t.brand, stripW / 2, paddingY + headerH / 2);

    // Photos
    let y = paddingY + headerH;
    for (let i = 0; i < totalPhotos; i++) {
      const x = paddingX;

      ctx.save();
      ctx.shadowColor = 'rgba(0,0,0,0.12)';
      ctx.shadowBlur = 6;
      ctx.shadowOffsetY = 2;
      ctx.beginPath();
      roundRect(ctx, x, y, photoW, photoH, cornerRadius);
      ctx.clip();
      ctx.drawImage(frames[i], 0, 0, frames[i].width, frames[i].height, x, y, photoW, photoH);
      ctx.restore();

      ctx.strokeStyle = t.border;
      ctx.lineWidth = 1;
      ctx.beginPath();
      roundRect(ctx, x, y, photoW, photoH, cornerRadius);
      ctx.stroke();

      if (i < totalPhotos - 1) {
        const decoY = y + photoH + gap / 2;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.font = '16px sans-serif';
        ctx.fillText(t.betweenEmojis[i % t.betweenEmojis.length], stripW / 2, decoY);
      }

      y += photoH + gap;
    }

    // Divider
    ctx.fillStyle = grad;
    ctx.fillRect(paddingX, y - gap + 6, photoW, 3);

    // Footer
    ctx.fillStyle = t.textMuted;
    ctx.font = '12px Nunito, sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(formatDate() + `  ✦  ${totalPhotos} pose  ✦  Synapse`, stripW / 2, y + footerH / 2 + 4);
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
