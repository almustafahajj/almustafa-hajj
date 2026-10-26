# -*- coding: utf-8 -*-
"""البورتال (العمرة): قائمة البرامج تعرض الطيران قبل السعة والمتبقّي، وخانة
«الغرف المتبقّية» لكل فندق = عدد غرفه − الغرف المشغولة حسب أنواع الغرف."""
import io
import os
import re
import sys
import tempfile

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["HAJJ_DATA_DIR"] = tempfile.mkdtemp(prefix="prog_list_")

from hajj_app import app_mode, auth, storage, umrah  # noqa: E402
from hajj_app.mrz import PassportData  # noqa: E402


def P(room, trip="U1"):
    return PassportData(full_name_ar="م", room_type=room, trip=trip)


# ---- 1) الغرف المشغولة حسب أنواع الغرف ----
assert umrah.rooms_needed([]) == 0
assert umrah.rooms_needed([P("ثنائي")] * 5) == 3                 # ٥ ÷ ٢ ↑
assert umrah.rooms_needed([P("ثلاثي")] * 3 + [P("رباعي")] * 5) == 1 + 2
assert umrah.rooms_needed([P("مفرد")] * 2 + [P("طفل (بدون سرير)"), P("رضيع"),
                                            P("طفل"), P("")]) == 2
assert umrah.rooms_needed([P("جناح غرفة وصالة")] * 2) == 2        # غير معروف: لكلٍّ غرفة

t = umrah.UmrahTrip(code="U1", makkah_rooms="10", madinah_rooms="", airline="الاتحاد")
recs = [P("ثنائي")] * 6 + [P("ثنائي", trip="U2")] * 8              # U2 لا يُحسب
assert umrah.trip_rooms_left(t, recs) == [("مكة", 10, 3, 7)]
t.madinah_rooms = "2"
assert umrah.trip_rooms_left(t, recs) == [("مكة", 10, 3, 7), ("المدينة", 2, 3, -1)]
assert umrah.trip_rooms_left(umrah.UmrahTrip(code="U9"), recs) == []
print("[ok] الغرف المشغولة والمتبقّية")

try:
    from webapp import server
except ImportError as exc:
    print(f"[skip] مسارات الويب: {exc}")
    print("ALL OK")
    sys.exit(0)

# ---- 2) صفحة البرامج ----
auth.create_account("owner", "Passw0rd!x")
app_mode.set_mode(app_mode.UMRAH)
st = storage.load_settings()
umrah.save_trips(st, [
    umrah.UmrahTrip(code="U1", name="رمضان", airline="الاتحاد", flight_out="EY611",
                    flight_ret="EY612", capacity="20", makkah_rooms="10",
                    madinah_rooms="2"),
    umrah.UmrahTrip(code="U2", name="شعبان")])
storage.save_settings(st)
c = server.app.test_client()
c.post("/login", data={"username": "owner", "password": "Passw0rd!x"})
SESS = server._SESSIONS[next(iter(server._SESSIONS))]
app_mode.set_mode(app_mode.UMRAH)
storage.save_records(recs, session=SESS)

html = c.get("/programs").get_data(as_text=True)
heads = re.findall(r"<th>([^<]*)</th>", html)
assert heads.index("الطيران") < heads.index("السعة") < heads.index("المتبقّي") \
    < heads.index("الغرف المتبقّية"), heads
rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S)[1:]
u1 = next(r for r in rows if "<td>U1</td>" in r)
cells = [re.sub(r"<[^>]+>", " ", x).split() for x in re.findall(r"<td>(.*?)</td>", u1, re.S)]
assert cells[heads.index("الطيران")] == ["الاتحاد", "EY611", "/", "EY612"], cells
assert cells[heads.index("السعة")] == ["20"] and cells[heads.index("المتبقّي")] == ["14"]
assert cells[heads.index("الغرف المتبقّية")] == ["مكة:", "7", "المدينة:", "⚠", "زيادة", "1"], cells
assert "color:#C0392B" in u1                                     # تجاوز بالأحمر
u2 = next(r for r in rows if "<td>U2</td>" in r)
u2c = [re.sub(r"<[^>]+>", " ", x).split() for x in re.findall(r"<td>(.*?)</td>", u2, re.S)]
assert u2c[heads.index("الطيران")] == ["—"] and u2c[heads.index("الغرف المتبقّية")] == ["—"]
print("[ok] صفحة البرامج: الطيران قبل السعة والمتبقّي + الغرف المتبقّية")

# ---- 3) الباقات ----
c.post("/programs/packages/add", data={"name": "برامج ديسمبر"})
c.post("/programs/packages/add", data={"name": "  برامج   رمضان "})   # تُنظَّف المسافات
assert "msg=" in c.post("/programs/packages/add",
                        data={"name": "برامج ديسمبر"}).headers["Location"]  # مكرّرة
app_mode.set_mode(app_mode.UMRAH)
assert umrah.load_packages(storage.load_settings()) == ["برامج ديسمبر", "برامج رمضان"]
# برنامج جديد من زرّ الباقة يأتي بها مختارة، والباقات الأخرى في القائمة
new = c.get("/programs/new", query_string={"package": "برامج رمضان"}).get_data(as_text=True)
assert 'name="package" value="برامج رمضان"' in new and '<option value="برامج ديسمبر">' in new
form = {k: "" for k in server._PROG_KEYS}
form.update(code="U3", name="رمضان الأولى", package="برامج رمضان")
c.post("/programs/save", data=form)
form.update(code="U1", orig="U1", name="رمضان", package="برامج ديسمبر",
            airline="الاتحاد", capacity="20", makkah_rooms="10", madinah_rooms="2",
            flight_out="EY611", flight_ret="EY612")
c.post("/programs/save", data=form)
html = c.get("/programs").get_data(as_text=True)
# الباقات قوائم مستقلّة في القائمة الجانبية تحت «برامج العمرة»
side = re.findall(r'class="navlink subnav[^"]*" href="([^"]+)">📦 ([^<]+)</a>', html)
assert [n for _h, n in side] == ["برامج ديسمبر", "برامج رمضان"], side
assert "<td>U1</td>" in html and "<td>U2</td>" in html     # الصفحة العامة: الكل
dec = c.get("/programs", query_string={"package": "برامج ديسمبر"}).get_data(as_text=True)
table = dec.split("<tbody>")[1].split("</tbody>")[0]
assert "<td>U1</td>" in table and "<td>U3</td>" not in table and "<td>U2</td>" not in table
assert 'navlink subnav active' in dec
# قائمة الإضافة تعرض غير المنضمّ فقط (U3 في «برامج رمضان» لا يظهر)
add_box = dec.split("إضافة برامج مسجّلة")[1]
assert 'value="U2"' in add_box and 'value="U3"' not in add_box
# ضمّ برامج مسجّلة: U3 في باقة أخرى فلا يُنقل
c.post("/programs/packages/assign", data={"name": "برامج ديسمبر", "code": ["U2", "U3"]})
dec = c.get("/programs", query_string={"package": "برامج ديسمبر"}).get_data(as_text=True)
table = dec.split("<tbody>")[1].split("</tbody>")[0]
assert "<td>U1</td>" in table and "<td>U2</td>" in table and "<td>U3</td>" not in table
app_mode.set_mode(app_mode.UMRAH)
pk = {t.code: t.package for t in umrah.load_trips(storage.load_settings())}
assert pk == {"U1": "برامج ديسمبر", "U2": "برامج ديسمبر", "U3": "برامج رمضان"}, pk
# ولا يُنقل من نموذج التعديل أيضاً (تُحفظ بقية الحقول برسالة)
form.update(code="U3", orig="U3", name="رمضان المعدّل", package="برامج ديسمبر")
r = c.post("/programs/save", data=form)
assert "msg=" in r.headers["Location"]
app_mode.set_mode(app_mode.UMRAH)
u3 = next(t for t in umrah.load_trips(storage.load_settings()) if t.code == "U3")
assert u3.package == "برامج رمضان" and u3.name == "رمضان المعدّل"
# بعد الإخراج يصبح متاحاً لباقة أخرى
c.post("/programs/packages/assign", data={"name": "برامج رمضان", "remove": "U3"})
c.post("/programs/packages/assign", data={"name": "برامج ديسمبر", "code": ["U3"]})
c.post("/programs/packages/assign", data={"name": "برامج ديسمبر", "remove": "U3"})
app_mode.set_mode(app_mode.UMRAH)
pk = {t.code: t.package for t in umrah.load_trips(storage.load_settings())}
assert pk == {"U1": "برامج ديسمبر", "U2": "برامج ديسمبر", "U3": ""}, pk
assert c.get("/programs", query_string={"package": "مجهولة"}).status_code == 302
# حذف باقة فيها برامج يُرفض، والفارغة تُحذف
assert "msg=" in c.post("/programs/packages/delete",
                        data={"name": "برامج ديسمبر"}).headers["Location"]
c.post("/programs/packages/add", data={"name": "فارغة"})
assert "🗑 حذف الباقة" in c.get("/programs", query_string={"package": "فارغة"}).get_data(as_text=True)
c.post("/programs/packages/delete", data={"name": "فارغة"})
app_mode.set_mode(app_mode.UMRAH)
assert "فارغة" not in umrah.load_packages(storage.load_settings())
# باقة تُكتب يدوياً في نموذج البرنامج تُسجَّل
form.update(code="U3", orig="U3", name="شعبان", package="برامج شعبان")
c.post("/programs/save", data=form)
app_mode.set_mode(app_mode.UMRAH)
assert umrah.load_packages(storage.load_settings())[-1] == "برامج شعبان"
print("[ok] الباقات: إضافة/تجميع/برنامج داخل باقة/حذف الفارغة فقط")

# ---- 4) غرف فندق مشتركة بين برامج الطيران بنفس التاريخ ----
A = umrah.UmrahTrip(code="A", makkah_rooms="30", madinah_rooms="20")
B = umrah.UmrahTrip(code="B", room_share="A", makkah_rooms="99")   # عدده لا يُحتسب
C = umrah.UmrahTrip(code="C", room_share="B")                      # سلسلة → A
ts = [A, B, C]
assert umrah.room_base(C, ts).code == "A"
assert [t.code for t in umrah.room_pool(B, ts)] == ["A", "B", "C"]
rs = [P("ثنائي", "A")] * 3 + [P("ثنائي", "B")] * 1 + [P("رباعي", "C")] * 4
# المشغول مجموع غرف كل برنامج: A=2، B=1، C=1 → 4
assert umrah.trip_rooms_left(B, rs, ts) == [("مكة", 30, 4, 26), ("المدينة", 20, 4, 16)]
assert umrah.trip_rooms_left(A, rs, ts) == umrah.trip_rooms_left(C, rs, ts)
assert umrah.trip_rooms_left(A, rs) == [("مكة", 30, 2, 28), ("المدينة", 20, 2, 18)]
# حلقة أو رمز محذوف لا يعلّق الحساب
L1 = umrah.UmrahTrip(code="L1", room_share="L2", makkah_rooms="5")
L2 = umrah.UmrahTrip(code="L2", room_share="L1")
assert umrah.room_base(L1, [L1, L2]).code in ("L1", "L2")
assert umrah.room_base(umrah.UmrahTrip(code="X", room_share="محذوف"), ts).code == "X"

# عبر الويب: U5 الاتحاد (أساسي، 10 غرف مكة) + U6 فلاي دبي يشاركه
form = {k: "" for k in server._PROG_KEYS}
form.update(code="U5", name="رمضان 1", airline="الاتحاد", capacity="40",
            makkah_hotel="فندق مكة", madinah_hotel="فندق المدينة", makkah_rooms="10")
c.post("/programs/save", data=form)
new = c.get("/programs/new").get_data(as_text=True)
assert 'name="room_share"' in new and '<option value="U5"' in new
form.update(code="U6", name="رمضان 1", airline="فلاي دبي", capacity="25",
            makkah_hotel="", madinah_hotel="", makkah_rooms="", room_share="U5")
c.post("/programs/save", data=form)
app_mode.set_mode(app_mode.UMRAH)
u6 = next(t for t in umrah.load_trips(storage.load_settings()) if t.code == "U6")
assert u6.room_share == "U5" and u6.makkah_hotel == "فندق مكة"      # نفس الفندق
storage.save_records(recs + [P("ثنائي", "U5")] * 4 + [P("ثلاثي", "U6")] * 3,
                     session=SESS)
html = c.get("/programs").get_data(as_text=True)
rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S)[1:]
heads = re.findall(r"<th>([^<]*)</th>", html)
for code, other in (("U5", "U6"), ("U6", "U5")):
    row = next(r for r in rows if f"<td>{code}</td>" in r)
    cl = [re.sub(r"<[^>]+>", " ", x).split()
          for x in re.findall(r"<td>(.*?)</td>", row, re.S)]
    # 10 − (U5: غرفتان + U6: غرفة) = 7 في البرنامجين، والمقاعد لكلٍّ وحده
    assert cl[heads.index("الغرف المتبقّية")] == ["مكة:", "7", "🔗", "مع", other], cl
assert "🔗" not in next(r for r in rows if "<td>U1</td>" in r)
ed = c.get("/programs/U6").get_data(as_text=True)
assert '<option value="U5" selected>' in ed and "يُؤخذ من «U5»" in ed
# U5 لا يمكنه مشاركة U6 (حلقة)، ولا تظهر U6 في خياراته
ed5 = c.get("/programs/U5").get_data(as_text=True)
assert '<option value="U6"' not in ed5
form.update(code="U5", orig="U5", room_share="U6", makkah_hotel="فندق مكة",
            makkah_rooms="10", airline="الاتحاد", capacity="40")
assert "msg=" in c.post("/programs/save", data=form).headers["Location"]
app_mode.set_mode(app_mode.UMRAH)
u5 = next(t for t in umrah.load_trips(storage.load_settings()) if t.code == "U5")
assert u5.room_share == "" and u5.makkah_rooms == "10"
# حذف الأساسي: المشارك يرث عدد الغرف ويصبح أساسياً
c.post("/programs/U5/delete")
app_mode.set_mode(app_mode.UMRAH)
u6 = next(t for t in umrah.load_trips(storage.load_settings()) if t.code == "U6")
assert u6.room_share == "" and u6.makkah_rooms == "10"

# المتاح لبرنامج مشارك = غرف الأساسي − غرف البرامج الأخرى (للتطبيق المكتبي)
assert umrah.rooms_available(B, ts, rs, "makkah_rooms") == 30 - 2 - 1
assert umrah.rooms_available(A, ts, rs, "makkah_rooms") == 30 - 1 - 1
assert umrah.rooms_available(A, ts, [P("مفرد", "B")] * 30, "makkah_rooms") == -1
assert umrah.rooms_available(umrah.UmrahTrip(code="Z"), ts, rs, "makkah_rooms") == 0
# اسم الفندق: المشارك يتبع الأساسي، وتعديل فندق الأساسي يصل إلى المشاركين
form = {k: "" for k in server._PROG_KEYS}
form.update(code="U7", makkah_hotel="هيلتون", makkah_rooms="12")
c.post("/programs/save", data=form)
form.update(code="U8", makkah_hotel="فندق آخر", makkah_rooms="", room_share="U7")
c.post("/programs/save", data=form)
form.update(code="U7", orig="U7", makkah_hotel="سويس أوتيل", makkah_rooms="12",
            room_share="")
c.post("/programs/save", data=form)
app_mode.set_mode(app_mode.UMRAH)
hot = {t.code: t.makkah_hotel for t in umrah.load_trips(storage.load_settings())}
assert hot["U7"] == hot["U8"] == "سويس أوتيل", hot
# صفحة «إشغال الغرف» تعرض العدد المشترك صفّاً واحداً
occ = c.get("/occupancy").get_data(as_text=True)
assert "الغرف المتبقّية حسب البرامج" in occ and "U7" in occ and "U8" in occ
assert occ.count("سويس أوتيل") == 1
# رمز محذوف خارج البورتال (التطبيق المكتبي) ثم أُعيد استخدامه لبرنامج جديد:
# لا يصبح أساساً للبرامج القديمة، ولا تتكوّن حلقة
st = storage.load_settings()
umrah.save_trips(st, [t for t in umrah.load_trips(st) if t.code != "U7"])
storage.save_settings(st)                          # U8 يشير إلى U7 المحذوف
form = {k: "" for k in server._PROG_KEYS}
form.update(code="U7", makkah_hotel="جديد", makkah_rooms="5", room_share="U8")
c.post("/programs/save", data=form)
app_mode.set_mode(app_mode.UMRAH)
sh = {t.code: t.room_share for t in umrah.load_trips(storage.load_settings())}
assert sh["U8"] == "" and sh["U7"] == "U8", sh                 # بلا حلقة
# تغيير الرمز (orig ≠ code): المشاركون يتبعون الرمز الجديد
form = {k: "" for k in server._PROG_KEYS}
form.update(code="U9", orig="U8", makkah_rooms="7")
c.post("/programs/save", data=form)
app_mode.set_mode(app_mode.UMRAH)
sh = {t.code: t.room_share for t in umrah.load_trips(storage.load_settings())}
assert "U8" not in sh and sh["U7"] == "U9", sh
# الحساب مرّة واحدة: 400 برنامج في مجموعات ثلاثية تُحسب بسرعة
import time
big = [umrah.UmrahTrip(code=f"P{i}", makkah_rooms="9",
                       room_share=(f"P{i - i % 3}" if i % 3 else "")) for i in range(400)]
t0 = time.perf_counter()
pl = umrah.room_pools(big)
assert time.perf_counter() - t0 < 1.0 and [t.code for t in pl["P5"]] == ["P3", "P4", "P5"]
print("[ok] غرف فندق مشتركة بين برامج الطيران")
print("ALL OK")
