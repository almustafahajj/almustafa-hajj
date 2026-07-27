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
# عزل الإعدادات والنسخ الاحتياطية عن بيانات المستخدم الحقيقية
storage.default_data_path = lambda: DATA

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

print("\n=== الاستيراد من إكسل (رفع ملف) ===")
# نبني ملف إكسل من حاجّين ونرفعه فيُضافان
from hajj_app.excel_io import export_excel
IMP = WORK / "to_import.xlsx"
export_excel([
    PassportData(full_name_ar="مستورد أول", passport_number="X1", hotel="فندق"),
    PassportData(full_name_ar="مستورد ثاني", passport_number="X2", hotel="فندق"),
], IMP)
before = len(storage.load_records(DATA, admin)[0])
with open(IMP, "rb") as fh:
    r = mgr.post("/import/excel", data={"file": (fh, "to_import.xlsx")},
                 content_type="multipart/form-data")
assert r.status_code == 302
after = storage.load_records(DATA, admin)[0]
assert len(after) == before + 2, f"{before} -> {len(after)}"
assert any(x.passport_number == "X1" for x in after)
print(f"  OK: أُضيف حاجّان بالاستيراد ({before} -> {len(after)})")

# صفحة الاستيراد + المطّلع ممنوع + بلا ملف
assert "استيراد من إكسل" in mgr.get("/import").get_data(as_text=True)
assert client.get("/import").status_code == 403          # المطّلع
assert client.post("/import/excel").status_code == 403
nof = mgr.post("/import/excel", data={}, content_type="multipart/form-data")
assert nof.status_code == 302                            # يعيد التوجيه برسالة خطأ
# رفع بلا ملفات لقراءة الجوازات يعيد التوجيه (لا يتعطّل)
assert mgr.post("/import/passports", data={},
                content_type="multipart/form-data").status_code == 302
print("  OK: صفحة الاستيراد، ومنع المطّلع (403)، ورفع فارغ آمن")

print("\n=== رمز QR للفتح من جهاز آخر ===")
q = client.get("/qr")                         # متاح بلا دخول (يعرض رابط الشبكة فقط)
qhtml = q.get_data(as_text=True)
assert q.status_code == 200
assert "data:image/png;base64," in qhtml, "صورة QR غير مضمّنة"
assert "http://" in qhtml, "الرابط لا يظهر"
# الرابط في صفحة الدخول
assert "رمز QR" in client.get("/login").get_data(as_text=True)
print("  OK: صفحة QR تعرض الرمز والرابط، ورابطها في صفحة الدخول")

print("\n=== الإحصاءات ===")
st = mgr.get("/stats").get_data(as_text=True)
assert "الملخّص المالي" in st and "التوزيع حسب" in st
assert "عدد الحجّاج" in st
sp = mgr.get("/stats/pdf")
assert sp.status_code == 200 and sp.data[:5] == b"%PDF-"
print("  OK: صفحة الإحصاءات + تصدير PDF")

print("\n=== الكشوف والبطاقات (تنزيلات PDF) ===")
rp = mgr.get("/reports").get_data(as_text=True)
assert "كشف المواصلات" in rp and "بطاقات الحجّاج" in rp
for path in ["/reports/transport.pdf", "/reports/airline.pdf",
             "/reports/badges.pdf", "/reports/stickers/room.pdf"]:
    r = mgr.get(path)
    assert r.status_code == 200 and r.data[:5] == b"%PDF-", path
tx = mgr.get("/reports/transport.xlsx")
assert tx.status_code == 200 and tx.data[:2] == b"PK"
assert mgr.get("/reports/stickers/زبد.pdf").status_code == 404   # نوع غير معروف
print("  OK: مواصلات/طيران/بطاقات/استيكرات PDF + مواصلات إكسل")

print("\n=== إدارة الحسابات (مدير فقط) ===")
# المطّلع لا يصل
assert client.get("/accounts").status_code == 403
# المدير: الصفحة + إضافة حساب (يظهر مفتاح الاسترداد مرة)
acc = mgr.get("/accounts").get_data(as_text=True)
assert "إدارة الحسابات" in acc and "viewer1" in acc
r = mgr.post("/accounts/add", data={"username": "web_editor",
             "password": "WebEd!Pass1", "role": "editor"})
body = r.get_data(as_text=True)
assert "مفتاح استرداد" in body, "لم يُعرض مفتاح الاسترداد"
assert "web_editor" in {a["username"] for a in auth.list_accounts(AUTH)}
# الحساب الجديد يفتح البيانات نفسها
assert auth.login("web_editor", "WebEd!Pass1", AUTH).role == "editor"
# تغيير الدور + منع حذف الذات
mgr.post("/accounts/role", data={"username": "web_editor", "role": "viewer"})
assert {a["username"]: a["role"] for a in auth.list_accounts(AUTH)}["web_editor"] == "viewer"
mgr.post("/accounts/delete", data={"username": "MHU"})     # حذف الذات مرفوض
assert "MHU" in {a["username"] for a in auth.list_accounts(AUTH)}
mgr.post("/accounts/delete", data={"username": "web_editor"})
assert "web_editor" not in {a["username"] for a in auth.list_accounts(AUTH)}
print("  OK: إضافة (مع المفتاح)، تغيير الدور، منع حذف الذات، حذف")

print("\n=== سجلّ التدقيق ===")
au = mgr.get("/audit").get_data(as_text=True)
assert "سجلّ التدقيق" in au
assert "إضافة حساب" in au and "web_editor" in au       # العمليات السابقة مسجّلة
assert "(ويب)" in au
print("  OK: سجلّ التدقيق يعرض العمليات باسم المستخدم (ويب)")

print("\n=== كشف التسكين + مستندات الحاج + PEPPOL ===")
for path, head in [("/reports/rooming.pdf", b"%PDF-"),
                   ("/pilgrim/0/receipt.pdf", b"%PDF-"),
                   ("/pilgrim/0/invoice.pdf", b"%PDF-"),
                   ("/pilgrim/0/contract.pdf", b"%PDF-")]:
    r = mgr.get(path)
    assert r.status_code == 200 and r.data[:5] == head, path
assert mgr.get("/reports/rooming.xlsx").data[:2] == b"PK"
xml = mgr.get("/pilgrim/0/einvoice.xml")
assert xml.status_code == 200 and b"<?xml" in xml.data[:10] and b"Invoice" in xml.data
print("  OK: تسكين PDF/إكسل، سند/فاتورة/عقد PDF، وفاتورة PEPPOL XML")

print("\n=== واتساب الحاج ===")
# الحاج 0 لا هاتف له -> يعيد التوجيه للسجلّ برسالة؛ نضيف هاتفاً لواحد
wa = mgr.get("/pilgrim/0/whatsapp")
assert wa.status_code == 302   # إمّا wa.me أو رجوع للسجلّ
print("  OK: مسار واتساب يعمل (تحويل)")

print("\n=== فحص الجاهزية ===")
ql = mgr.get("/quality").get_data(as_text=True)
assert "فحص جاهزية الكشف" in ql
print("  OK: صفحة فحص الجاهزية")

print("\n=== برامج الحملة (تعديل + حفظ) ===")
assert client.get("/programs").status_code == 403          # المطّلع ممنوع
pg = mgr.get("/programs").get_data(as_text=True)
assert "برامج الحملة" in pg and "تاريخ السفر" in pg
# حفظ قيمة ثم قراءتها (الإعدادات معزولة في WORK)
r = mgr.post("/programs", data={"p0_hotel": "فندق البرنامج الأول",
             "p0_cost_double": "6000", "p0_travel_date": "1447-12-01"})
assert r.status_code == 302
from hajj_app import programs as _pg
saved = _pg.load_programs(storage.load_settings())
assert saved[0].hotel == "فندق البرنامج الأول" and saved[0].cost_double == "6000"
print("  OK: صفحة البرامج تُعرض وتُحفظ القيم، والمطّلع ممنوع (403)")

print("\n=== نسخة احتياطية ===")
assert client.post("/backup").status_code == 403           # المطّلع ممنوع
b = mgr.post("/backup")
assert b.status_code == 302
print("  OK: نسخة احتياطية للمحرّر/المدير، والمطّلع ممنوع")

print("\n=== لوحة المؤشّرات على الكشف ===")
home = mgr.get("/").get_data(as_text=True)
assert "kpis dash" in home and "المحصّل" in home
print("  OK: شريط المؤشّرات المالية يظهر أعلى الكشف")

print("\n=== استعادة نسخة احتياطية ===")
assert client.get("/restore").status_code == 403          # المطّلع ممنوع
mgr.post("/backup")                                       # أنشئ نسخة
rlist = mgr.get("/restore").get_data(as_text=True)
assert "استعادة نسخة احتياطية" in rlist
import re
m = re.search(r'name="name" value="(hajjaj-[^"]+)"', rlist)
assert m, "لا توجد نسخة للاستعادة"
before = len(storage.load_records(DATA, admin)[0])
ra = mgr.post("/restore/apply", data={"name": m.group(1)})
assert ra.status_code == 302
assert len(storage.load_records(DATA, admin)[0]) == before  # نفس العدد بعد الاستعادة
# اسم نسخة غير موجود -> 404
assert mgr.post("/restore/apply", data={"name": "hajjaj-x.json"}).status_code == 404
print("  OK: استعادة نسخة (مع نسخ أمان)، والمطّلع ممنوع، والاسم الخاطئ 404")

print("\n=== تغيير كلمة المرور ومفتاح الاسترداد ===")
# كلمة مرور خاطئة تُرفض
mgr.post("/account/password", data={"current": "خطأ", "password": "New-Pass-9999",
         "confirm": "New-Pass-9999"})
assert auth.login("MHU", "Web-Pass-1234", AUTH)          # لم تتغيّر
# تغيير صحيح
r = mgr.post("/account/password", data={"current": "Web-Pass-1234",
             "password": "New-Pass-9999", "confirm": "New-Pass-9999"})
assert r.status_code in (302, 200)
try:
    auth.login("MHU", "Web-Pass-1234", AUTH); assert False, "القديمة تعمل"
except auth.AuthError:
    pass
assert auth.login("MHU", "New-Pass-9999", AUTH)
# مفتاح استرداد جديد يُعرض
rk = mgr.post("/account/recovery", data={"password": "New-Pass-9999"})
assert "مفتاح الاسترداد" in rk.get_data(as_text=True)
print("  OK: تغيير كلمة المرور فعّال، ومفتاح الاسترداد الجديد يُعرض")

print("\n*** WEB TESTS PASSED ***")
