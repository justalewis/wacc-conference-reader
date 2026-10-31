/* One line chart for any set of series. D = {years, series: [{key, short, color, values, ocr}]}.
   Colour comes from the page's --cat-N tokens, so red-figure and black-figure both work; a year read from a
   heavily OCR'd scan is drawn as a diamond, and a missing year leaves a gap in the line. */
function drawSeries(canvasId, D, yTitle, asShare) {
  var css = getComputedStyle(document.documentElement);
  var sets = D.series.map(function (s) {
    var c = css.getPropertyValue("--cat-" + s.color).trim() || "#888";
    return {label: s.short, data: s.values, borderColor: c, backgroundColor: c, tension: 0, spanGaps: false, pointRadius: 3,
            pointStyle: s.ocr.map(function (o) { return o ? "rectRot" : "circle"; }),
            pointRadius: s.ocr.map(function (o) { return o ? 5 : 3; })};
  });
  return new Chart(document.getElementById(canvasId), {
    type: "line", data: {labels: D.years, datasets: sets},
    options: {maintainAspectRatio: false, interaction: {mode: "nearest", intersect: false},
      scales: {y: {beginAtZero: true, title: {display: true, text: yTitle},
                   ticks: asShare ? {callback: function (v) { return Math.round(v * 100) + "%"; }} : {}}},
      plugins: {tooltip: {callbacks: {label: function (c) {
        var v = c.parsed.y; if (v === null) return c.dataset.label + ": no data";
        return c.dataset.label + ": " + (asShare ? (v * 100).toFixed(1) + "%" : v);
      }}}}}
  });
}
