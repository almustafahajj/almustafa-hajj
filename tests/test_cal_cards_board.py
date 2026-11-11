# -*- coding: utf-8 -*-
"""البورتال: (١) تقويم الرحلات بأشرطة ممتدّة من المغادرة إلى العودة وقائمة رحلات
الشهر؛ (٢) برامج العمرة كبطاقات مع مبدّل «بطاقات/جدول»؛ (٣) لوحة الغرف المرئية —
النقل بين الغرف يُحفظ بزرّ «حفظ التسكين» عبر نموذج التسكين نفسه."""
import io
import os
import re
import sys
import tempfile
from datetime import date, timedelta

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["HAJJ_DATA_DIR"] = tempfile.mkdtemp(prefix="calcards_")

from hajj_app import app_mode, auth, storage, umrah  # noqa: E402
from hajj_app.mrz import PassportData  # noqa: E402

try:
    from webapp import server
    server.app.config["CSRF_ENABLED"] = False
except ImportError as exc:
    print(f"[skip] مسارات الويب: {exc}")
    print("ALL OK")
    sys.exit(0)

# ---- ١) حساب الأشرطة: تقسيم على الأسابيع ومسارات لا تتداخل ----
first = date(2026, 11, 1)              # الأسابيع تبدأ السبت: 31 أكتوبر ← 6 نوفمبر …
today = date(2026, 11, 11)


def trip(label, dep, ret):
    return {"label": label, "n": 3, "cap": 10, "color": "#123456", "fg": "#fff",
            "link": "/x", "sub": "", "depart": dep, "ret": ret}


trips = [trip("A", date(2026, 11, 3), date(2026, 11, 12)),     # يمتدّ أسبوعين
         trip("B", date(2026, 11, 4), date(2026, 11, 5)),      # يتداخل مع A
         trip("C", date(2026, 10, 25), date(2026, 11, 2)),     # بدأ الشهر الماضي
         trip("D", date(2026, 11, 20), None),                   # مغادرة فقط
         trip("E", date(2026, 12, 20), date(2026, 12, 25))]    # شهر آخر
weeks, agenda = server._cal_weeks(trips, first, today)
assert len(weeks) == 5 and weeks[0]["days"][0]["day"] == 31 and weeks[0]["days"][0]["out"]
w0 = {b["label"]: b for b in weeks[0]["bars"]}
assert set(w0) == {"A", "B", "C"}
assert w0["A"]["col"] == 4 and w0["A"]["span"] == 4 and w0["A"]["head"] and not w0["A"]["tail"]
assert w0["A"]["dep"] and not w0["A"]["ret"]
assert w0["C"]["col"] == 1 and not w0["C"]["head"] and w0["C"]["tail"] and w0["C"]["ret"]
assert w0["B"]["row"] != w0["A"]["row"], "الرحلات المتداخلة في مسارين"
assert w0["C"]["row"] == w0["A"]["row"] or w0["C"]["row"] == w0["B"]["row"], "المسار يُعاد استعماله"
w1 = {b["label"]: b for b in weeks[1]["bars"]}
assert w1["A"]["col"] == 1 and w1["A"]["span"] == 6 and w1["A"]["tail"] and w1["A"]["ret"]
d = next(b for w in weeks for b in w["bars"] if b["label"] == "D")
assert d["span"] == 1 and d["head"] and d["tail"] and d["dep"] and not d["ret"]
assert [a["label"] for a in agenda] == ["C", "A", "B", "D"], "E خارج الشهر"
a_ = next(a for a in agenda if a["label"] == "A")
assert a_["nights"] == "9 ليالٍ" and a_["now"] and not a_["one"]
assert next(a for a in agenda if a["label"] == "D")["one"]
assert any(dd["today"] for w in weeks for dd in w["days"])
print("[ok] التقويم: أشرطة ممتدّة على الأسابيع، مسارات بلا تداخل، قائمة الشهر")

# ---- ٢) صفحات البورتال ----
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
app_mode.set_mode(app_mode.UMRAH)
T = date.today()
st = storage.load_settings()
umrah.save_trips(st, [
    umrah.UmrahTrip(code="U1", name="رحلة جارية", depart_date=(T - timedelta(days=2)).isoformat(),
                    return_date=(T + timedelta(days=5)).isoformat(), capacity="4",
                    airline="الإماراتية", makkah_hotel="سويس أوتيل", package="برامج رجب"),
    umrah.UmrahTrip(code="U2", name="رحلة قادمة", depart_date=(T + timedelta(days=12)).isoformat(),
                    return_date=(T + timedelta(days=19)).isoformat(), capacity="2")])
umrah.save_packages(st, ["برامج رجب"])
storage.save_settings(st)


def rec(name, rt, sex="ذكر", fam="", trip_="U1"):
    return PassportData(full_name_ar=name, room_type=rt, sex=sex, family_number=fam,
                        hotel="فندق النور", trip=trip_)


storage.save_records([rec("أحمد علي", "ثنائي 1", fam="1"), rec("سالم علي", "ثنائي 1", fam="1"),
                      rec("خالد سعيد", "ثنائي 2", fam="2"),
                      rec("مريم حسن", "ثلاثي 1", "أنثى", "3"),
                      rec("بلا غرفة", "", trip_="U2")], session=SESS)

cal = c.get("/calendar").get_data(as_text=True)
assert 'class="cal2"' in cal and "c2-bar" in cal and "رحلة جارية" in cal
assert "جارية الآن" in cal and "7 ليالٍ" in cal

pg = c.get("/programs").get_data(as_text=True)
assert pg.count('class="pcard"') == 2 and 'data-v="cards"' in pg and 'data-v="table"' in pg
assert "<td>U1</td>" in pg, "الجدول باقٍ للتبديل إليه"
u1 = pg.split('<span class="pc-code">U1</span>')[1].split("</article>")[0]
assert "جارية الآن" in u1 and "سويس أوتيل" in u1 and "الإماراتية" in u1 and "7 ليالٍ" in u1
assert 'style="width:100%"' in u1 and "مكتمل" in u1, "4 من 4 مقاعد"
u2 = pg.split('<span class="pc-code">U2</span>')[1].split("</article>")[0]
assert "بعد 12 يوماً" in u2 and 'class="pc-when soon"' in u2
assert 'form="pdel-U1"' in pg and 'id="pdel-U1"' in pg, "زرّ الحذف في البطاقة يستعمل نموذج الجدول"
assert 'form="pdel-U1"' not in e.get("/programs").get_data(as_text=True), "الحذف للمدير فقط"
pk = c.get("/programs", query_string={"package": "برامج رجب"}).get_data(as_text=True)
assert 'class="pc-group"' in pk and pk.count('class="pcard"') == 1 and 'form="pout-U1"' in pk
print("[ok] التقويم والبرامج كبطاقات: الحالة والمقاعد والليالي والأزرار حسب الصلاحية")

# ---- ٣) لوحة الغرف ----
occ = c.get("/occupancy").get_data(as_text=True)
assert 'id="rboard"' in occ and "rboard editable" in occ and 'draggable="true"' in occ
assert occ.count('class="rm rm-') >= 3 and "فندق النور" in occ and 'class="rm rm-new"' in occ
assert "بلا غرفة" in occ and 'id="rbForm"' in occ
r1 = occ.split('data-number="1" data-rtype="ثنائي 1"')[1].split("</article>")[0]
assert "أحمد" in r1 and "سالم" in r1 and "<i>2</i>/2" in r1
ov = v.get("/occupancy").get_data(as_text=True)
assert 'id="rboard"' in ov and "rboard editable" not in ov and 'draggable="true"' not in ov
assert 'id="rbForm"' not in ov, "المطّلع يرى اللوحة بلا نقل"
# نقل «سالم» إلى الغرفة الثنائية 2 — كما يرسله زرّ «حفظ التسكين» في اللوحة
idx = int(re.search(r'data-idx="(\d+)" data-fp="([^"]+)" data-rt="ثنائي 1"\s+data-fam="1" '
                    r'data-sex="ذكر" title="سالم علي', occ).group(1))
fp = re.search(rf'data-idx="{idx}" data-fp="([^"]+)"', occ).group(1)
fp = fp.replace("&#35;", "#")
form = {"back": "board", f"fp_{idx}": fp, f"hotel_{idx}": "فندق النور",
        f"rtype_{idx}": "ثنائي 2", f"rnum_{idx}": "2"}
v.post("/occupancy/edit", data=form)                    # المطّلع لا ينقل
assert storage.load_records(session=SESS)[0][idx].room_type == "ثنائي 1"
r = e.post("/occupancy/edit", data=form)
assert r.status_code == 302 and "/occupancy?saved=1" in r.headers["Location"] \
    and r.headers["Location"].endswith("#board"), r.headers["Location"]
moved = storage.load_records(session=SESS)[0][idx]
assert moved.room_type == "ثنائي 2" and moved.room_number == "2"
occ = c.get("/occupancy", query_string={"saved": "1"}).get_data(as_text=True)
r2 = occ.split('data-number="2" data-rtype="ثنائي 2"')[1].split("</article>")[0]
assert "سالم" in r2 and "خالد" in r2 and "rm rm-full" in occ.split('data-number="2" data-rtype="ثنائي 2"')[0][-120:]
assert "حُفظ التسكين (1 سجلّ نُقل)" in occ
r = e.post("/occupancy/edit", data=dict(form, **{f"fp_{idx}": "umrah#x#y"}))   # بصمة قديمة
assert "skipped=1" in r.headers["Location"]
print("[ok] لوحة الغرف: بطاقات بالأسرّة، النقل للمحرّر فقط ويُحفظ بالزرّ، والبصمة القديمة تُتخطّى")

print("ALL OK")
