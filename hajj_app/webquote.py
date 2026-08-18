"""محرّر «عرض سعر / برنامج الحج» عبر المتصفّح — حلٌّ جذري لمشكلة عرض العربية
أثناء التحرير في Tkinter. تُفتح صفحة HTML محلّية في المتصفّح (الذي يدعم bidi
بالكامل)، فيكتب المستخدم ويرى النصّ صحيحاً، ثم تُرسَل البيانات إلى البرنامج
عبر خادمٍ محلّي مؤقّت (127.0.0.1) ليحفظ ويولّد الـ PDF."""

from __future__ import annotations

import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def serve_editor(data: dict, doc_title: str = "عرض سعر الحج",
                 timeout: int = 1800) -> dict | None:
    """يفتح المحرّر في المتصفّح ويحجب حتى يضغط المستخدم «حفظ» (أو المهلة).

    يعيد قاموس البيانات المُدخَلة، أو ``None`` عند الإلغاء/المهلة. يجب استدعاؤه
    من خيطٍ خلفي (لا من خيط الواجهة) لأنه يحجب."""
    box: dict = {}
    done = threading.Event()
    html = _editor_html(data, doc_title).encode("utf-8")

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
            self.wfile.write(_done_html().encode("utf-8"))
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


def _done_html() -> str:
    return (
        "<!doctype html><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<body style='font-family:Segoe UI,Tahoma,sans-serif;direction:rtl;"
        "text-align:center;padding:60px 20px;background:#F4F1EC;color:#2C2318'>"
        "<div style='font-size:52px'>✅</div>"
        "<h2>تمّ حفظ العرض بنجاح</h2>"
        "<p style='color:#6E543A;font-size:18px'>يمكنك إغلاق هذه الصفحة "
        "والعودة إلى البرنامج — ستُفتح معاينة الـ PDF تلقائياً.</p></body>")


def _editor_html(data: dict, doc_title: str) -> str:
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return _TEMPLATE.replace("__DATA__", payload).replace(
        "__TITLE__", doc_title)


_TEMPLATE = r"""<!doctype html>
<html lang="ar" dir="rtl"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
  :root{ --bronze:#8A6E4B; --deep:#6E543A; --bg:#F4F1EC; --panel:#fff;
         --border:#E2DACE; --ink:#2C2318; --muted:#8A7E68; }
  *{ box-sizing:border-box; }
  body{ font-family:"Segoe UI",Tahoma,"Traditional Arabic",sans-serif;
        background:var(--bg); color:var(--ink); margin:0; padding:0 0 90px; }
  header{ background:var(--bronze); color:#fff; padding:16px 22px;
          position:sticky; top:0; z-index:5; box-shadow:0 2px 8px #0002;
          display:flex; justify-content:space-between; align-items:center; }
  header h1{ font-size:19px; margin:0; }
  header .num{ font-size:14px; opacity:.9; }
  .wrap{ max-width:900px; margin:18px auto; padding:0 16px; }
  fieldset{ background:var(--panel); border:1px solid var(--border);
            border-radius:14px; padding:14px 16px; margin:0 0 16px; }
  legend{ color:var(--bronze); font-weight:700; font-size:15px; padding:0 8px; }
  label.row{ display:flex; align-items:center; gap:10px; margin:8px 0; }
  label.row > span{ width:170px; color:var(--ink); font-size:14px;
                    flex:none; text-align:left; }
  input, textarea, select{ flex:1; font:inherit; font-size:15px; color:var(--ink);
      background:#fff; border:1px solid var(--border); border-radius:9px;
      padding:9px 11px; direction:rtl; }
  input[readonly]{ background:#F2ECE3; color:var(--muted); }
  textarea{ min-height:70px; resize:vertical; line-height:1.7; }
  .prices{ display:grid; grid-template-columns:repeat(4,1fr); gap:10px; }
  .prices label{ display:flex; flex-direction:column; gap:4px; font-size:13px;
                 color:var(--muted); }
  .prices input{ text-align:center; font-weight:700; font-size:16px;
                 color:var(--ink); }
  .sec, .flt{ border:1px dashed var(--border); border-radius:10px;
              padding:10px; margin:10px 0; background:#FBF8F3; }
  .flt{ display:grid; grid-template-columns: 1.2fr 1fr 1fr 1fr auto; gap:8px;
        align-items:center; }
  .btn{ font:inherit; font-weight:700; border:none; border-radius:10px;
        padding:9px 16px; cursor:pointer; }
  .btn.add{ background:#EDE4D5; color:var(--deep); }
  .btn.del{ background:#F3D9D2; color:#B23A3A; padding:7px 11px; }
  footer{ position:fixed; bottom:0; inset-inline:0; background:#fff;
          border-top:1px solid var(--border); padding:12px 20px;
          display:flex; gap:12px; justify-content:flex-start;
          box-shadow:0 -2px 8px #0001; z-index:6; }
  .btn.save{ background:var(--bronze); color:#fff; font-size:16px;
             padding:11px 26px; }
  .btn.save:hover{ background:var(--deep); }
  small.hint{ color:var(--muted); }
  h3{ margin:6px 0; color:var(--deep); font-size:14px; }
</style></head>
<body>
<header>
  <h1>🕋 عرض سعر / برنامج الحج</h1>
  <span class="num" id="hnum"></span>
</header>
<div class="wrap" id="form"></div>
<footer>
  <button class="btn save" onclick="submitForm()">💾 حفظ ومعاينة PDF</button>
  <small class="hint">اكتب بحرّية — العربية تعمل هنا بشكل صحيح تماماً.</small>
</footer>

<script>
const Q = __DATA__;
const TITLES = ["السيد","السيدة","الشيخ","سعادة","معالي"];
const CURR = ["درهم","ريال","دولار","AED"];
const HOTELS = ["كونراد مكة – فندق خمسة نجوم فاخر مقابل للحرم.",
  "فيرمونت مكة (برج الساعة).","رافلز مكة.","سويس أوتيل المقام.",
  "هيلتون مكة.","أنجم مكة.","دار التوحيد إنتركونتيننتال."];
const el = (t,a={},kids=[])=>{const e=document.createElement(t);
  for(const k in a){ if(k==='class')e.className=a[k]; else if(k==='html')e.innerHTML=a[k];
    else e.setAttribute(k,a[k]); }
  (Array.isArray(kids)?kids:[kids]).forEach(c=>c&&e.append(c)); return e;};
function rowInput(key,label,val,type='text',ro=false){
  const inp = el('input',{id:'f_'+key, type:type, value:(val??'')});
  if(ro) inp.setAttribute('readonly','');
  return el('label',{class:'row'},[el('span',{},document.createTextNode(label)),inp]);
}
function rowArea(key,label,val){
  const ta=el('textarea',{id:'f_'+key}); ta.value=val??'';
  return el('label',{class:'row',style:'align-items:flex-start'},
    [el('span',{},document.createTextNode(label)),ta]);
}
function rowSelect(key,label,val,opts){
  const s=el('select',{id:'f_'+key});
  opts.forEach(o=>{const op=el('option',{value:o},document.createTextNode(o));
    if(o===val)op.setAttribute('selected',''); s.append(op);});
  return el('label',{class:'row'},[el('span',{},document.createTextNode(label)),s]);
}
function fs(legend,kids){ return el('fieldset',{},[el('legend',{},
  document.createTextNode(legend)), ...kids]); }

const root=document.getElementById('form');
document.getElementById('hnum').textContent = 'الرقم: '+(Q.number||'');

// بيانات العرض
root.append(fs('بيانات العرض',[
  rowInput('number','الرقم المرجعي',Q.number,'text',true),
  rowInput('date','التاريخ',Q.date,'date'),
  rowSelect('lang','لغة العرض',Q.lang||'ar',['ar','en']),
  rowSelect('addressed_title','لقب المستلِم',Q.addressed_title||'السيد',TITLES),
  rowInput('addressed_to','عناية (اسم المستلِم)',Q.addressed_to),
  rowInput('title','عنوان البرنامج',Q.title),
  rowInput('salutation','عبارة التحية',Q.salutation),
  rowInput('intro2','سطر التقديم',Q.intro2),
]));

// الفترة ومكة
root.append(fs('الفترة ومكة المُكرمة',[
  rowInput('period_hijri','الفترة (هجري)',Q.period_hijri),
  rowInput('period_greg','الفترة (ميلادي)',Q.period_greg),
  rowInput('makkah_title','عنوان قسم مكة',Q.makkah_title),
  rowInput('makkah_period','فترة مكة',Q.makkah_period),
  rowSelect('makkah_hotel','الفندق',Q.makkah_hotel,
    HOTELS.includes(Q.makkah_hotel)?HOTELS:[Q.makkah_hotel,...HOTELS]),
  rowInput('makkah_rooms','الغرف',Q.makkah_rooms),
  rowInput('makkah_meals','الوجبات',Q.makkah_meals),
]));

// البنود (أقسام)
const secBox=el('div',{id:'secs'});
(Q.sections||[]).forEach(s=>addSection(s[0],(s[1]||[]).join('\n')));
function addSection(title,bullets){
  const t=el('input',{type:'text',value:title||''});
  const ta=el('textarea'); ta.value=bullets||'';
  const del=el('button',{class:'btn del',type:'button'},document.createTextNode('🗑 حذف البند'));
  const box=el('div',{class:'sec'},[
    el('h3',{},document.createTextNode('عنوان البند:')), t,
    el('h3',{},document.createTextNode('النقاط (سطر لكل نقطة):')), ta, del]);
  box._t=t; box._ta=ta; del.onclick=()=>box.remove(); secBox.append(box);
}
root.append(fs('البنود (منى/عرفات/مزدلفة/المواصلات/الخدمات...)',[
  secBox, el('button',{class:'btn add',type:'button',
    onclick:''},document.createTextNode('➕ إضافة بند'))]));
root.lastChild.querySelector('.add').onclick=()=>addSection('',['']);

// الطيران
const fltBox=el('div',{id:'flts'});
(Q.flights||[]).forEach(r=>addFlight(r));
function addFlight(r){ r=r||[];
  const day=el('input',{type:'text',placeholder:'اليوم',value:r[0]||''});
  const car=el('input',{type:'text',placeholder:'الناقل',value:r[1]||''});
  const frm=el('input',{type:'text',placeholder:'من',value:r[3]||''});
  const to=el('input',{type:'text',placeholder:'إلى',value:r[5]||''});
  const del=el('button',{class:'btn del',type:'button'},document.createTextNode('🗑'));
  const box=el('div',{class:'flt'},[day,car,frm,to,del]);
  box._get=()=>[day.value,car.value,'',frm.value,'',to.value];
  del.onclick=()=>box.remove(); fltBox.append(box);
}
root.append(fs('الطيران',[
  rowInput('flights_title','عنوان القسم',Q.flights_title),
  rowInput('flight_intro','سطر مقدّمة الطيران',Q.flight_intro),
  el('div',{class:'flt',style:'background:none;border:none;color:#8A7E68;font-size:13px'},
    [el('span',{},document.createTextNode('اليوم')),el('span',{},document.createTextNode('الناقل')),
     el('span',{},document.createTextNode('من')),el('span',{},document.createTextNode('إلى')),el('span')]),
  fltBox,
  el('button',{class:'btn add',type:'button'},document.createTextNode('➕ إضافة رحلة'))]));
root.lastChild.querySelector('.add').onclick=()=>addFlight(['','SAUDIA','','','','']);

// الهدايا
root.append(fs('هدايا ومستلزمات الحاج',[
  rowInput('gifts_title','عنوان القسم',Q.gifts_title),
  rowArea('gifts_txt','النقاط (سطر لكل نقطة)',(Q.gifts||[]).join('\n')),
]));

// الأسعار
const pr=Q.prices||{};
const pg=el('div',{class:'prices'});
[['single','المفردة'],['double','الثنائية'],['triple','الثلاثية'],['quad','الرباعية']]
  .forEach(([k,l])=>{ const i=el('input',{id:'p_'+k,type:'text',value:pr[k]||''});
    pg.append(el('label',{},[el('span',{},document.createTextNode(l)),i])); });
root.append(fs('الأسعار (التكلفة للشخص حسب نوع الغرفة)',[
  rowInput('prices_title','عنوان القسم',Q.prices_title),
  rowInput('prices_caption','تسمية الجدول',Q.prices_caption),
  rowSelect('currency','العملة',Q.currency,CURR.includes(Q.currency)?CURR:[Q.currency,...CURR]),
  pg]));

// ملاحظات
root.append(fs('ملاحظات هامة',[
  rowInput('notes_title','عنوان القسم',Q.notes_title),
  rowArea('notes_txt','النقاط (سطر لكل نقطة)',(Q.notes||[]).join('\n')),
]));

// الخاتمة والتوقيع
root.append(fs('الخاتمة والتوقيع',[
  rowArea('closing','عبارة الختام',Q.closing),
  rowInput('manager_title','المسمّى الوظيفي',Q.manager_title),
  rowInput('manager','اسم المدير',Q.manager),
  rowInput('manager_phone','هاتف المدير',Q.manager_phone),
]));

const v = id => (document.getElementById(id)?.value ?? '');
const lines = id => v(id).split('\n').map(x=>x.trim()).filter(Boolean);
function submitForm(){
  const out = Object.assign({}, Q);
  ['number','date','lang','addressed_title','addressed_to','title','salutation',
   'intro2','period_hijri','period_greg','makkah_title','makkah_period',
   'makkah_hotel','makkah_rooms','makkah_meals','flights_title','flight_intro',
   'gifts_title','prices_title','prices_caption','currency','notes_title',
   'manager_title','manager','manager_phone']
    .forEach(k=> out[k]=v('f_'+k));
  out.sections = Array.from(secBox.children).map(b=>[b._t.value.trim(),
    b._ta.value.split('\n').map(x=>x.trim()).filter(Boolean)])
    .filter(s=>s[0]||s[1].length);
  out.flights = Array.from(fltBox.children).map(b=>b._get())
    .filter(r=>r.some(x=>x&&x.trim()));
  out.gifts = lines('f_gifts_txt');
  out.notes = lines('f_notes_txt');
  out.closing = v('f_closing').trim();
  out.prices = {single:v('p_single'),double:v('p_double'),
                triple:v('p_triple'),quad:v('p_quad')};
  fetch('/save',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify(out)}).then(()=>{ document.open();
      document.write('<meta charset=utf-8><body style="font-family:sans-serif;'
      +'direction:rtl;text-align:center;padding:60px;background:#F4F1EC;color:#2C2318">'
      +'<div style="font-size:52px">✅</div><h2>تمّ حفظ العرض</h2>'
      +'<p style="color:#6E543A">عُد إلى البرنامج — ستُفتح معاينة الـ PDF.</p>');
      document.close(); }).catch(e=>alert('تعذّر الحفظ: '+e));
}
</script>
</body></html>
"""
