/* Red-figure and black-figure toggle. The button names the figure it would switch you TO and
   the choice is remembered; figure-head.js applies it before first paint on the next page.
   An enhancement: the pages read the same without it. Ported from the WPA-L Archive Reader. */
(function () {
  var b = document.getElementById('figure-toggle');
  if (b) {
    var current = function () {
      var set = document.documentElement.getAttribute('data-theme');
      if (set === 'light' || set === 'dark') return set;
      return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    };
    var label = function () { b.textContent = current() === 'dark' ? 'Red-figure' : 'Black-figure'; };
    label();
    b.hidden = false;
    b.addEventListener('click', function () {
      var next = current() === 'dark' ? 'light' : 'dark';
      var el = document.documentElement;
      el.classList.add('figure-switching');
      el.setAttribute('data-theme', next);
      try { localStorage.setItem('conf-figure', next); } catch (e) {}
      label();
      requestAnimationFrame(function () {
        requestAnimationFrame(function () { el.classList.remove('figure-switching'); });
      });
    });
  }
  document.querySelectorAll('th').forEach(function (t) {
    if (!t.getAttribute('scope')) t.setAttribute('scope', t.closest('thead') ? 'col' : 'row');
  });
})();
