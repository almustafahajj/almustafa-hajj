/* شاشة المكتب: شرائح تتناوب — الساعة والتاريخ الهجري والصلاة القادمة في مكة، الرحلات
   القادمة، آراء المعتمرين (بلا أسماء)، وحضور اليوم. البيانات تُجلب كل دقيقتين. */
(function () {
  'use strict';
  var cfg = {};
  try { cfg = JSON.parse(document.getElementById('tvCfg').textContent || '{}'); } catch (e) { }
  var stage = document.getElementById('tvStage'), dots = document.getElementById('tvDots');
  var clockSlide = stage.querySelector('[data-kind=clock]');
  var calm = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
  var data = null, slides = [clockSlide], cur = 0, timer = null;
  function $(id) { return document.getElementById(id); }
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function pad(n) { return (n < 10 ? '0' : '') + n; }
  var fGreg = new Intl.DateTimeFormat('ar', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric', numberingSystem: 'latn' });
  var fHij;
  try { fHij = new Intl.DateTimeFormat('ar-SA-u-ca-islamic-umalqura-nu-latn', { day: 'numeric', month: 'long', year: 'numeric' }); } catch (e) { }

  /* الساعة والتاريخ ثم الصلاة القادمة في مكة */
  function tick() {
    var n = new Date(), hm = pad(n.getHours()) + ':' + pad(n.getMinutes());
    $('tvClock').textContent = hm; $('tvBig').textContent = hm;
    var g = fGreg.format(n);
    $('tvDate').textContent = g; $('tvGreg').textContent = g;
    if (fHij) $('tvHijri').textContent = fHij.format(n);
    if (data && data.prayer && data.prayer.times) {
      var mk = (n.getUTCHours() * 60 + n.getUTCMinutes() + 180) % 1440, t = data.prayer.times, nm = data.prayer.names, k = -1;
      for (var i = 0; i < t.length; i++) { var p = t[i].split(':'), m = +p[0] * 60 + +p[1]; if (i !== 1 && m > mk) { k = i; break; } }
      if (k < 0) k = 0;
      var left = ((+t[k].split(':')[0] * 60 + +t[k].split(':')[1]) - mk + 1440) % 1440;
      $('tvPray').hidden = false;
      $('tvPName').textContent = nm[k];
      $('tvPTime').textContent = t[k] + ' · بعد ' + Math.floor(left / 60) + ':' + pad(left % 60);
    }
  }

  function slide(kind, html) {
    var s = document.createElement('section');
    s.className = 'tv-slide'; s.dataset.kind = kind; s.innerHTML = html;
    return s;
  }
  function build() {
    slides.forEach(function (s) { if (s !== clockSlide) s.remove(); });
    slides = [clockSlide];
    if (!data) return;
    var tr = data.trips || [];
    if (tr.length) {
      var rows = tr.map(function (t) {
        var chip = t.state === 'now' ? '<span class="tv-chip now">جارية</span>' :
          t.state === 'today' ? '<span class="tv-chip today">تنطلق اليوم</span>' :
            t.days === 1 ? '<span class="tv-chip">غداً</span>' : t.days === 2 ? '<span class="tv-chip">بعد يومين</span>' :
            '<span class="tv-chip">بعد <b>' + t.days + '</b> ' + esc(t.unit) + '</span>';
        var cap = t.cap ? Math.min(100, Math.round(100 * t.n / t.cap)) : 0;
        return '<li><div class="tv-tn"><b>' + esc(t.label) + '</b><small>' + esc(t.noun) + ' · ' + esc(t.dep_txt) +
          (t.ret_txt ? ' ← ' + esc(t.ret_txt) : '') + '</small></div>' + chip +
          '<div class="tv-seats"><span><b>' + t.n + '</b>' + (t.cap ? ' / ' + t.cap : '') + ' مسجّل</span>' +
          (t.cap ? '<i><u style="width:' + cap + '%"></u></i>' : '') + '</div></li>';
      }).join('');
      slides.push(slide('trips', '<h2 class="tv-h">الرحلات القادمة</h2><ol class="tv-trips">' + rows + '</ol>'));
    }
    (data.reviews || []).slice(0, 5).forEach(function (r) {
      var st = ''; for (var i = 0; i < 5; i++) st += '<span class="' + (i < r.stars ? 'on' : '') + '">★</span>';
      slides.push(slide('review', '<h2 class="tv-h">من آراء معتمرينا</h2><figure class="tv-rev"><div class="tv-stars">' + st +
        '</div><blockquote>«' + esc(r.comment) + '»</blockquote><figcaption>' + esc(r.kind) + ' ' + esc(r.when) + '</figcaption></figure>'));
    });
    var ck = data.checkins || [];
    if (ck.length) {
      var cards = ck.map(function (c) {
        var p = c.total ? Math.round(100 * c.present / c.total) : 0, C = 2 * Math.PI * 52;
        return '<li><svg viewBox="0 0 120 120" aria-hidden="true"><circle cx="60" cy="60" r="52" class="tv-rb"/>' +
          '<circle cx="60" cy="60" r="52" class="tv-rf" stroke-dasharray="' + (C * p / 100).toFixed(1) + ' ' + C.toFixed(1) + '"/></svg>' +
          '<div class="tv-ck"><b>' + c.present + '<small> / ' + c.total + '</small></b><span>' + esc(c.stage) + '</span></div>' +
          '<p>' + esc(c.label) + '</p></li>';
      }).join('');
      slides.push(slide('airport', '<h2 class="tv-h">حضور اليوم</h2><ul class="tv-att">' + cards + '</ul>'));
    }
    slides.forEach(function (s) { if (s !== clockSlide) stage.appendChild(s); });
    dots.innerHTML = slides.map(function (_s, i) { return '<i class="' + (i === cur ? 'on' : '') + '"></i>'; }).join('');
    if (data.updated) {
      var d = new Date(data.updated);
      $('tvUpd').textContent = isNaN(d) ? '' : 'آخر تحديث ' + pad(d.getHours()) + ':' + pad(d.getMinutes());
    }
  }
  function show(i) {
    cur = (i + slides.length) % slides.length;
    slides.forEach(function (s, k) { s.classList.toggle('on', k === cur); });
    [].forEach.call(dots.children, function (d, k) { d.classList.toggle('on', k === cur); });
    clearTimeout(timer);
    var kind = slides[cur].dataset.kind;
    timer = setTimeout(function () { show(cur + 1); }, kind === 'review' ? 11000 : kind === 'clock' ? 14000 : 16000);
  }
  function load() {
    if (!cfg.url) return;
    fetch(cfg.url, { cache: 'no-store' }).then(function (r) { return r.ok ? r.json() : null; }).then(function (d) {
      if (d && d.ok) { data = d; build(); tick(); if (cur >= slides.length) show(0); }
    }).catch(function () { });
  }
  tick(); setInterval(tick, 5000);
  load(); setInterval(load, 120000);
  show(0);
  if (calm) document.documentElement.classList.add('tv-calm');
  // لا تُطفأ الشاشة (حيث يدعمه المتصفّح)
  if ('wakeLock' in navigator) {
    var lock = null, req = function () { navigator.wakeLock.request('screen').then(function (l) { lock = l; }).catch(function () { }); };
    req(); document.addEventListener('visibilitychange', function () { if (document.visibilityState === 'visible') req(); });
  }
})();
