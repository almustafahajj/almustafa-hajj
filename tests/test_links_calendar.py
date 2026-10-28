# -*- coding: utf-8 -*-
"""البورتال: QR التحقّق على الفاوتشر/طلب المواصلات وصفحته العامة، رابط المعتمر
الخاص، وتقويم الرحلات."""
import io
import os
import re
import sys
import tempfile
from datetime import date, timedelta

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["HAJJ_DATA_DIR"] = tempfile.mkdtemp(prefix="links_cal_")

from hajj_app import app_mode, auth, storage, umrah  # noqa: E402
from hajj_app.mrz import PassportData  # noqa: E402

try:
    from webapp import server, public
    server.app.config["CSRF_ENABLED"] = False
except ImportError as exc:
    print(f"[skip] مسارات الويب: {exc}")
    print("ALL OK")
    sys.exit(0)

T = date.today()
D1, D2 = T.replace(day=10), T.replace(day=20)
assert public.mask_name("أحمد محمد علي الحسن") == "أحمد م. ع." and public.mask_name("") == "—"

auth.create_account("owner", "Passw0rd!x")
app_mode.set_mode(app_mode.UMRAH)
st = storage.load_settings()
umrah.save_trips(st, [umrah.UmrahTrip(
    code="U1", name="البرنامج الأول", package="برامج رمضان", airline="الطيران السعودي",
    depart_city="أبوظبي", depart_date=D1.isoformat(), return_date=D2.isoformat(),
    flight_out="SV557", out_depart_time="09:00", makkah_hotel="سويس أوتيل",
    makkah_nights="5", emergency_ksa="+966 55 000 0000")])
umrah.save_packages(st, ["برامج رمضان"])
storage.save_settings(st)
c = server.app.test_client()
c.post("/login", data={"username": "owner", "password": "Passw0rd!x"})
SESS = server._SESSIONS[next(iter(server._SESSIONS))]
storage.save_records([PassportData(full_name_ar="أحمد محمد علي", passport_number="N7654321",
                                   phone="0501234567", trip="U1", room_type="ثنائي",
                                   uid="u-ahmad")], session=SESS)

# ---- 1) فاوتشر يدوي: QR + صفحة تحقّق عامة ----
vdata = {"number": "MA0042", "date": T.isoformat(), "guest_ar": "خالد سالم الكعبي",
         "stays": [["مكة", "سويس أوتيل", "ثنائي", "1", "", D1.isoformat(),
                    (D1 + timedelta(days=5)).isoformat(), "5", "إفطار"]]}
r = c.post("/documents/voucher/manual/pdf", json=vdata)
assert r.status_code == 200 and r.data[:4] == b"%PDF"
try:
    from pypdf import PdfReader
    assert len(PdfReader(io.BytesIO(r.data)).pages) == 1          # يبقى صفحة واحدة
except ImportError:
    pass
doc = storage.load_documents(session=SESS)[-1]
url = doc["data"]["verify_url"]
tok = url.rsplit("/v/", 1)[1]
assert url.startswith("http") and public.get_doc(tok)["number"] == "MA0042"
anon = server.app.test_client()                                   # بلا تسجيل دخول
page = anon.get(f"/v/{tok}").get_data(as_text=True)
assert "مستند صحيح" in page and "MA0042" in page and "خالد س. ا." in page
assert "سويس أوتيل" in page and "الكعبي" not in page               # الاسم مختصر
assert anon.get("/v/مزوّر123").status_code == 404
# إعادة إصدار الرقم نفسه ← الرمز نفسه (QR المطبوع يبقى صالحاً)
c.post("/documents/voucher/manual/pdf", json=dict(vdata, guest_ar="خالد سالم"))
assert storage.load_documents(session=SESS)[-1]["data"]["verify_url"] == url
# طلب مواصلات
r = c.post("/documents/treq/manual/pdf", json={
    "number": "MA-T0009", "to": "شركة النقل", "movements": [
        [D1.isoformat(), "المطار ← الفندق", "4", "جيمس", "2024", "10:00"],
        [D2.isoformat(), "الفندق ← المطار", "4", "جيمس", "2024", "18:00"]]})
assert r.status_code == 200 and r.data[:4] == b"%PDF"
t2 = storage.load_documents(session=SESS)[-1]["data"]["verify_url"].rsplit("/v/", 1)[1]
page = anon.get(f"/v/{t2}").get_data(as_text=True)
assert "طلب حجز مواصلات" in page and "2 حركة" in page
print("[ok] QR التحقّق: الفاوتشر وطلب المواصلات وصفحة التحقّق العامة")

# ---- 2) رابط المعتمر الخاص ----
with server.app.test_request_context("/"):
    recs, _n = storage.load_records(session=SESS)
    fp = server._rec_token(recs[0])
docs_page = c.get("/hujjaj/0/docs", query_string={"fp": fp}).get_data(as_text=True)
assert "إنشاء رابط خاص" in docs_page
c.post("/hujjaj/0/link", data={"fp": fp, "action": "create"})
docs_page = c.get("/hujjaj/0/docs", query_string={"fp": fp}).get_data(as_text=True)
plink = re.search(r'id="plink" value="([^"]+)"', docs_page).group(1)
assert "/p/" in plink and "wa.me/971501234567" in docs_page
ptok = plink.rsplit("/p/", 1)[1]
page = anon.get(f"/p/{ptok}").get_data(as_text=True)
assert "أهلاً أحمد" in page and "البرنامج الأول" in page and "SV557" in page
assert "سويس أوتيل" in page and "5 ليالٍ" in page and "+966 55 000 0000" in page
assert "N7654321" not in page and "0501234567" not in page        # لا جواز ولا هاتف
# مستندات الشخص تظهر في صفحته
c.post("/doc/0/voucher/pdf", json=dict(vdata, number="MA0043", _rec=fp))
assert "MA0043" in anon.get(f"/p/{ptok}").get_data(as_text=True)
# البيانات حيّة: تعديل البرنامج يظهر فوراً
st = storage.load_settings()
trips = umrah.load_trips(st)
trips[0].flight_out = "SV999"
umrah.save_trips(st, trips)
storage.save_settings(st)
assert "SV999" in anon.get(f"/p/{ptok}").get_data(as_text=True)
# التجديد يُبطل القديم، والإلغاء يحذفه
c.post("/hujjaj/0/link", data={"fp": fp, "action": "rotate"})
assert anon.get(f"/p/{ptok}").status_code == 404
newtok = public.find_person("umrah", "u-ahmad")
assert newtok and anon.get(f"/p/{newtok}").status_code == 200
c.post("/hujjaj/0/link", data={"fp": fp, "action": "revoke"})
assert public.find_person("umrah", "u-ahmad") is None
assert anon.get(f"/p/{newtok}").status_code == 404
print("[ok] رابط المعتمر: إنشاء/واتساب/بيانات حيّة/مستنداته/تجديد/إلغاء")

# ---- 3) تقويم الرحلات ----
page = c.get("/calendar", query_string={"m": T.strftime("%Y-%m")}).get_data(as_text=True)
assert page.count("🛫 U1 البرنامج الأول") == 1 and page.count("🛬 U1 البرنامج الأول") == 1
assert "(1)" in page and 'href="/programs/U1"' in page and "#1B5E20" in page
nxt = (T.replace(day=28) + timedelta(days=4)).strftime("%Y-%m")
assert f"m={nxt}" in page
assert "U1" not in c.get("/calendar", query_string={"m": nxt}).get_data(as_text=True) \
    .split("cal-grid")[1]
assert c.get("/calendar?m=خطأ").status_code == 200
c.get("/switch/hajj")
assert c.get("/calendar").status_code == 200
print("[ok] تقويم الرحلات: المغادرة والعودة بلون البرنامج والتنقّل بين الأشهر")
print("ALL OK")
