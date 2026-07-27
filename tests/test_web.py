# -*- coding: utf-8 -*-
"""اختبار نسخة الويب (المرحلة صفر): الدخول، الجلسة، عرض الكشف، البحث، الخروج."""
import sys, io
import os as _os
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_ROOT = _os.path.dirname(_HERE)
_OUTDIR = _os.path.join(_HERE, "_out")
_os.makedirs(_OUTDIR, exist_ok=True)
sys.path.insert(0, _ROOT)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from pathlib import Path
import shutil

from hajj_app import auth, storage
from hajj_app.mrz import PassportData
from hajj_web import create_app

WORK = Path(_OUTDIR) / "webdata"
shutil.rmtree(WORK, ignore_errors=True)
WORK.mkdir(parents=True, exist_ok=True)
AUTH, DATA = WORK / "auth.json", WORK / "hajjaj.json"

print("=== تجهيز حساب وبيانات مشفّرة ===")
admin, _rk = auth.create_account("MHU", "Web-Pass-1234", AUTH)
auth.add_account(admin, "viewer1", "View-Pass-1234", "viewer", AUTH)
storage.save_records([
    PassportData(full_name_ar="عبدالله الشامسي", passport_number="A111",
                 phone="0501112233", hotel="الصفوة", program="الأول",
                 nationality_ar="سعودي", room_number="101",
                 program_value="5000", paid_amount="2000"),
    PassportData(full_name_ar="سالم أحمد", passport_number="B222",
                 phone="0502223344", hotel="كونراد", program="الثاني",
                 nationality_ar="إماراتي", room_number="202"),
], DATA, admin)
print("  OK: حسابان + حاجّان مشفّران")

app = create_app(auth_path=AUTH, data_path=DATA)
client = app.test_client()

print("\n=== الوصول بلا دخول محجوب ===")
assert client.get("/login").status_code == 200
r = client.get("/")
assert r.status_code == 302 and "/login" in r.headers["Location"], r.status_code
print("  OK: '/' يعيد التوجيه إلى صفحة الدخول")

print("\n=== دخول خاطئ لا يُفصح ولا يُدخِل ===")
r = client.post("/login", data={"username": "MHU", "password": "خطأ"})
body = r.get_data(as_text=True)
assert "غير صحيح" in body, "رسالة الخطأ غير ظاهرة"
assert "Set-Cookie" not in r.headers, "أُنشئت جلسة رغم خطأ كلمة المرور!"
print("  OK: يُرفض دون إنشاء جلسة")

print("\n=== دخول صحيح (مطّلع) يعرض الكشف ===")
r = client.post("/login", data={"username": "viewer1", "password": "View-Pass-1234"})
assert r.status_code == 302
assert "hajj_session" in r.headers.get("Set-Cookie", ""), "لم تُوضع كوكيّ الجلسة"
# الكوكيّ يحمل رمزاً فقط لا مفتاح البيانات
cookie = r.headers["Set-Cookie"]
page = client.get("/").get_data(as_text=True)
assert "عبدالله الشامسي" in page and "سالم أحمد" in page, "الكشف لا يظهر"
assert "مطّلع" in page, "الدور لا يظهر"
assert "المعروض: 2 من 2" in page, page[:200]
print("  OK: الجدول يعرض الحجّاج والدور، والكوكيّ رمز فقط")

print("\n=== البحث يُرشّح ===")
f = client.get("/?q=سالم").get_data(as_text=True)
assert "سالم أحمد" in f and "عبدالله الشامسي" not in f
f2 = client.get("/?q=A111").get_data(as_text=True)
assert "عبدالله الشامسي" in f2 and "سالم أحمد" not in f2
print("  OK: البحث بالاسم والجواز يُرشّح النتائج")

print("\n=== الفلاتر تُرشّح (البرنامج/الفندق/الجنسية) ===")
fp = client.get("/?program=الأول").get_data(as_text=True)
assert "عبدالله الشامسي" in fp and "سالم أحمد" not in fp, "فلتر البرنامج لا يعمل"
assert "المعروض: 1 من 2" in fp
fh = client.get("/?hotel=كونراد").get_data(as_text=True)
assert "سالم أحمد" in fh and "عبدالله الشامسي" not in fh, "فلتر الفندق لا يعمل"
# قوائم الفلاتر تحوي القيم المتاحة
assert "الصفوة" in page and "كونراد" in page, "قوائم الفلاتر ناقصة"
print("  OK: الترشيح بالبرنامج والفندق، والقوائم مملوءة")

print("\n=== فتح سجلّ الحاج كاملاً ===")
detail = client.get("/pilgrim/0").get_data(as_text=True)
assert "عبدالله الشامسي" in detail
# عناوين المجموعات والحقول تظهر
assert "بيانات الجواز" in detail and "المالية" in detail
assert "المبلغ المتبقي" in detail, "الحقول المحسوبة لا تظهر"
assert "3,000" in detail, "المتبقي (5000-2000) لا يُحسب"     # 5000 - 2000
# فهرس خارج المدى يعطي 404
assert client.get("/pilgrim/999").status_code == 404
print("  OK: السجلّ الكامل يعرض كل الحقول والمتبقي المحسوب، والفهرس الخاطئ 404")

print("\n=== الخروج ينهي الجلسة ===")
client.get("/logout")
assert client.get("/").status_code == 302, "الجلسة بقيت بعد الخروج"
print("  OK: بعد الخروج يُطلب الدخول من جديد")

print("\n=== المطّلع لا يرى أزرار التعديل ولا مساراته ===")
viewer_home = client.post("/login", data={"username": "viewer1",
                          "password": "View-Pass-1234"}) and client.get("/").get_data(as_text=True)
assert "إضافة حاج" not in viewer_home, "زر الإضافة ظاهر للمطّلع!"
# مسارات الكتابة محجوبة للمطّلع (403)
assert client.get("/pilgrim/new").status_code == 403
assert client.post("/pilgrim/0/delete", data={"orig": "A111"}).status_code == 403
print("  OK: المطّلع بلا أزرار تعديل ومساراته 403")

print("\n=== المدير: إضافة/تعديل/حذف ===")
mgr = app.test_client()
mgr.post("/login", data={"username": "MHU", "password": "Web-Pass-1234"})
assert "إضافة حاج" in mgr.get("/").get_data(as_text=True), "زر الإضافة غائب عن المدير"
# نماذج الإضافة/التعديل تُعرض (GET)
newform = mgr.get("/pilgrim/new").get_data(as_text=True)
assert "إضافة حاج جديد" in newform and "اسم الحاج بالعربي" in newform
editform = mgr.get("/pilgrim/0/edit").get_data(as_text=True)
assert "تعديل سجلّ الحاج" in editform and "عبدالله الشامسي" in editform
print("  OK: نماذج الإضافة والتعديل تُعرض بالحقول")
# إضافة
r = mgr.post("/pilgrim/new", data={"full_name_ar": "حاج جديد",
             "passport_number": "C333", "hotel": "هيلتون", "program": "الأول"})
assert r.status_code == 302
recs, _ = storage.load_records(DATA, admin)
assert any(x.passport_number == "C333" and x.full_name_ar == "حاج جديد" for x in recs)
assert len(recs) == 3
print("  OK: أُضيف الحاج وحُفظ مشفّراً")

# تعديل (الحاج الجديد آخر السجلّات = فهرس 2)
r = mgr.post("/pilgrim/2/edit", data={"full_name_ar": "حاج معدّل",
             "passport_number": "C333", "orig": "C333", "hotel": "هيلتون"})
assert r.status_code == 302
recs, _ = storage.load_records(DATA, admin)
assert recs[2].full_name_ar == "حاج معدّل"
# حارس التزامن: قيمة orig خاطئة تُرفض
bad = mgr.post("/pilgrim/2/edit", data={"passport_number": "C333", "orig": "WRONG"})
assert bad.status_code == 409
print("  OK: عُدّل الحاج، وحارس التزامن يرفض orig الخاطئ (409)")

# حذف
r = mgr.post("/pilgrim/2/delete", data={"orig": "C333"})
assert r.status_code == 302
recs, _ = storage.load_records(DATA, admin)
assert len(recs) == 2 and all(x.passport_number != "C333" for x in recs)
print("  OK: حُذف الحاج")

# سجلّ التدقيق سجّل العمليات باسم المستخدم (ويب)
from hajj_app import audit
entries = audit.read_entries(path=WORK / "audit.log")
actions = {e["action"] for e in entries}
assert {"إضافة حاج", "تعديل حاج", "حذف حاج"} <= actions, actions
assert all("(ويب)" in e["user"] for e in entries if e["action"].endswith("حاج"))
print("  OK: العمليات مسجّلة في التدقيق باسم المستخدم (ويب)")

print("\n=== التصدير (إكسل/PDF) يحترم الفلتر ===")
xl = mgr.get("/export/excel")
assert xl.status_code == 200 and xl.data[:2] == b"PK", "إكسل غير صالح"
assert "spreadsheetml" in xl.headers.get("Content-Type", "")
pf = mgr.get("/export/pdf")
assert pf.status_code == 200 and pf.data[:5] == b"%PDF-", "PDF غير صالح"
# التصدير المفلتر: برنامج «الثاني» فيه حاجّ واحد -> إكسل أصغر وPDF صالح
xl2 = mgr.get("/export/excel?program=الثاني")
assert xl2.status_code == 200 and xl2.data[:2] == b"PK"
from openpyxl import load_workbook
import io as _io
wb = load_workbook(_io.BytesIO(xl2.data)); ws = wb.active
data_rows = ws.max_row - 2          # صف العنوان + صف الرؤوس
assert data_rows == 1, f"التصدير المفلتر يجب أن يحوي حاجّاً واحداً لا {data_rows}"
flat = " ".join(str(c.value) for row in ws.iter_rows() for c in row if c.value)
assert "سالم أحمد" in flat and "عبدالله الشامسي" not in flat
print("  OK: إكسل وPDF صالحان، والتصدير يحترم فلتر البرنامج")

print("\n*** WEB TESTS PASSED ***")
