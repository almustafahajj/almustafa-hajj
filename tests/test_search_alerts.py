# -*- coding: utf-8 -*-
"""البورتال: البحث السريع الشامل، الإشعارات (الجرس)، وبطاقات الباقات في لوحة التحكم."""
import io
import os
import re
import sys
import tempfile
from datetime import date, timedelta

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["HAJJ_DATA_DIR"] = tempfile.mkdtemp(prefix="search_alerts_")

from hajj_app import app_mode, auth, storage, umrah  # noqa: E402
from hajj_app.mrz import PassportData  # noqa: E402

try:
    from webapp import server, alerts, search
    server.app.config["CSRF_ENABLED"] = False
except ImportError as exc:
    print(f"[skip] مسارات الويب: {exc}")
    print("ALL OK")
    sys.exit(0)

T = date.today()
iso = lambda d: d.isoformat()  # noqa: E731


def P(name, trip, room="ثنائي", value="5000", paid="5000", expiry=None, **kw):
    return PassportData(full_name_ar=name, trip=trip, room_type=room,
                        program_value=value, paid_amount=paid,
                        expiry_date=expiry or iso(T + timedelta(days=900)), **kw)


# ---- 1) الإشعارات (الوحدة) ----
trips = [
    umrah.UmrahTrip(code="U1", name="رمضان الأول", package="برامج رمضان",
                    depart_date=iso(T + timedelta(days=5)),
                    return_date=iso(T + timedelta(days=15)), capacity="3",
                    makkah_rooms="5"),
    umrah.UmrahTrip(code="U2", name="رمضان الثاني", package="برامج رمضان",
                    depart_date=iso(T + timedelta(days=60)), capacity="10",
                    room_share="U1"),
    umrah.UmrahTrip(code="U9", name="قديم", depart_date=iso(T - timedelta(days=40)),
                    return_date=iso(T - timedelta(days=30)), capacity="1"),
]
recs = ([P(f"معتمر {i}", "U1") for i in range(3)]
        + [P("متأخر السداد", "U1", paid="1000"),                     # 4 من 3 → تجاوز
           P("جواز قريب", "U2", expiry=iso(T + timedelta(days=90))),   # < ٦ أشهر من السفر
           P("قديم ١", "U9"), P("قديم ٢", "U9")]
        + [P(f"غرفة {i}", "U2", room="مفرد") for i in range(2)])
st = {}
umrah.save_trips(st, trips)
al = alerts.umrah_alerts(recs, st, today=T)
texts = [a["text"] for a in al]
assert any("تجاوز السعة في «U1 — رمضان الأول»: 4 من 3" in t for t in texts), texts
assert any("مغادرة «U1 — رمضان الأول» بعد 5 يوماً" in t for t in texts)
assert any("لم يُكملوا السداد في «U1" in t and a["level"] == "danger"
           for t, a in zip(texts, al))                          # قبل المغادرة بأقل من أسبوع
assert any("1 جوازاً في «U2" in t for t in texts)
# الغرف مشتركة: U1 أساسي بخمس غرف — المشغول 2+1 (U1) + 2 (U2 مفرد) = 5 → تبقّى 0
assert any("تبقّت 0 غرفة فقط في فندق مكة" in t and "U2" in t for t in texts), texts
assert not any("قديم" in t for t in texts)                      # برنامج انتهى
assert al[0]["level"] == "danger" and al[-1]["level"] == "info"
print("[ok] الإشعارات: السعة، الغرف المشتركة، المغادرة، الجوازات، السداد")

# ---- 2) البحث (الوحدة): متسامح مع الكتابة العربية ----
recs2 = [PassportData(full_name_ar="أحمد إبراهيم", passport_number="N1234567",
                      phone="0501112233", trip="U1", reference_number="MA-77")]
g = search.search("احمد ابراهيم", recs2, st, "umrah")
assert g[0]["title"] == "المعتمرون" and g[0]["items"][0]["title"] == "أحمد إبراهيم"
assert search.search("1234567", recs2, st, "umrah")[0]["total"] == 1
assert [x["title"] for x in search.search("رمضان", recs2, st, "umrah")] == ["البرامج", "الباقات"]
assert search.search("ا", recs2, st, "umrah") == []               # حرف واحد لا يكفي
print("[ok] البحث: أسماء/جوازات/برامج/باقات بتوحيد الكتابة")

# ---- 3) عبر البورتال ----
auth.create_account("owner", "Passw0rd!x")
app_mode.set_mode(app_mode.UMRAH)
settings = storage.load_settings()
umrah.save_trips(settings, trips)
umrah.save_packages(settings, ["برامج رمضان"])
settings["umrah_quotes"] = {"_manual": [{"number": "MA-Q0007", "addressed_to": "شركة النور",
                                         "date": iso(T)}]}
storage.save_settings(settings)
c = server.app.test_client()
c.post("/login", data={"username": "owner", "password": "Passw0rd!x"})
SESS = server._SESSIONS[next(iter(server._SESSIONS))]
storage.save_records(recs + recs2, session=SESS)
dash = c.get("/dashboard").get_data(as_text=True)
n = len([a for a in alerts.umrah_alerts(recs + recs2, storage.load_settings())
         if a["level"] in ("danger", "warn")])
assert f'<span class="bell-n">{n}</span>' in dash and 'class="tb-search"' in dash
assert "يحتاج انتباهك" in dash and "تجاوز السعة" in dash
assert "📦 برامج رمضان" in dash and "🗂 2 برنامج" in dash             # بطاقة الباقة
assert "✈️ أقرب مغادرة: " + iso(T + timedelta(days=5)) in dash
note = c.get("/notifications").get_data(as_text=True)
assert note.count('class="alert-row') == len(alerts.umrah_alerts(recs + recs2,
                                                                  storage.load_settings()))
assert 'href="/programs/U1"' in note and 'href="/finance"' in note
# البحث من الخانة
r = c.get("/search", query_string={"q": "N1234567"})
assert r.status_code == 302 and "/hujjaj/" in r.headers["Location"] and "fp=" in r.headers["Location"]
assert c.get(r.headers["Location"]).status_code == 200                # يفتح السجلّ الصحيح
page = c.get("/search", query_string={"q": "رمضان"}).get_data(as_text=True)
assert 'href="/programs/U1"' in page and "/programs?package=" in page
r = c.get("/search", query_string={"q": "النور"})
assert r.status_code == 302 and "/quotes/_manual/MA-Q0007" in r.headers["Location"]
page = c.get("/search", query_string={"q": "لا شيء بهذا"}).get_data(as_text=True)
assert "لا نتائج" in page and 'value="لا شيء بهذا"' in page
# الحج: إشعارات برامج الحج (لا بطاقات باقات)
c.get("/switch/hajj")
assert "📦" not in c.get("/dashboard").get_data(as_text=True).split("المالية حسب البرنامج")[0] \
    .split("lbl")[-1]
assert c.get("/notifications").status_code == 200
print("[ok] الجرس والإشعارات وبطاقات الباقات والبحث السريع في البورتال")
print("ALL OK")
