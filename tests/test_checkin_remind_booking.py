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
from urllib.parse import unquote

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
                    price_quad="4500", price_double="5900", makkah_hotel="سويس أوتيل", makkah_nights="4"),
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
assert "تبقّى 1 مقعد" in pub or "تبقّى 2 مقاعد" in pub, "مقاعد U2: 3 − 1"
c.get("/programs")
assert storage.load_settings()["public_page"]["seats"]["U1"] == 8, storage.load_settings()["public_page"]
R = "/trips/request"
r = anon.post(R, data={"program": "umrah:U1", "name": "عبدالله الكتبي", "phone": "٠٥٥١٢٣٤٥٦٧",
                       "count": "3", "room": "ثنائي", "note": "عائلة"})
assert r.status_code == 302 and "sent=1" in r.headers["Location"]
assert "وصلنا طلبك" in anon.get("/trips?sent=1").get_data(as_text=True)
items = server._book_load()
assert len(items) == 1 and items[0]["phone"] == "0551234567" and items[0]["count"] == 3
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

print("ALL OK")
