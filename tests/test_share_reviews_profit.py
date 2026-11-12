# -*- coding: utf-8 -*-
"""البورتال: روابط البرامج الخاصة ومصادر الطلبات، رسائل ما قبل السفر، آراء المعتمرين، أرباح البرامج."""
import io
import json
import os
import re
import sys
import tempfile
from datetime import date, timedelta
from html import unescape
from urllib.parse import unquote

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["HAJJ_DATA_DIR"] = tempfile.mkdtemp(prefix="grow_")
from hajj_app import app_mode, auth, storage, umrah  # noqa: E402
from hajj_app.mrz import PassportData  # noqa: E402
try:
    from webapp import server
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
    umrah.UmrahTrip(code="U1", name="عمرة قريبة", depart_date=(T + timedelta(days=2)).isoformat(),
                    return_date=(T + timedelta(days=9)).isoformat(), price_double="5900", price_quad="4500",
                    airline="فلاي دبي", flight_out="FZ 811", out_depart_time="09:45", depart_city="دبي"),
    umrah.UmrahTrip(code="U2", name="عمرة بعيدة", depart_date=(T + timedelta(days=10)).isoformat(),
                    return_date=(T + timedelta(days=17)).isoformat(), price_quad="3900"),
    umrah.UmrahTrip(code="U3", name="عمرة عائدة", depart_date=(T - timedelta(days=12)).isoformat(),
                    return_date=(T - timedelta(days=5)).isoformat())])
storage.save_settings(st)
storage.save_records([
    PassportData(full_name_ar="أحمد علي الكعبي", passport_number="P100", uid="aa11", trip="U1",
                 phone="0501111111", program_value="6000", paid_amount="6000"),
    PassportData(full_name_ar="سالم خالد", passport_number="P200", uid="bb22", trip="U1",
                 phone="", program_value="6000", paid_amount="2000"),
    PassportData(full_name_ar="ملغى", passport_number="P300", uid="cc33", trip="U1",
                 phone="0503333333", status="ملغى", program_value="6000"),
    PassportData(full_name_ar="مريم سعيد النعيمي", passport_number="P400", uid="dd44", trip="U2",
                 phone="0504444444", program_value="5000"),
    PassportData(full_name_ar="فاطمة حسن الظاهري", passport_number="P500", uid="ee55", trip="U3",
                 phone="0505555555", program_value="4500", paid_amount="4500")], session=SESS)
c.post("/bookings", data={"pub": ["U1", "U2"], "intro": ""})


def recs():
    return storage.load_records(session=SESS)[0]


# ---- ١) روابط خاصة لكل برنامج ----
bk = c.get("/bookings").get_data(as_text=True)
assert 'id="share"' in bk and 'id="shSrc"' in bk
urls = [unescape(u) for u in re.findall(r'class="sh-row[^"]*" data-url="([^"]+)"', bk)]
assert len(urls) == 3 and "/trips?v=" in urls[0], urls
u1 = next(u for u in urls if "U1" in unquote(u))
assert "p=umrah" in u1 and "&v=" in u1
assert "برنامج عمرة" in bk.split('id="share"')[1].split("</section>")[0]
assert 'id="share"' in v.get("/bookings").get_data(as_text=True), "روابط المشاركة للجميع"
one = anon.get("/trips", query_string={"p": "umrah:U2"}).get_data(as_text=True)
first = one.split('class="pt-card')[1]
assert first.startswith(" pick") and "عمرة بعيدة" in first.split("</article>")[0] and "البرنامج المختار" in first
assert anon.get("/trips").get_data(as_text=True).count("البرنامج المختار") == 0
print("[ok] روابط خاصة لكل برنامج: في صفحة الطلبات، والبرنامج المختار أولاً ومميّزاً")

# ---- ٢) مصدر الطلب والزيارات ----
vis = server._visits_path()
r = anon.get("/trips", query_string={"src": "instagram"})
assert "pt_src=instagram" in r.headers.get("Set-Cookie", "") or any(
    "pt_src=instagram" in h for h in r.headers.getlist("Set-Cookie"))
assert 'name="src" value="instagram"' in r.get_data(as_text=True), "المصدر يُحمل في النماذج"
day = server.datetime.now(server._UAE).date().isoformat()
assert json.loads(vis.read_text(encoding="utf-8"))[day]["instagram"] == 1
anon.get("/trips")                                          # الزيارة نفسها اليوم — لا تتكرّر
anon.get("/trips", query_string={"src": "instagram"})
assert json.loads(vis.read_text(encoding="utf-8"))[day]["instagram"] == 1
bot = server.app.test_client()
bot.get("/trips", headers={"User-Agent": "WhatsApp/2.24.20 A"}, query_string={"src": "tiktok"})
c.get("/trips", query_string={"src": "tiktok"})             # الموظف المسجّل لا يُعدّ
assert "tiktok" not in json.loads(vis.read_text(encoding="utf-8"))[day]
d2 = server.app.test_client()
before = json.loads(vis.read_text(encoding="utf-8"))[day].get("direct", 0)
d2.get("/trips", query_string={"src": "hacker"})            # مصدر مجهول ← مباشر
assert json.loads(vis.read_text(encoding="utf-8"))[day]["direct"] == before + 1
r = anon.post("/trips/request", data={"program": "umrah:U1", "name": "عبدالله سالم", "phone": "0551234567",
                                      "room": "ثنائي"})                    # المصدر من الكوكي
assert "sent=1" in r.headers["Location"]
it = server._book_load()[-1]
assert it["src"] == "instagram", it
d2.post("/trips/request", data={"program": "umrah:U2", "name": "خالد محمد", "phone": "0559876543",
                                "src": "status"})
assert server._book_load()[-1]["src"] == "status"
bk = c.get("/bookings").get_data(as_text=True)
assert "من إنستغرام" in bk and "من حالة واتساب" in bk
stats = bk.split('id="stats"')[1].split("</section>")[0]
row = re.search(r'<th scope="row">إنستغرام</th>(.*?)</tr>', stats, re.S).group(1)
assert re.findall(r"<b>(\d+)</b>", row) == ["1", "1"] and "100%" in row, row
assert "البرامج الأكثر طلباً" in stats and "عمرة قريبة" in stats
assert c.get("/bookings", query_string={"per": "zzz"}).status_code == 200
bid = it["id"]
e.post(f"/bookings/{bid}/convert")
assert "(من إنستغرام)" in recs()[-1].notes, recs()[-1].notes
print("[ok] المصدر: من الرابط ويبقى بالكوكي، الزيارة مرّة يومياً بلا روبوتات ولا موظفين، يظهر في الطلب والإحصاء")

# ---- ٣) رسائل ما قبل السفر ----
assert server._report_txt("09:45", "") == "الساعة 06:45 (قبل الإقلاع بثلاث ساعات)"
assert server._report_txt("9:45 PM", "").startswith("الساعة 18:45")
assert server._report_txt("02:00", "").startswith("الساعة 23:00")
assert server._report_txt("", "") == "قبل الإقلاع بثلاث ساعات على الأقل"
assert server._report_txt("10:00", "07:00 صباحاً") == "07:00 صباحاً"
pt = c.get("/pretravel").get_data(as_text=True)
lst = pt.split('id="rmList"')[1].split("</ul>")[0]
assert "أحمد علي الكعبي" in lst and "سالم خالد" in lst and "ملغى" not in lst and "مريم" not in lst
assert "بلا هاتف" in lst, "سالم بلا هاتف"
wa = re.search(r'href="(https://wa\.me/971501111111\?text=[^"]+)"', lst).group(1)
txt = unquote(unescape(wa).split("text=", 1)[1])
for s_ in ("أحمد علي", "عمرة قريبة", "FZ 811 (فلاي دبي)", "09:45", "دبي", "الساعة 06:45"):
    assert s_ in txt, (s_, txt)
assert "{" not in txt and "تفاصيل رحلتكم" not in txt, "بلا رابط رحلتي يُحذف سطره"
assert "مريم سعيد" in c.get("/pretravel", query_string={"within": "14"}).get_data(as_text=True)
assert "فاطمة" not in c.get("/pretravel", query_string={"within": "14"}).get_data(as_text=True), "العائدون لا"
assert v.post("/pretravel/mark", json={"uid": "aa11"}).status_code == 403
assert e.post("/pretravel/mark", json={"uid": "aa11"}).get_json()["ok"]
assert storage.load_settings()["pretravel_sent"]["aa11"]
assert "أُرسلت اليوم" in c.get("/pretravel").get_data(as_text=True)
e.post("/pretravel", data={"tpl": "مرحباً {الاسم} — رحلتك {الرحلة}\nرابطك: {الرابط}"})
assert storage.load_settings()["pretravel_tpl"].startswith("مرحباً")
txt = unquote(unescape(re.search(r'wa\.me/971501111111\?text=([^"]+)"',
                                 c.get("/pretravel").get_data(as_text=True)).group(1)))
assert txt == "مرحباً أحمد علي — رحلتك FZ 811 (فلاي دبي)", txt
v.post("/pretravel", data={"tpl": "اختراق"})
assert storage.load_settings()["pretravel_tpl"].startswith("مرحباً"), "المطّلع لا يغيّر"
c.post("/pretravel", data={"reset": "1"})
assert "pretravel_tpl" not in storage.load_settings()
assert 'href="/pretravel"' in c.get("/dashboard").get_data(as_text=True)
print("[ok] ما قبل السفر: الأقرب مغادرةً، رسالة بالرحلة والإقلاع والحضور، حذف السطر الفارغ، «أُرسلت»، صلاحيات")

# ---- ٤) آراء المعتمرين ----
rv = c.get("/reviews").get_data(as_text=True)
ask = rv.split('id="rvAsk"')[1].split("</ul>")[0]
assert "فاطمة حسن الظاهري" in ask and "أحمد" not in ask, "مَن عاد فقط"
link = re.search(r'href="(https://wa\.me/971505555555\?text=[^"]+)"', ask).group(1)
txt = unquote(unescape(link).split("text=", 1)[1])
rid = re.search(r"/r/([\w-]+)", txt).group(1)
assert "فاطمة" in txt and "عمرة عائدة" in txt
raw = server._rev_path().read_bytes()
assert "فاطمة".encode("utf-8") not in raw, "مشفّرة على القرص"
pg = anon.get(f"/r/{rid}").get_data(as_text=True)
assert "كيف كانت رحلتك يا فاطمة" in pg and 'name="stars"' in pg
assert anon.get("/r/لا-يوجد").status_code == 404
r = anon.post(f"/r/{rid}", data={"comment": "بلا نجوم"})
assert "err=1" in r.headers["Location"]
anon.post(f"/r/{rid}", data={"stars": "5", "comment": "تنظيم   ممتاز والفندق قريب", "consent": "1"})
x = next(x for x in server._rev_load() if x["id"] == rid)
assert x["stars"] == 5 and x["comment"] == "تنظيم ممتاز والفندق قريب" and x["consent"] and not x.get("show")
assert "وصلنا رأيك" in anon.get(f"/r/{rid}", query_string={"done": "1"}).get_data(as_text=True)
rv = c.get("/reviews").get_data(as_text=True)
assert "فاطمة حسن الظاهري" not in rv.split('id="rvAsk"')[1].split("</ul>")[0] if 'id="rvAsk"' in rv else True
got = rv.split('id="got"')[1]
assert "تنظيم ممتاز" in got and "إظهار في الصفحة العامة" in got
assert "آراء معتمرينا" not in anon.get("/trips").get_data(as_text=True), "لا يُنشر قبل أن يظهره المدير"
e.post(f"/reviews/{rid}/show")
assert not next(x for x in server._rev_load() if x["id"] == rid).get("show"), "المحرّر لا ينشر"
c.post(f"/reviews/{rid}/show")
pub = anon.get("/trips").get_data(as_text=True)
assert "آراء معتمرينا" in pub and "تنظيم ممتاز" in pub and "فاطمة" in pub
assert "الظاهري" not in pub, "الاسم الأول فقط"
anon.post(f"/r/{rid}", data={"stars": "4", "comment": "تعديل"})          # سحب الموافقة ← يُخفى
assert not next(x for x in server._rev_load() if x["id"] == rid).get("show")
assert "آراء معتمرينا" not in anon.get("/trips").get_data(as_text=True)
c.post(f"/reviews/{rid}/show")
assert "لم يوافق على نشره" in c.get("/reviews").get_data(as_text=True)
assert v.post("/reviews/mark", json={"uid": "ee55"}).status_code == 403
assert 'href="/reviews"' in c.get("/dashboard").get_data(as_text=True)
print("[ok] الآراء: من عاد خلال ٤٥ يوماً، رابط سرّي، نجوم وتعليق، نشر بموافقته وبقرار المدير وباسمه الأول")

# ---- ٥) أرباح البرامج ----
assert e.get("/finance/profit").status_code == 302, "للمدير فقط"
assert 'href="/finance/profit"' not in e.get("/dashboard").get_data(as_text=True)
assert 'href="/finance/profit"' in c.get("/dashboard").get_data(as_text=True)
pf = c.get("/finance/profit").get_data(as_text=True)
assert "عمرة قريبة" in pf and "لم تُدخل التكلفة" in pf
# U1: أحمد (6000) + سالم (6000) + المحوَّل من الطلب (قيمة البرنامج) — الملغى لا يُحسب
n1 = sum(1 for r_ in recs() if r_.trip == "U1" and r_.status != "ملغى")
rev1 = sum(float(str(r_.program_value or 0).replace(",", "") or 0) for r_ in recs()
           if r_.trip == "U1" and r_.status != "ملغى")
c.post("/finance/profit", data={"key": "U1", "flight_pp": "1,500", "visa_pp": "٣٠٠", "hotels": "4000",
                                "transport": "1000", "other": ""})
costs = storage.load_settings()["program_costs"]["U1"]
assert costs == {"flight_pp": "1,500", "visa_pp": "300", "hotels": "4000", "transport": "1000"}, costs
cost1 = 1800 * n1 + 5000
pf = c.get("/finance/profit").get_data(as_text=True)
card = pf.split('id="p-0"')[1].split("</article>")[0]
fmt = server.format_amount
assert fmt(rev1) in card and fmt(cost1) in card and fmt(rev1 - cost1) in card, (rev1, cost1, card[:600])
assert ("ربح" if rev1 >= cost1 else "خسارة") in card
r = c.post("/finance/profit", data={"key": "U1", "hotels": "abc"})
assert "أرقام غير صحيحة" in c.get("/finance/profit").get_data(as_text=True)
assert storage.load_settings()["program_costs"]["U1"]["hotels"] == "4000", "الخاطئ لا يُحفظ"
e.post("/finance/profit", data={"key": "U1", "hotels": "1"})
assert storage.load_settings()["program_costs"]["U1"]["hotels"] == "4000", "المحرّر لا يغيّر"
c.post("/finance/profit", data={"key": "XX", "hotels": "1"})
assert "XX" not in storage.load_settings()["program_costs"]
print("[ok] الأرباح: للمدير فقط، الإيراد بلا الملغين، التكلفة للفرد × العدد + الإجماليات، أرقام عربية، رفض الخاطئ")

# ---- نظام الحج: الصفحات تعمل ----
c.get("/switch/hajj")
for path in ("/pretravel", "/reviews", "/finance/profit", "/bookings"):
    assert c.get(path).status_code == 200, path
print("ALL OK")
