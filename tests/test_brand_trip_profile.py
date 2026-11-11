# -*- coding: utf-8 -*-
"""البورتال: (١) هوية مستندات العميل — ترويسة بالشعار وبيانات الشركة، تذييل، ختم
«مدفوع بالكامل»، وترويسة يحفظها المدير؛ (٢) صفحة «رحلتي» للمعتمر — عدّ تنازلي
وبطاقتا الطيران والفنادق والمرشد؛ (٣) صفحة السجلّ كملفّ شخصي — جاهزية السفر
والسداد وحقول التأشيرة والصحة."""
import io
import os
import sys
import tempfile
import unicodedata
from datetime import date, timedelta

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["HAJJ_DATA_DIR"] = tempfile.mkdtemp(prefix="brand_")

from hajj_app import app_mode, auth, pdf_io, storage, umrah  # noqa: E402
from hajj_app.mrz import PassportData  # noqa: E402

try:
    from webapp import server, public
    server.app.config["CSRF_ENABLED"] = False
except ImportError as exc:
    print(f"[skip] مسارات الويب: {exc}")
    print("ALL OK")
    sys.exit(0)

import fitz  # noqa: E402

OUT = tempfile.mkdtemp(prefix="brand_pdf_")


def pdf_text(path) -> str:
    """نصّ الـ PDF بلا مسافات وبالحروف العربية الأصلية (لا أشكال العرض)."""
    d = fitz.open(str(path))
    t = "".join(p.get_text() for p in d)
    d.close()
    return "".join(unicodedata.normalize("NFKC", t).split())


def flat(s: str) -> str:
    return "".join(s.split())


CO = {"name_ar": "المصطفى للحج والعمرة", "name_en": "Al Mustafa Hajj & Umrah",
      "phone": "+971 4 123 4567", "email": "info@almustafa.ae", "trn": "100234567800003"}

# ---- ١) المستندات بالهوية الجديدة ----
r = PassportData(full_name_ar="فاطمة سالم المنصوري", passport_number="N7654321",
                 phone="0559876543", program_value="12000", paid_amount="4000")
p = os.path.join(OUT, "receipt.pdf")
pdf_io.export_receipt_pdf(r, p, company=CO, number="0201",
                          data={"chq_no": "000123", "chq_date": "2026-11-10"})
t = pdf_text(p)
assert flat("سند قبض") in t and "RECEIPTVOUCHER" in t and "No.0201" in t, t[:300]
assert "+97141234567" in t and "info@almustafa.ae" in t and "TRN100234567800003" in t, "الترويسة بالتواصل"
assert "4,000.00" in t and "000123" in t, "المبلغ ورقم الشيك"
assert any(f["key"] == "chq_no" for g in pdf_io.RECEIPT_SCHEMA for f in g["fields"]), "الشيك قابل للتحرير"
# اسم الشركة نصّاً (كما في الاستدعاءات القديمة) يعمل أيضاً
pdf_io.export_receipt_pdf(r, os.path.join(OUT, "r_old.pdf"), company="المصطفى للحج والعمرة")

p = os.path.join(OUT, "invoice.pdf")
pdf_io.export_invoice_pdf(r, p, company=CO, number="INV-0200")
t = pdf_text(p)
assert "TAXINVOICE" in t and "INV-0200" in t and flat("فاتورة إلى") in t
assert "PAIDINFULL" not in t, "لا ختم والمبلغ لم يُسدَّد كاملاً"
paid = PassportData(full_name_ar="سعيد", program_value="5000", paid_amount="5000")
p = os.path.join(OUT, "invoice_paid.pdf")
pdf_io.export_invoice_pdf(paid, p, company=CO, number="INV-0201", vat_mode="inclusive")
t = pdf_text(p)
assert "PAIDINFULL" in t and flat("مدفوع بالكامل") in t, "ختم السداد الكامل"
pdf_io.export_invoice_pdf(paid, os.path.join(OUT, "einv.pdf"), company=CO, electronic=True)

p = os.path.join(OUT, "contract.pdf")
pdf_io.export_umrah_contract_pdf(r, p, program_name="رجب", company=CO, number="CON-0300")
t = pdf_text(p)
assert "UMRAHSERVICESAGREEMENT" in t and flat("البند الأول") in t and flat("موضوع العقد") in t
assert flat("الطرف الثاني") in t and "N7654321" in t
# بند طويل يلتفّ: أسطره بترتيب القراءة (السطر الأول قبل الثاني)
body = "البند الأول: موضوع العقد\n" + "كلمة_أولى " + "نص طويل للبند " * 30 + "كلمة_أخيرة"
pdf_io.export_contract_pdf(r, os.path.join(OUT, "c2.pdf"), company=CO, data={"body": body})
t = pdf_text(os.path.join(OUT, "c2.pdf"))
assert t.index("كلمة_أولى") < t.index("كلمة_أخيرة"), "أسطر البند مقلوبة"

for lg in ("ar", "en"):
    p = os.path.join(OUT, f"v_{lg}.pdf")
    pdf_io.export_umrah_voucher_pdf(r, p, program_name="رجب", company=CO, lang=lg)
    d = fitz.open(p)
    assert d.page_count == 1, "الفاوتشر صفحة واحدة"
    d.close()
    assert "HOTELVOUCHER" in pdf_text(p) and "info@almustafa.ae" in pdf_text(p)
p = os.path.join(OUT, "treq.pdf")
pdf_io.export_umrah_transport_request_pdf(r, p, company=CO)
assert flat("طلب حجز مواصلات") in pdf_text(p) and "TRANSPORTATIONREQUEST" in pdf_text(p)
print("[ok] المستندات: ترويسة وتذييل وختم «مدفوع» وترتيب أسطر العقد")

# ---- ٢) ترويسة الشركة يحفظها المدير ----
owner, _rk = auth.create_account("owner", "Passw0rd!x")
auth.add_account(owner, "sara", "Passw0rd!s", role="editor")
c = server.app.test_client()
c.post("/login", data={"username": "owner", "password": "Passw0rd!x"})
SESS = next(v for v in server._SESSIONS.values() if v.username == "owner")
e = server.app.test_client()
e.post("/login", data={"username": "sara", "password": "Passw0rd!s"})
app_mode.set_mode(app_mode.UMRAH)

page = c.get("/documents").get_data(as_text=True)
assert 'id="letterhead"' in page and "ترويسة المستندات" in page
assert 'id="letterhead"' not in e.get("/documents").get_data(as_text=True), "للمدير فقط"
form = {"name_ar": "المصطفى للحج والعمرة", "name_en": "Al Mustafa Hajj & Umrah",
        "phone": "+971 4 555 0000", "email": "office@almustafa.ae",
        "website": "www.almustafa.ae", "address": "دبي", "trn": "100234567800003"}
e.post("/documents/company", data=form)
assert not (storage.load_settings().get("company") or {}).get("phone"), "المحرّر لا يغيّر الترويسة"
r1 = c.post("/documents/company", data=dict(form, trn="123"))
assert r1.status_code == 302 and not (storage.load_settings().get("company") or {}).get("phone")
assert "١٥ رقماً" in c.get("/documents").get_data(as_text=True)
c.post("/documents/company", data=dict(form, email="ليس-بريداً"))
assert not (storage.load_settings().get("company") or {}).get("phone"), "بريد غير صحيح يُرفض"
st = storage.load_settings()
st["company"] = {"extra_key": "يبقى"}
storage.save_settings(st)
c.post("/documents/company", data=form)
for m in app_mode.MODES:                          # يُحفظ في النظامين معاً
    app_mode.set_mode(m)
    co = storage.load_settings().get("company") or {}
    assert co.get("phone") == "+971 4 555 0000" and co.get("trn") == "100234567800003", (m, co)
app_mode.set_mode(app_mode.UMRAH)
assert storage.load_settings()["company"].get("extra_key") == "يبقى", "المفاتيح الأخرى تبقى"
pv = c.get("/documents/company/preview.pdf")
assert pv.status_code == 200 and pv.data[:4] == b"%PDF"
pp = os.path.join(OUT, "preview.pdf")
open(pp, "wb").write(pv.data)
assert "office@almustafa.ae" in pdf_text(pp), "المعاينة بالترويسة المحفوظة"
assert server.app.test_client().get("/documents/company/preview.pdf").status_code == 302
print("[ok] ترويسة الشركة: المدير يحفظ (النظامان)، المحرّر يُرفض، التحقّق من TRN والبريد")

# ---- ٣) صفحة «رحلتي» ----
T = date.today()
assert server._nights_txt("1") == "ليلة واحدة" and server._nights_txt("5") == "5 ليالٍ"
assert server._nights_txt("12") == "12 ليلة" and server._nights_txt("") == ""
s0 = server._trip_status(T + timedelta(days=12), T + timedelta(days=20), T)
assert s0 == {"state": "before", "n": 12, "unit": "يوماً"}, s0
s1 = server._trip_status(T - timedelta(days=3), T + timedelta(days=6), T)
assert s1["state"] == "during" and s1["n"] == 4 and s1["total"] == 10
assert server._trip_status(T - timedelta(days=9), T - timedelta(days=1), T)["state"] == "after"
assert server._trip_status(None, None, T)["state"] == "unknown"

trip = umrah.UmrahTrip(code="U1", name="عمرة رجب", airline="طيران الإمارات", depart_city="دبي",
                       depart_date=(T + timedelta(days=12)).isoformat(),
                       return_date=(T + timedelta(days=21)).isoformat(),
                       flight_out="EK 2803", out_depart_time="08:40", out_arrive_time="10:15",
                       makkah_hotel="سويس أوتيل", makkah_nights="5",
                       madinah_hotel="دار التقوى", madinah_nights="4",
                       emergency_ksa="+966 55 000 0000")
st = storage.load_settings()
umrah.save_trips(st, [trip])
st["groups"] = {"النور": {"guide": "عبدالله الكعبي", "phone": "0501112233"}}
storage.save_settings(st)
rec = PassportData(full_name_ar="أحمد محمد الهاشمي", trip="U1", room_type="رباعية", uid="u-1",
                   group="النور", phone="0509998877", passport_number="P1234567",
                   expiry_date="2030-01-01", program_value="6,500", paid_amount="4,000")
storage.save_records([rec], session=SESS)
with server.app.test_request_context("/"):
    fp = server._rec_token(storage.load_records(session=SESS)[0][0])
c.post("/hujjaj/0/link", data={"fp": fp, "action": "create"})
tok = public.find_person("umrah", "u-1")
assert public.get_person(tok)["team"] == "النور", "المجموعة تُحفظ في الرابط"
anon = server.app.test_client()
html = anon.get(f"/p/{tok}").get_data(as_text=True)
assert "أهلاً أحمد" in html and "عمرة رجب" in html and 'class="tp-num">12<' in html
assert "يوماً على المغادرة" in html and "EK 2803" in html and "08:40" in html
assert "سويس أوتيل" in html and "5 ليالٍ" in html and "4 ليالٍ" in html
assert "عبدالله الكعبي" in html and 'href="tel:0501112233"' in html and "wa.me/971501112233" in html
assert "+966 55 000 0000" in html and "قبل السفر" in html
assert "P1234567" not in html and "0509998877" not in html and "6,500" not in html, "لا بيانات حسّاسة"
st = storage.load_settings()                         # أثناء الرحلة
trips = umrah.load_trips(st)
trips[0].depart_date = (T - timedelta(days=3)).isoformat()
trips[0].return_date = (T + timedelta(days=6)).isoformat()
umrah.save_trips(st, trips)
storage.save_settings(st)
html = anon.get(f"/p/{tok}").get_data(as_text=True)
assert "رحلتك جارية — اليوم 4 من 10" in html and "قبل السفر" not in html
assert anon.get("/p/غير-موجود").status_code == 404
print("[ok] رحلتي: عدّ تنازلي، الطيران، الفنادق، المرشد، الطوارئ، بلا بيانات حسّاسة")

# ---- ٤) صفحة السجلّ كملفّ شخصي ----
page = c.get("/hujjaj/0", query_string={"fp": fp}).get_data(as_text=True)
assert 'class="prof"' in page and "جاهزية السفر" in page and ">75%<" in page
assert "ينقص: التأشيرة" in page and 'name="visa_number"' in page and "<em>ناقص</em>" in page
assert 'name="emergency_phone"' in page and 'name="blood_type"' in page
assert 'name="permit_status"' not in page, "تصريح الحج لا يظهر في العمرة"
assert "سداد جزئي" in page and "62%" in page and "2,500" in page
assert 'id="secNav"' in page and "rec-form needs-save" in page and "صفحة رحلتي" in page
assert "/hujjaj/0/docs?fp=" in page and "/hujjaj/0/images?fp=" in page
c.post("/hujjaj/0", data={"fp": fp, "visa_number": "V-77", "blood_type": "O+",
                          "full_name_ar": "أحمد محمد الهاشمي"})
saved = storage.load_records(session=SESS)[0][0]
assert saved.visa_number == "V-77" and saved.blood_type == "O+", "الحقول الجديدة تُحفظ"
with server.app.test_request_context("/"):
    fp = server._rec_token(saved)
page = c.get("/hujjaj/0", query_string={"fp": fp}).get_data(as_text=True)
assert ">100%<" in page and "البيانات الأساسية مكتملة" in page
new = c.get("/hujjaj/new").get_data(as_text=True)
assert 'class="prof"' not in new and 'class="rec-form"' in new, "السجلّ الجديد بلا رأس ولا قفل الحفظ"
assert c.get("/hujjaj/0/avatar.jpg", query_string={"fp": fp}).status_code == 404, "بلا صورة"
assert anon.get("/hujjaj/0/avatar.jpg").status_code == 401
ed = e.get("/hujjaj/0", query_string={"fp": fp}).get_data(as_text=True)
assert "جاهزية السفر" in ed
print("[ok] ملفّ السجلّ: الجاهزية والسداد والأقسام وحقول التأشيرة والصحة")

print("ALL OK")
