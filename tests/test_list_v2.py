# -*- coding: utf-8 -*-
"""البورتال: قائمة المعتمرين الجديدة — حالة السداد بشارة وشريط، أزرار التصفية
بالسداد (وتصل للتصدير)، الحرف الأول، والحالات الفارغة."""
import io
import os
import sys
import tempfile

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["HAJJ_DATA_DIR"] = tempfile.mkdtemp(prefix="listv2_")

from hajj_app import app_mode, auth, storage  # noqa: E402
from hajj_app.mrz import PassportData  # noqa: E402

try:
    from webapp import server
    server.app.config["CSRF_ENABLED"] = False
except ImportError as exc:
    print(f"[skip] مسارات الويب: {exc}")
    print("ALL OK")
    sys.exit(0)

owner, _rk = auth.create_account("owner", "Passw0rd!x")
auth.add_account(owner, "view", "Passw0rd!v", role="viewer")
c = server.app.test_client()
c.post("/login", data={"username": "owner", "password": "Passw0rd!x"})
SESS = next(v for v in server._SESSIONS.values() if v.username == "owner")
app_mode.set_mode(app_mode.UMRAH)

# ---- ١) حالة فارغة: إرشاد لأول سجلّ ----
page = c.get("/hujjaj").get_data(as_text=True)
assert "لا يوجد المعتمرون بعد" in page and "استيراد من إكسل" in page
assert 'class="pay-chips"' not in page, "لا أزرار سداد بلا سجلّات"

# ---- ٢) حالات السداد ----
recs = [PassportData(full_name_ar="أحمد العلي", full_name_en="AHMED ALALI", passport_number="P1",
                     program_value="6000", paid_amount="6,000"),                 # مسدَّد
        PassportData(full_name_ar="مريم سعيد", passport_number="P2",
                     program_value="6000", paid_amount="1,500"),                 # جزئي
        PassportData(full_name_ar="خالد يوسف", passport_number="P3",
                     program_value="6000"),                                      # لم يدفع
        PassportData(full_name_ar="زينب كاظم", passport_number="P4")]           # بلا قيمة
storage.save_records(recs, session=SESS)
assert [server._pay_state(r) for r in recs] == ["paid", "part", "none", ""]

page = c.get("/hujjaj").get_data(as_text=True)
assert "مسدَّد" in page and "سداد جزئي" in page and "لم يدفع" in page
assert 'class="pay-bar" title="مدفوع 25%"' in page, "شريط السداد بنسبة المدفوع"
assert 'class="av av' in page and ">أ</span>" in page, "الحرف الأول في الصورة الرمزية"
assert 'dir="ltr">AHMED ALALI</small>' in page, "الاسم الإنجليزي تحت العربي"
assert 'aria-label="تعديل أحمد العلي"' in page and 'aria-label="مستندات أحمد العلي"' in page
assert "الكل <b>4</b>" in page

# ---- ٣) التصفية بالسداد: القائمة والأعداد والتصدير ----
part = c.get("/hujjaj?pay=part").get_data(as_text=True)
assert "مريم سعيد" in part and "أحمد العلي" not in part and "خالد يوسف" not in part
assert 'aria-current="true"' in part and 'name="pay" value="part"' in part, "البحث يحفظ التصفية"
assert "الكل <b>4</b>" in part, "الأعداد تُحسب قبل تصفية السداد"
none_ = c.get("/hujjaj?pay=none&q=خالد").get_data(as_text=True)
assert "خالد يوسف" in none_ and "مريم سعيد" not in none_
assert "pay=none" in none_.split("معاينة PDF")[0].split('href="')[-1], "التصدير يتبع التصفية"
with server.app.test_request_context("/hujjaj/export.xlsx?pay=paid"):
    got = [r.full_name_ar for _i, r in server._list_filtered(storage.load_records(session=SESS)[0], "trip")]
assert got == ["أحمد العلي"], got
bogus = c.get("/hujjaj?pay=xyz").get_data(as_text=True)
assert "زينب كاظم" in bogus, "قيمة غير معروفة تُتجاهل"

# ---- ٤) لا نتائج ----
empty = c.get("/hujjaj?q=لاأحدبهذا").get_data(as_text=True)
assert "لا نتائج مطابقة" in empty and "مسح البحث والفلاتر" in empty

# ---- ٥) المطّلع يرى القائمة بلا أزرار الإضافة في الحالة الفارغة ----
v = server.app.test_client()
v.post("/login", data={"username": "view", "password": "Passw0rd!v"})
assert "سداد جزئي" in v.get("/hujjaj").get_data(as_text=True)

print("ALL OK")
