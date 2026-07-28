(function () {
  var saved = localStorage.getItem('synapse_theme') || 'system';

  function getTheme() {
    if (saved === 'dark') return 'dark';
    if (saved === 'light') return 'light';
    return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
  }

  function applyTheme() {
    document.documentElement.setAttribute('data-theme', getTheme());
  }

  applyTheme();

  var mq = window.matchMedia('(prefers-color-scheme: light)');
  try { mq.addEventListener('change', function () { if (saved === 'system') applyTheme(); }); } catch (e) {}

  var MODES = [
    { key: 'system', icon: 'monitor', label: 'System' },
    { key: 'dark', icon: 'moon', label: 'Dark' },
    { key: 'light', icon: 'sun', label: 'Light' },
  ];

  function getModeInfo() {
    for (var i = 0; i < MODES.length; i++) {
      if (MODES[i].key === saved) return MODES[i];
    }
    return MODES[0];
  }

  function updateToggles() {
    var info = getModeInfo();
    var els = document.querySelectorAll('.theme-toggle');
    for (var i = 0; i < els.length; i++) {
      var el = els[i];
      var iconEl = el.querySelector('[data-lucide]');
      if (iconEl) {
        iconEl.setAttribute('data-lucide', info.icon);
      }
      var labelEl = el.querySelector('.tt-label');
      if (labelEl) {
        labelEl.textContent = info.label;
      }
    }
    try { lucide.createIcons(); } catch (e) {}
  }

  window.__theme = {
    getCurrent: function () { return document.documentElement.getAttribute('data-theme'); },
    getMode: function () { return saved; },
    setMode: function (mode) {
      saved = mode;
      localStorage.setItem('synapse_theme', mode);
      applyTheme();
      updateToggles();
    },
    next: function () {
      var idx = MODES.findIndex(function (m) { return m.key === saved; });
      if (idx === -1) idx = 0;
      var nextMode = MODES[(idx + 1) % MODES.length].key;
      this.setMode(nextMode);
      return nextMode;
    },
    updateToggles: updateToggles,
    MODES: MODES,
    getModeInfo: getModeInfo,
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', updateToggles);
  } else {
    updateToggles();
  }

  document.addEventListener('click', function (e) {
    var btn = e.target.closest('.theme-toggle');
    if (btn && window.__theme) {
      e.preventDefault();
      window.__theme.next();
    }
  });
})();
