"""محرّر مستندات عام عبر المتصفّح — يُولّد نموذجاً من «مخطّط حقول» لأيّ مستند
(فاتورة، سند قبض، عقد، عرض سعر…)، فيحرّر المستخدم بالعربية بلا تبعثر ثم يحفظ.

يشترك مع :mod:`hajj_app.webquote` في الفكرة: صفحة HTML محلّية + خادم مؤقّت على
127.0.0.1 يعيد البيانات المُدخَلة إلى البرنامج ليولّد الـ PDF. الفرق أنّ النموذج
هنا **مُوجَّه بمخطّط** (schema) لا مكتوب يدوياً لكلّ مستند.

مخطّط الحقول ``schema`` قائمة أقسام، كل قسم إمّا:
* حقول: ``{"legend": "...", "fields": [ {field}, ... ]}``
* جدول متكرّر: ``{"legend": "...", "table": "key",
                  "columns": [ {"key","label","type","options"}, ... ]}``

و``field`` قاموس: ``{"key","label","type","options","ro"}`` حيث ``type`` واحد من:
``text`` (افتراضي) / ``area`` (نصّ متعدّد الأسطر) / ``lines`` (نصّ→قائمة أسطر) /
``date`` / ``select`` (مع ``options``) / ``money``.
"""

from __future__ import annotations

import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def serve_doc_editor(data: dict, schema: list, doc_title: str = "مستند",
                     header_icon: str = "📄", timeout: int = 1800) -> dict | None:
    """يفتح المحرّر في المتصفّح ويحجب حتى «حفظ» (أو المهلة)؛ يعيد البيانات أو ``None``.

    يُستدعى من خيطٍ خلفي (لا من خيط الواجهة) لأنه يحجب."""
    box: dict = {}
    done = threading.Event()
    html = _doc_html(data, schema, doc_title, header_icon).encode("utf-8")

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


_BACK_LINK = ('<a href="__URL__" style="color:#fff;background:#0003;'
              'padding:7px 14px;border-radius:9px;text-decoration:none;'
              'font-weight:700">↩ رجوع</a>')


def _doc_html(data: dict, schema: list, doc_title: str, header_icon: str,
              submit_action: str | None = None,
              back_url: str | None = None) -> str:
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    sch = json.dumps(schema, ensure_ascii=False).replace("</", "<\\/")
    back = _BACK_LINK.replace("__URL__", back_url) if back_url else ""
    return (_TEMPLATE.replace("__DATA__", payload)
            .replace("__SCHEMA__", sch)
            .replace("__TITLE__", doc_title)
            .replace("__ICON__", header_icon)
            .replace("__SUBMIT_ACTION__",
                     submit_action or _SUBMIT_ACTION_DESKTOP)
            .replace("__BACK__", back))


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
  label.row > span{ width:190px; color:var(--ink); font-size:14px;
                    flex:none; text-align:left; }
  input, textarea, select{ flex:1; font:inherit; font-size:15px; color:var(--ink);
      background:#fff; border:1px solid var(--border); border-radius:9px;
      padding:9px 11px; direction:rtl; }
  input[readonly]{ background:#F2ECE3; color:var(--muted); }
  textarea{ min-height:70px; resize:vertical; line-height:1.7; }
  .tbl{ border:1px dashed var(--border); border-radius:10px; padding:10px;
        margin:8px 0; background:#FBF8F3; overflow-x:auto; }
  .trow{ display:flex; gap:8px; align-items:center; margin:6px 0; }
  .trow input, .trow select{ min-width:90px; }
  .thead{ color:var(--muted); font-size:13px; font-weight:700; }
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
</style></head>
<body>
<header>
  <h1>__ICON__ __TITLE__</h1>
  <div style="display:flex;align-items:center;gap:14px">
    <span class="num" id="hnum"></span>
    __BACK__
  </div>
</header>
<div class="wrap" id="form"></div>
<footer>
  <button class="btn save" onclick="submitForm()">💾 حفظ ومعاينة PDF</button>
  <small class="hint">اكتب بحرّية — العربية تعمل هنا بشكل صحيح تماماً.</small>
</footer>
<script>
const D = __DATA__;
const SCHEMA = __SCHEMA__;
const txt = s => document.createTextNode(s==null?'':String(s));
const el = (t,a={},kids=[])=>{const e=document.createElement(t);
  for(const k in a){ if(k==='class')e.className=a[k];
    else if(k==='html')e.innerHTML=a[k]; else e.setAttribute(k,a[k]); }
  (Array.isArray(kids)?kids:[kids]).forEach(c=>c&&e.append(c)); return e;};

function field(f){
  const key=f.key, type=f.type||'text', ro=!!f.ro;
  let val = D[key];
  if(type==='lines' && Array.isArray(val)) val = val.join('\n');
  let inp;
  if(type==='bool'){
    inp = el('input',{id:'f_'+key, type:'checkbox'});
    inp.style.flex='none'; inp.style.width='20px'; inp.style.height='20px';
    if(val) inp.setAttribute('checked','');
    const lab0 = el('label',{class:'row'},[el('span',{},txt(f.label)), inp]);
    return lab0;
  }
  if(type==='area' || type==='lines'){
    inp = el('textarea',{id:'f_'+key}); inp.value = val==null?'':val;
  } else if(type==='select'){
    inp = el('select',{id:'f_'+key});
    let opts = (f.options||[]).slice();
    if(val!=null && val!=='' && !opts.includes(val)) opts = [val,...opts];
    opts.forEach(o=>{const op=el('option',{value:o},txt(o));
      if(o===val)op.setAttribute('selected',''); inp.append(op);});
  } else {
    inp = el('input',{id:'f_'+key, type:(type==='date'?'date':'text'),
      value:(val==null?'':val)});
    if(ro) inp.setAttribute('readonly','');
  }
  const lab = el('label',{class:'row'},[el('span',{},txt(f.label)), inp]);
  if(type==='area'||type==='lines') lab.style.alignItems='flex-start';
  return lab;
}

function tableSection(sec){
  const cols = sec.columns||[];
  const box = el('div',{class:'tbl'});
  const head = el('div',{class:'trow thead'});
  cols.forEach(c=>head.append(el('span',{style:'flex:1'},txt(c.label))));
  head.append(el('span',{style:'width:40px'}));
  box.append(head);
  const rowsBox = el('div',{});
  box.append(rowsBox);
  function addRow(vals){
    vals = vals||[];
    const r = el('div',{class:'trow'});
    const cells = cols.map((c,i)=>{
      let w;
      if((c.type||'')==='select'){
        w = el('select',{style:'flex:1'});
        let opts=(c.options||[]).slice();
        if(vals[i]!=null && vals[i]!=='' && !opts.includes(vals[i])) opts=[vals[i],...opts];
        opts.forEach(o=>{const op=el('option',{value:o},txt(o));
          if(o===vals[i])op.setAttribute('selected',''); w.append(op);});
      } else if((c.type||'')==='date'){
        w = el('input',{type:'date',style:'flex:1',value:(vals[i]==null?'':vals[i])});
      } else {
        w = el('input',{type:'text',style:'flex:1',value:(vals[i]==null?'':vals[i])});
      }
      r.append(w); return w;
    });
    const del = el('button',{class:'btn del',type:'button'},txt('🗑'));
    del.onclick=()=>r.remove(); r.append(del);
    r._get=()=>cells.map(w=>w.value);
    rowsBox.append(r);
  }
  (D[sec.table]||[]).forEach(row=>addRow(row));
  const add = el('button',{class:'btn add',type:'button'},txt('➕ إضافة صف'));
  add.onclick=()=>addRow(cols.map(()=> ''));
  box._rows=rowsBox; box._key=sec.table;
  return {node: el('div',{},[box, add]), box};
}

const root=document.getElementById('form');
document.getElementById('hnum').textContent = D.number ? ('الرقم: '+D.number) : '';
const _tables=[];
SCHEMA.forEach(sec=>{
  const kids=[];
  if(sec.table){
    const ts=tableSection(sec); kids.push(ts.node); _tables.push(ts.box);
  } else {
    (sec.fields||[]).forEach(f=>kids.push(field(f)));
  }
  root.append(el('fieldset',{},[el('legend',{},txt(sec.legend)), ...kids]));
});

function submitForm(){
  const out = Object.assign({}, D);
  SCHEMA.forEach(sec=>{
    if(sec.table) return;
    (sec.fields||[]).forEach(f=>{
      const e=document.getElementById('f_'+f.key); if(!e) return;
      if((f.type||'')==='bool') out[f.key]=e.checked;
      else if((f.type||'')==='lines')
        out[f.key]=e.value.split('\n').map(x=>x.trim()).filter(Boolean);
      else out[f.key]=e.value;
    });
  });
  _tables.forEach(b=>{
    out[b._key]=Array.from(b._rows.children).map(r=>r._get())
      .filter(row=>row.some(x=>x&&String(x).trim()));
  });
  __SUBMIT_ACTION__
}
</script>
</body></html>
"""


# سلوك الحفظ في سطح المكتب: يرسل للخادم المحلّي ثم يعرض رسالة نجاح.
_SUBMIT_ACTION_DESKTOP = r"""fetch('/save',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify(out)}).then(()=>{ document.open();
      document.write('<meta charset=utf-8><body style="font-family:sans-serif;'
      +'direction:rtl;text-align:center;padding:60px;background:#F4F1EC;color:#2C2318">'
      +'<div style="font-size:52px">✅</div><h2>تمّ الحفظ</h2>'
      +'<p style="color:#6E543A">عُد إلى البرنامج — ستُفتح معاينة الـ PDF.</p>');
      document.close(); }).catch(e=>alert('تعذّر الحفظ: '+e));"""


def web_submit_action(save_url: str) -> str:
    """سلوك الحفظ في الويب: يرسل البيانات فيعيد الخادم PDF يُفتح مباشرةً."""
    return (
        "fetch('" + save_url + "',{method:'POST',"
        "headers:{'Content-Type':'application/json'},body:JSON.stringify(out)})"
        ".then(r=>{if(!r.ok)throw new Error('HTTP '+r.status);return r.blob();})"
        ".then(b=>{window.location=URL.createObjectURL(b);})"
        ".catch(e=>alert('تعذّر إنشاء PDF: '+e));")
