(function () {
  try {
    var key = 'pref-theme'; // PaperMod uses this key
    var ls = localStorage.getItem(key); // "light" | "dark" | null
    var sys = window.matchMedia('(prefers-color-scheme: dark)').matches;
    var dark = (ls === 'dark') || (ls === null && sys);
    // Use the root <html>, not <body>
    document.documentElement.classList.toggle('dark', dark);
  } catch (e) {}
})();

