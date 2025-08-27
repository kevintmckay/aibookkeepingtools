(function () {
  var menu = document.getElementById('menu');
  if (menu) {
    try {
      var pos = localStorage.getItem('menu-scroll-position');
      if (pos) menu.scrollLeft = +pos;
      menu.addEventListener('scroll', function () {
        localStorage.setItem('menu-scroll-position', String(menu.scrollLeft));
      });
    } catch (e) {}
  }
  function onReady(fn){ if(document.readyState!=='loading'){fn()} else {document.addEventListener('DOMContentLoaded',fn)} }
  onReady(function () {
    var prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    document.querySelectorAll('a[href^="#"]').forEach(function (a) {
      a.addEventListener('click', function (e) {
        var id = this.getAttribute('href').slice(1);
        if (!id) return;
        var target = document.getElementById(decodeURIComponent(id));
        if (!target) return;
        e.preventDefault();
        if (prefersReduced) target.scrollIntoView();
        else target.scrollIntoView({ behavior: 'smooth' });
        history[(id === 'top') ? 'replaceState' : 'pushState'](null, '', (id === 'top') ? ' ' : '#' + id);
      });
    });
  });
})();

