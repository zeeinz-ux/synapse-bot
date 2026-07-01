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
  let cellRotations = [];

  function generateRotations(count) {
    cellRotations = [];
    for (let i = 0; i < count; i++) {
      cellRotations.push((Math.random() - 0.5) * 6);
    }
  }

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
    const preset = LAYOUTS[currentLayoutPreset];
    if (!preset || !preset.cells[TOTAL_SHOTS]) {
      const fallbackId = CATEGORY_PRESETS[currentLayoutCategory].find((id) => LAYOUTS[id].cells[TOTAL_SHOTS]) || CATEGORY_PRESETS[currentLayoutCategory][0];
      if (fallbackId) applyLayoutPreset(fallbackId);
    }
    capturedFrames = [];
    generateRotations(TOTAL_SHOTS);
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
      // Ensure current preset supports this count; fallback if not
      const preset = LAYOUTS[currentLayoutPreset];
      if (!preset || !preset.cells[TOTAL_SHOTS]) {
        const fallbackId = CATEGORY_PRESETS[currentLayoutCategory].find((id) => LAYOUTS[id].cells[TOTAL_SHOTS]) || CATEGORY_PRESETS[currentLayoutCategory][0];
        if (fallbackId) applyLayoutPreset(fallbackId);
      }
      capturedFrames = [];
      generateRotations(TOTAL_SHOTS);
      buildStepIndicator(TOTAL_SHOTS);
      updateStep(1);
      showState('camera');
    });
  });

  // Layout category buttons (picker page)
  document.querySelectorAll('.pb-layout-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      const cat = btn.dataset.category;
      if (!cat || cat === currentLayoutCategory) return;
      currentLayoutCategory = cat;
      const firstPreset = CATEGORY_PRESETS[cat][0];
      applyLayoutPreset(firstPreset);
    });
  });

  // Layout sub-preset buttons (picker page)
  document.querySelectorAll('.pb-sub-layout-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      applyLayoutPreset(btn.dataset.preset);
    });
  });

  // Live layout category buttons (camera page)
  document.querySelectorAll('.live-layout-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      const cat = btn.dataset.category;
      if (!cat || cat === currentLayoutCategory) return;
      currentLayoutCategory = cat;
      const firstPreset = CATEGORY_PRESETS[cat][0];
      applyLayoutPreset(firstPreset);
    });
  });

  // Live layout sub-preset buttons (camera page)
  document.querySelectorAll('.live-sub-layout-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      applyLayoutPreset(btn.dataset.preset);
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
  // LAYOUT DEFINITIONS (multi-preset with sub-variants)
  // ═══════════════════════════════════════════════
  const LAYOUTS = {
    'strip': {
      label: 'Strip',
      category: 'strip',
      icon: '<svg viewBox="0 0 24 32" width="24" height="32"><rect x="2" y="2" rx="2" width="20" height="8" fill="currentColor" opacity=".7"/><rect x="2" y="12" rx="2" width="20" height="8" fill="currentColor" opacity=".5"/><rect x="2" y="22" rx="2" width="20" height="8" fill="currentColor" opacity=".3"/></svg>',
      cells: {
        1: [ { x: 0, y: 0, w: 1, h: 0.75 } ],
        2: [ { x: 0, y: 0, w: 1, h: 0.75 }, { x: 0, y: 0.75, w: 1, h: 0.75 } ],
        3: [ { x: 0, y: 0, w: 1, h: 0.75 }, { x: 0, y: 0.75, w: 1, h: 0.75 }, { x: 0, y: 1.5, w: 1, h: 0.75 } ],
        4: [ { x: 0, y: 0, w: 1, h: 0.75 }, { x: 0, y: 0.75, w: 1, h: 0.75 }, { x: 0, y: 1.5, w: 1, h: 0.75 }, { x: 0, y: 2.25, w: 1, h: 0.75 } ],
        5: [ { x: 0, y: 0, w: 1, h: 0.75 }, { x: 0, y: 0.75, w: 1, h: 0.75 }, { x: 0, y: 1.5, w: 1, h: 0.75 }, { x: 0, y: 2.25, w: 1, h: 0.75 }, { x: 0, y: 3, w: 1, h: 0.75 } ],
      }
    },
    'collage-split': {
      label: 'Split',
      category: 'collage',
      icon: '<svg viewBox="0 0 24 24" width="24" height="24"><rect x="0" y="0" rx="2" width="24" height="12" fill="currentColor" opacity=".7"/><rect x="0" y="13" rx="2" width="11.5" height="11" fill="currentColor" opacity=".5"/><rect x="12.5" y="13" rx="2" width="11.5" height="11" fill="currentColor" opacity=".3"/></svg>',
      cells: {
        1: [ { x: 0, y: 0, w: 1, h: 0.75 } ],
        2: [ { x: 0, y: 0, w: 1, h: 0.75 }, { x: 0, y: 0.75, w: 1, h: 0.75 } ],
        3: [ { x: 0, y: 0, w: 1, h: 0.667 }, { x: 0, y: 0.667, w: 0.5, h: 0.333 }, { x: 0.5, y: 0.667, w: 0.5, h: 0.333 } ],
        4: [ { x: 0, y: 0, w: 0.5, h: 0.5 }, { x: 0.5, y: 0, w: 0.5, h: 0.5 }, { x: 0, y: 0.5, w: 0.5, h: 0.5 }, { x: 0.5, y: 0.5, w: 0.5, h: 0.5 } ],
        5: [ { x: 0, y: 0, w: 0.5, h: 0.375 }, { x: 0.5, y: 0, w: 0.5, h: 0.375 }, { x: 0, y: 0.375, w: 0.5, h: 0.375 }, { x: 0.5, y: 0.375, w: 0.5, h: 0.375 }, { x: 0, y: 0.75, w: 1, h: 0.75 } ],
      }
    },
    'collage-1+2': {
      label: '1+2',
      category: 'collage',
      icon: '<svg viewBox="0 0 24 24" width="24" height="24"><rect x="0" y="0" rx="2" width="14" height="24" fill="currentColor" opacity=".7"/><rect x="15" y="0" rx="2" width="9" height="11.5" fill="currentColor" opacity=".5"/><rect x="15" y="12.5" rx="2" width="9" height="11.5" fill="currentColor" opacity=".3"/></svg>',
      cells: {
        3: [ { x: 0, y: 0, w: 0.55, h: 1 }, { x: 0.55, y: 0, w: 0.45, h: 0.5 }, { x: 0.55, y: 0.5, w: 0.45, h: 0.5 } ],
      }
    },
    'collage-2+1': {
      label: '2+1',
      category: 'collage',
      icon: '<svg viewBox="0 0 24 24" width="24" height="24"><rect x="0" y="0" rx="2" width="11.5" height="11.5" fill="currentColor" opacity=".7"/><rect x="12.5" y="0" rx="2" width="11.5" height="11.5" fill="currentColor" opacity=".5"/><rect x="0" y="12.5" rx="2" width="24" height="11.5" fill="currentColor" opacity=".3"/></svg>',
      cells: {
        3: [ { x: 0, y: 0, w: 0.5, h: 0.5 }, { x: 0.5, y: 0, w: 0.5, h: 0.5 }, { x: 0, y: 0.5, w: 1, h: 0.5 } ],
      }
    },
    'collage-1+3': {
      label: '1+3',
      category: 'collage',
      icon: '<svg viewBox="0 0 24 24" width="24" height="24"><rect x="0" y="0" rx="2" width="24" height="11.5" fill="currentColor" opacity=".7"/><rect x="0" y="12.5" rx="2" width="7.5" height="11.5" fill="currentColor" opacity=".5"/><rect x="8.25" y="12.5" rx="2" width="7.5" height="11.5" fill="currentColor" opacity=".3"/><rect x="16.5" y="12.5" rx="2" width="7.5" height="11.5" fill="currentColor" opacity=".4"/></svg>',
      cells: {
        4: [ { x: 0, y: 0, w: 1, h: 0.5 }, { x: 0, y: 0.5, w: 0.333, h: 0.5 }, { x: 0.333, y: 0.5, w: 0.333, h: 0.5 }, { x: 0.666, y: 0.5, w: 0.333, h: 0.5 } ],
      }
    },
    'collage-3+1': {
      label: '3+1',
      category: 'collage',
      icon: '<svg viewBox="0 0 24 24" width="24" height="24"><rect x="0" y="0" rx="2" width="7.5" height="11.5" fill="currentColor" opacity=".7"/><rect x="8.25" y="0" rx="2" width="7.5" height="11.5" fill="currentColor" opacity=".5"/><rect x="16.5" y="0" rx="2" width="7.5" height="11.5" fill="currentColor" opacity=".3"/><rect x="0" y="12.5" rx="2" width="24" height="11.5" fill="currentColor" opacity=".4"/></svg>',
      cells: {
        4: [ { x: 0, y: 0, w: 0.333, h: 0.5 }, { x: 0.333, y: 0, w: 0.333, h: 0.5 }, { x: 0.666, y: 0, w: 0.333, h: 0.5 }, { x: 0, y: 0.5, w: 1, h: 0.5 } ],
      }
    },
    'collage-2+3': {
      label: '2+3',
      category: 'collage',
      icon: '<svg viewBox="0 0 24 24" width="24" height="24"><rect x="0" y="0" rx="2" width="11.5" height="10" fill="currentColor" opacity=".7"/><rect x="12.5" y="0" rx="2" width="11.5" height="10" fill="currentColor" opacity=".5"/><rect x="0" y="11" rx="2" width="7.5" height="13" fill="currentColor" opacity=".3"/><rect x="8.25" y="11" rx="2" width="7.5" height="13" fill="currentColor" opacity=".4"/><rect x="16.5" y="11" rx="2" width="7.5" height="13" fill="currentColor" opacity=".2"/></svg>',
      cells: {
        5: [ { x: 0, y: 0, w: 0.5, h: 0.4 }, { x: 0.5, y: 0, w: 0.5, h: 0.4 }, { x: 0, y: 0.4, w: 0.333, h: 0.6 }, { x: 0.333, y: 0.4, w: 0.333, h: 0.6 }, { x: 0.666, y: 0.4, w: 0.333, h: 0.6 } ],
      }
    },
    'collage-3+2': {
      label: '3+2',
      category: 'collage',
      icon: '<svg viewBox="0 0 24 24" width="24" height="24"><rect x="0" y="0" rx="2" width="7.5" height="14" fill="currentColor" opacity=".7"/><rect x="8.25" y="0" rx="2" width="7.5" height="14" fill="currentColor" opacity=".5"/><rect x="16.5" y="0" rx="2" width="7.5" height="14" fill="currentColor" opacity=".3"/><rect x="0" y="15" rx="2" width="11.5" height="9" fill="currentColor" opacity=".4"/><rect x="12.5" y="15" rx="2" width="11.5" height="9" fill="currentColor" opacity=".2"/></svg>',
      cells: {
        5: [ { x: 0, y: 0, w: 0.333, h: 0.6 }, { x: 0.333, y: 0, w: 0.333, h: 0.6 }, { x: 0.666, y: 0, w: 0.333, h: 0.6 }, { x: 0, y: 0.6, w: 0.5, h: 0.4 }, { x: 0.5, y: 0.6, w: 0.5, h: 0.4 } ],
      }
    },
  };

  const CATEGORIES = ['strip', 'collage'];
  const CATEGORY_PRESETS = {
    'strip': ['strip'],
    'collage': ['collage-split', 'collage-1+2', 'collage-2+1', 'collage-1+3', 'collage-3+1', 'collage-2+3', 'collage-3+2'],
  };

  let currentLayoutCategory = 'collage';
  let currentLayoutPreset = 'collage-split';

  function getLayoutPreset(count) {
    const preset = LAYOUTS[currentLayoutPreset];
    if (preset && preset.cells[count]) return currentLayoutPreset;
    const fallbacks = CATEGORY_PRESETS[currentLayoutCategory];
    for (const id of fallbacks) {
      if (LAYOUTS[id].cells[count]) return id;
    }
    return 'collage-split';
  }

  function getLayout(count) {
    const pid = getLayoutPreset(count);
    return LAYOUTS[pid].cells[count] || LAYOUTS['collage-split'].cells[count] || LAYOUTS.strip.cells[3];
  }

  function getLayoutMaxYFromCells(cells) {
    let maxY = 0;
    cells.forEach((c) => {
      const b = c.y + c.h;
      if (b > maxY) maxY = b;
    });
    return maxY;
  }

  function getLayoutMaxY(count) {
    return getLayoutMaxYFromCells(getLayout(count));
  }

  function generateSvgIcon(layoutId) {
    return LAYOUTS[layoutId] ? LAYOUTS[layoutId].icon : '';
  }

  function applyLayoutPreset(presetId) {
    if (!LAYOUTS[presetId] || presetId === currentLayoutPreset) return;

    const newCategory = LAYOUTS[presetId].category;
    if (newCategory && newCategory !== currentLayoutCategory) {
      currentLayoutCategory = newCategory;
    }
    // If switching to strip, use 'strip' preset
    const effectiveId = newCategory === 'strip' ? 'strip' : presetId;
    currentLayoutPreset = effectiveId;
    generateRotations(TOTAL_SHOTS);

    // Update picker buttons
    document.querySelectorAll('.pb-layout-btn').forEach((b) => {
      b.classList.toggle('active', b.dataset.category === currentLayoutCategory);
    });
    document.querySelectorAll('.pb-sub-layout-btn').forEach((b) => {
      b.classList.toggle('active', b.dataset.preset === currentLayoutPreset);
    });
    // Update live buttons
    document.querySelectorAll('.live-layout-btn').forEach((b) => {
      b.classList.toggle('active', b.dataset.category === currentLayoutCategory);
    });
    document.querySelectorAll('.live-sub-layout-btn').forEach((b) => {
      b.classList.toggle('active', b.dataset.preset === currentLayoutPreset);
    });

    // Toggle sub-layout visibility
    const subRow = document.getElementById('pbSubLayoutRow');
    const liveSub = document.getElementById('pbLiveSubLayout');
    if (subRow) subRow.classList.toggle('hidden', currentLayoutCategory !== 'collage');
    if (liveSub) liveSub.classList.toggle('hidden', currentLayoutCategory !== 'collage');

    if (states.camera && !states.camera.classList.contains('hidden')) {
      renderCameraGrid();
    }
  }

  // ═══════════════════════════════════════════════
  // DRAW A SINGLE PHOTO FRAME (shared)
  // ═══════════════════════════════════════════════
  function drawCellContent(ctx, fx, fy, fw, fh, t, index, source, isVideo) {
    const radius = Math.round(Math.min(fw, fh) * 0.04);

    // ── Film edge (thin dark border) ──
    ctx.fillStyle = '#222222';
    ctx.beginPath();
    roundRect(ctx, fx, fy, fw, fh, radius);
    ctx.fill();

    // ── Film inset ──
    const filmInset = 2;
    const frameX = fx + filmInset;
    const frameY = fy + filmInset;
    const frameW = fw - filmInset * 2;
    const frameH = fh - filmInset * 2;

    // ── Polaroid frame shadow ──
    ctx.shadowColor = 'rgba(0,0,0,0.12)';
    ctx.shadowBlur = 6;
    ctx.shadowOffsetY = 2;
    ctx.fillStyle = t.stripBg;
    ctx.beginPath();
    roundRect(ctx, frameX, frameY, frameW, frameH, radius - 1);
    ctx.fill();
    ctx.shadowBlur = 0;
    ctx.shadowOffsetY = 0;

    // ── Polaroid asymmetric padding (thick bottom) ──
    const padSide = Math.round(fw * 0.04);
    const padTop = Math.round(fw * 0.04);
    const padBottom = Math.round(fw * 0.15);

    // Photo area
    const photoX = frameX + padSide;
    const photoY = frameY + padTop;
    const photoW = frameW - padSide * 2;
    const photoH = frameH - padTop - padBottom - 2;

    // ── Inner accent border ──
    ctx.strokeStyle = t.grad1;
    ctx.lineWidth = 1;
    ctx.setLineDash([3, 4]);
    ctx.beginPath();
    roundRect(ctx, frameX + 3, frameY + 3, frameW - 6, frameH - 6, radius - 2);
    ctx.stroke();
    ctx.setLineDash([]);

    // ── Draw photo ──
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

    // ── Photo border ──
    ctx.strokeStyle = 'rgba(0,0,0,0.06)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    roundRect(ctx, photoX, photoY, photoW, photoH, radius - 2);
    ctx.stroke();

    // ── Date stamp overlay on photo (bottom-right of photo) ──
    if (!isVideo) {
      ctx.save();
      const stampSize = Math.round(fw * 0.055);
      ctx.fillStyle = 'rgba(255,200,100,0.80)';
      ctx.font = `bold ${stampSize}px monospace`;
      ctx.textAlign = 'right';
      ctx.textBaseline = 'bottom';
      const today = formatDate().replace(/ /g, '.');
      ctx.fillText(today, photoX + photoW - 4, photoY + photoH - 3);
      const stampY = photoY + photoH - stampSize - 6;
      ctx.fillStyle = 'rgba(0,0,0,0.06)';
      ctx.fillRect(photoX + photoW - stampSize * 7, stampY, stampSize * 6.5, stampSize + 4);
      ctx.fillStyle = 'rgba(255,180,60,0.85)';
      ctx.fillText(today, photoX + photoW - 4, photoY + photoH - 3);
      ctx.restore();
    }

    // ── Signature area (polaroid bottom) ──
    const sigAreaY = photoY + photoH + 4;
    const sigAreaH = frameY + frameH - sigAreaY - 4;

    // Signature line
    ctx.strokeStyle = t.border;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(photoX + 6, sigAreaY + Math.round(sigAreaH * 0.35));
    ctx.lineTo(photoX + photoW - 6, sigAreaY + Math.round(sigAreaH * 0.35));
    ctx.stroke();

    // Signature text (left) — emoji + sticker label
    const badges = ['✨ cute', '💕 oke', '⭐ yes', '🌸 ay', '🌙 nyah'];
    const sigFontSize = Math.round(fw * 0.055);
    ctx.fillStyle = t.textMuted;
    ctx.font = `${sigFontSize}px Nunito, sans-serif`;
    ctx.textAlign = 'left';
    ctx.textBaseline = 'middle';
    ctx.fillText(badges[index % badges.length], photoX + 8, sigAreaY + Math.round(sigAreaH * 0.7));

    // Signature text (right) — small decorative text
    ctx.textAlign = 'right';
    ctx.fillText(t.deco[index % t.deco.length], photoX + photoW - 8, sigAreaY + Math.round(sigAreaH * 0.7));

    // ── Corner decorations (4 corners) ──
    const decoSize = Math.round(fw * 0.055);
    ctx.font = `${decoSize}px sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    const decoOff = Math.round(fw * 0.04);
    ctx.fillText(t.deco[0], frameX + decoOff, frameY + decoOff);
    ctx.fillText(t.deco[1], frameX + frameW - decoOff, frameY + decoOff);
    ctx.fillText(t.deco[2 % t.deco.length], frameX + decoOff, frameY + frameH - decoOff);
    ctx.fillText(t.deco[3 % t.deco.length], frameX + frameW - decoOff, frameY + frameH - decoOff);

    // ── Washi tape decoration (top-right) ──
    const tapeW = Math.round(fw * 0.15);
    const tapeH = Math.round(fw * 0.03);
    const tapeX = frameX + Math.round(fw * 0.55);
    const tapeY = frameY - Math.round(fw * 0.008);
    ctx.save();
    ctx.globalAlpha = 0.55;
    ctx.fillStyle = t.grad1;
    ctx.beginPath();
    roundRect(ctx, tapeX, tapeY, tapeW, tapeH, 1);
    ctx.fill();
    ctx.globalAlpha = 1;
    // Tiny tape texture lines
    ctx.strokeStyle = 'rgba(255,255,255,0.25)';
    ctx.lineWidth = 0.5;
    for (let i = 0; i < 3; i++) {
      const lx = tapeX + Math.round(tapeW * (0.25 + i * 0.25));
      ctx.beginPath();
      ctx.moveTo(lx, tapeY + 1);
      ctx.lineTo(lx, tapeY + tapeH - 1);
      ctx.stroke();
    }
    ctx.restore();

    // ── Photo corner tabs (top-left + bottom-right) ──
    const tabSize = Math.round(fw * 0.025);
    ctx.fillStyle = 'rgba(0,0,0,0.04)';
    // Top-left tab
    ctx.beginPath();
    ctx.moveTo(photoX + tabSize, photoY);
    ctx.lineTo(photoX, photoY + tabSize);
    ctx.lineTo(photoX, photoY);
    ctx.closePath();
    ctx.fill();
    // Bottom-right tab
    ctx.beginPath();
    ctx.moveTo(photoX + photoW - tabSize, photoY + photoH);
    ctx.lineTo(photoX + photoW, photoY + photoH - tabSize);
    ctx.lineTo(photoX + photoW, photoY + photoH);
    ctx.closePath();
    ctx.fill();
  }

  function drawPhotoFrame(ctx, fx, fy, fw, fh, t, index, source, isVideo, rotation) {
    if (rotation) {
      ctx.save();
      const cx = fx + fw / 2;
      const cy = fy + fh / 2;
      ctx.translate(cx, cy);
      ctx.rotate(rotation * Math.PI / 180);
      drawCellContent(ctx, -fw / 2, -fh / 2, fw, fh, t, index, source, isVideo);
      ctx.restore();
    } else {
      drawCellContent(ctx, fx, fy, fw, fh, t, index, source, isVideo);
    }
  }

  // ═══════════════════════════════════════════════
  // BUILD STRIP (collage layout, theme-aware)
  // ═══════════════════════════════════════════════
  function getStripMaxW() {
    const wrapper = document.querySelector('.pb-strip-wrapper');
    const fallback = currentLayoutCategory === 'collage' ? 310 : 250;
    if (!wrapper) return fallback;
    const availW = wrapper.clientWidth - 4;
    if (availW < 50) return fallback;
    const maxLimit = currentLayoutCategory === 'collage' ? 310 : 250;
    return Math.min(availW, maxLimit);
  }

  function buildStrip(frames) {
    const t = THEMES[currentTheme];
    const count = frames.length;
    const cells = getLayout(count);
    const maxY = getLayoutMaxY(count);

    const photoAreaW = getStripMaxW();
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
      const rot = cellRotations[i] || 0;
      drawPhotoFrame(ctx, fx, fy, fw, fh, t, i, frames[i], false, rot);
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

  function getGridMaxW() {
    const gridWrap = document.querySelector('.pb-camera-grid-wrap');
    const fallback = currentLayoutCategory === 'collage' ? 280 : 250;
    if (!gridWrap) return fallback;
    const availW = gridWrap.clientWidth - 4;
    if (availW < 50) return fallback;
    const maxLimit = currentLayoutCategory === 'collage' ? 310 : 260;
    return Math.min(availW, maxLimit);
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
    const maxW = getGridMaxW();
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
      const rot = hasPhoto ? (cellRotations[i] || 0) : 0;
      drawPhotoFrame(ctx, fx, fy, fw, fh, t, i, source, !hasPhoto, rot);
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
        showState('preview');
        requestAnimationFrame(() => {
          buildStrip(capturedFrames);
        });
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
    generateRotations(TOTAL_SHOTS);
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
    generateRotations(TOTAL_SHOTS);
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
  // INIT — populate sub-layout buttons
  // ═══════════════════════════════════════════════
  function initSubLayoutButtons() {
    const subRow = document.getElementById('pbSubLayoutRow');
    const liveSub = document.getElementById('pbLiveSubLayout');
    if (!subRow && !liveSub) return;

    const presets = CATEGORY_PRESETS['collage'];
    presets.forEach((id) => {
      const p = LAYOUTS[id];
      if (!p) return;
      const label = p.label;
      const icon = p.icon || '';

      const makeBtn = (container, cls) => {
        const btn = document.createElement('button');
        btn.className = cls;
        btn.dataset.preset = id;
        btn.title = label;
        btn.innerHTML = icon;
        btn.addEventListener('click', () => applyLayoutPreset(id));
        container.appendChild(btn);
      };

      if (subRow) makeBtn(subRow, 'pb-sub-layout-btn' + (id === currentLayoutPreset ? ' active' : ''));
      if (liveSub) makeBtn(liveSub, 'live-sub-layout-btn' + (id === currentLayoutPreset ? ' active' : ''));
    });
  }

  // Set SVG icons on category buttons
  function initLayoutIcons() {
    const stripIcon = LAYOUTS.strip.icon;
    const collageIcon = LAYOUTS['collage-split'].icon;
    const stripEl = document.getElementById('pbLayoutIconStrip');
    const collageEl = document.getElementById('pbLayoutIconCollage');
    if (stripEl) stripEl.innerHTML = stripIcon;
    if (collageEl) collageEl.innerHTML = collageIcon;
  }

  initSubLayoutButtons();
  initLayoutIcons();
  generateRotations(TOTAL_SHOTS);

  // Re-render camera grid on resize/orientation change
  let resizeTimeout;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimeout);
    resizeTimeout = setTimeout(() => {
      if (states.camera && !states.camera.classList.contains('hidden')) {
        renderCameraGrid();
      }
    }, 200);
  });

  startCamera();
})();
