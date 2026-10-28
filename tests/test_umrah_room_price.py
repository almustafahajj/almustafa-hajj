# -*- coding: utf-8 -*-
"""البورتال (العمرة): نوع الغرفة عند إضافة/تعديل معتمر قائمةٌ من أسعار البرنامج
المختار، والسعر يملأ «قيمة البرنامج» تلقائياً (في الصفحة، واحتياطاً عند الحفظ)."""
import io
import os
import re
import sys
import tempfile

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["HAJJ_DATA_DIR"] = tempfile.mkdtemp(prefix="umrah_room_")

from hajj_app import app_mode, auth, storage, umrah  # noqa: E402

# ---- 1) أسعار الغرف من البرنامج ----
t1 = umrah.UmrahTrip(code="U1", name="رمضان", price_single="7,500",
                     price_double="5000", price_triple="", price_quad="3800",
                     price_child="1500")
t2 = umrah.UmrahTrip(code="U2", name="بلا أسعار")
assert umrah.trip_room_prices(t1) == [("مفرد", "7,500"), ("ثنائي", "5000"),
                                      ("رباعي", "3800"),
                                      ("طفل (بدون سرير)", "1500")]
assert umrah.trip_room_prices(t2) == []
assert umrah.trip_room_price([t1, t2], "U1", "ثنائي") == "5000"
assert umrah.trip_room_price([t1, t2], " U1 ", " رباعي ") == "3800"
assert umrah.trip_room_price([t1, t2], "U1", "ثلاثي") == ""     # غير مسعّر
assert umrah.trip_room_price([t1, t2], "U9", "ثنائي") == ""     # برنامج مجهول
assert umrah.trip_room_price([t1, t2], "", "") == ""
print("[ok] أسعار الغرف من البرنامج")

try:
    from webapp import server
    server.app.config["CSRF_ENABLED"] = False     # الحماية تُختبر في test_security
except ImportError as exc:
    print(f"[skip] مسارات الويب: {exc}")
    print("ALL OK")
    sys.exit(0)

auth.create_account("owner", "Passw0rd!x")
app_mode.set_mode(app_mode.UMRAH)
st = storage.load_settings()
umrah.save_trips(st, [t1, t2])
storage.save_settings(st)

c = server.app.test_client()
c.post("/login", data={"username": "owner", "password": "Passw0rd!x"})


def edit(i, data):
    """حفظ صفحة التعديل كما يفعل المتصفّح: مع بصمة السجلّ المعروض."""
    page = c.get(f"/hujjaj/{i}").get_data(as_text=True)
    fp = re.search(r'name="fp" value="([^"]*)"', page).group(1)
    return c.post(f"/hujjaj/{i}", data=dict(data, fp=fp))


def select_opts(html, key):
    m = re.search(r'<select name="%s" id="f_%s">(.*?)</select>' % (key, key),
                  html, re.S)
    assert m, key
    return re.findall(r'<option value="([^"]*)"\s*(selected)?>([^<]*)</option>',
                      m.group(1))


# ---- 2) صفحة الإضافة ----
html = c.get("/hujjaj/new").get_data(as_text=True)
trip_opts = select_opts(html, "trip")
assert ("U1", "", "U1 — رمضان") in trip_opts, trip_opts
room_opts = select_opts(html, "room_type")       # بلا برنامج: كل الأنواع
assert [v for v, _s, _t in room_opts] == [""] + [n for _k, n, _c in
                                                 umrah.ROOM_TYPES]
import json  # noqa: E402
_P = json.loads(re.search(r"var P = (\{.*?\}), ALL", html, re.S).group(1))
assert _P["U1"] == [["مفرد", "7,500"], ["ثنائي", "5000"], ["رباعي", "3800"],
                    ["طفل (بدون سرير)", "1500"]] and _P["U2"] == []
assert "يُملأ تلقائياً بسعر الفرد" in html
assert 'id="f_program_value"' in html

# ---- 3) الحفظ: السعر يُملأ من البرنامج إن تُرك فارغاً ----
c.post("/hujjaj/new", data={"full_name_ar": "معتمر أول", "trip": "U1",
                            "room_type": "ثنائي", "program_value": ""})
c.post("/hujjaj/new", data={"full_name_ar": "معتمر ثانٍ", "trip": "U1",
                            "room_type": "مفرد", "program_value": "7000"})
c.post("/hujjaj/new", data={"full_name_ar": "معتمر ثالث", "trip": "U2",
                            "room_type": "ثنائي", "program_value": ""})
app_mode.set_mode(app_mode.UMRAH)
recs, _n = storage.load_records(session=server._SESSIONS[
    next(iter(server._SESSIONS))])
by = {r.full_name_ar: r for r in recs}
assert by["معتمر أول"].program_value == "5000"         # من سعر الثنائي
assert by["معتمر ثانٍ"].program_value == "7000"        # المُدخل يدوياً لا يُمسّ
assert by["معتمر ثالث"].program_value == ""            # برنامج بلا أسعار
assert by["معتمر أول"].trip == "U1" and by["معتمر أول"].room_type == "ثنائي"

# ---- 4) صفحة التعديل: أنواع البرنامج بأسعارها، والمختار محدَّد ----
idx = [r.full_name_ar for r in recs].index("معتمر أول")
html = c.get(f"/hujjaj/{idx}").get_data(as_text=True)
room_opts = select_opts(html, "room_type")
assert ("ثنائي", "selected", "ثنائي — 5000") in room_opts, room_opts
assert ("ثلاثي", "", "ثلاثي") not in room_opts                 # غير مسعّر
assert [v for v, _s, _t in room_opts] == ["", "مفرد", "ثنائي", "رباعي",
                                          "طفل (بدون سرير)"]
# قيمة قديمة ليست في أسعار البرنامج تبقى ظاهرة ومختارة
edit(idx, {"full_name_ar": "معتمر أول", "trip": "U1",
                               "room_type": "جناح", "program_value": "5000"})
room_opts = select_opts(c.get(f"/hujjaj/{idx}").get_data(as_text=True),
                        "room_type")
assert ("جناح", "selected", "جناح") in room_opts, room_opts

# ---- 4b) الخدمات وسعر الغرفة الأساسي (توافق سطح المكتب) ----
from hajj_app.mrz import PassportData  # noqa: E402
_sess = server._SESSIONS[next(iter(server._SESSIONS))]
app_mode.set_mode(app_mode.UMRAH)
recs, _n = storage.load_records(session=_sess)
svc_rec = PassportData(full_name_ar="معتمر بخدمات", trip="U1", room_type="ثنائي",
                       room_value="5000", program_value="6200")
svc_rec.umrah_services = [{"name": "تأمين طبّي", "price": "1200"}]
recs.append(svc_rec)
storage.save_records(recs, session=_sess)
sidx = len(recs) - 1
html = c.get(f"/hujjaj/{sidx}").get_data(as_text=True)
assert "var SVC = 1200" in html and 'var built = "U1"' in html
# تعديل حقل آخر فقط: لا يتغيّر الأساس ولا القيمة
edit(sidx, {"full_name_ar": "معتمر بخدمات", "trip": "U1",
                                "room_type": "ثنائي", "program_value": "6200",
                                "phone": "0501112233"})
app_mode.set_mode(app_mode.UMRAH)
r = storage.load_records(session=_sess)[0][sidx]
assert (r.room_value, r.program_value) == ("5000", "6200"), (r.room_value,
                                                              r.program_value)
# تغيير الغرفة مع ترك القيمة فارغة: الأساس = سعر المفرد، والقيمة = الغرفة + الخدمات
edit(sidx, {"full_name_ar": "معتمر بخدمات", "trip": "U1",
                                "room_type": "مفرد", "program_value": ""})
app_mode.set_mode(app_mode.UMRAH)
r = storage.load_records(session=_sess)[0][sidx]
assert (r.room_value, r.program_value) == ("7,500", "8,700"), (r.room_value,
                                                               r.program_value)
assert r.umrah_services == [{"name": "تأمين طبّي", "price": "1200"}]
print("[ok] السعر = الغرفة + الخدمات، وأساس الغرفة يتبع البرنامج")

# ---- 4c) الموظف المسؤول: قائمة موظفي المكتب ----
STAFF = ["", "أيمن الشهابي", "أحمد الشبراوي", "علاء بريخان", "رامي الشلبي",
         "مريم الحوسني", "محمد صابر"]
assert [v for v, _s, _t in select_opts(c.get("/hujjaj/new").get_data(
    as_text=True), "staff")] == STAFF
edit(sidx, {"full_name_ar": "معتمر بخدمات", "trip": "U1",
                                "room_type": "مفرد", "program_value": "8,700",
                                "staff": "مريم الحوسني"})
opts = select_opts(c.get(f"/hujjaj/{sidx}").get_data(as_text=True), "staff")
assert ("مريم الحوسني", "selected", "مريم الحوسني") in opts
# اسم قديم خارج القائمة يبقى ظاهراً ومختاراً (لا يضيع عند الحفظ)
edit(sidx, {"full_name_ar": "معتمر بخدمات", "staff": "موظف سابق"})
opts = select_opts(c.get(f"/hujjaj/{sidx}").get_data(as_text=True), "staff")
assert ("موظف سابق", "selected", "موظف سابق") in opts and len(opts) == 8
# المواصلات: GMC / FORD
assert [v for v, _s, _t in select_opts(c.get("/hujjaj/new").get_data(
    as_text=True), "transport")] == ["", "GMC", "FORD"]
edit(sidx, {"full_name_ar": "معتمر بخدمات", "transport": "FORD"})
opts = select_opts(c.get(f"/hujjaj/{sidx}").get_data(as_text=True), "transport")
assert ("FORD", "selected", "FORD") in opts
print("[ok] الموظف المسؤول والمواصلات قائمتان منسدلتان")

# ---- 5) الحج كما هو: نوع الغرفة حقل نصّي بلا سكربت أسعار ----
c.get("/switch/hajj")
html = c.get("/hujjaj/new").get_data(as_text=True)
assert '<input name="room_type" id="f_room_type"' in html
assert '<input name="transport" id="f_transport"' in html    # الحج: رقم الباص نصّ حرّ
assert '<input name="staff" id="f_staff"' in html
assert "room_type" not in "".join(re.findall(r"<select[^>]*>", html))
assert "var P = " not in html
print("[ok] نوع الغرفة من البرنامج + ملء قيمة البرنامج تلقائياً")
print("ALL OK")
