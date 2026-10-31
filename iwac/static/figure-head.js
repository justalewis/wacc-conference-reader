/* Red-figure and black-figure follow the reader's system setting. This applies a saved
   override before first paint so the page does not repaint into it. Taken from the WPA-L
   Archive Reader; the key is shared by all five readers and the landing page (one origin). */
(function () {
  try {
    var f = localStorage.getItem('conf-figure');
    if (f === 'light' || f === 'dark') document.documentElement.setAttribute('data-theme', f);
  } catch (e) {}
})();
