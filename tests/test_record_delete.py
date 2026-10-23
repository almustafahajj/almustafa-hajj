# -*- coding: utf-8 -*-
"""البورتال: حذف سجلّ معتمر/حاج بعد إضافته — للمحرّرين فقط، بالتحقّق من بصمة
السجلّ، مع حذف صوره المشفّرة وإصلاح الإشارات بالموضع (الأرشيف والمخيمات)."""
import io
import os
import re
import sys
import tempfile

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["HAJJ_DATA_DIR"] = tempfile.mkdtemp(prefix="rec_delete_")

from hajj_app import app_mode, auth, images, storage  # noqa: E402

try:
    from webapp import server
except ImportError as exc:
    print(f"[skip] مسارات الويب: {exc}")
    print("ALL OK")
    sys.exit(0)

owner, _key = auth.create_account("owner", "Passw0rd!x")
auth.add_account(owner, "viewer", "Passw0rd!y", role="viewer")
c = server.app.test_client()
c.post("/login", data={"username": "owner", "password": "Passw0rd!x"})
SESS = server._SESSIONS[next(iter(server._SESSIONS))]


def names():
    recs, _n = storage.load_records(session=SESS)
    return [r.full_name_ar for r in recs]


def fp_of(html):
    m = re.search(r'name="fp" value="([^"]*)"', html)
    return m.group(1) if m else None


# ---- 1) العمرة: إضافة ثلاثة ثم حذف الأوسط ----
for n in ("أحمد", "بلال", "جابر"):
    c.post("/hujjaj/new", data={"full_name_ar": n, "passport_number": "P-" + n})
app_mode.set_mode(app_mode.UMRAH)
assert names() == ["أحمد", "بلال", "جابر"]
# صور مشفّرة للسجلّ الأوسط (ملفّات بمعرّفه)
recs, _n = storage.load_records(session=SESS)
recs[1].image_id = "img-b"
storage.save_records(recs, session=SESS)
images.images_dir().mkdir(parents=True, exist_ok=True)
for kind in images.KINDS:
    (images.images_dir() / f"img-b.{kind}").write_bytes(b"x")
# مستندات مؤرشفة بإشارات موضعية
storage.save_documents([
    {"id": "d0", "kind": "receipt", "idx": 0, "name": "أحمد", "data": {}},
    {"id": "d1", "kind": "receipt", "idx": 1, "name": "بلال", "data": {}},
    {"id": "d2", "kind": "receipt", "idx": 2, "name": "جابر", "data": {}},
    {"id": "dm", "kind": "voucher", "idx": None, "name": "يدوي", "data": {}},
], session=SESS)

page = c.get("/hujjaj/1").get_data(as_text=True)
assert "حذف هذا السجلّ" in page and 'action="/hujjaj/1/delete"' in page
fp_b = fp_of(page)
assert fp_b and fp_b.startswith("umrah#") and fp_b.count("#") == 2
assert "حذف هذا السجلّ" not in c.get("/hujjaj/new").get_data(as_text=True)

# بصمة خاطئة → لا حذف
r = c.post("/hujjaj/1/delete", data={"fp": "غير موجود"})
assert r.status_code == 302 and "msg=notfound" in r.headers["Location"]
assert names() == ["أحمد", "بلال", "جابر"]

# الحذف الصحيح
r = c.post("/hujjaj/1/delete", data={"fp": fp_b})
assert r.status_code == 302 and "msg=deleted" in r.headers["Location"]
assert names() == ["أحمد", "جابر"]
assert not any((images.images_dir() / f"img-b.{k}").exists() for k in images.KINDS)
docs = {d["id"]: d["idx"] for d in storage.load_documents(session=SESS)}
assert docs == {"d0": 0, "d1": None, "d2": 1, "dm": None}, docs   # جابر تقدّم
lst = c.get(r.headers["Location"]).get_data(as_text=True)
assert "تم حذف السجلّ «بلال»" in lst

# الموضع تغيّر (أضاف غيرك سجلّاً في المقدّمة): الحذف بالبصمة يصيب الصحيح
page = c.get("/hujjaj/1").get_data(as_text=True)            # جابر في الموضع 1
fp_j = fp_of(page)
recs, _n = storage.load_records(session=SESS)
from hajj_app.mrz import PassportData  # noqa: E402
recs.insert(0, PassportData(full_name_ar="دخيل", passport_number="P-دخيل"))
storage.save_records(recs, session=SESS)                    # جابر صار في 2
r = c.post("/hujjaj/1/delete", data={"fp": fp_j})           # الموضع القديم
assert "msg=deleted" in r.headers["Location"]
assert names() == ["دخيل", "أحمد"], names()                 # حُذف جابر لا أحمد
# موضع خارج المدى مع بصمة مكرّرة/غير موجودة → رفض
assert "msg=notfound" in c.post("/hujjaj/99/delete",
                                data={"fp": "x"}).headers["Location"]
print("[ok] حذف سجلّ عمرة: البصمة، الصور، وإصلاح أرشيف المستندات")

# ---- 2) المطّلع لا يرى زرّ الحذف ولا يستطيع الحذف ----
v = server.app.test_client()
v.post("/login", data={"username": "viewer", "password": "Passw0rd!y"})
vp = v.get("/hujjaj/0").get_data(as_text=True)
assert "حذف هذا السجلّ" not in vp
real_fp = fp_of(c.get("/hujjaj/0").get_data(as_text=True))   # بصمة صحيحة
assert real_fp
v.post("/hujjaj/0/delete", data={"fp": real_fp})
app_mode.set_mode(app_mode.UMRAH)
assert names() == ["دخيل", "أحمد"]
print("[ok] المطّلع لا يحذف")

# ---- 3) الحج: إصلاح تسكين المخيمات بعد الحذف ----
c.get("/switch/hajj")
for n in ("حاج١", "حاج٢", "حاج٣", "حاج٤"):
    c.post("/hujjaj/new", data={"full_name_ar": n, "passport_number": "H-" + n})
app_mode.set_mode(app_mode.HAJJ)
assert names() == ["حاج١", "حاج٢", "حاج٣", "حاج٤"]
storage.save_camps({"mina": {"camp": "mina", "number": 3,
                             "assigned": [0, 1, 2, 3],
                             "tents": [{"indices": [1], "number": "1"},
                                       {"indices": [0, 2, 3], "number": "2"}],
                             "last": {"indices": [0, 2, 3]}},
                    "arafat": {"camp": "arafat", "assigned": [1],
                               "tents": [{"indices": [1]}],
                               "last": {"indices": [1]}}}, session=SESS)
fp2 = fp_of(c.get("/hujjaj/1").get_data(as_text=True))
assert "msg=deleted" in c.post("/hujjaj/1/delete",
                               data={"fp": fp2}).headers["Location"]
app_mode.set_mode(app_mode.HAJJ)
assert names() == ["حاج١", "حاج٣", "حاج٤"]
camps = storage.load_camps(session=SESS)
assert camps["mina"]["assigned"] == [0, 1, 2]
assert [t["indices"] for t in camps["mina"]["tents"]] == [[0, 1, 2]]  # الفارغة حُذفت
assert camps["mina"]["last"]["indices"] == [0, 1, 2]
assert camps["arafat"]["assigned"] == [] and camps["arafat"]["tents"] == []
assert camps["arafat"]["last"] is None
# العمرة لم تتأثّر
app_mode.set_mode(app_mode.UMRAH)
assert names() == ["دخيل", "أحمد"]
print("[ok] حذف سجلّ حج: تسكين المخيمات يتقدّم ولا يُنسب لغير صاحبه")

# ---- 4) صفحات فُتحت قبل حذف سجلّ قبلها: لا تكتب على شخصٍ آخر أبداً ----
import json  # noqa: E402

from hajj_app.fields import parse_amount  # noqa: E402

c.get("/switch/umrah")
for n in ("س١", "س٢", "س٣", "س٤", "س٥"):
    c.post("/hujjaj/new", data={"full_name_ar": n, "passport_number": "S-" + n,
                                "program_value": "1000"})
app_mode.set_mode(app_mode.UMRAH)
assert names() == ["دخيل", "أحمد", "س١", "س٢", "س٣", "س٤", "س٥"]


def recs_by_name(mode=app_mode.UMRAH):
    app_mode.set_mode(mode)
    return {r.full_name_ar: r for r in storage.load_records(session=SESS)[0]}


def fin_rows(html):
    """صفوف المتأخّرات في صفحة المالية: (الاسم، الموضع، الرمز) — صفّاً صفّاً."""
    out = []
    for tr in re.findall(r"<tr>(.*?)</tr>", html, re.S):
        m = re.search(r'action="/finance/(\d+)/pay"', tr)
        f = re.search(r'name="fp" value="([^"]*)"', tr)
        n = re.search(r"<td>([^<]*)</td>", tr)
        if m and f and n:
            out.append((n.group(1), m.group(1), f.group(1)))
    return out


def delete_by_name(name):
    i = names().index(name)
    page = c.get(f"/hujjaj/{i}").get_data(as_text=True)
    assert "msg=deleted" in c.post(f"/hujjaj/{i}/delete",
                                   data={"fp": fp_of(page)}).headers["Location"]


# (أ) صفحة تعديل س٢ مفتوحة، ثم يُحذف س١ → الحفظ يصيب س٢ لا س٣
i2 = names().index("س٢")
stale_fp = fp_of(c.get(f"/hujjaj/{i2}").get_data(as_text=True))
delete_by_name("س١")
r = c.post(f"/hujjaj/{i2}", data={"fp": stale_fp, "full_name_ar": "س٢",
                                  "passport_number": "S-س٢", "phone": "0501"})
assert r.status_code == 200
by = recs_by_name()
assert by["س٢"].phone == "0501" and by["س٣"].phone == ""
assert by["س٣"].passport_number == "S-س٣"                  # هوية س٣ سليمة
# (ب) عدّل غيرك اسم س٣ بعد أن فتحتَ صفحته → صفحتك القديمة تُرفض
i3 = names().index("س٣")
old_fp3 = fp_of(c.get(f"/hujjaj/{i3}").get_data(as_text=True))
c.post(f"/hujjaj/{i3}", data={"fp": old_fp3, "full_name_ar": "س٣ معدّل",
                              "passport_number": "S-س٣"})
r = c.post(f"/hujjaj/{i3}", data={"fp": old_fp3, "full_name_ar": "س٣",
                                  "passport_number": "S-س٣"})
assert "msg=stale" in r.headers["Location"]
assert "س٣ معدّل" in names()
assert "msg=stale" in c.post(f"/hujjaj/{i3}", data={"full_name_ar": "x"}
                             ).headers["Location"]       # بلا بصمة → رفض
assert "x" not in names()

# (ج) صفحة تعديل التسكين مفتوحة، ثم يُحذف سجلّ قبل الآخرين → كلٌّ يأخذ رقمه
page = c.get("/occupancy/edit").get_data(as_text=True)
rows = re.findall(r'<td class="prog-name">([^<]*)</td>.*?name="fp_(\d+)" '
                  r'value="([^"]*)"', page, re.S)
form = {}
for nm, i, tok in rows:
    form.update({f"fp_{i}": tok, f"hotel_{i}": "H-" + nm,
                 f"rtype_{i}": "", f"rnum_{i}": "R-" + nm})
delete_by_name("دخيل")                                       # الكل يتقدّم
r = c.post("/occupancy/edit", data=form)
assert "skipped=1" in r.headers["Location"]                  # دخيل حُذف فتُخطّي
for nm, rec in recs_by_name().items():
    assert rec.room_number == "R-" + nm and rec.hotel == "H-" + nm, (nm, rec.room_number)
print("[ok] صفحات قديمة: التعديل والتسكين يصيبان أصحابهما")

# (د) دفعة من صفحة المالية القديمة → تُسجَّل لصاحبها
fin = c.get("/finance").get_data(as_text=True)
target = next((i, tok) for nm, i, tok in fin_rows(fin) if nm == "س٤")
delete_by_name("أحمد")
c.post(f"/finance/{target[0]}/pay", data={"fp": target[1], "amount": "250"})
by = recs_by_name()
assert parse_amount(by["س٤"].paid_amount) == 250
assert not (by["س٢"].paid_amount or "").strip()
assert "msg=stale" in c.post(f"/finance/{target[0]}/pay",
                             data={"fp": "umrah#x", "amount": "5"}).headers["Location"]

# (هـ) مستند من محرّر مفتوح قبل الحذف → يُؤرشف لصاحبه، وبصمة مجهولة تُرفض
i4 = names().index("س٤")
html = c.get(f"/doc/{i4}/receipt").get_data(as_text=True)
data = json.loads(re.search(r"const D\s*=\s*(\{.*?\});\n", html, re.S).group(1))
assert data["_rec"].startswith("umrah#")
delete_by_name("س٢")                                         # س٤ يتقدّم
r = c.post(f"/doc/{i4}/receipt/pdf", json=data)
assert r.status_code == 200 and r.data[:4] == b"%PDF"
last = storage.load_documents(session=SESS)[-1]
assert last["name"] == "س٤" and last["idx"] == names().index("س٤")
assert "_rec" not in last["data"]
assert c.post(f"/doc/{i4}/receipt/pdf", json={"_rec": "umrah#?"}).status_code == 409

# (و) حذف صورة من صفحة صور قديمة → يحذف صورة صاحبها فقط
by = recs_by_name()
app_mode.set_mode(app_mode.UMRAH)
recs, _n = storage.load_records(session=SESS)
for r_ in recs:
    r_.image_id = "img-" + r_.passport_number
    (images.images_dir() / f"{r_.image_id}.{images.KINDS[0]}").write_bytes(b"x")
storage.save_records(recs, session=SESS)
i4 = names().index("س٤")
ip = c.get(f"/hujjaj/{i4}/images").get_data(as_text=True)
img_fp = fp_of(ip)
delete_by_name("س٣ معدّل")
c.post(f"/hujjaj/{i4}/images/{images.KINDS[0]}/delete", data={"fp": img_fp})
assert not (images.images_dir() / f"img-S-س٤.{images.KINDS[0]}").exists()
# بلا التحقّق كان الموضع القديم يشير إلى س٥ فتُحذف صورته هو
assert (images.images_dir() / f"img-S-س٥.{images.KINDS[0]}").exists()
print("[ok] صفحات قديمة: الدفعة والمستند والصورة تصيب أصحابها")

# (ز) حذف من تبويب عمرة بعد التبديل للحج في تبويب آخر → لا يحذف سجلّ الحج
c.get("/switch/umrah")
c.post("/hujjaj/new", data={"full_name_ar": "مشترك", "passport_number": "Z1"})
iu = names().index("مشترك")
ufp = fp_of(c.get(f"/hujjaj/{iu}").get_data(as_text=True))
c.get("/switch/hajj")
c.post("/hujjaj/new", data={"full_name_ar": "مشترك", "passport_number": "Z1"})
app_mode.set_mode(app_mode.HAJJ)
hn = names()
assert "msg=notfound" in c.post(f"/hujjaj/{iu}/delete", data={"fp": ufp}).headers["Location"]
app_mode.set_mode(app_mode.HAJJ)
assert names() == hn and "مشترك" in hn

# (ح) تسكين خيمة يدوياً من صفحة قديمة → الأشخاص الصحيحون
man = c.get("/camps/tents/manual?camp=arafat").get_data(as_text=True)
picks = re.findall(r'name="fp_(\d+)" value="([^"]*)"></td>\s*<td>([^<]*)</td>', man)
want = {i: tok for i, tok, nm in picks if nm in ("حاج٤", "مشترك")}
assert len(want) == 2, picks
app_mode.set_mode(app_mode.HAJJ)
first = names()[0]
delete_by_name(first)                                        # الكل يتقدّم
form = [("camp", "arafat"), ("number", "7")] + [("pick", i) for i in want] + \
       [(f"fp_{i}", tok) for i, tok in want.items()]
from werkzeug.datastructures import MultiDict  # noqa: E402
c.post("/camps/tents/manual/assign", data=MultiDict(form))
app_mode.set_mode(app_mode.HAJJ)
tent = storage.load_camps(session=SESS)["arafat"]["tents"][-1]
assert sorted(names()[i] for i in tent["indices"]) == sorted(["حاج٤", "مشترك"]), tent
print("[ok] الوضع الآخر لا يُمسّ، وتسكين الخيام اليدوي يصيب أصحابه")


# (ط) نسختان مكرّرتان (استيراد الإكسل مرّتين): حذف النسخة مرّتين لا يحذف الأصل
c.get("/switch/umrah")
for _ in range(2):
    c.post("/hujjaj/new", data={"full_name_ar": "مكرّر", "passport_number": "D1"})
app_mode.set_mode(app_mode.UMRAH)
dup_i = [i for i, n in enumerate(names()) if n == "مكرّر"][-1]
dfp = fp_of(c.get(f"/hujjaj/{dup_i}").get_data(as_text=True))
assert "msg=deleted" in c.post(f"/hujjaj/{dup_i}/delete", data={"fp": dfp}).headers["Location"]
assert "msg=notfound" in c.post(f"/hujjaj/{dup_i}/delete", data={"fp": dfp}).headers["Location"]
app_mode.set_mode(app_mode.UMRAH)
assert names().count("مكرّر") == 1                           # الأصل باقٍ

# (ي) اسم فيه سطر جديد (من الإكسل) يُحفظ ويُحذف بلا رفض
from hajj_app.mrz import PassportData as _PD  # noqa: E402
recs, _n = storage.load_records(session=SESS)
recs.append(_PD(full_name_ar="محمد\nأحمد", passport_number="NL1"))
storage.save_records(recs, session=SESS)
app_mode.set_mode(app_mode.UMRAH)
nl_i = [i for i, n in enumerate(names()) if n.startswith("محمد")][0]
nfp = fp_of(c.get(f"/hujjaj/{nl_i}").get_data(as_text=True))
assert "\n" not in nfp and "\r" not in nfp
r = c.post(f"/hujjaj/{nl_i}", data={"fp": nfp, "full_name_ar": "محمد\r\nأحمد",
                                    "phone": "0509"})
assert r.status_code == 200, r.headers.get("Location")
app_mode.set_mode(app_mode.UMRAH)
assert recs_by_name()["محمد\r\nأحمد"].phone == "0509"

# (ك) رابط عرض صورة من صفحة قديمة لا يعرض صورة شخصٍ آخر
from PIL import Image as _Img  # noqa: E402
kind = images.KINDS[0]
_tmpd = tempfile.mkdtemp()
app_mode.set_mode(app_mode.UMRAH)
recs, _n = storage.load_records(session=SESS)
for n_, r_ in enumerate(recs):                  # صورة جواز مشفّرة حقيقية لكلٍّ
    r_.image_id = "img2-" + r_.uid
    src = os.path.join(_tmpd, f"{n_}.png")
    _Img.new("RGB", (30 + n_ * 7, 20), (n_ * 40 % 256, 90, 160)).save(src)
    images.save_image(r_.image_id, kind, src, SESS)
storage.save_records(recs, session=SESS)
app_mode.set_mode(app_mode.UMRAH)
k = names().index("مكرّر")
assert k + 1 < len(names())                     # بعده شخص يأخذ موضعه بعد الحذف
own = images.load_image(recs[k].image_id, kind, SESS)
nxt = images.load_image(recs[k + 1].image_id, kind, SESS)
assert own and nxt and own != nxt
ip = c.get(f"/hujjaj/{k}/images").get_data(as_text=True)
link = re.search(r'src="(/hujjaj/%d/images/[^"]+)"' % k, ip)
assert link and "fp=" in link.group(1), link
vfp = fp_of(ip)
assert c.get(link.group(1).replace("&amp;", "&")).data == own   # الرابط نفسه
assert c.get(f"/hujjaj/{k}/images/{kind}.file").status_code == 404     # بلا رمز
before = names()
delete_by_name(before[0])                                    # الكل يتقدّم
r = c.get(f"/hujjaj/{k}/images/{kind}.file", query_string={"fp": vfp})
assert r.status_code == 200 and r.data == own and r.data != nxt  # صاحبها لا التالي
assert c.get(f"/hujjaj/{k}/images/{kind}.file",
             query_string={"fp": "umrah#nope#x"}).status_code == 404
print("[ok] المكرّرات والأسطر الجديدة وروابط الصور آمنة")

# (ل) حفظ سطح المكتب (بلا معرّف) يمنح معرّفاً يبقى ثابتاً في الحفظ التالي
_tmp_db = os.path.join(tempfile.mkdtemp(), "desk.json")
desk = [PassportData(full_name_ar="مكتبي١"), PassportData(full_name_ar="مكتبي٢")]
storage.save_records(desk, _tmp_db)
u1 = [r.uid for r in desk]
assert all(u1) and len(set(u1)) == 2                        # في الذاكرة نفسها
storage.save_records(desk, _tmp_db)                         # حفظ تالٍ
assert [r.uid for r in storage.load_records(_tmp_db)[0]] == u1
dup = storage.load_records(_tmp_db)[0]
import copy  # noqa: E402
dup.append(copy.deepcopy(dup[0]))                           # نسخة بالمعرّف نفسه
storage.save_records(dup, _tmp_db)
back = [r.uid for r in storage.load_records(_tmp_db)[0]]
assert len(set(back)) == 3                                  # المكرّر أخذ معرّفاً جديداً

# (م) روابط الصفحات تحمل الرمز: رابط قديم يُوجَّه لصاحبه أو للقائمة
c.get("/switch/umrah")
app_mode.set_mode(app_mode.UMRAH)
nm_list = names()
tgt = len(nm_list) - 1
page = c.get(f"/hujjaj/{tgt}").get_data(as_text=True)
tok = fp_of(page)
assert f"/hujjaj/{tgt}/images?fp=" in page and f"/hujjaj/{tgt}/docs?fp=" in page
delete_by_name(nm_list[0])                                  # الكل يتقدّم
for path in (f"/hujjaj/{tgt}/images", f"/hujjaj/{tgt}/docs", f"/hujjaj/{tgt}",
             f"/doc/{tgt}/receipt", f"/hujjaj/{tgt}/packet.pdf"):
    r = c.get(path, query_string={"fp": tok})
    assert r.status_code == 302, (path, r.status_code)
    assert f"/{tgt - 1}" in r.headers["Location"] and "fp=" in r.headers["Location"], (
        path, r.headers["Location"])
delete_by_name(nm_list[-1])                                 # صاحب الرابط حُذف
r = c.get(f"/hujjaj/{tgt - 1}/images", query_string={"fp": tok})
assert "msg=stale" in r.headers["Location"]

# (ن) تعديل غيرك للاسم يمنع حفظ صفحة التعديل القديمة فقط — الدفعة تبقى لصاحبها
recs, _n = storage.load_records(session=SESS)
recs.append(PassportData(full_name_ar="دافع", passport_number="PAY1",
                         program_value="900"))
storage.save_records(recs, session=SESS)
app_mode.set_mode(app_mode.UMRAH)
fin = c.get("/finance").get_data(as_text=True)
pi, ptok = next((i, t) for n_, i, t in fin_rows(fin) if n_ == "دافع")
ep = c.get(f"/hujjaj/{pi}").get_data(as_text=True)
c.post(f"/hujjaj/{pi}", data={"fp": fp_of(ep), "full_name_ar": "دافع (مصحّح)",
                              "passport_number": "PAY1"})
c.post(f"/finance/{pi}/pay", data={"fp": ptok, "amount": "100"})
assert parse_amount(recs_by_name()["دافع (مصحّح)"].paid_amount) == 100

# (س) كشف تسكين كبير (~2000 صفّ برموزها) لا يُرفض لحجمه
big = {"pad": "ا" * 400_000}                                 # ~800KB بعد الترميز
r = c.post("/occupancy/edit", data=big)
assert r.status_code == 302, r.status_code

# (ع) رسالة رفض المحرّر واضحة لا «HTTP 409» فقط
from hajj_app import webdoc  # noqa: E402
assert "r.text()" in webdoc.web_submit_action("/x")
print("[ok] سطح المكتب يمنح المعرّف، الروابط تتبع صاحبها، والحدود والرسائل سليمة")

# ---- 5) دالّة إزاحة المواضع ----
assert [server._shift_idx(i, 2) for i in (0, 1, 2, 3, 7)] == [0, 1, None, 2, 6]
assert server._shift_idx(None, 0) is None and server._shift_idx(True, 0) is True
print("ALL OK")
