(function () {
  var bg = document.querySelector('.bg-glow');
  if (!bg) return;

  var canvas = document.createElement('canvas');
  canvas.style.cssText = 'position:fixed;inset:0;z-index:0;pointer-events:none;width:100%;height:100%';
  canvas.width = window.innerWidth;
  canvas.height = window.innerHeight;
  bg.parentNode.insertBefore(canvas, bg);

  var ctx = canvas.getContext('2d');
  var stars = [];
  var shootingStars = [];
  var W, H;

  function resize() {
    W = canvas.width = window.innerWidth;
    H = canvas.height = window.innerHeight;
  }
  window.addEventListener('resize', resize);
  resize();

  var count = Math.min(200, Math.floor((W * H) / 5000));

  function getTheme() {
    return document.documentElement.getAttribute('data-theme') || 'dark';
  }

  function getColorPalette() {
    if (getTheme() === 'light') {
      return {
        warm: ['255,80,80', '255,180,50', '255,230,50', '80,220,80', '50,180,255', '180,80,255', '255,100,200'],
        violet: ['200,150,255', '255,150,200', '150,200,255'],
        white: '255,255,255',
        shootingHead: '255,200,100',
        shootingTail: '0,212,255',
      };
    }
    return {
      warm: ['255,220,150', '255,200,100', '255,180,80'],
      violet: ['200,180,255', '180,150,255', '160,130,255'],
      white: '255,255,255',
      shootingHead: '255,255,255',
      shootingTail: '0,212,255',
    };
  }

  var palette = getColorPalette();

  function rebuildStars() {
    stars = [];
    palette = getColorPalette();
    var warmCount = Math.floor(count * 0.25);
    var violetCount = Math.floor(count * 0.1);

    for (var i = 0; i < count; i++) {
      var color = palette.white;
      if (i < warmCount) {
        color = palette.warm[Math.floor(Math.random() * palette.warm.length)];
      } else if (i < warmCount + violetCount) {
        color = palette.violet[Math.floor(Math.random() * palette.violet.length)];
      }
      stars.push({
        x: Math.random() * W,
        y: Math.random() * H,
        r: 0.5 + Math.random() * 1.8,
        alpha: 0.2 + Math.random() * 0.8,
        speed: 0.005 + Math.random() * 0.02,
        phase: Math.random() * Math.PI * 2,
        color: color,
      });
    }
  }

  rebuildStars();

  function spawnShootingStar() {
    var x = Math.random() * W * 1.2 - W * 0.1;
    var y = Math.random() * H * 0.4;
    var angle = Math.PI / 4 + Math.random() * Math.PI / 4;
    var speed = 4 + Math.random() * 6;
    var len = 60 + Math.random() * 100;
    shootingStars.push({
      x: x, y: y,
      vx: Math.cos(angle) * speed,
      vy: Math.sin(angle) * speed,
      len: len,
      life: 1,
      decay: 0.008 + Math.random() * 0.012,
    });
  }

  var lastShooting = 0;
  var lastThemeCheck = 0;

  function draw(t) {
    var now = Date.now();

    if (now - lastThemeCheck > 2000) {
      lastThemeCheck = now;
      var currentTheme = getTheme();
      var currentPalette = getColorPalette();
      if (currentPalette.warm[0] !== palette.warm[0]) {
        rebuildStars();
      }
    }

    ctx.clearRect(0, 0, W, H);

    for (var i = 0; i < stars.length; i++) {
      var s = stars[i];
      var a = s.alpha * (0.5 + 0.5 * Math.sin(t * s.speed + s.phase));
      ctx.beginPath();
      ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(' + s.color + ',' + a + ')';
      ctx.fill();
    }

    for (var i = shootingStars.length - 1; i >= 0; i--) {
      var ss = shootingStars[i];
      ss.x += ss.vx;
      ss.y += ss.vy;
      ss.life -= ss.decay;

      if (ss.life <= 0) {
        shootingStars.splice(i, 1);
        continue;
      }

      var gradient = ctx.createLinearGradient(ss.x, ss.y, ss.x - ss.vx * 2, ss.y - ss.vy * 2);
      gradient.addColorStop(0, 'rgba(' + palette.shootingHead + ',' + (ss.life * 0.9) + ')');
      gradient.addColorStop(1, 'rgba(' + palette.shootingTail + ',0)');

      ctx.beginPath();
      ctx.moveTo(ss.x, ss.y);
      ctx.lineTo(ss.x - ss.vx / ss.vy * (ss.len * ss.life), ss.y - ss.len * ss.life);
      ctx.strokeStyle = gradient;
      ctx.lineWidth = 1.5;
      ctx.stroke();

      ctx.beginPath();
      ctx.arc(ss.x, ss.y, 2, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(' + palette.shootingHead + ',' + (ss.life * 0.9) + ')';
      ctx.fill();
    }

    var elapsed = now - lastShooting;
    if (elapsed > 4000 + Math.random() * 8000) {
      spawnShootingStar();
      lastShooting = now;
    }

    requestAnimationFrame(draw);
  }

  requestAnimationFrame(draw);
})();
