# -*- coding: utf-8 -*-
"""البورتال: (١) تسجيل الحضور بالمسح — رمز «رحلتي» أو الجواز أو الضغط على الاسم؛
(٢) حملة التحصيل بالواتساب — من عليه متبقٍّ بقرب مغادرته ورسالة جاهزة؛
(٣) الصفحة العامة للبرامج وطلبات الحجز — نشر، استقبال بحماية، وتحويل إلى سجلّ."""
import io
import os
import re
import sys
import tempfile
from datetime import date, timedelta
from html import unescape
from urllib.parse import unquote, urlsplit

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["HAJJ_DATA_DIR"] = tempfile.mkdtemp(prefix="ckrb_")

from hajj_app import app_mode, auth, storage, umrah  # noqa: E402
from hajj_app.mrz import PassportData  # noqa: E402

try:
    from webapp import server, public
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
app_mode.set_mode(app_mode.UMRAH)
T = date.today()
st = storage.load_settings()
umrah.save_trips(st, [
    umrah.UmrahTrip(code="U1", name="عمرة قريبة", depart_date=(T + timedelta(days=5)).isoformat(),
                    return_date=(T + timedelta(days=12)).isoformat(), capacity="10",
                    price_quad="4500", price_double="5900", makkah_hotel="سويس أوتيل", makkah_nights="4",
                    airline="فلاي دبي", flight_out="FZ 811", out_depart_time="09:45", out_arrive_time="11:50",
                    flight_ret="FZ 812", ret_depart_time="13:10", ret_arrive_time="17:05"),
    umrah.UmrahTrip(code="U2", name="عمرة بعيدة", depart_date=(T + timedelta(days=60)).isoformat(),
                    capacity="3", price_quad="3900"),
    umrah.UmrahTrip(code="U0", name="عمرة مضت", depart_date=(T - timedelta(days=20)).isoformat())])
storage.save_settings(st)
storage.save_records([
    PassportData(full_name_ar="أحمد علي", passport_number="P100", uid="aa11", trip="U1",
                 phone="0501111111", program_value="6000", paid_amount="1000"),
    PassportData(full_name_ar="سالم خالد", passport_number="P200", uid="bb22", trip="U1",
                 phone="0502222222", program_value="6000", paid_amount="6000"),
    PassportData(full_name_ar="مريم سعيد", passport_number="P300", uid="cc33", trip="U2",
                 phone="", program_value="5000", paid_amount="0"),
    PassportData(full_name_ar="ملغى", passport_number="P400", uid="dd44", trip="U1",
                 status="ملغى", program_value="5000")], session=SESS)


def recs():
    return storage.load_records(session=SESS)[0]


# ---- ١) الحضور ----
assert server._checkin_code("umrah", "aa11") == "MSTF-umrah-aa11" and server._checkin_code("umrah", "") == ""
svg = server._qr_svg("MSTF-umrah-aa11")
assert svg.startswith("<svg") and "<path" in svg and len(svg) < 12000, len(svg)
pg = c.get("/checkin", query_string={"stage": "المطار", "grp": "U1"}).get_data(as_text=True)
assert 'id="ckStart"' in pg and "أحمد علي" in pg and "سالم خالد" in pg and "ملغى" not in pg
assert 'id="ckTotal">2<' in pg and 'id="ckPresent">0<' in pg
M = "/checkin/mark"
r = c.post(M, json={"stage": "المطار", "grp": "U1", "code": "MSTF-umrah-aa11"}).get_json()
assert r["ok"] and r["name"] == "أحمد علي" and not r["already"] and r["present"] == 1 and r["total"] == 2
assert re.fullmatch(r"\d\d:\d\d", r["time"])
assert "المطار" in recs()[0].checkins
r = c.post(M, json={"stage": "المطار", "grp": "U1", "code": "MSTF-umrah-aa11"}).get_json()
assert r["ok"] and r["already"] and r["present"] == 1, "المسح الثاني لا يكرّر"
r = c.post(M, json={"stage": "المطار", "grp": "U1", "code": "p200"}).get_json()           # جواز بأحرف صغيرة
assert r["ok"] and r["name"] == "سالم خالد" and r["present"] == 2
r = c.post(M, json={"stage": "الفندق", "grp": "U1", "code": "الحاج: سالم\nالجواز: P200"}).get_json()
assert r["ok"] and r["present"] == 1, "نصّ البطاقة القديمة يُقرأ، والمراحل مستقلّة"
r = c.post(M, json={"stage": "المطار", "grp": "U1", "code": "P300"}).get_json()
assert not r["ok"] and "ليس في هذا البرنامج" in r["msg"], r
r = c.post(M, json={"stage": "المطار", "code": "MSTF-hajj-aa11"}).get_json()
assert not r["ok"] and "بدّل النظام" in r["msg"]
assert not c.post(M, json={"stage": "المطار", "code": "XYZ"}).get_json()["ok"]
assert c.post(M, json={"stage": "السوق", "code": "P100"}).status_code == 400
assert v.post(M, json={"stage": "المطار", "code": "P300"}).status_code == 403, "المطّلع لا يسجّل"
assert anon.post(M, json={"stage": "المطار", "code": "P300"}).status_code == 401
with server.app.test_request_context("/"):
    fp0 = server._rec_token(recs()[0])
r = e.post(M, json={"stage": "المطار", "grp": "U1", "idx": 0, "fp": fp0, "undo": True}).get_json()
assert r["ok"] and r["undo"] and r["present"] == 1 and "المطار" not in recs()[0].checkins
vp = v.get("/checkin").get_data(as_text=True)
assert 'id="ckStart"' not in vp and 'class="ck-mark' not in vp, "المطّلع يرى القوائم فقط"
rep = c.get("/checkin/report.pdf", query_string={"grp": "U1"})
assert rep.status_code == 200 and rep.data[:4] == b"%PDF"
# رمز الحضور في صفحة «رحلتي»
with server.app.test_request_context("/"):
    fp1 = server._rec_token(recs()[1])
c.post("/hujjaj/1/link", data={"fp": fp1, "action": "create"})
tp = anon.get("/p/" + public.find_person("umrah", "bb22")).get_data(as_text=True)
head = tp.split("</head>")[0]
assert "/static/share/trip-og.jpg" in head and 'og:title" content="رحلتي' in head
assert "سالم" not in head, "معاينة رابط رحلتي بلا اسم المعتمر"
im = anon.get("/static/share/trip-og.jpg")
assert im.status_code == 200 and im.data[:3] == b"\xff\xd8\xff"
im.close()
assert "رمز الحضور" in tp and "<svg" in tp.split("رمز الحضور")[1]
assert 'href="/checkin"' in c.get("/dashboard").get_data(as_text=True)
print("[ok] الحضور: رمز رحلتي والجواز ونصّ البطاقة، بلا تكرار، بالبرنامج، إلغاء، تقرير، صلاحيات")

# ---- ٢) حملة التحصيل ----
rm = c.get("/finance/remind").get_data(as_text=True)
assert "أحمد علي" in rm and "سالم خالد" not in rm, "المسدَّد لا يظهر"
assert "مريم سعيد" not in rm, "المغادرة بعد شهرين خارج «شهر»"
assert "ملغى" not in rm.split('id="rmList"')[1]
assert "مريم سعيد" in c.get("/finance/remind", query_string={"within": "all"}).get_data(as_text=True)
wa = re.search(r'href="(https://wa\.me/971501111111\?text=[^"]+)"', rm).group(1)
txt = unquote(wa.split("text=", 1)[1])
assert "أحمد علي" in txt and "5,000" in txt and "عمرة قريبة" in txt and "{" not in txt, txt
assert "(المغادرة" in txt and "/p/" not in txt, "بلا رابط رحلتي لا سطر رابط"
allp = c.get("/finance/remind", query_string={"within": "all"}).get_data(as_text=True)
assert "بلا هاتف" in allp, "مريم بلا هاتف"
assert c.post("/finance/remind/mark", json={"uid": "aa11"}).get_json()["ok"]
assert storage.load_settings()["reminders"]["aa11"]
rm2 = c.get("/finance/remind").get_data(as_text=True)
assert "ذُكّر اليوم" in rm2 and 'id="rsDone">1<' in rm2
assert "أحمد علي" not in c.get("/finance/remind", query_string={"fresh": "1"}).get_data(as_text=True)
assert v.post("/finance/remind/mark", json={"uid": "aa11"}).status_code == 403
c.post("/finance/remind", data={"tpl": "مرحباً {الاسم} — عليك {المتبقّي} — {الرابط}"})
assert storage.load_settings()["remind_tpl"].startswith("مرحباً")
txt = unquote(re.search(r'wa\.me/971501111111\?text=([^"]+)"',
                        c.get("/finance/remind").get_data(as_text=True)).group(1))
assert txt == "مرحباً أحمد علي — عليك 5,000 —", txt
v.post("/finance/remind", data={"tpl": "اختراق"})
assert storage.load_settings()["remind_tpl"].startswith("مرحباً"), "المطّلع لا يغيّر النصّ"
c.post("/finance/remind", data={"reset": "1"})
assert "remind_tpl" not in storage.load_settings()
print("[ok] حملة التحصيل: الأقرب مغادرةً، رسالة باسمه ومبلغه، «ذُكّر»، نصّ قابل للتعديل")

# ---- ٣) الصفحة العامة وطلبات الحجز ----
pub = anon.get("/trips").get_data(as_text=True)
assert "لا برامج معروضة حالياً" in pub
e.post("/bookings", data={"pub": ["U1"]})
assert not (storage.load_settings().get("public_page") or {}).get("published"), "النشر للمدير فقط"
c.post("/bookings", data={"pub": ["U1", "U2", "U0"], "intro": "أهلاً بكم"})
pub = anon.get("/trips").get_data(as_text=True)
assert "عمرة قريبة" in pub and "عمرة بعيدة" in pub and "عمرة مضت" not in pub and "أهلاً بكم" in pub
assert "4,500" in pub and "3,900" in pub and "سويس أوتيل" in pub
assert "أحمد علي" not in pub and "P100" not in pub, "لا بيانات أشخاص"
assert "تبقّى" not in pub and pub.count("مقاعد محدودة") == 2, "«مقاعد محدودة» بدل العدد"
# كل الأسعار بالترتيب (مفرد ← رباعي) قابلة للاختيار، ومواعيد الرحلتين، والسيارة الخاصة
card1 = pub.split("عمرة قريبة")[1].split("</article>")[0]
assert card1.index("ثنائي") < card1.index("رباعي") and "5,900" in card1 and "4,500" in card1
assert 'name="r" value="ثنائي"' in card1 and 'name="r" value="مفرد"' not in card1, "غير المسعّر لا يظهر"
for s_ in ("FZ 811", "09:45", "11:50", "FZ 812", "13:10", "17:05", "إقلاع", "وصول", "الذهاب", "العودة"):
    assert s_ in card1, s_
assert "سيارة خاصة" in card1 and "فلاي دبي" in card1 and "يبدأ من" not in pub
assert "wa.me/971549964801" in pub, "واتساب «راسلنا» على الرقم الافتراضي"
# معاينة الرابط (واتساب): صورة مطلقة الرابط بمقاسها، وأيقونة الشعار
og = unescape(re.search(r'<meta property="og:image" content="([^"]+)">', pub).group(1))
assert og.startswith("http") and "/trips/og.jpg?v=" in og, og
assert 'og:image:width" content="1200"' in pub and 'twitter:card" content="summary_large_image"' in pub
assert 'rel="icon"' in pub and "icons/icon-192.png" in pub
im = anon.get(urlsplit(og).path, query_string=urlsplit(og).query)
assert im.status_code == 200 and im.mimetype == "image/jpeg" and im.data[:3] == b"\xff\xd8\xff"
assert len(im.data) < 300_000, "صورة JPEG خفيفة"
from PIL import ImageFont  # noqa: E402
from webapp import share_image  # noqa: E402
assert share_image._font("Amiri-Bold.ttf", 20).layout_engine == ImageFont.Layout.BASIC,     "التخطيط البسيط دائماً (libraqm على الخادم يقلب النصّ المُشكَّل مسبقاً)"
im.close()
# العنوان حسب البرامج المنشورة (هنا عمرة فقط): في العنوان والمعاينة وأعلى الصفحة
lbl = server._progs_label(server._all_public_programs()[0])
assert lbl.startswith("برامج عمرة ") or lbl == "برامج العمرة", lbl
assert f"<title>{lbl} — " in pub and f'og:title" content="{lbl} — ' in pub
assert lbl in pub.split('class="pt-kicker"')[1][:400] and "برامج العمرة والحج" not in pub
# الرابط المنسوخ من البورتال يحمل رمز المعاينة (يتغيّر بتغيّرها فيجلب واتساب الصورة من جديد)
cp = unescape(re.search(r'id="bkCopy" data-url="([^"]+)"', c.get("/bookings").get_data(as_text=True)).group(1))
assert "/trips?v=" in cp and cp.split("v=")[1] == og.split("v=")[1], (cp, og)
assert f'og:url" content="{cp}"' in pub, "og:url = الرابط المنسوخ نفسه"
_ps = server._all_public_programs()[0]
assert server._trips_share_v(_ps) != server._trips_share_v(_ps[:1]), "يتغيّر الرمز بتغيّر البرامج"
one = anon.get("/trips", query_string={"p": "umrah:U1"}).get_data(as_text=True)
assert re.search(r"<title>برنامج (عمرة \S+|العمرة) «عمرة قريبة» — ", one), "رابط برنامج واحد"
og1 = unescape(re.search(r'<meta property="og:image" content="([^"]+)">', one).group(1))
assert "p=umrah:U1" in unquote(og1) and og1 != og
assert anon.get(urlsplit(og1).path, query_string=urlsplit(og1).query).status_code == 200
assert anon.get("/trips/og.jpg", query_string={"p": "umrah:لا-يوجد"}).status_code == 200, "رمز خاطئ ← صورة الكلّ"
# قاعدة التسمية: الشهر أو رمضان، والحج، والمفرد
U, HJ = app_mode.UMRAH, app_mode.HAJJ


def P_(m, d=None, r=False):
    return {"mode": m, "d0": d, "ramadan": r}


L = server._progs_label
assert L([P_(U, date(2026, 12, 4)), P_(U, date(2026, 12, 20))]) == "برامج عمرة ديسمبر"
assert L([P_(U, date(2027, 1, 9)), P_(U, date(2026, 12, 4))]) == "برامج عمرة ديسمبر ويناير"
assert L([P_(U, date(2027, 2, 12), True), P_(U, date(2027, 2, 25), True)]) == "برامج عمرة رمضان"
assert L([P_(U, date(2026, 12, 4)), P_(U, date(2027, 1, 9)), P_(U, date(2027, 3, 1))]) == "برامج العمرة"
assert L([P_(HJ, date(2027, 5, 10)), P_(HJ, date(2027, 5, 12))]) == "برامج الحج"
assert L([P_(U, date(2027, 2, 12), True), P_(HJ, date(2027, 5, 10))]) == "برامج عمرة رمضان والحج"
assert L([P_(U, date(2026, 12, 4))]) == "برنامج عمرة ديسمبر" and L([]) == "برامج العمرة والحج"
assert server._hijri_month(date(2026, 2, 18)) == 9 and server._hijri_month(date(2026, 2, 16)) == 8
assert server._hijri_month(date(2027, 2, 20)) == 9 and server._hijri_month(date(2026, 12, 4)) == 6
pk = anon.get("/trips", query_string={"p": "umrah:U1", "r": "ثنائي"}).get_data(as_text=True)
assert '<option value="ثنائي" selected>ثنائي — 5,900 درهم للفرد</option>' in pk, "الغرفة المختارة من البطاقة"
assert '<option value="مفرد"' not in pk.split('id="ptRoom"')[1].split("</select>")[0]
# رقم الواتساب: المدير يغيّره (يُكتب في النظامين)، والخاطئ مرفوض، والمحرّر لا يغيّره
c.post("/bookings", data={"pub": ["U1", "U2"], "intro": "أهلاً بكم", "wa": "12"})
assert "رقم الواتساب غير صحيح" in c.get("/bookings").get_data(as_text=True)
assert not storage.load_settings()["public_page"].get("wa")
c.post("/bookings", data={"pub": ["U1", "U2"], "intro": "أهلاً بكم", "wa": "+971 50 999 8877"})
assert storage.load_settings()["public_page"]["wa"] == "+971509998877"
assert "wa.me/971509998877" in anon.get("/trips").get_data(as_text=True)
app_mode.set_mode(app_mode.HAJJ)
assert storage.load_settings()["public_page"]["wa"] == "+971509998877", "الرقم في نظام الحج أيضاً"
app_mode.set_mode(app_mode.UMRAH)
e.post("/bookings", data={"pub": ["U1"], "wa": "0501111111"})
assert storage.load_settings()["public_page"]["wa"] == "+971509998877", "المحرّر لا يغيّر الرقم"
c.post("/bookings", data={"pub": ["U1", "U2"], "intro": "أهلاً بكم", "wa": ""})
assert "wa.me/971549964801" in anon.get("/trips").get_data(as_text=True), "الفارغ يعود للافتراضي"
c.get("/programs")
assert storage.load_settings()["public_page"]["seats"]["U1"] == 8, storage.load_settings()["public_page"]
R = "/trips/request"
r = anon.post(R, data={"program": "umrah:U1", "name": "عبدالله الكتبي", "phone": "٠٥٥١٢٣٤٥٦٧",
                       "count": "3", "room": "ثنائي", "note": "عائلة"})
assert r.status_code == 302 and "sent=1" in r.headers["Location"]
assert "وصلنا طلبك" in anon.get("/trips?sent=1").get_data(as_text=True)
items = server._book_load()
assert len(items) == 1 and items[0]["phone"] == "0551234567" and items[0]["count"] == 3
assert items[0]["room"] == "ثنائي" and items[0]["rprice"] == "5,900", "سعر الغرفة المختارة مع الطلب"
raw = server._book_path().read_bytes()
assert "عبدالله".encode("utf-8") not in raw and b"0551234567" not in raw, "مشفّرة على القرص"
r = anon.post(R, data={"program": "umrah:U0", "name": "اسم صحيح", "phone": "0551234567"})
assert "err=" in r.headers["Location"], "برنامج غير منشور/مضى"
r = anon.post(R, data={"program": "umrah:U1", "name": "اسم صحيح", "phone": "123"})
assert "err=" in r.headers["Location"]
anon.post(R, data={"program": "umrah:U1", "name": "روبوت", "phone": "0551234567", "website": "x"})
assert len(server._book_load()) == 1, "حقل الفخّ"
for i in range(6):
    r = anon.post(R, data={"program": "umrah:U2", "name": f"اسم رقم {i}", "phone": "0551234567"})
assert "err=" in r.headers["Location"] and len(server._book_load()) == 5, "حدّ الإرسال (٥ في ١٠ دقائق)"
bk = c.get("/bookings").get_data(as_text=True)
assert "عبدالله الكتبي" in bk and "wa.me/971551234567" in bk and 'class="nav-count">5<' in bk
assert "(5,900 درهم للفرد)" in bk
assert "طلبات الحجز" in v.get("/bookings").get_data(as_text=True)
first = next(x for x in server._book_load() if x["name"] == "عبدالله الكتبي")
v.post(f"/bookings/{first['id']}/convert")
assert next(x for x in server._book_load() if x["id"] == first["id"])["status"] == "new", "المطّلع لا يحوّل"
e.post(f"/bookings/{first['id']}/contacted")
assert next(x for x in server._book_load() if x["id"] == first["id"])["status"] == "contacted"
r = e.post(f"/bookings/{first['id']}/convert")
assert r.status_code == 302 and "/hujjaj/" in r.headers["Location"]
new = recs()[-1]
assert new.full_name_ar == "عبدالله الكتبي" and new.trip == "U1" and new.room_type == "ثنائي"
assert new.phone == "0551234567" and "3 أشخاص" in new.notes and new.program_value, new.program_value
assert next(x for x in server._book_load() if x["id"] == first["id"])["status"] == "converted"
n = len(recs())
e.post(f"/bookings/{first['id']}/convert")
assert len(recs()) == n, "لا يُحوَّل مرّتين"
c.get("/switch/hajj")
other = next(x for x in server._book_load() if x["status"] == "new")
r = c.post(f"/bookings/{other['id']}/convert")
assert "بدّل النظام" in c.get("/bookings").get_data(as_text=True), "التحويل في نظام الطلب فقط"
print("[ok] الصفحة العامة: نشر للمدير، بلا بيانات أشخاص، طلب مشفّر بحماية، تحويل إلى سجلّ")

# ---- ٤) حذف طلب حجز — للمدير حصراً ----
items = server._book_load()
n0 = len(items)
victim = next(x for x in items if x["status"] == "new")
assert 'class="inline bk-del"' in c.get("/bookings", query_string={"show": "all"}).get_data(as_text=True)
assert 'class="inline bk-del"' not in e.get("/bookings", query_string={"show": "all"}).get_data(as_text=True)
assert 'class="inline bk-del"' not in v.get("/bookings", query_string={"show": "all"}).get_data(as_text=True)
for cl in (e, v, anon):                                  # المحرّر والمطّلع والزائر لا يحذفون
    cl.post(f"/bookings/{victim['id']}/delete")
assert len(server._book_load()) == n0 and any(x["id"] == victim["id"] for x in server._book_load())
r = c.post(f"/bookings/{victim['id']}/delete", query_string={"show": "all"})
assert r.status_code == 302 and "show=all" in r.headers["Location"]
assert len(server._book_load()) == n0 - 1 and not any(x["id"] == victim["id"] for x in server._book_load())
assert "حُذف طلب" in c.get("/bookings").get_data(as_text=True)
assert "حذف طلب حجز" in c.get("/audit").get_data(as_text=True), "يُسجَّل في سجلّ التدقيق"
conv = next(x for x in server._book_load() if x["status"] == "converted")
c.post(f"/bookings/{conv['id']}/delete")
app_mode.set_mode(app_mode.UMRAH)
assert any(r.uid == conv["uid"] for r in storage.load_records(session=SESS)[0]), "السجلّ المُنشأ يبقى"
assert c.post("/bookings/غير-موجود/delete").status_code == 302 and len(server._book_load()) == n0 - 2
print("[ok] حذف طلبات الحجز: للمدير حصراً، بتأكيد، ويُسجَّل، والسجلّ المُنشأ منه يبقى")

print("ALL OK")
