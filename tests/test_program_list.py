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
print("ALL OK")
