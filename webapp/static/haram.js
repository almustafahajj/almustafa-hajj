/* «في الحرم» في صفحة «رحلتي»: الصلاة القادمة بعدّ تنازلي (مواقيت محسوبة في الخادم
   بتقويم أمّ القرى) + عدّاد أشواط الطواف والسعي يبقى محفوظاً في الجوال. */
(function () {
  'use strict';
  var sec = document.getElementById('haram');
  var raw = document.getElementById('haramData');
  if (!sec || !raw) return;
  var data;
  try { data = JSON.parse(raw.textContent || '{}'); } catch (e) { return; }
  var KEY = 'hr-' + (sec.dataset.key || 'x');
  var store = {
    get: function (k, d) { try { var v = localStorage.getItem(KEY + k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
    set: function (k, v) { try { localStorage.setItem(KEY + k, JSON.stringify(v)); } catch (e) { } }
  };
  var calm = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
  function $(id) { return document.getElementById(id); }
  function buzz(p) { if (navigator.vibrate) { try { navigator.vibrate(p); } catch (e) { } } }

  /* ---------------- مواقيت الصلاة ---------------- */
  var city = store.get('city', 'makkah');
  if (!data.cities || !data.cities[city]) city = 'makkah';

  function makkahNow() {                       // الوقت الآن بتوقيت السعودية (UTC+3) أيّاً كان الجوال
    var n = new Date();
    return new Date(n.getTime() + (n.getTimezoneOffset() + 180) * 60000);
  }
  function iso(d) {
    var m = d.getMonth() + 1, dd = d.getDate();
    return d.getFullYear() + '-' + (m < 10 ? '0' : '') + m + '-' + (dd < 10 ? '0' : '') + dd;
  }
  function mins(t) { var p = String(t || '').split(':'); return (+p[0]) * 60 + (+p[1]); }
  function pad(n) { return (n < 10 ? '0' : '') + n; }

  var list = $('hrList'), names = data.names || [];
  function paint() {
    var now = makkahNow(), key = iso(now), day = (data.days || {})[key];
    var times = day && day[city];
    $('hrCityName').textContent = data.cities[city] || '';
    if (!times) { $('hrName').textContent = '—'; list.innerHTML = ''; return; }
    var cur = now.getHours() * 60 + now.getMinutes() + now.getSeconds() / 60;
    var next = -1;
    for (var i = 0; i < times.length; i++) { if (i !== 1 && mins(times[i]) > cur) { next = i; break; } }
    var nName, nTime, target;
    if (next >= 0) { nName = names[next]; nTime = times[next]; target = mins(nTime); }
    else {                                       // بعد العشاء: فجر الغد
      var tm = new Date(now.getTime() + 86400000), t2 = (data.days || {})[iso(tm)];
      nName = names[0]; nTime = t2 ? t2[city][0] : times[0]; target = mins(nTime) + 1440;
    }
    var left = Math.max(0, Math.round((target - cur) * 60));
    $('hrName').textContent = nName;
    $('hrTime').textContent = nTime;
    $('hrLeft').textContent = pad(Math.floor(left / 3600)) + ':' + pad(Math.floor(left % 3600 / 60)) + ':' + pad(left % 60);
    // القائمة
    var html = '';
    for (var j = 0; j < times.length; j++) {
      var cls = j === next ? 'next' : (mins(times[j]) <= cur ? 'past' : '');
      if (j === 1) cls += ' rise';
      html += '<li class="' + cls + '"><span>' + names[j] + '</span><b dir="ltr">' + times[j] + '</b></li>';
    }
    if (list.innerHTML !== html) list.innerHTML = html;
    // الشمس على قوسها بين الشروق والمغرب، والقمر ليلاً
    var rise = mins(times[1]), set = mins(times[4]), f = (cur - rise) / (set - rise);
    var day_ = f >= 0 && f <= 1, sun = $('hrSun'), moon = $('hrMoon');
    sec.classList.toggle('night', !day_);
    if (day_) {
      var a = Math.PI * (1 - f);                   // الشروق يميناً (الشرق) والغروب يساراً
      var x = 110 + 92 * Math.cos(a), y = 100 - 92 * Math.sin(a);
      sun.setAttribute('transform', 'translate(' + (220 - x).toFixed(1) + ' ' + y.toFixed(1) + ')');
      $('hrDay').setAttribute('stroke-dasharray', (f * 100).toFixed(2) + ' 100');
    } else { $('hrDay').setAttribute('stroke-dasharray', '0 100'); }
    $('hrDay').style.visibility = day_ && f * 100 >= 0.5 ? '' : 'hidden';   // لا نقطة برأسٍ دائري ليلاً
    sun.style.display = day_ ? '' : 'none';
    moon.style.display = day_ ? 'none' : '';
  }
  var cityBtns = $('hrCity').querySelectorAll('button');
  function setCity(c) {
    city = c; store.set('city', c);
    for (var i = 0; i < cityBtns.length; i++) cityBtns[i].setAttribute('aria-pressed', cityBtns[i].dataset.city === c ? 'true' : 'false');
    paint();
  }
  for (var b = 0; b < cityBtns.length; b++) cityBtns[b].addEventListener('click', function () { setCity(this.dataset.city); });
  setCity(city);
  setInterval(paint, 1000);

  /* ---------------- عدّاد الأشواط ---------------- */
  // لكلٍّ من الطواف والسعي عدّه الخاص — فالتبديل بينهما لا يُضيّع الأشواط
  var saved = store.get('count', null), st = { mode: 'tawaf', counts: { tawaf: 0, sai: 0 }, ts: Date.now() };
  if (saved && Date.now() - (saved.ts || 0) <= 8 * 3600 * 1000) {
    st.mode = saved.mode === 'sai' ? 'sai' : 'tawaf';
    if (saved.counts) { st.counts.tawaf = +saved.counts.tawaf || 0; st.counts.sai = +saved.counts.sai || 0; }
    else if (typeof saved.n === 'number') st.counts[st.mode] = saved.n;          // الصيغة القديمة
  } else if (saved && saved.mode === 'sai') st.mode = 'sai';
  st.counts.tawaf = Math.max(0, Math.min(7, st.counts.tawaf | 0));
  st.counts.sai = Math.max(0, Math.min(7, st.counts.sai | 0));
  Object.defineProperty(st, 'n', { get: function () { return st.counts[st.mode]; },
    set: function (v) { st.counts[st.mode] = v; } });
  var ring = $('hrRing'), SEG = 7, R = 50, C = 2 * Math.PI * R, GAP = 16;   // الفجوة أوسع من الرأسين الدائريين (10)
  var segLen = C / SEG - GAP, svg = '';
  svg += '<circle cx="60" cy="60" r="' + R + '" class="hr-r-bg"/>';
  for (var s = 0; s < SEG; s++) {
    svg += '<circle cx="60" cy="60" r="' + R + '" class="hr-r-seg" data-i="' + s + '" stroke-dasharray="' + segLen.toFixed(2) + ' ' + (C - segLen).toFixed(2) +
      '" stroke-dashoffset="' + (-(s * C / SEG) - GAP / 2 + C / 4).toFixed(2) + '"/>';
  }
  ring.innerHTML = svg;
  var segs = ring.querySelectorAll('.hr-r-seg'), modeBtns = $('hrMode').querySelectorAll('button');
  var lock = null;
  function wake() {
    if (lock || !('wakeLock' in navigator) || document.visibilityState !== 'visible') return;
    navigator.wakeLock.request('screen').then(function (l) { lock = l; l.addEventListener('release', function () { lock = null; }); }).catch(function () { });
  }
  function sleep() { if (lock) { try { lock.release(); } catch (e) { } lock = null; } }
  document.addEventListener('visibilitychange', function () { if (document.visibilityState === 'visible' && st.n > 0 && st.n < SEG) wake(); });

  function lapText() {
    var tawaf = st.mode === 'tawaf', k = st.n + 1;
    if (st.n >= SEG) return tawaf ? 'تمّ الطواف — تقبّل الله منك 🤍' : 'تمّ السعي — تقبّل الله منك 🤍';
    if (tawaf) return st.n === 0 ? 'ابدأ من محاذاة الحجر الأسود، واضغط عند إتمام كل شوط'
      : 'الشوط ' + k + ' من 7';
    return (k % 2 ? 'الشوط ' + k + ': من الصفا إلى المروة' : 'الشوط ' + k + ': من المروة إلى الصفا');
  }
  function draw() {
    $('hrN').textContent = st.n;
    for (var i = 0; i < segs.length; i++) segs[i].classList.toggle('on', i < st.n);
    $('hrLap').textContent = lapText();
    $('hrCount').classList.toggle('done', st.n >= SEG);
    for (var j = 0; j < modeBtns.length; j++) modeBtns[j].setAttribute('aria-pressed', modeBtns[j].dataset.mode === st.mode ? 'true' : 'false');
    $('hrUndo').disabled = st.n === 0;
    if (st.n > 0 && st.n < SEG) wake(); else sleep();   // الشاشة تبقى مضاءة أثناء العدّ فقط
  }
  function save() { st.ts = Date.now(); store.set('count', { mode: st.mode, counts: st.counts, ts: st.ts }); }
  $('hrTap').addEventListener('click', function () {
    if (st.n >= SEG) return;
    st.n += 1; save(); draw();
    if (!calm) { var t = $('hrTap'); t.classList.remove('pop'); void t.offsetWidth; t.classList.add('pop'); }
    buzz(st.n >= SEG ? [40, 60, 40, 60, 120] : 30);
  });
  $('hrUndo').addEventListener('click', function () { if (st.n > 0) { st.n -= 1; save(); draw(); } });
  var armed = null;
  $('hrReset').addEventListener('click', function () {
    var btn = this;
    if (st.n === 0) return;
    if (!armed) {                                  // ضغطتان لتأكيد التصفير (حتى لا يضيع العدّ خطأً)
      btn.classList.add('arm'); btn.lastChild.textContent = ' اضغط للتأكيد';
      armed = setTimeout(function () { armed = null; btn.classList.remove('arm'); btn.lastChild.textContent = ' من جديد'; }, 3000);
      return;
    }
    clearTimeout(armed); armed = null; btn.classList.remove('arm'); btn.lastChild.textContent = ' من جديد';
    st.n = 0; save(); draw();
  });
  for (var m = 0; m < modeBtns.length; m++) modeBtns[m].addEventListener('click', function () {
    if (this.dataset.mode === st.mode) return;
    st.mode = this.dataset.mode === 'sai' ? 'sai' : 'tawaf'; save(); draw();
    if (armed) { clearTimeout(armed); armed = null; var rb = $('hrReset'); rb.classList.remove('arm'); rb.lastChild.textContent = ' من جديد'; }
  });
  draw();
})();
