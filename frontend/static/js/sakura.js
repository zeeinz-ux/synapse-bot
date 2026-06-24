(function() {
  var c = document.getElementById('sakuraContainer');
  if (!c) return;

  var colors = ['#ffb7c5','#ffc0cb','#ffb3ba','#ffd1dc','#f8c8d2','#fce4ec','#f8bbd0','#ffcdd2','#e8a0b4'];
  var petals = [];
  var count = 120;
  var start = Date.now();
  var dh = Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);

  for (var i = 0; i < count; i++) {
    var el = document.createElement('div');
    el.className = 'sakura-p';
    var sz = 5 + Math.random() * 13;
    var x = Math.random() * 94;
    var y = Math.random() * (dh - 40) + 5;

    el.style.cssText =
      'width:' + sz + 'px;' +
      'height:' + (sz * (1 + Math.random() * 0.3)) + 'px;' +
      'left:' + x + '%;' +
      'top:' + y + 'px;' +
      'background:' + colors[Math.floor(Math.random() * colors.length)] + ';' +
      'opacity:' + (0.25 + Math.random() * 0.4) + ';';

    if (Math.random() > 0.55) {
      var inner = document.createElement('div');
      var iw = sz * 0.35;
      inner.style.cssText =
        'position:absolute;top:' + (sz * 0.2) + 'px;left:' + (sz * 0.15) + 'px;' +
        'width:' + iw + 'px;height:' + iw + 'px;' +
        'border-radius:50% 0 50% 0;background:' + colors[Math.floor(Math.random() * colors.length)] + ';opacity:0.3;';
      el.appendChild(inner);
    }

    c.appendChild(el);

    petals.push({
      el: el,
      phaseX: Math.random() * Math.PI * 2,
      phaseY: Math.random() * Math.PI * 2,
      phaseR: Math.random() * Math.PI * 2,
      ampX: 10 + Math.random() * 25,
      ampY: 2 + Math.random() * 4,
      ampR: 2 + Math.random() * 5,
      speedX: 0.06 + Math.random() * 0.1,
      speedY: 0.04 + Math.random() * 0.08,
      speedR: 0.04 + Math.random() * 0.06,
    });
  }

  function tick() {
    var t = (Date.now() - start) / 1000;
    for (var i = 0; i < petals.length; i++) {
      var p = petals[i];
      var x = Math.sin(t * p.speedX + p.phaseX) * p.ampX;
      var y = Math.sin(t * p.speedY + p.phaseY) * p.ampY;
      var r = Math.sin(t * p.speedR + p.phaseR) * p.ampR;
      p.el.style.transform = 'translate(' + x + 'px,' + y + 'px) rotate(' + r + 'deg)';
    }
    requestAnimationFrame(tick);
  }

  requestAnimationFrame(tick);
})();
