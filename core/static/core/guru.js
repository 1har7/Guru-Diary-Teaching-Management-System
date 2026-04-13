(function () {
  function initProgressBars() {
    document.querySelectorAll('[data-progress]').forEach(function (el) {
      var raw = el.getAttribute('data-progress');
      if (raw === null || raw === undefined) return;
      var num = parseFloat(raw);
      if (isNaN(num)) return;
      if (num < 0) num = 0;
      if (num > 100) num = 100;
      el.style.width = num.toFixed(2).replace(/\.00$/, '') + '%';
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initProgressBars);
  } else {
    initProgressBars();
  }
})();

