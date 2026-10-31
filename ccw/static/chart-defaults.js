/* Chart.js defaults: follow the page's text colour and type, and skip animation for readers who ask for reduced motion. */
if (window.Chart) {
  const cs = getComputedStyle(document.body);
  Chart.defaults.color = cs.color;
  Chart.defaults.font.family = cs.fontFamily;
  Chart.defaults.borderColor = "rgba(128,120,105,.25)";
  if (window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches) Chart.defaults.animation = false;
}
