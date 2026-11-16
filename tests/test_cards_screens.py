# -*- coding: utf-8 -*-
"""البورتال: بطاقة المعتمر لحالة الواتساب، صفحة خاصة لكل برنامج، سماء مكة وصفحات الخطأ،
بطاقات تهنئة المواسم، النظرة السريعة على المعتمر، بطاقة ختام اليوم، وشاشة المكتب."""
import io
import json
import os
import re
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from html import unescape

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["HAJJ_DATA_DIR"] = tempfile.mkdtemp(prefix="cards_")
from hajj_app import app_mode, auth, storage, umrah  # noqa: E402
from hajj_app.mrz import PassportData  # noqa: E402
try:
    from webapp import server, public, hijri, cards
    server.app.config["CSRF_ENABLED"] = False
except ImportError as exc:
    print(f"[skip] مسارات الويب: {exc}")
    print("ALL OK")
    sys.exit(0)

owner, _rk = auth.create_account("owner", "Passw0rd!x")
auth.add_account(owner, "sara", "Passw0rd!s", role="editor")
auth.add_account(owner, "view", "Passw0rd!v", role="viewer")
c = server.app.test_client()
c.post("/login", data={"username": "owner", "password": "Passw0rd!x"})
SESS = next(v for v in server._SESSIONS.values() if v.username == "owner")
e = server.app.test_client()
e.post("/login", data={"username": "sara", "password": "Passw0rd!s"})
v = server.app.test_client()
v.post("/login", data={"username": "view", "password": "Passw0rd!v"})
anon = server.app.test_client()
UA = {"User-Agent": "Mozilla/5.0 (iPhone) Safari"}
app_mode.set_mode(app_mode.UMRAH)
T = datetime.now(server._UAE).date()
st = storage.load_settings()
umrah.save_trips(st, [
    umrah.UmrahTrip(code="U1", name="عمرة رمضان الأولى", depart_date=(T + timedelta(days=12)).isoformat(),
                    return_date=(T + timedelta(days=22)).isoformat(), makkah_hotel="سويس أوتيل",
                    makkah_nights="6", madinah_hotel="دار التقوى", madinah_nights="4", depart_city="دبي",
                    airline="فلاي دبي", flight_out="FZ 811", out_depart_time="09:45", out_arrive_time="11:50",
                    price_double="6,500", price_quad="4,900", capacity="30"),
    umrah.UmrahTrip(code="U2", name="عمرة جارية", depart_date=(T - timedelta(days=2)).isoformat(),
                    return_date=(T + timedelta(days=5)).isoformat()),
    umrah.UmrahTrip(code="U3", name="عمرة انتهت", depart_date=(T - timedelta(days=12)).isoformat(),
                    return_date=(T - timedelta(days=4)).isoformat())])
st["public_page"] = {"published": ["U1"]}
st["company"] = {"name_ar": "المصطفى للحج والعمرة", "phone": "+971 2 555 0000"}
storage.save_settings(st)
storage.save_records([
    PassportData(full_name_ar="أحمد علي الكعبي", passport_number="P100", uid="aa11", trip="U1",
                 phone="0501111111", program_value="6000", paid_amount="1000", expiry_date=(T + timedelta(days=60)).isoformat(),
                 room_type="ثنائية"),
    PassportData(full_name_ar="سالم خالد", passport_number="P200", uid="bb22", trip="U2", phone="0502222222"),
    PassportData(full_name_ar="مريم سعيد", passport_number="P300", uid="cc33", trip="U3", phone="0503333333")],
    session=SESS)


def recs():
    return storage.load_records(session=SESS)[0]


def fp(i):
    with server.app.test_request_context("/"):
        return server._rec_token(recs()[i])


def person(i):
    c.post(f"/hujjaj/{i}/link", data={"fp": fp(i), "action": "create"})
    return public.find_person("umrah", recs()[i].uid)


def jpeg(r):
    return r.status_code == 200 and r.mimetype == "image/jpeg" and r.data[:2] == b"\xff\xd8"


# ---- ٤) بطاقة المعتمر لحالة الواتساب ----
toks = [person(i) for i in range(3)]
pages = [anon.get("/p/" + t).get_data(as_text=True) for t in toks]
urls = [unescape(re.search(r'id="tsSave" href="([^"]+)"', p).group(1)) for p in pages]
assert all('id="story"' in p for p in pages) and "بطاقتك التذكارية" in pages[2] and "شارك فرحتك" in pages[0]
imgs = [anon.get(u.replace("&dl=1", "")) for u in urls]
assert all(jpeg(r) for r in imgs), [r.status_code for r in imgs]
assert len({r.data for r in imgs}) == 3, "قبل وأثناء وبعد: ثلاث بطاقات مختلفة"
dl = anon.get(urls[0])
assert "attachment" in dl.headers.get("Content-Disposition", "") and "umrah-card.jpg" in dl.headers["Content-Disposition"]
assert anon.get("/p/not-a-token/card.jpg").status_code == 404
try:                                               # رمز البطاقة يوصل لصفحة البرامج بمصدر «بطاقات المعتمرين»
    import cv2
    import numpy as np
    img = cv2.imdecode(np.frombuffer(imgs[0].data, np.uint8), cv2.IMREAD_COLOR)
    txt = cv2.QRCodeDetector().detectAndDecode(img)[0]
    assert txt.endswith("/trips?src=card"), txt
    print("[ok] رمز البطاقة يُقرأ: صفحة البرامج بمصدر البطاقات")
except ImportError:
    print("[skip] قراءة رمز البطاقة (لا cv2)")
assert ("card", "بطاقات المعتمرين") in server._BOOK_SOURCES
print("[ok] بطاقة الحالة: قبل/أثناء/بعد، تنزيل، رابط خاطئ 404")

# ---- ٥) صفحة خاصة لكل برنامج ----
r = anon.get("/trips/umrah/U1?src=instagram", headers=UA)
pg = r.get_data(as_text=True)
assert r.status_code == 200 and "عمرة رمضان الأولى" in pg and "animateMotion" in pg and "pg-bar" in pg
assert "6,500" in pg and "4,900" in pg and "يبدأ من" in pg and "دبي" in pg and "المدينة المنورة" in pg
assert 'name="back" value="prog"' in pg and 'value="umrah:U1"' in pg and "/trips/umrah/U1" in pg
assert server._visits_load().get(T.isoformat(), {}).get("instagram") == 1, "زيارة من إنستغرام"
nf = anon.get("/trips/umrah/U2")
assert nf.status_code == 404 and "لم يعد متاحاً" in nf.get_data(as_text=True), "غير المنشور لا يُعرض"
assert anon.get("/trips/umrah/NOPE").status_code == 404
r = anon.post("/trips/request", data={"program": "umrah:U1", "back": "prog", "name": "خالد عبدالله",
                                      "phone": "0509998887", "count": "2", "room": "ثنائي", "src": "card"})
assert r.headers["Location"].startswith("/trips/umrah/U1?sent=1"), r.headers["Location"]
bk = server._book_load()[-1]
assert bk["key"] == "U1" and bk["src"] == "card" and bk["count"] == 2
r = anon.post("/trips/request", data={"program": "umrah:U1", "back": "prog", "name": "خ", "phone": "1"})
assert "/trips/umrah/U1?err=" in r.headers["Location"] and r.headers["Location"].endswith("#book")
assert "/trips/umrah/U1" in anon.get("/trips").get_data(as_text=True), "رابط «تفاصيل البرنامج» في الصفحة العامة"
bpage = c.get("/bookings").get_data(as_text=True)
assert "/trips/umrah/U1?v=" in bpage and "بطاقات المعتمرين" in bpage, "رابط المشاركة لكل برنامج + مصدر البطاقات"
print("[ok] صفحة البرنامج: الخريطة والأسعار والحجز منها، غير المنشور 404، روابط المشاركة")

# ---- ٦) سماء مكة وصفحات الخطأ ----
lg = anon.get("/login").get_data(as_text=True)
assert 'class="sky sky-' in lg and "sky.js" in lg and "مكة الآن" in lg
mk = timezone(timedelta(hours=3))
d0 = date(2026, 6, 21)
assert server._makkah_sky(datetime(2026, 6, 21, 2, 30, tzinfo=mk))["phase"] == "night"
assert server._makkah_sky(datetime(2026, 6, 21, 4, 40, tzinfo=mk))["phase"] == "dawn"
assert server._makkah_sky(datetime(2026, 6, 21, 12, 0, tzinfo=mk))["phase"] == "day"
sk = server._makkah_sky(datetime(2026, 6, 21, 19, 0, tzinfo=mk))
assert sk["phase"] == "sunset" and 10 <= sk["x"] <= 20, sk
assert server._makkah_sky(datetime(2026, 6, 21, 22, 0, tzinfo=mk))["phase"] == "night"
r = anon.get("/no-such-page")
h = r.get_data(as_text=True)
assert r.status_code == 404 and "هذه الصفحة غير موجودة" in h and "برامجنا" in h and 'class="sky' in h
assert "لوحة التحكم" in c.get("/no-such-page").get_data(as_text=True)
r = anon.get("/trips/request")
assert r.status_code == 405 and "بهذه الطريقة" in r.get_data(as_text=True)
r = anon.get("/missing.json")
assert r.status_code == 404 and "<html" not in r.get_data(as_text=True), "الطلبات غير الصفحات: نصّ قصير"
print("[ok] سماء مكة: المراحل الأربع حسب الوقت، صفحات خطأ عربية (404/405)")

# ---- ٧) بطاقات تهنئة المواسم ----
assert hijri.to_greg(1448, 10, 1) == date(2027, 3, 9) and hijri.to_greg(1448, 12, 9) == date(2027, 5, 15)
assert hijri.fmt(date(2026, 11, 16)) == "6 جمادى الآخرة 1448 هـ"
occ = {o["key"]: o for o in hijri.occasions(date(2027, 3, 7))}
assert occ["fitr"]["now"] and occ["fitr"]["days"] == 2 and not occ["arafah"]["now"]
assert hijri.occasions(date(2027, 5, 14))[0]["key"] == "arafah"
gp = c.get("/greetings").get_data(as_text=True)
assert "عيد الفطر" in gp and "يوم عرفة" in gp and "/greetings/fitr.jpg" in gp and "نسخ نصّ التهنئة" in gp
assert jpeg(c.get("/greetings/fitr.jpg?y=1448")) and jpeg(v.get("/greetings/adha.jpg"))
assert c.get("/greetings/nope.jpg").status_code == 404 and anon.get("/greetings/fitr.jpg").status_code == 401
assert anon.get("/greetings").status_code == 302
# صورة خاصة للمناسبة: ترفع فتحلّ محلّ الأصلية، والعودة للأصلية، والمطّلع لا يغيّر
from PIL import Image as _Im  # noqa: E402
_buf = io.BytesIO()
_Im.new("RGB", (1600, 1200), (180, 40, 40)).save(_buf, "PNG")
orig = c.get("/greetings/fitr.jpg?y=1448").data
r = c.post("/greetings/fitr/photo", data={"photo": (io.BytesIO(_buf.getvalue()), "trip.png")},
           content_type="multipart/form-data")
assert r.status_code == 302 and "#g-fitr" in r.headers["Location"]
gp2 = c.get("/greetings").get_data(as_text=True)
assert "حُفظت الصورة" in gp2 and "البطاقة بصورتك الخاصة" in gp2 and "العودة للصورة الأصلية" in gp2
mine = c.get("/greetings/fitr.jpg?y=1448").data
assert mine != orig and _Im.open(io.BytesIO(mine)).size == (1080, 1350)
assert _Im.open(io.BytesIO(mine)).getpixel((540, 420))[0] > 120, "الصورة المرفوعة (حمراء) تظهر في البطاقة"
v.post("/greetings/fitr/photo", data={"action": "reset"})
assert c.get("/greetings/fitr.jpg?y=1448").data == mine, "المطّلع لا يغيّر الصورة"
r = c.post("/greetings/fitr/photo", data={"photo": (io.BytesIO(b"not an image"), "x.png")},
           content_type="multipart/form-data")
assert "ليس صورة صالحة" in c.get("/greetings").get_data(as_text=True)
c.post("/greetings/fitr/photo", data={"action": "reset"})
assert c.get("/greetings/fitr.jpg?y=1448").data == orig, "العودة للصورة الأصلية"
assert "استعمل صورة من رحلاتكم" in c.get("/greetings").get_data(as_text=True)
assert "استعمل صورة من رحلاتكم" not in v.get("/greetings").get_data(as_text=True)
_occ = hijri.occasions
hijri.occasions = lambda today: [{"key": "fitr", "name": "عيد الفطر", "date": today + timedelta(days=2),
                                  "hy": 1448, "start": today, "end": today, "now": True, "days": 2}]
dash = c.get("/dashboard").get_data(as_text=True)
hijri.occasions = _occ
assert "gr-banner" in dash and "عيد الفطر بعد يومين" in dash and "o=fitr" in dash
print("[ok] التهنئة: تواريخ أمّ القرى، البطاقات وصورها، تنبيه لوحة التحكم عند اقتراب المناسبة")

# ---- ٨) نظرة سريعة على المعتمر ----
lst = c.get("/hujjaj").get_data(as_text=True)
assert "data-peek=" in lst and 'id="pkOverlay"' in lst
pk = c.get("/hujjaj/0/peek", query_string={"fp": fp(0)})
ph = pk.get_data(as_text=True)
assert pk.status_code == 200 and "أحمد علي الكعبي" in ph and "P100" in ph and "سجّل الدفعة" in ph
assert "wa.me" in ph and "tel:0501111111" in ph and "ثنائية" in ph and "أقل من ٦ أشهر" in ph
assert 'name="back" value="list"' in ph
assert "سجّل الدفعة" not in v.get("/hujjaj/0/peek", query_string={"fp": fp(0)}).get_data(as_text=True), "المطّلع يرى بلا تسجيل"
assert c.get("/hujjaj/0/peek?fp=zz").status_code == 409 and anon.get("/hujjaj/0/peek", query_string={"fp": fp(0)}).status_code == 401
r = e.post("/finance/0/pay", data={"fp": fp(0), "amount": "1500", "method": "نقد", "back": "list",
                                   "ret": "/hujjaj?q=%D8%A3%D8%AD%D9%85%D8%AF"})
assert r.headers["Location"] == "/hujjaj?q=%D8%A3%D8%AD%D9%85%D8%AF", r.headers["Location"]
assert 'id="pmOverlay"' in e.get(r.headers["Location"]).get_data(as_text=True), "لحظة الدفعة تظهر في القائمة"
r = e.post("/finance/0/pay", data={"fp": fp(0), "amount": "10", "back": "list", "ret": "//evil.example/x"})
assert r.headers["Location"] == "/hujjaj", "لا تحويل لموقع خارجي"
print("[ok] النظرة السريعة: البيانات وأزرار الاتصال، دفعة من اللوحة تعود للقائمة، صلاحيات")

# ---- ٩) بطاقة ختام اليوم ----
c.post("/checkin/mark", json={"stage": "المطار", "idx": 1, "fp": fp(1)})
with server.app.test_request_context("/"):
    server.session["sid"] = next(k for k, s_ in server._SESSIONS.items() if s_.username == "owner")
    d = server._day_summary(T)
assert d["paid"] == "1,510" and d["n"] == 2 and d["checkins"] == 1 and d["books"] == 1, d
assert d["trip_name"].startswith("U2") and "العودة" in d["trip_when"], d
dp = c.get("/day-card").get_data(as_text=True)
assert "1,510" in dp and "دفعتان" in dp and "/day-card.jpg" in dp and "wa.me/?text=" in dp
assert jpeg(c.get("/day-card.jpg"))
assert e.get("/day-card").status_code == 302 and e.get("/day-card.jpg").status_code == 403
assert "سالم" not in dp and "أحمد" not in dp, "بلا أسماء"
print("[ok] ختام اليوم: المحصّل والدفعات والحضور والحجوزات وأقرب رحلة، للمدير وحده")

# ---- ١٠) شاشة المكتب ----
assert e.get("/office-screen").status_code in (302, 403)
op = c.get("/office-screen").get_data(as_text=True)
assert "الشاشة متوقّفة" in op
c.post("/office-screen", data={"action": "on"})
op = c.get("/office-screen").get_data(as_text=True)
tok = re.search(r'/tv/([\w-]+)"', op).group(1)
tv = anon.get(f"/tv/{tok}")
assert tv.status_code == 200 and "tv.js" in tv.get_data(as_text=True) and 'class="sky' in tv.get_data(as_text=True)
c.get("/dashboard")                                 # لقطة الأرقام تُكتب حين يعمل الموظفون
c.post("/checkin/mark", json={"stage": "المطار", "idx": 1, "fp": fp(1), "undo": True})
c.post("/checkin/mark", json={"stage": "المطار", "idx": 1, "fp": fp(1)})
dj = anon.get(f"/tv/{tok}/data.json")
data = dj.get_json()
assert dj.status_code == 200 and data["ok"] and dj.headers.get("Cache-Control") == "no-store"
labels = [t["label"] for t in data["trips"]]
assert any(x.startswith("U1") for x in labels) and any(x.startswith("U2") for x in labels), labels
u1 = next(t for t in data["trips"] if t["label"].startswith("U1"))
assert u1["n"] == 1 and u1["cap"] == 30 and u1["state"] == "soon" and u1["days"] == 12
att = [x for x in data["checkins"] if x["stage"] == "المطار" and x["label"].startswith("U2")]
assert att and att[0]["present"] == 1 and att[0]["total"] == 1, data["checkins"]
assert len(data["prayer"]["times"]) == 6
raw = dj.get_data(as_text=True)
assert "أحمد" not in raw and "سالم" not in raw and "P100" not in raw and "6000" not in raw, "بلا أسماء ولا مبالغ"
c.post("/office-screen", data={"action": "rotate"})
assert anon.get(f"/tv/{tok}").status_code == 404 and anon.get(f"/tv/{tok}/data.json").status_code == 404
c.post("/office-screen", data={"action": "off"})
assert "الشاشة متوقّفة" in c.get("/office-screen").get_data(as_text=True)
assert anon.get("/tv/anything").status_code == 404
print("[ok] شاشة المكتب: رابط سرّي للمدير، رحلات وحضور بلا أسماء ولا مبالغ، تجديد وإيقاف")
print("ALL OK")
