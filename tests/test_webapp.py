# -*- coding: utf-8 -*-
"""اختبار نسخة الويب المحلية: الخادم وواجهة الـ API (تكامل حقيقي)."""
import sys, io
import json
import os as _os
import pathlib as _pl
import threading
import urllib.request as _u
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_ROOT = _os.path.dirname(_HERE)
_OUTDIR = _os.path.join(_HERE, "_out")
_os.makedirs(_OUTDIR, exist_ok=True)
sys.path.insert(0, _ROOT)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from hajj_app.webapp import WebState, make_server, TABLE_COLUMNS, FORM_FIELDS

DB = _pl.Path(_OUTDIR) / "web" / "hajjaj-web.json"
DB.parent.mkdir(parents=True, exist_ok=True)
for _p in (DB, DB.with_suffix(".bak")):
    _p.unlink(missing_ok=True)


print("=== WebState (منطق CRUD معزول) ===")
st = WebState(DB)
assert st.rows() == []
rec = st.add({"full_name_ar": "محمد الشامسي", "passport_number": "A1",
              "program_value": "20000", "paid_amount": "5000"})
assert rec.full_name_ar == "محمد الشامسي"
rows = st.rows()
assert len(rows) == 1
assert rows[0]["program_value"] == "20,000"          # طُبِّع المبلغ
assert rows[0]["remaining_amount"] == "15,000"        # المتبقّي محسوب
assert rows[0]["serial"] == "1"
assert st.update(0, {"hotel": "كونراد"}) and st.rows()[0]["hotel"] == "كونراد"
assert st.update(9, {"hotel": "x"}) is False          # فهرس خارج المدى
# الحفظ يبقى بين النُّسخ
st2 = WebState(DB)
assert st2.rows()[0]["full_name_ar"] == "محمد الشامسي"
assert st.delete(0) and st.rows() == []
# البيانات لغير القابل للتعديل تُتجاهَل
st.add({"remaining_amount": "999", "serial": "5", "full_name_ar": "ب"})
assert st.rows()[0]["remaining_amount"] == ""         # محسوب لا مُدخَل
print("  OK: إضافة/تعديل/حذف/حفظ + تطبيع + تجاهل غير القابل للتعديل")

print("\n=== الخادم وواجهة الـ API ===")
for _p in (DB, DB.with_suffix(".bak")):
    _p.unlink(missing_ok=True)
srv = make_server("127.0.0.1", 0, path=DB)
port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{port}"


def req(method, path, body=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    r = _u.Request(base + path, data=data, method=method,
                   headers={"Content-Type": "application/json"})
    try:
        resp = _u.urlopen(r, timeout=10)
        return resp.status, resp.read()
    except _u.HTTPError as exc:          # 4xx/5xx تُعاد كرمز لا كاستثناء
        return exc.code, exc.read()


try:
    # الصفحة الرئيسية
    s, b = req("GET", "/")
    assert s == 200 and "برنامج الحج" in b.decode("utf-8")
    # كشف فارغ
    s, b = req("GET", "/api/records")
    d = json.loads(b)
    assert d["rows"] == [] and len(d["meta"]["columns"]) == len(TABLE_COLUMNS)
    assert len(d["meta"]["form"]) == len(FORM_FIELDS)
    # إضافة
    s, b = req("POST", "/api/records",
               {"full_name_ar": "سالم النيادي", "passport_number": "B2",
                "program_value": "18000", "paid_amount": "18000"})
    assert s == 201, (s, b)
    s, b = req("GET", "/api/records")
    rows = json.loads(b)["rows"]
    assert len(rows) == 1 and rows[0]["remaining_amount"] == "0"
    # تعديل
    s, _b = req("PUT", "/api/records/0", {"hotel": "الصفوة"})
    assert s == 200
    assert json.loads(req("GET", "/api/records")[1])["rows"][0]["hotel"] == "الصفوة"
    # تصدير إكسل وPDF
    s, b = req("GET", "/api/export/excel")
    assert s == 200 and b[:2] == b"PK", s
    s, b = req("GET", "/api/export/pdf")
    assert s == 200 and b[:5] == b"%PDF-", s
    # حذف
    s, _b = req("DELETE", "/api/records/0")
    assert s == 200
    assert json.loads(req("GET", "/api/records")[1])["rows"] == []
    # مسار غير معروف
    s, _b = req("GET", "/api/nope")
    assert s == 404
finally:
    srv.shutdown()

print(f"  OK: الخادم يخدم الصفحة والـ API والتصدير (منفذ {port})")
print("\n*** WEB APP TESTS PASSED ***")
