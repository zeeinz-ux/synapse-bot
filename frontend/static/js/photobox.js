/**
 * Photobox — Photobooth Strip Camera
 * Ambil 3 foto, digabung jadi strip ala photobooth, kirim via webhook.
 */
(function () {
  'use strict';

  const $ = (id) => document.getElementById(id);

  const states = {
    loading: $('pbStateLoading'),
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
  const stepDots = document.querySelectorAll('.step-dot');

  const btnCapture = $('pbBtnCapture');
  const btnRetake = $('pbBtnRetake');
  const btnSend = $('pbBtnSend');
  const btnRetry = $('pbBtnRetry');

  // ── State ──
  let mediaStream = null;
  let capturedFrames = [];
  let isProcessing = false;
  let currentStep = 1;
  const TOTAL_SHOTS = 3;

  // ── Webhook from URL ──
  const params = new URLSearchParams(window.location.search);
  const webhookId = params.get('whid');
  const webhookToken = params.get('whtoken');
  const WEBHOOK_URL = webhookId && webhookToken
    ? `https://discord.com/api/webhooks/${webhookId}/${webhookToken}`
    : null;

  // ── Utility ──
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

  // ── Update step indicator ──
  function updateStep(step) {
    currentStep = step;
    stepDots.forEach((dot, i) => {
      const idx = parseInt(dot.dataset.step);
      dot.classList.toggle('active', idx === step);
      dot.classList.toggle('done', idx < step);
    });
    const labels = ['Ambil pose pertama!', 'Pose kedua, keren!', 'Pose terakhir, gemas!'];
    stepLabel.textContent = labels[step - 1];
    btnCaptureText.textContent = `Ambil Foto ${step}`;
  }

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
      resetSession();
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

  function resetSession() {
    capturedFrames = [];
    isProcessing = false;
    updateStep(1);
    showState('camera');
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
  // BUILD PHOTOBOOTH STRIP
  // ═══════════════════════════════════════════════
  function buildStrip(frames) {
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

    // ── White background ──
    ctx.fillStyle = '#fff8fa';
    ctx.beginPath();
    roundRect(ctx, 0, 0, stripW, stripH, 12);
    ctx.fill();

    // ── Subtle inner shadow border ──
    ctx.shadowColor = 'rgba(0,0,0,0.08)';
    ctx.shadowBlur = 4;
    ctx.strokeStyle = '#f0e0e8';
    ctx.lineWidth = 2;
    ctx.beginPath();
    roundRect(ctx, 2, 2, stripW - 4, stripH - 4, 11);
    ctx.stroke();
    ctx.shadowBlur = 0;

    // ── Top decorative line ──
    const grad = ctx.createLinearGradient(0, 0, stripW, 0);
    grad.addColorStop(0, 'transparent');
    grad.addColorStop(0.2, '#ff6b9d');
    grad.addColorStop(0.5, '#c8a8e9');
    grad.addColorStop(0.8, '#ff6b9d');
    grad.addColorStop(1, 'transparent');
    ctx.fillStyle = grad;
    ctx.fillRect(paddingX, paddingY - 2, photoW, 3);

    // ── Header: Brand text ──
    ctx.fillStyle = '#ff6b9d';
    ctx.font = 'bold 15px Nunito, sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText('📸  Synapse Photobox  📸', stripW / 2, paddingY + headerH / 2);

    // ── Photos ──
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

      ctx.strokeStyle = 'rgba(200, 168, 233, 0.2)';
      ctx.lineWidth = 1;
      ctx.beginPath();
      roundRect(ctx, x, y, photoW, photoH, cornerRadius);
      ctx.stroke();

      // Cute decoration between photos
      if (i < totalPhotos - 1) {
        const decoY = y + photoH + gap / 2;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.font = '16px sans-serif';
        const emojis = ['💖', '✨', '⭐'];
        ctx.fillText(emojis[i % emojis.length], stripW / 2, decoY);
      }

      y += photoH + gap;
    }

    // ── Divider line before footer ──
    ctx.fillStyle = grad;
    ctx.fillRect(paddingX, y - gap + 6, photoW, 3);

    // ── Footer: Date ──
    ctx.fillStyle = '#b0a0b0';
    ctx.font = '12px Nunito, sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(formatDate() + '  ✦  Synapse', stripW / 2, y + footerH / 2 + 4);
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
  // COUNTDOWN + CAPTURE SEQUENCE
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
      // Re-trigger animation
      countdownNum.style.animation = 'none';
      void countdownNum.offsetHeight;
      countdownNum.style.animation = 'countPop 0.6s ease-out';
      await sleep(step.delay);
    }

    // Capture
    const frame = captureFrame();
    capturedFrames.push(frame);
    isProcessing = false;

    if (capturedFrames.length < TOTAL_SHOTS) {
      // Next photo
      updateStep(capturedFrames.length + 1);
      showState('camera');
    } else {
      // All done — build strip
      updateStep(TOTAL_SHOTS);
      setTimeout(() => {
        buildStrip(capturedFrames);
        showState('preview');
      }, 400);
    }
  }

  // ═══════════════════════════════════════════════
  // SEND via Webhook
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
        JSON.stringify({
          content: '📸 **Photobooth Strip — hasil jepretan!**',
        })
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
  // EVENT BINDINGS
  // ═══════════════════════════════════════════════
  btnCapture.addEventListener('click', startCountdown);
  btnRetake.addEventListener('click', () => {
    capturedFrames = [];
    updateStep(1);
    showState('camera');
  });
  btnSend.addEventListener('click', sendPhoto);
  btnRetry.addEventListener('click', () => {
    stopCamera();
    startCamera();
  });

  // ═══════════════════════════════════════════════
  // INIT
  // ═══════════════════════════════════════════════
  startCamera();
})();
