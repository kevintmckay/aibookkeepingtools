(function () {
  function onReady(fn){ if(document.readyState!=='loading'){fn()} else {document.addEventListener('DOMContentLoaded',fn)} }
  onReady(function () {
    var btn = document.getElementById('theme-toggle');
    if (!btn) return;
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
    });
    var mq = window.matchMedia('(prefers-color-scheme: dark)');
    mq.addEventListener('change', function (e) {
      try {
        if (!localStorage.getItem('pref-theme')) {
          document.documentElement.classList.toggle('dark', e.matches);
        }
      } catch (err) {}
    });
  });
})();

