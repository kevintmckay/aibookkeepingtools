(function () {
  function onReady(fn){
    if (document.readyState !== 'loading') fn();
    else document.addEventListener('DOMContentLoaded', fn);
  }

  function renderIcons() {
    var root = document.documentElement;
    var isDark = root.classList.contains('dark');
    var sun = document.getElementById('sun');
    var moon = document.getElementById('moon');
    if (sun && moon) {
      // Show the icon for the *next* action:
      // If it's dark now, show sun (click -> go light). If it's light, show moon (click -> go dark).
      sun.style.display  = isDark ? 'inline' : 'none';
      moon.style.display = isDark ? 'none'  : 'inline';
    }
  }

  onReady(function () {
    var btn = document.getElementById('theme-toggle');
    if (!btn) return;

    // Initial icon state (matches what theme-init.js applied)
    renderIcons();

    btn.addEventListener('click', function () {
      var root = document.documentElement;
      var isDark = root.classList.contains('dark');

      if (isDark) {
        root.classList.remove('dark');
        try { localStorage.setItem('pref-theme', 'light'); } catch (e) {}
      } else {
        root.classList.add('dark');
        try { localStorage.setItem('pref-theme', 'dark'); } catch (e) {}
      }

      // Update icons after toggling
      renderIcons();
    });

    // Follow OS changes only when no explicit choice stored
    var mq = window.matchMedia('(prefers-color-scheme: dark)');
    mq.addEventListener('change', function (e) {
      try {
        if (!localStorage.getItem('pref-theme')) {
          document.documentElement.classList.toggle('dark', e.matches);
          renderIcons();
        }
      } catch (err) {}
    });
  });
})();

