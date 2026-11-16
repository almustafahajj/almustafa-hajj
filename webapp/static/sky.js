/* سماء مكة الآن (صفحة الدخول وصفحات الخطأ): المرحلة — فجر/نهار/غروب/ليل — والشمس أو القمر
   على قوسهما حسب الوقت في مكة (UTC+3)، من مواقيت اليوم المحسوبة في الخادم. */
(function () {
  'use strict';
  var sky = document.getElementById('sky');
  if (!sky) return;
  var t;
  try { t = JSON.parse(sky.getAttribute('data-t') || '{}'); } catch (e) { return; }
  var orb = document.getElementById('skyOrb'), clock = document.getElementById('skyClock'),
      lbl = document.getElementById('skyLbl');
  var LABEL = { dawn: 'وقت الفجر', day: 'نهار', sunset: 'وقت الغروب', night: 'ليل' };

  function makkahMin() {
    var n = new Date(), m = (n.getUTCHours() * 60 + n.getUTCMinutes() + 180) % 1440;
    return m + n.getUTCSeconds() / 60;
  }
  function pad(n) { return (n < 10 ? '0' : '') + n; }
  function arc(f) {                       // 0 عند الشروق (يميناً/شرقاً) → 1 عند الغروب (يساراً)
    f = Math.max(0, Math.min(1, f));
    return { x: 86 - 72 * f, y: 74 - 60 * Math.sin(Math.PI * f) };
  }
  function paint() {
    var cur = makkahMin(), F = t.fajr, R = t.sunrise, M = t.maghrib, ph, p;
    if (cur >= F && cur < R + 25) ph = 'dawn';
    else if (cur >= R + 25 && cur < M - 40) ph = 'day';
    else if (cur >= M - 40 && cur < M + 25) ph = 'sunset';
    else ph = 'night';
    if (ph === 'night') {                 // القمر من المغرب إلى الفجر
      var span = (F + 1440 - M) % 1440 || 600, k = ((cur - M + 1440) % 1440) / span;
      p = arc(k);
    } else {
      p = arc((cur - R) / Math.max(1, M - R));
    }
    for (var c in LABEL) sky.classList.toggle('sky-' + c, c === ph);
    orb.style.setProperty('--x', p.x.toFixed(1) + '%');
    orb.style.setProperty('--y', p.y.toFixed(1) + '%');
    var m = Math.floor(cur);
    if (clock) clock.textContent = pad(Math.floor(m / 60)) + ':' + pad(m % 60);
    if (lbl) lbl.textContent = LABEL[ph];
  }
  paint();
  setInterval(paint, 30000);
})();
