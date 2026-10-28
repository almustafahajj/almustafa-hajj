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
    server.app.config["CSRF_ENABLED"] = False     # الحماية تُختبر في test_security
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
# زر «إخراج» للمدير فقط: المحرّر لا يراه ولا يستطيع الإخراج
auth.add_account(SESS, "ed1", "Passw0rd!e", role="editor")
ed = server.app.test_client()
ed.post("/login", data={"username": "ed1", "password": "Passw0rd!e"})
app_mode.set_mode(app_mode.UMRAH)
assert "↩ إخراج" in c.get("/programs", query_string={"package": "برامج رمضان"}).get_data(as_text=True)
app_mode.set_mode(app_mode.UMRAH)
assert "↩ إخراج" not in ed.get("/programs", query_string={"package": "برامج رمضان"}).get_data(as_text=True)
ed.post("/programs/packages/assign", data={"name": "برامج رمضان", "remove": "U3"})
app_mode.set_mode(app_mode.UMRAH)
assert next(t for t in umrah.load_trips(storage.load_settings()) if t.code == "U3").package == "برامج رمضان"
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

# ---- 5) البرنامج في الباقة = خط طيران (الناقل + المغادرة من) بلونه، وترتيب ▲▼ ----
# أسماء الناقلين والمدن بأشكال مختلفة تُوحَّد
assert umrah.split_airline("السعودية") == ("الطيران السعودي", "")
assert umrah.split_airline("الطيران السعودي من أبوظبي") == ("الطيران السعودي", "أبوظبي")
assert umrah.split_airline("Saudia - DXB") == ("الطيران السعودي", "دبي")
assert umrah.split_airline("فلاي دبي") == ("فلاي دبي", "")          # ناقل لا مدينة
assert umrah.split_airline("flydubai") == ("فلاي دبي", "")
assert umrah.split_airline("طيران الإتحاد") == ("الاتحاد", "")
assert umrah.split_airline("طيران الخليج") == ("طيران الخليج", "")
assert umrah.find_city("رمضان من ابو ظبي") == "أبوظبي"
assert umrah.find_city("رمضان 2") == "" and umrah.find_city("من دبي إلى أبوظبي") == ""
assert umrah.canon_city("AUH") == "أبوظبي" and umrah.canon_city("مسقط") == "مسقط"
T = umrah.UmrahTrip
L = umrah.program_lines([
    T(code="a1", airline="الطيران السعودي", depart_city="أبوظبي"),
    T(code="a2", airline="السعودية", name="رمضان من دبي"),
    T(code="a3", airline="السعودي من ابوظبي"),
    T(code="b1", airline="فلاي دبي", name="رمضان"),
    T(code="b2", airline="flydubai", name="رمضان من دبي"),
    T(code="c1", airline="")])
assert L["a1"][0] == L["a3"][0] != L["a2"][0]
assert L["a1"][1:] == ("الطيران السعودي", "أبوظبي") and L["a2"][2] == "دبي"
assert L["b1"][0] == L["b2"][0] and L["b1"][1:] == ("فلاي دبي", "")  # «من دبي» لا تتكرّر
assert L["c1"][0] == "#c1"                                       # بلا ناقل: وحده
# كتابات المستخدم المختلفة لنفس الناقل/المدينة (من المراجعة)
for s_, exp in (("طيران سعودي من أبوظبي", ("الطيران السعودي", "أبوظبي")),
                ("طيران فلاي دبي", ("فلاي دبي", "")),
                ("فلاي دبي من دبي", ("فلاي دبي", "دبي")),
                ("Fly Dubai - DXB", ("فلاي دبي", "دبي")),
                ("Etihad Airlines", ("الاتحاد", "")),
                ("Saudia (SV)", ("الطيران السعودي", "")),
                ("الخطوط الجوية العربية السعودية", ("الطيران السعودي", "")),
                ("العربية للطيران - الشارقة", ("العربية للطيران", "الشارقة")),
                ("طيران الخليج من أبوظبي", ("طيران الخليج", "أبوظبي")),
                ("السعودی", ("الطيران السعودي", "")),
                ("أبوظبي", ("", "أبوظبي"))):
    assert umrah.split_airline(s_) == exp, (s_, umrah.split_airline(s_))
assert umrah.canon_city("ابوضبي") == umrah.canon_city("أبو ضبي") == "أبوظبي"
assert umrah.canon_city(" - ") == "" and umrah.canon_city("مسقط") == "مسقط"
assert umrah.canon_city("N/A") == umrah.canon_city("غير محدد") == ""
# كتابتان لمدينة غير معروفة مدينةٌ واحدة (لا تقسم الناقل)
L3 = umrah.program_lines([T(code="m1", airline="طيران عُمان", depart_city="صلالة"),
                          T(code="m2", airline="طيران عمان", depart_city="صلاله"),
                          T(code="m3", airline="طيران عمان", depart_city="N/A")])
assert L3["m1"][0] == L3["m2"][0] == L3["m3"][0] and L3["m1"][2] == "صلالة", L3
assert umrah.find_city("قرة العين", strict=True) == ""          # كلمة لا مدينة
assert umrah.find_city("رمضان من العين", strict=True) == "العين"
L2 = umrah.program_lines([
    T(code="s1", airline="طيران سعودي من أبوظبي"),
    T(code="s2", airline="الطيران السعودي", depart_city="ابوضبي"),
    T(code="s3", airline="Saudia (SV)", depart_city="دبي"),
    T(code="e1", airline="Etihad Airlines"), T(code="e2", airline="الاتحاد", depart_city="-"),
    T(code="e3", airline="الاتحاد", name="قرة العين"),
    T(code="g1", airline="طيران الخليج من أبوظبي"),
    T(code="g2", airline="طيران الخليج", depart_city="أبوظبي"),
    T(code="f1", airline="فلاي دبي - دبي"), T(code="f2", airline="flydubai")])
assert L2["s1"][0] == L2["s2"][0] != L2["s3"][0]
assert L2["s1"][1:] == ("الطيران السعودي", "أبوظبي") and L2["s3"][2] == "دبي"
assert L2["e1"][0] == L2["e2"][0] == L2["e3"][0] and L2["e2"][1:] == ("الاتحاد", "")
assert L2["g1"][0] == L2["g2"][0] and L2["g1"][1:] == ("طيران الخليج", "أبوظبي")
assert L2["f1"][0] == L2["f2"][0] and L2["f1"][1:] == ("فلاي دبي", "")

PK = "رمضان 2027"
c.post("/programs/packages/add", data={"name": PK})
# رحلتان لكل خط بتاريخين؛ الترتيب الافتراضي بأقرب تاريخ ثم ترتيب الإضافة
trips5 = (("S1", "الطيران السعودي", "أبوظبي", "رمضان 1", "2027-02-08"),
          ("D1", "السعودية", "", "رمضان 1 من دبي", "2027-02-08"),
          ("F1", "فلاي دبي", "", "رمضان 1", "2027-02-08"),
          ("E1", "الاتحاد", "", "", "2027-02-08"),
          ("S2", "الطيران السعودي", "أبوظبي", "رمضان 2", "2027-02-20"),
          ("E2", "طيران الاتحاد", "", "", "2027-02-20"),
          ("F2", "flydubai", "", "", "2027-02-20"),
          ("D2", "الطيران السعودي", "دبي", "", "2027-02-20"))
for code, air, city, name, dep in trips5:
    form = {k: "" for k in server._PROG_KEYS}
    form.update(code=code, package=PK, airline=air, depart_city=city, name=name,
                depart_date=dep, capacity="2")
    c.post("/programs/save", data=form)


def pk5():
    return c.get("/programs", query_string={"package": PK}).get_data(as_text=True)


def bands(page):
    return re.findall(r'<tr class="pg-head" style="--pc:([^;]+);--pf:[^"]+">.*?'
                      r'<span class="pg-title">([^<]+)</span>', page, re.S)


def row_order(page):
    body = page.split("<tbody>")[1]
    return re.findall(r"<td>([A-Z]\d)</td>", body)


def row_colors(page):
    return dict((code, col) for col, code in re.findall(
        r'<tr class="pcol" style="--pc:([^;]+);[^"]*">\s*<td>(\w+)</td>', page))


page = pk5()
B = bands(page)
assert [t for _c, t in B] == ["البرنامج الأول · ✈️ الطيران السعودي من أبوظبي",
                              "البرنامج الثاني · ✈️ الطيران السعودي من دبي",
                              "البرنامج الثالث · ✈️ فلاي دبي",
                              "البرنامج الرابع · ✈️ الاتحاد"], B
GREEN_D, GREEN_L, SKY, GOLD = (p[0] for p in server._PROG_COLORS[:4])
assert [c_ for c_, _t in B] == [GREEN_D, GREEN_L, SKY, GOLD]
assert row_order(page) == ["S1", "S2", "D1", "D2", "F1", "F2", "E1", "E2"]
rc = row_colors(page)
assert rc["S1"] == rc["S2"] == GREEN_D and rc["D2"] == GREEN_L and rc["F2"] == SKY \
    and rc["E1"] == rc["E2"] == GOLD, rc
assert page.count("عدد الرحلات: 2") == 4 and page.count('class="pg-gap"') == 3
allp = row_colors(c.get("/programs").get_data(as_text=True))
assert all(allp[k] == v for k, v in rc.items())                  # نفس اللون في الصفحتين
# ▲▼ تنقل البرنامج كاملاً (كل رحلاته)، ويُحفظ الترتيب
assert page.count('name="dir" value="up"') == 3 and page.count('name="dir" value="down"') == 3
ekey = re.search(r'name="group" value="([^"]+)">\s*<input type="hidden" name="dir" '
                 r'value="up">', page.split("البرنامج الرابع")[0].rsplit("pg-head", 1)[1]).group(1)
for _ in range(4):                                     # الزائد عند الطرف لا يضرّ
    c.post("/programs/packages/move", data={"name": PK, "group": ekey, "dir": "up"})
page = pk5()
assert [t for _c, t in bands(page)][0] == "البرنامج الأول · ✈️ الاتحاد"
assert bands(page)[0][0] == GREEN_D and row_order(page)[:2] == ["E1", "E2"]
app_mode.set_mode(app_mode.UMRAH)
assert server._pkg_orders(storage.load_settings())[PK][0] == ekey
for _ in range(3):
    c.post("/programs/packages/move", data={"name": PK, "group": ekey, "dir": "down"})
assert [t for _c, t in bands(pk5())][3] == "البرنامج الرابع · ✈️ الاتحاد"
# رحلة جديدة لخط موجود تنضمّ إليه (لا برنامج جديد)، وتعديل رحلة لا يغيّر الترتيب
form = {k: "" for k in server._PROG_KEYS}
form.update(code="E3", package=PK, airline="Etihad", depart_date="2027-03-01")
c.post("/programs/save", data=form)
page = pk5()
assert len(bands(page)) == 4 and row_order(page)[-3:] == ["E1", "E2", "E3"]
form = {k: "" for k in server._PROG_KEYS}
form.update(code="S1", orig="S1", package=PK, airline="الطيران السعودي",
            depart_city="أبوظبي", depart_date="2027-03-30", capacity="2")
c.post("/programs/save", data=form)
assert [t for _c, t in bands(pk5())][0] == "البرنامج الأول · ✈️ الطيران السعودي من أبوظبي"
# ترتيب قديم محفوظ برموز البرامج (قبل هذا الإصدار) يُفهم: E1 أولاً
st = storage.load_settings()
st["umrah_package_order"] = {PK: ["E1"]}
storage.save_settings(st)
assert [t for _c, t in bands(pk5())][0] == "البرنامج الأول · ✈️ الاتحاد"
c.post("/programs/packages/move", data={"name": PK, "group": ekey, "dir": "down"})
app_mode.set_mode(app_mode.UMRAH)
assert "E1" not in server._pkg_orders(storage.load_settings())[PK]       # صار بالمفاتيح
# حالة السعة بعلامة في خانة المتبقّي (الألوان للبرامج)
storage.save_records([P("ثنائي", "F1")] * 2 + [P("ثنائي", "F2")] * 3, session=SESS)
page = pk5()
f1 = next(r for r in re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.S) if "<td>F1</td>" in r)
f2 = next(r for r in re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.S) if "<td>F2</td>" in r)
assert "✅ مكتمل" in f1 and "⛔ زيادة 1" in f2 and "rover" not in page
assert "👥 المعتمرون: 5" in page and "🪑 المقاعد المتبقّية: 0 من 4 · ⛔ زيادة 1" in page
# برنامج بلا ناقل: شريط وحده باسمه
form = {k: "" for k in server._PROG_KEYS}
form.update(code="X1", package=PK, name="عمرة خاصة")
c.post("/programs/save", data=form)
assert [t for _c, t in bands(pk5())][-1] == "البرنامج الخامس · عمرة خاصة"
# خانة «المغادرة من» والقوائم في نموذج البرنامج
new = c.get("/programs/new").get_data(as_text=True)
assert 'name="depart_city"' in new and '<option value="أبوظبي">' in new
assert 'list="airlinelist"' in new and '<option value="الطيران السعودي">' in new
# الترتيب القديم بالرموز يتحوّل إلى مفاتيح الخطوط قبل الحذف، ولا يبقى للمحذوف أثر
st = storage.load_settings()
st["umrah_package_order"] = {PK: ["X1", "E1"]}
storage.save_settings(st)
c.post("/programs/X1/delete")
app_mode.set_mode(app_mode.UMRAH)
saved = server._pkg_orders(storage.load_settings())[PK]
assert saved[0] == "الاتحاد|" and not {"X1", "#X1", "E1"} & set(saved), saved
assert c.post("/programs/packages/move",
              data={"name": "مجهولة", "group": ekey, "dir": "up"}).status_code == 302
# ترتيب (من المراجعة): شريط «بلا مدينة» يتحرّك بالسهم، وحذف رحلات مدينةٍ أو
# رحلةٍ مرتّبة بالترتيب القديم لا يُضيع مكان الخط ولونه
import html as _html
PO = "اختبار الترتيب"
c.post("/programs/packages/add", data={"name": PO})


def save_po(code, air, city, dep):
    form = {k: "" for k in server._PROG_KEYS}
    form.update(code=code, package=PO, airline=air, depart_city=city, depart_date=dep)
    c.post("/programs/save", data=form)


def po_bands():
    page = c.get("/programs", query_string={"package": PO}).get_data(as_text=True)
    out = []
    for head in re.findall(r'<tr class="pg-head".*?</tr>', page, re.S):
        title = re.search(r'<span class="pg-title">([^<]+)</span>', head).group(1)
        key = re.search(r'name="group" value="([^"]+)"', head)
        out.append((title.split(" · ", 1)[1], _html.unescape(key.group(1)) if key else ""))
    return out


def po_move(word, d, times=1):
    key = next(k for t, k in po_bands() if t == word)
    for _ in range(times):
        c.post("/programs/packages/move", data={"name": PO, "group": key, "dir": d})


save_po("QF", "فلاي دبي", "", "2027-01-01")
save_po("QA", "الطيران السعودي", "أبوظبي", "2027-01-02")
save_po("QD", "الطيران السعودي", "دبي", "2027-01-03")
save_po("QN", "الطيران السعودي", "", "2027-01-04")          # بلا مدينة: شريط وحده
assert [t for t, _k in po_bands()] == ["✈️ فلاي دبي", "✈️ الطيران السعودي من أبوظبي",
                                       "✈️ الطيران السعودي من دبي", "✈️ الطيران السعودي"]
po_move("✈️ الطيران السعودي", "up")                           # كان لا يتحرّك
assert [t for t, _k in po_bands()][2] == "✈️ الطيران السعودي"
po_move("✈️ الطيران السعودي من أبوظبي", "up")
assert [t for t, _k in po_bands()][0] == "✈️ الطيران السعودي من أبوظبي"
c.post("/programs/QD/delete")
c.post("/programs/QN/delete")                     # بقي السعودي من أبوظبي وحده
assert [t for t, _k in po_bands()] == ["✈️ الطيران السعودي من أبوظبي", "✈️ فلاي دبي"]
# ترتيب قديم برموز البرامج: حذف الرحلة التي حدّدت مكان الخط لا يُضيعه
save_po("QE", "الاتحاد", "", "2027-01-05")
save_po("QE2", "الاتحاد", "", "2027-01-09")
st = storage.load_settings()
st["umrah_package_order"] = {PO: ["QE", "QF", "QA"]}
storage.save_settings(st)
assert [t for t, _k in po_bands()][0] == "✈️ الاتحاد"
c.post("/programs/QE/delete")
assert [t for t, _k in po_bands()] == ["✈️ الاتحاد", "✈️ فلاي دبي",
                                       "✈️ الطيران السعودي من أبوظبي"]
# برنامج بلا ناقل («#رمز»): تغيير رمزه يُبقي مكانه
save_po("QZ", "", "", "2027-01-07")
st = storage.load_settings()
st["umrah_package_order"] = {PO: ["#QZ"] + [k for _t, k in po_bands() if k != "#QZ"]}
storage.save_settings(st)
assert po_bands()[0][1] == "#QZ"
form = {k: "" for k in server._PROG_KEYS}
form.update(code="QZ2", orig="QZ", package=PO, depart_date="2027-01-07")
c.post("/programs/save", data=form)
assert po_bands()[0][1] == "#QZ2"
print("[ok] البرنامج = خط طيران بلونه في الباقة + ترتيب ▲▼")

# ---- 6) «البرنامج الأول/الثاني…» المكتوب في اسم الرحلة يحدّد برنامجها ولونه ----
assert umrah.program_ordinal("البرنامج الأول") == 1
assert umrah.program_ordinal("البرنامج الاول - السعودي") == 1
assert umrah.program_ordinal("رمضان البرنامج الثاني") == 2
assert umrah.program_ordinal("البرنامج الرايع") == 4                 # خطأ كتابة شائع
assert umrah.program_ordinal("برنامج رقم 3") == 3 and umrah.program_ordinal("رمضان 1") == 0
PN = "رمضان بالأسماء"
c.post("/programs/packages/add", data={"name": PN})
named = (("N2", "البرنامج الثاني", "الطيران السعودي", "دبي", "2027-02-01"),
         ("N4", "البرنامج الرابع", "الاتحاد", "", "2027-02-02"),
         ("N1", "البرنامج الأول", "الطيران السعودي", "أبوظبي", "2027-02-20"),
         ("N3", "البرنامج الثالث", "فلاي دبي", "", "2027-02-03"),
         ("N1b", "البرنامج الأول", "الاتحاد", "", "2027-02-25"),      # طيران آخر
         ("N4b", "البرنامج الرايع", "الاتحاد", "", "2027-03-01"),
         ("NX", "رحلة خاصة", "طيران الإمارات", "", "2027-01-01"))
for code, name, air, city, dep in named:
    form = {k: "" for k in server._PROG_KEYS}
    form.update(code=code, package=PN, name=name, airline=air, depart_city=city,
                depart_date=dep)
    c.post("/programs/save", data=form)
page = c.get("/programs", query_string={"package": PN}).get_data(as_text=True)
heads = re.findall(r'<tr class="pg-head" style="--pc:([^;]+);--pf:[^"]+">.*?'
                   r'<span class="pg-title">([^<]+)</span>', page, re.S)
assert [t for _c, t in heads] == ["البرنامج الأول", "البرنامج الثاني", "البرنامج الثالث",
                                  "البرنامج الرابع", "✈️ طيران الإمارات"], heads
assert [c_ for c_, _t in heads] == [p[0] for p in server._PROG_COLORS[:5]]
body = page.split("<tbody>")[1]
assert re.findall(r"<td>(N\w*)</td>", body) == ["N1", "N1b", "N2", "N3", "N4", "N4b", "NX"]
rc = dict((code, col) for col, code in re.findall(
    r'<tr class="pcol" style="--pc:([^;]+);[^"]*">\s*<td>(\w+)</td>', page))
GD, GL, SK, GO = (p[0] for p in server._PROG_COLORS[:4])
assert rc["N1"] == rc["N1b"] == GD and rc["N2"] == GL and rc["N3"] == SK
assert rc["N4"] == rc["N4b"] == GO
assert "✈️ الطيران السعودي من أبوظبي + الاتحاد" in page          # طيرانات البرنامج الأول
assert 'name="dir"' not in page          # ترتيب المرقّمة رقمها (والباقي برنامج واحد)
allp = dict((code, col) for col, code in re.findall(
    r'<tr class="pcol" style="--pc:([^;]+);[^"]*">\s*<td>(\w+)</td>',
    c.get("/programs").get_data(as_text=True)))
assert all(allp[k] == v for k, v in rc.items())                  # نفس اللون في الصفحتين
print("[ok] «البرنامج الأول…» في الاسم: برنامجه ولونه ثابتان")
print("ALL OK")
