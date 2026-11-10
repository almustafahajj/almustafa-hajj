# -*- coding: utf-8 -*-
"""البورتال: لوحة البحث السريع (Ctrl+K) وتنبيه «بيانات ناقصة قبل المغادرة» مع قائمة
من تنقصهم البيانات بالضبط."""
import io
import os
import sys
import tempfile
from datetime import date, timedelta

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["HAJJ_DATA_DIR"] = tempfile.mkdtemp(prefix="smart_")

from hajj_app import app_mode, auth, storage, umrah  # noqa: E402
from hajj_app.mrz import PassportData  # noqa: E402

try:
    from webapp import server, alerts
    server.app.config["CSRF_ENABLED"] = False
except ImportError as exc:
    print(f"[skip] مسارات الويب: {exc}")
    print("ALL OK")
    sys.exit(0)

T = date.today()
iso = date.isoformat

# ---- ١) البيانات الناقصة لكل سجلّ ----
full = PassportData(full_name_ar="كامل", passport_number="P1", expiry_date="2030-01-01",
                    visa_number="V1", phone="0501", permit_status="نسك", vaccination="نعم")
assert alerts.missing_fields(full, "umrah") == [] and alerts.missing_fields(full, "hajj") == []
part = PassportData(full_name_ar="ناقص", passport_number="P2", expiry_date="2030-01-01")
assert alerts.missing_fields(part, "umrah") == ["التأشيرة", "الهاتف"]
assert alerts.missing_fields(part, "hajj") == ["التأشيرة", "الهاتف", "التصريح", "التطعيم"]

# ---- ٢) التنبيه: خلال ٣ أسابيع من المغادرة فقط، وعاجل في الأسبوع الأخير ----
trips = [umrah.UmrahTrip(code="U1", name="قريبة", depart_date=iso(T + timedelta(days=5))),
         umrah.UmrahTrip(code="U2", name="متوسطة", depart_date=iso(T + timedelta(days=15))),
         umrah.UmrahTrip(code="U3", name="بعيدة", depart_date=iso(T + timedelta(days=40)))]
st = {}
umrah.save_trips(st, trips)
recs = [PassportData(full_name_ar="أحمد", passport_number="P1", expiry_date="2030-01-01",
                     phone="0501", trip="U1"),                                   # ينقصه التأشيرة
        PassportData(full_name_ar="مريم", passport_number="P2", expiry_date="2030-01-01",
                     visa_number="V2", phone="0502", trip="U1"),                 # مكتمل
        PassportData(full_name_ar="خالد", trip="U2"),                            # ينقصه الكثير
        PassportData(full_name_ar="سعيد", trip="U3")]                            # الرحلة بعيدة
al = [a for a in alerts.umrah_alerts(recs, st, today=T) if a["kind"] == "missing"]
assert len(al) == 2, [a["text"] for a in al]
u1 = next(a for a in al if a["ref"] == "U1")
assert u1["level"] == "danger" and "1 شخصاً (التأشيرة 1)" in u1["text"], u1["text"]
u2 = next(a for a in al if a["ref"] == "U2")
assert u2["level"] == "warn" and "بعد 15 يوماً" in u2["text"]
assert not any(a["ref"] == "U3" for a in al), "لا تنبيه لرحلة بعد ٤٠ يوماً"

# ---- ٣) عبر البورتال: الرابط يفتح من تنقصهم البيانات في الرحلة بالضبط ----
owner, _rk = auth.create_account("owner", "Passw0rd!x")
auth.add_account(owner, "sara", "Passw0rd!s", role="editor")
auth.add_account(owner, "view", "Passw0rd!v", role="viewer")
c = server.app.test_client()
c.post("/login", data={"username": "owner", "password": "Passw0rd!x"})
SESS = next(v for v in server._SESSIONS.values() if v.username == "owner")
app_mode.set_mode(app_mode.UMRAH)
settings = storage.load_settings()
umrah.save_trips(settings, trips)
storage.save_settings(settings)
storage.save_records(recs, session=SESS)
note = c.get("/notifications").get_data(as_text=True)
assert "بيانات ناقصة قبل مغادرة" in note and 'href="/hujjaj?grp=U1&amp;need=1"' in note, note[-3000:]
lst = c.get("/hujjaj?grp=U1&need=1").get_data(as_text=True)
assert "أحمد" in lst and "مريم" not in lst and "خالد" not in lst
assert "من تنقصهم بيانات السفر" in lst and "ينقص: التأشيرة" in lst
assert 'name="need" value="1"' in lst and 'name="grp" value="U1"' in lst, "البحث يحفظ النطاق"
allneed = c.get("/hujjaj?need=1").get_data(as_text=True)
assert "خالد" in allneed and "سعيد" in allneed and "مريم" not in allneed
assert "ينقص:" not in c.get("/hujjaj").get_data(as_text=True), "التلميح في عرض النواقص فقط"

# ---- ٤) لوحة البحث السريع ----
dash = c.get("/dashboard").get_data(as_text=True)
assert 'id="cmdk"' in dash and 'id="cmdData"' in dash and "<kbd>Ctrl</kbd>" in dash
import json  # noqa: E402
assert "إدارة الحسابات" in [x["t"] for x in json.loads(dash.split('id="cmdData">')[1].split("</script>")[0])]
j = c.get("/search/suggest", query_string={"q": "أحمد"}).get_json()
assert j["q"] == "أحمد" and j["groups"][0]["title"] == "المعتمرون"
item = j["groups"][0]["items"][0]
assert item["t"] == "أحمد" and item["u"].startswith("/hujjaj/") and item["i"] == "user"
assert j["all"].startswith("/search?q=")
assert c.get("/search/suggest", query_string={"q": "ا"}).get_json()["groups"] == [], "حرف واحد لا يكفي"
assert c.get("/search/suggest", query_string={"q": "U1"}).get_json()["groups"], "البرامج أيضاً"
anon = server.app.test_client()
assert anon.get("/search/suggest?q=أحمد").status_code in (302, 401), "لا اقتراحات بلا دخول"
page = c.get("/search", query_string={"q": "خالد"})
assert page.status_code == 302 and "/hujjaj/" in page.headers["Location"], "صفحة البحث الكاملة كما هي"

# الصلاحيات في الإجراءات السريعة
def cmds(client):
    html = client.get("/dashboard").get_data(as_text=True)
    return [x["t"] for x in json.loads(html.split('id="cmdData">')[1].split("</script>")[0])]
e = server.app.test_client()
e.post("/login", data={"username": "sara", "password": "Passw0rd!s"})
ec = cmds(e)
assert "إدارة الحسابات" not in ec and "إضافة سجلّ جديد" in ec
v = server.app.test_client()
v.post("/login", data={"username": "view", "password": "Passw0rd!v"})
vc = cmds(v)
assert "إضافة سجلّ جديد" not in vc and "استيراد من إكسل" not in vc and "السجلّات والبيانات" in vc

print("ALL OK")
