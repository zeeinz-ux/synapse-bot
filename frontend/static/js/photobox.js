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
  const cameraGrid = $('pbCameraGrid');
  const countdownNum = $('pbCountdownNum');
  const countdownLabel = $('pbCountdownLabel');
  const errorText = $('pbErrorText');
  const stepLabel = $('pbStepLabel');
  const btnCaptureText = $('pbBtnCaptureText');
  const stepIndicator = $('pbStepIndicator');
  const frameLabel = $('pbFrameLabel');
  const floaties = $('pbFloaties');

  const pickerCards = document.querySelectorAll('.pb-picker-card');
  const themeBtns = document.querySelectorAll('.pb-theme-btn');
  const liveDots = document.querySelectorAll('.live-theme-dot');
  const liveCountBtns = document.querySelectorAll('.live-count-btn');
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
  let animFrameId = null;

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

    renderCameraGrid();
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
    if (name === 'camera') {
      renderCameraGrid();
    } else if (animFrameId) {
      cancelAnimationFrame(animFrameId);
      animFrameId = null;
    }
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

  // Live count buttons (camera page)
  liveCountBtns.forEach((btn) => {
    btn.addEventListener('click', () => {
      const newCount = parseInt(btn.dataset.count);
      if (newCount === TOTAL_SHOTS) return;
      TOTAL_SHOTS = newCount;
      liveCountBtns.forEach((b) => b.classList.toggle('active', parseInt(b.dataset.count) === TOTAL_SHOTS));
      capturedFrames = [];
      buildStepIndicator(TOTAL_SHOTS);
      updateStep(1);
      showState('camera');
    });
  });

  // Layout style buttons (picker page)
  document.querySelectorAll('.pb-layout-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      applyLayoutStyle(btn.dataset.layout);
    });
  });

  // Live layout buttons (camera page)
  document.querySelectorAll('.live-layout-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      applyLayoutStyle(btn.dataset.layout);
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
  // LAYOUT DEFINITIONS (multi-style)
  // ═══════════════════════════════════════════════
  const LAYOUTS = {
    strip: {
      1: [ { x: 0, y: 0, w: 1, h: 1 } ],
      2: [ { x: 0, y: 0, w: 1, h: 0.5 }, { x: 0, y: 0.5, w: 1, h: 0.5 } ],
      3: [ { x: 0, y: 0, w: 1, h: 1/3 }, { x: 0, y: 1/3, w: 1, h: 1/3 }, { x: 0, y: 2/3, w: 1, h: 1/3 } ],
      4: [ { x: 0, y: 0, w: 1, h: 0.25 }, { x: 0, y: 0.25, w: 1, h: 0.25 }, { x: 0, y: 0.5, w: 1, h: 0.25 }, { x: 0, y: 0.75, w: 1, h: 0.25 } ],
      5: [ { x: 0, y: 0, w: 1, h: 0.2 }, { x: 0, y: 0.2, w: 1, h: 0.2 }, { x: 0, y: 0.4, w: 1, h: 0.2 }, { x: 0, y: 0.6, w: 1, h: 0.2 }, { x: 0, y: 0.8, w: 1, h: 0.2 } ],
    },
    collage: {
      1: [ { x: 0, y: 0, w: 1, h: 1 } ],
      2: [ { x: 0, y: 0, w: 1, h: 0.5 }, { x: 0, y: 0.5, w: 1, h: 0.5 } ],
      3: [ { x: 0, y: 0, w: 1, h: 0.55 }, { x: 0, y: 0.55, w: 0.5, h: 0.45 }, { x: 0.5, y: 0.55, w: 0.5, h: 0.45 } ],
      4: [ { x: 0, y: 0, w: 0.5, h: 0.5 }, { x: 0.5, y: 0, w: 0.5, h: 0.5 }, { x: 0, y: 0.5, w: 0.5, h: 0.5 }, { x: 0.5, y: 0.5, w: 0.5, h: 0.5 } ],
      5: [ { x: 0, y: 0, w: 1, h: 0.4 }, { x: 0, y: 0.4, w: 0.5, h: 0.35 }, { x: 0.5, y: 0.4, w: 0.5, h: 0.35 }, { x: 0, y: 0.75, w: 0.5, h: 0.25 }, { x: 0.5, y: 0.75, w: 0.5, h: 0.25 } ],
    },
  };

  let currentLayoutStyle = 'collage';

  function getLayout(count) {
    const s = LAYOUTS[currentLayoutStyle];
    return (s && s[count]) || LAYOUTS.strip[count] || LAYOUTS.strip[3];
  }

  function getLayoutMaxY(count) {
    const cells = getLayout(count);
    let maxY = 0;
    cells.forEach((c) => {
      const b = c.y + c.h;
      if (b > maxY) maxY = b;
    });
    return maxY;
  }

  function applyLayoutStyle(style) {
    if (!LAYOUTS[style] || style === currentLayoutStyle) return;
    currentLayoutStyle = style;
    document.querySelectorAll('.live-layout-btn').forEach((b) => b.classList.toggle('active', b.dataset.layout === style));
    document.querySelectorAll('.pb-layout-btn').forEach((b) => b.classList.toggle('active', b.dataset.layout === style));
    if (states.camera && !states.camera.classList.contains('hidden')) {
      renderCameraGrid();
    }
  }

  // ═══════════════════════════════════════════════
  // DRAW A SINGLE PHOTO FRAME (shared)
  // ═══════════════════════════════════════════════
  function drawPhotoFrame(ctx, fx, fy, fw, fh, t, index, source, isVideo) {
    const framePad = Math.round(fw * 0.045);
    const radius = Math.round(Math.min(fw, fh) * 0.045);

    // White polaroid frame
    ctx.shadowColor = 'rgba(0,0,0,0.10)';
    ctx.shadowBlur = 6;
    ctx.shadowOffsetY = 2;
    ctx.fillStyle = '#ffffff';
    ctx.beginPath();
    roundRect(ctx, fx, fy, fw, fh, radius);
    ctx.fill();
    ctx.shadowBlur = 0;
    ctx.shadowOffsetY = 0;

    // Frame border
    ctx.strokeStyle = t.border;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    roundRect(ctx, fx, fy, fw, fh, radius);
    ctx.stroke();

    // Inner accent border
    ctx.strokeStyle = t.grad1;
    ctx.lineWidth = 1;
    ctx.beginPath();
    roundRect(ctx, fx + 2, fy + 2, fw - 4, fh - 4, radius - 1);
    ctx.stroke();

    // Photo area
    const photoX = fx + framePad;
    const photoY = fy + framePad;
    const photoW = fw - framePad * 2;
    const photoH = fh - framePad * 2;

    ctx.save();
    ctx.beginPath();
    roundRect(ctx, photoX, photoY, photoW, photoH, radius - 2);
    ctx.clip();

    if (source) {
      if (isVideo) {
        if (source.readyState >= 2) {
          ctx.translate(photoX + photoW, photoY);
          ctx.scale(-1, 1);
          ctx.drawImage(source, 0, 0, source.videoWidth, source.videoHeight, 0, 0, photoW, photoH);
          ctx.setTransform(1, 0, 0, 1, 0, 0);
        }
      } else {
        ctx.drawImage(source, 0, 0, source.width, source.height, photoX, photoY, photoW, photoH);
      }
    }
    ctx.restore();

    // Photo border
    ctx.strokeStyle = 'rgba(0,0,0,0.05)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    roundRect(ctx, photoX, photoY, photoW, photoH, radius - 2);
    ctx.stroke();

    // Corner deco (top-left, top-right)
    const decoSize = Math.round(fw * 0.055);
    ctx.font = `${decoSize}px sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    const ce = t.deco[0];
    const decoOff = Math.round(fw * 0.048);
    ctx.fillText(ce, fx + decoOff, fy + decoOff);
    ctx.fillText(ce, fx + fw - decoOff, fy + decoOff);

    // Sticker badge (bottom-right)
    const badgeW = Math.round(fw * 0.12);
    const badgeH = Math.round(badgeW * 0.5);
    const badgeX = fx + fw - badgeW - Math.round(fw * 0.025);
    const badgeY = fy + fh - badgeH - Math.round(fw * 0.025);
    ctx.fillStyle = t.grad1;
    ctx.beginPath();
    roundRect(ctx, badgeX, badgeY, badgeW, badgeH, Math.round(badgeH * 0.5));
    ctx.fill();
    ctx.fillStyle = '#fff';
    ctx.font = `bold ${Math.round(badgeH * 0.5)}px Nunito, sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    const badges = ['✨ cute', '💕 oke', '⭐ yes', '🌸 ay', '🌙 nyah'];
    ctx.fillText(badges[index % badges.length], badgeX + badgeW / 2, badgeY + badgeH / 2);

    // Bottom-left deco
    ctx.font = `${Math.round(fw * 0.07)}px sans-serif`;
    ctx.fillText(t.deco[index % t.deco.length], fx + decoOff, fy + fh - decoOff);
  }

  // ═══════════════════════════════════════════════
  // BUILD STRIP (collage layout, theme-aware)
  // ═══════════════════════════════════════════════
  function buildStrip(frames) {
    const t = THEMES[currentTheme];
    const count = frames.length;
    const cells = getLayout(count);
    const maxY = getLayoutMaxY(count);

    const photoAreaW = 240;
    const margin = 10;
    const layoutH = photoAreaW * maxY;
    const headerH = 36;
    const footerH = 32;
    const stripW = photoAreaW + margin * 2;
    const stripH = headerH + layoutH + footerH + margin * 2;

    canvas.width = stripW;
    canvas.height = stripH;
    const ctx = canvas.getContext('2d');

    // Background
    ctx.fillStyle = t.stripBg;
    ctx.beginPath();
    roundRect(ctx, 0, 0, stripW, stripH, 10);
    ctx.fill();

    // Double border
    ctx.shadowColor = 'rgba(0,0,0,0.06)';
    ctx.shadowBlur = 6;
    ctx.strokeStyle = t.border;
    ctx.lineWidth = 2;
    ctx.beginPath();
    roundRect(ctx, 3, 3, stripW - 6, stripH - 6, 9);
    ctx.stroke();
    ctx.shadowBlur = 0;
    ctx.strokeStyle = t.grad2;
    ctx.setLineDash([4, 6]);
    ctx.lineWidth = 1;
    ctx.beginPath();
    roundRect(ctx, 8, 8, stripW - 16, stripH - 16, 6);
    ctx.stroke();
    ctx.setLineDash([]);

    // Header stripe
    const gradH = ctx.createLinearGradient(margin, 0, margin + photoAreaW, 0);
    gradH.addColorStop(0, 'transparent');
    gradH.addColorStop(0.05, t.grad1);
    gradH.addColorStop(0.5, t.grad2);
    gradH.addColorStop(0.95, t.grad1);
    gradH.addColorStop(1, 'transparent');
    ctx.fillStyle = gradH;
    ctx.fillRect(margin, margin + 4, photoAreaW, 2);

    ctx.fillStyle = t.grad1;
    ctx.font = 'bold 12px Nunito, sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(t.brand, stripW / 2, margin + headerH / 2 + 2);

    // Photo area
    const photoAreaX = margin;
    const photoAreaY = margin + headerH;
    const scaleX = photoAreaW;
    const scaleY = layoutH / maxY;

    for (let i = 0; i < count; i++) {
      const c = cells[i];
      const fx = photoAreaX + c.x * scaleX;
      const fy = photoAreaY + c.y * scaleY;
      const fw = c.w * scaleX;
      const fh = c.h * scaleY;
      drawPhotoFrame(ctx, fx, fy, fw, fh, t, i, frames[i], false);
    }

    // Footer stripe
    const footerY = margin + headerH + layoutH;
    ctx.fillStyle = gradH;
    ctx.fillRect(margin, footerY - 4, photoAreaW, 2);

    ctx.fillStyle = t.textMuted;
    ctx.font = '10px Nunito, sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(`✦ ${formatDate()}  ·  ${count} pose  ·  Synapse ✦`, stripW / 2, footerY + footerH / 2 + 2);

    // Footer corner deco
    ctx.font = '9px sans-serif';
    ctx.fillText(t.deco[1] || '✨', margin + 6, footerY + footerH / 2 + 2);
    ctx.fillText(t.deco[1] || '✨', stripW - margin - 6, footerY + footerH / 2 + 2);
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

  function renderCameraGrid() {
    if (!cameraGrid) return;
    if (animFrameId) {
      cancelAnimationFrame(animFrameId);
      animFrameId = null;
    }

    const t = THEMES[currentTheme];
    const count = TOTAL_SHOTS;
    const filled = capturedFrames.length;
    const cells = getLayout(count);
    const maxY = getLayoutMaxY(count);
    const maxW = 210;
    const margin = 6;

    const layoutH = maxW * maxY;
    const totalW = maxW + margin * 2;
    const totalH = layoutH + margin * 2;

    cameraGrid.width = totalW;
    cameraGrid.height = totalH;
    const ctx = cameraGrid.getContext('2d');

    // Background
    ctx.fillStyle = t.stripBg;
    ctx.beginPath();
    roundRect(ctx, 0, 0, totalW, totalH, 8);
    ctx.fill();

    ctx.strokeStyle = t.border;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    roundRect(ctx, 2, 2, totalW - 4, totalH - 4, 7);
    ctx.stroke();

    const areaX = margin;
    const areaY = margin;
    const scaleX = maxW;
    const scaleY = layoutH / maxY;

    for (let i = 0; i < count; i++) {
      const c = cells[i];
      const fx = areaX + c.x * scaleX;
      const fy = areaY + c.y * scaleY;
      const fw = c.w * scaleX;
      const fh = c.h * scaleY;

      const hasPhoto = i < filled;
      const source = hasPhoto ? capturedFrames[i] : video;
      drawPhotoFrame(ctx, fx, fy, fw, fh, t, i, source, !hasPhoto);
    }

    if (filled < count && states.camera && !states.camera.classList.contains('hidden')) {
      animFrameId = requestAnimationFrame(renderCameraGrid);
    }
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
