"""مسعّر المجموعات عبر المتصفّح — حاسبة حيّة: تُحسب كلفة الفرد وسعر البيع لكل
نوع غرفة فوراً وأنت تعدّل المدخلات (بنفس منطق :func:`hajj_app.umrah.group_pricing`)،
ثم تُحفظ وتُعاين. حلٌّ للعربية السليمة في أسماء البنود مع الإبقاء على المعاينة الحيّة.
"""

from __future__ import annotations

import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def serve_pricer(data: dict, doc_title: str = "مسعّر المجموعات",
                 timeout: int = 1800) -> dict | None:
    """يفتح المسعّر في المتصفّح ويحجب حتى «حفظ» (أو المهلة)؛ يعيد بيانات المدخلات
    أو ``None``. يُستدعى من خيطٍ خلفي (لا من خيط الواجهة) لأنه يحجب."""
    box: dict = {}
    done = threading.Event()
    html = _pricer_html(data, doc_title).encode("utf-8")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):                       # noqa: N802
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(html)

        def do_POST(self):                      # noqa: N802
            n = int(self.headers.get("Content-Length", 0) or 0)
            raw = self.rfile.read(n) if n else b""
            try:
                box["data"] = json.loads(raw.decode("utf-8"))
            except Exception:
                box["data"] = None
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"OK")
            done.set()

        def log_message(self, *a):              # noqa: A003
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        webbrowser.open(f"http://127.0.0.1:{port}/")
    except Exception:
        pass
    done.wait(timeout=timeout)
    try:
        srv.shutdown()
    except Exception:
        pass
    return box.get("data")


def _pricer_html(data: dict, doc_title: str) -> str:
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return (_TEMPLATE.replace("__DATA__", payload)
            .replace("__TITLE__", doc_title))


_TEMPLATE = r"""<!doctype html>
<html lang="ar" dir="rtl"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
  :root{ --bronze:#8A6E4B; --deep:#6E543A; --bg:#F4F1EC; --panel:#fff;
         --border:#E2DACE; --ink:#2C2318; --muted:#8A7E68; --green:#2E6B45; }
  *{ box-sizing:border-box; }
  body{ font-family:"Segoe UI",Tahoma,"Traditional Arabic",sans-serif;
        background:var(--bg); color:var(--ink); margin:0; padding:0 0 96px; }
  header{ background:var(--bronze); color:#fff; padding:16px 22px;
          position:sticky; top:0; z-index:5; box-shadow:0 2px 8px #0002;
          display:flex; justify-content:space-between; align-items:center; }
  header h1{ font-size:19px; margin:0; }
  header .num{ font-size:14px; opacity:.9; }
  .wrap{ max-width:940px; margin:18px auto; padding:0 16px; }
  fieldset{ background:var(--panel); border:1px solid var(--border);
            border-radius:14px; padding:14px 16px; margin:0 0 16px; }
  legend{ color:var(--bronze); font-weight:700; font-size:15px; padding:0 8px; }
  .grid{ display:grid; grid-template-columns:1fr 1fr; gap:10px 18px; }
  label.row{ display:flex; align-items:center; gap:10px; margin:4px 0; }
  label.row > span{ width:150px; color:var(--ink); font-size:14px; flex:none;
                    text-align:left; }
  input, select{ flex:1; font:inherit; font-size:15px; color:var(--ink);
      background:#fff; border:1px solid var(--border); border-radius:9px;
      padding:8px 10px; direction:rtl; width:100%; }
  input[readonly]{ background:#F2ECE3; color:var(--muted); }
  input[type=checkbox]{ width:20px; height:20px; flex:none; }
  .types{ display:flex; gap:16px; flex-wrap:wrap; }
  .types label{ display:flex; align-items:center; gap:6px; font-size:15px; }
  .item{ display:grid; grid-template-columns: 1fr 130px auto; gap:8px;
         align-items:center; margin:6px 0; }
  .btn{ font:inherit; font-weight:700; border:none; border-radius:10px;
        padding:9px 16px; cursor:pointer; }
  .btn.add{ background:#EDE4D5; color:var(--deep); }
  .btn.del{ background:#F3D9D2; color:#B23A3A; padding:7px 11px; }
  table.res{ width:100%; border-collapse:collapse; margin-top:6px;
             overflow:hidden; border-radius:10px; }
  table.res th, table.res td{ padding:9px 8px; text-align:center; font-size:14px;
      border:1px solid var(--border); }
  table.res th{ background:var(--bronze); color:#fff; }
  table.res td.sell{ font-weight:800; color:var(--green); font-size:16px; }
  table.res tr:nth-child(even) td{ background:#FBF8F3; }
  footer{ position:fixed; bottom:0; inset-inline:0; background:#fff;
          border-top:1px solid var(--border); padding:12px 20px;
          display:flex; gap:12px; justify-content:flex-start; align-items:center;
          box-shadow:0 -2px 8px #0001; z-index:6; }
  .btn.save{ background:var(--bronze); color:#fff; font-size:16px;
             padding:11px 26px; }
  .btn.save:hover{ background:var(--deep); }
  small.hint{ color:var(--muted); }
</style></head>
<body>
<header>
  <h1>🧮 مسعّر المجموعات</h1>
  <span class="num" id="hnum"></span>
</header>
<div class="wrap">
  <fieldset><legend>العنوان والفترة والعملة</legend>
    <div class="grid">
      <label class="row"><span>الرقم المرجعي</span>
        <input id="number" readonly></label>
      <label class="row"><span>عنوان التسعير</span><input id="title"></label>
      <label class="row"><span>الفترة من</span>
        <input id="period_from" type="date"></label>
      <label class="row"><span>الفترة إلى</span>
        <input id="period_to" type="date"></label>
      <label class="row"><span>العملة</span>
        <select id="currency"><option>درهم</option><option>ريال</option>
          <option>دولار</option></select></label>
    </div>
  </fieldset>

  <fieldset><legend>أنواع الغرف المطلوب تسعيرها</legend>
    <div class="types" id="types"></div>
  </fieldset>

  <fieldset><legend>الفنادق (سعر الغرفة/الليلة + الوجبات للفرد)</legend>
    <div class="grid">
      <label class="row"><span>فندق مكة</span><input id="makkah_hotel"></label>
      <label class="row"><span>ليالي مكة</span>
        <input id="makkah_nights" type="number" min="0"></label>
      <label class="row"><span>سعر غرفة مكة/ليلة</span>
        <input id="makkah_rate" type="number" min="0"></label>
      <label class="row"><span>وجبات مكة (للفرد)</span>
        <input id="makkah_meals" type="number" min="0"></label>
    </div>
    <label class="row" style="margin-top:8px"><span>تضمين المدينة</span>
      <input id="include_madinah" type="checkbox"></label>
    <div class="grid">
      <label class="row"><span>فندق المدينة</span>
        <input id="madinah_hotel"></label>
      <label class="row"><span>ليالي المدينة</span>
        <input id="madinah_nights" type="number" min="0"></label>
      <label class="row"><span>سعر غرفة المدينة/ليلة</span>
        <input id="madinah_rate" type="number" min="0"></label>
      <label class="row"><span>وجبات المدينة (للفرد)</span>
        <input id="madinah_meals" type="number" min="0"></label>
    </div>
  </fieldset>

  <fieldset><legend>البنود (للفرد) — أضِف أو احذف</legend>
    <div id="items"></div>
    <button class="btn add" type="button" onclick="addItem('','')">
      ➕ إضافة بند</button>
  </fieldset>

  <fieldset><legend>الربح والمصاريف (للفرد)</legend>
    <div class="grid">
      <label class="row"><span>نسبة الربح %</span>
        <input id="profit_pct" type="number"></label>
      <label class="row"><span>مصاريف أخرى</span>
        <input id="other" type="number"></label>
      <label class="row"><span>ربح عام (كل الأنواع)</span>
        <input id="profit" type="number"></label>
    </div>
    <small class="hint">أو مبلغ ربح لكل نوع غرفة (يعلو الربح العام):</small>
    <div class="grid">
      <label class="row"><span>مفرد</span>
        <input id="profit_single" type="number"></label>
      <label class="row"><span>ثنائي</span>
        <input id="profit_double" type="number"></label>
      <label class="row"><span>ثلاثي</span>
        <input id="profit_triple" type="number"></label>
      <label class="row"><span>رباعي</span>
        <input id="profit_quad" type="number"></label>
      <label class="row"><span>طفل</span>
        <input id="profit_child" type="number"></label>
    </div>
  </fieldset>

  <fieldset><legend>النتيجة — تُحسب فوراً</legend>
    <div style="overflow-x:auto">
      <table class="res"><thead><tr>
        <th>نوع الغرفة</th><th>التكلفة الصافية</th><th>الربح</th>
        <th>النسبة %</th><th>سعر البيع</th></tr></thead>
        <tbody id="resbody"></tbody></table>
    </div>
  </fieldset>
</div>
<footer>
  <button class="btn save" onclick="submitForm()">💾 حفظ ومعاينة PDF</button>
  <small class="hint">الأسعار تُحسب فوراً وأنت تعدّل — والعربية تعمل هنا تماماً.</small>
</footer>
<script>
const Q = __DATA__;
const ROOM_TYPES = [["مفرد",1],["ثنائي",2],["ثلاثي",3],["رباعي",4],["طفل",0]];
const PROFIT_KEYS = {"مفرد":"profit_single","ثنائي":"profit_double",
  "ثلاثي":"profit_triple","رباعي":"profit_quad","طفل":"profit_child"};
const SIMPLE = ["title","currency","period_from","period_to","makkah_hotel",
  "makkah_nights","makkah_rate","makkah_meals","madinah_hotel","madinah_nights",
  "madinah_rate","madinah_meals","profit_pct","other","profit","profit_single",
  "profit_double","profit_triple","profit_quad","profit_child"];
const gnum = x => parseFloat(String(x==null?'':x).replace(/[,،]/g,'').trim())||0;
const el = (t,a={},kids=[])=>{const e=document.createElement(t);
  for(const k in a){ if(k==='class')e.className=a[k]; else e.setAttribute(k,a[k]); }
  (Array.isArray(kids)?kids:[kids]).forEach(c=>c&&e.append(c)); return e;};
const $ = id => document.getElementById(id);

document.getElementById('hnum').textContent = 'الرقم: '+(Q.number||'');
$('number').value = Q.number||'';
SIMPLE.forEach(k=>{ if($(k)!=null && Q[k]!=null) $(k).value = Q[k]; });
$('currency').value = Q.currency||'درهم';
const incMd = ["","0","False","false"].includes(String(Q.include_madinah==null?"1":Q.include_madinah).trim()) ? false : true;
$('include_madinah').checked = incMd;

// أنواع الغرف (مربّعات اختيار)
const sel = (Array.isArray(Q.room_types)&&Q.room_types.length)?Q.room_types:ROOM_TYPES.map(r=>r[0]);
const typesBox = $('types');
ROOM_TYPES.forEach(([name],i)=>{
  const cb = el('input',{type:'checkbox',id:'rt_'+i});
  if(sel.includes(name)) cb.setAttribute('checked','');
  cb.onchange = recalc;
  typesBox.append(el('label',{},[cb, document.createTextNode(name)]));
});

// البنود الديناميكية
const itemsBox = $('items');
function addItem(name,amount){
  const n = el('input',{value:name||'',placeholder:'اسم البند'});
  const a = el('input',{type:'number',value:amount||'',placeholder:'المبلغ'});
  const del = el('button',{class:'btn del',type:'button'},document.createTextNode('🗑'));
  const row = el('div',{class:'item'},[n,a,del]);
  row._n=n; row._a=a;
  del.onclick=()=>{ row.remove(); recalc(); };
  a.oninput=recalc; n.oninput=recalc;
  itemsBox.append(row);
}
(Q.items||[]).forEach(it=>addItem((it||[])[0]||'',(it||[])[1]||''));
if(!(Q.items||[]).length) addItem('','');

// حساب حيّ (مطابق لـ umrah.group_pricing)
function collect(){
  const out = { number: Q.number };
  SIMPLE.forEach(k=> out[k] = ($(k)?.value ?? ''));
  out.include_madinah = $('include_madinah').checked ? '1':'0';
  out.room_types = ROOM_TYPES.filter((_,i)=>$('rt_'+i)?.checked).map(r=>r[0]);
  out.items = Array.from(itemsBox.children).map(r=>[r._n.value.trim(), r._a.value.trim()])
    .filter(x=>x[0]||x[1]);
  return out;
}
function pricing(D){
  let mkR=gnum(D.makkah_rate), mkN=gnum(D.makkah_nights);
  let mdR=gnum(D.madinah_rate), mdN=gnum(D.madinah_nights);
  let mkM=gnum(D.makkah_meals), mdM=gnum(D.madinah_meals);
  const inc = ["","0","False","false"].includes(String(D.include_madinah==null?"1":D.include_madinah).trim()) ? false : true;
  if(!inc){ mdR=mdN=mdM=0; }
  const services = (D.items||[]).reduce((s,it)=> s+gnum((it||[])[1]), 0);
  const pct=gnum(D.profit_pct), other=gnum(D.other);
  const selected = (D.room_types&&D.room_types.length)?D.room_types:null;
  const rows=[];
  for(const [name,occ] of ROOM_TYPES){
    if(selected && !selected.includes(name)) continue;
    let mkpp=0, mdpp=0;
    if(occ){ mkpp=(mkR*mkN)/occ; mdpp=(mdR*mdN)/occ; }
    const room = mkpp+mdpp+mkM+mdM;
    const net = room+services;
    const raw = String(D[PROFIT_KEYS[name]]||'').trim();
    const pAmt = raw!==''? gnum(raw) : gnum(D.profit);
    const margin = pAmt + net*pct/100 + other;
    const selling = net+margin;
    const mpct = net? (margin/net*100):0;
    rows.push({type:name, net, margin, mpct, selling});
  }
  return rows;
}
const fmt = v => (Math.round(v*100)/100).toLocaleString('en-US',{minimumFractionDigits:0,maximumFractionDigits:2});
function recalc(){
  const cur = $('currency').value||'درهم';
  const rows = pricing(collect());
  const body = $('resbody'); body.innerHTML='';
  rows.forEach(r=>{
    const tr = el('tr',{},[
      el('td',{},document.createTextNode(r.type)),
      el('td',{},document.createTextNode(fmt(r.net)+' '+cur)),
      el('td',{},document.createTextNode(fmt(r.margin)+' '+cur)),
      el('td',{},document.createTextNode(r.mpct.toFixed(1)+'٪')),
    ]);
    const sell = el('td',{class:'sell'},document.createTextNode(fmt(r.selling)+' '+cur));
    tr.append(sell); body.append(tr);
  });
}
SIMPLE.forEach(k=>{ const e=$(k); if(e){ e.oninput=recalc; e.onchange=recalc; } });
$('include_madinah').onchange=recalc;
recalc();

function submitForm(){
  fetch('/save',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify(collect())}).then(()=>{ document.open();
      document.write('<meta charset=utf-8><body style="font-family:sans-serif;'
      +'direction:rtl;text-align:center;padding:60px;background:#F4F1EC;color:#2C2318">'
      +'<div style="font-size:52px">✅</div><h2>تمّ حفظ التسعير</h2>'
      +'<p style="color:#6E543A">عُد إلى البرنامج — ستُفتح معاينة الـ PDF.</p>');
      document.close(); }).catch(e=>alert('تعذّر الحفظ: '+e));
}
</script>
</body></html>
"""
