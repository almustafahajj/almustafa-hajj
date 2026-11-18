# -*- coding: utf-8 -*-
"""البورتال: لحظة استلام الدفعة وسجلّ الدفعات، رفيق المعتمر في الحرم (المواقيت وعدّاد
الأشواط)، وختم الأصالة على صفحة التحقّق مع رمز التحقّق على السند والفاتورة والعقد."""
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
os.environ["HAJJ_DATA_DIR"] = tempfile.mkdtemp(prefix="phs_")
from hajj_app import app_mode, auth, storage, umrah  # noqa: E402
from hajj_app.mrz import PassportData  # noqa: E402
try:
    from webapp import server, public, prayer
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
                    return_date=(T + timedelta(days=9)).isoformat()),
    umrah.UmrahTrip(code="U2", name="عمرة بعيدة", depart_date=(T + timedelta(days=20)).isoformat(),
                    return_date=(T + timedelta(days=27)).isoformat()),
    umrah.UmrahTrip(code="U3", name="عمرة جارية", depart_date=(T - timedelta(days=2)).isoformat(),
                    return_date=(T + timedelta(days=5)).isoformat()),
    umrah.UmrahTrip(code="U4", name="عمرة انتهت", depart_date=(T - timedelta(days=12)).isoformat(),
                    return_date=(T - timedelta(days=4)).isoformat())])
storage.save_settings(st)
storage.save_records([
    PassportData(full_name_ar="أحمد علي الكعبي", passport_number="P100", uid="aa11", trip="U1",
                 phone="0501111111", program_value="6000", paid_amount="1000"),
    PassportData(full_name_ar="سالم خالد", passport_number="P200", uid="bb22", trip="U2", phone="0502222222"),
    PassportData(full_name_ar="مريم سعيد", passport_number="P300", uid="cc33", trip="U3", phone="0503333333"),
    PassportData(full_name_ar="فاطمة حسن", passport_number="P400", uid="dd44", trip="U4", phone="0504444444")],
    session=SESS)


def recs():
    return storage.load_records(session=SESS)[0]


def fp(i):
    with server.app.test_request_context("/"):
        return server._rec_token(recs()[i])


# ---- ١) لحظة استلام الدفعة ----
assert 'name="method"' in c.get("/finance").get_data(as_text=True)
r = c.post("/finance/0/pay", data={"fp": fp(0), "amount": "2000", "method": "نقد"})
assert r.status_code == 302 and r.headers["Location"].endswith("/finance")
pg = c.get("/finance").get_data(as_text=True)
ov = pg.split('id="pmOverlay"')[1].split("</script>")[0]
assert "أحمد علي الكعبي" in ov and "2,000" in ov and "الدفعة رقم 2" in ov, "الرصيد السابق دفعةٌ أولى"
assert 'data-from="17"' in ov and 'data-to="50"' in ov, "من 17% إلى 50%"
assert "المتبقّي <b>3,000</b>" in ov and "مدفوع" not in ov.split("pm-acts")[0].split("pm-left")[1][:60]
assert "نقد" in ov and 'class="pm-overlay"' in pg and "pm-seal" not in ov
wa = unquote(unescape(re.search(r'href="(https://wa\.me/[^"]+)"', ov).group(1)))
assert "2,000" in wa and "3,000" in wa and "أحمد" in wa, wa
assert "/doc/0/receipt" in ov, "زرّ إصدار السند"
# السند من النافذة لهذه الدفعة (2,000 نقداً) لا للمجموع المدفوع (3,000 بتحويل)
rl = unescape(re.search(r'href="([^"]*/doc/0/receipt[^"]*)"', ov).group(1))
assert "amount=2000.00" in rl, rl
ed_r = c.get(rl).get_data(as_text=True)
assert "2000.00" in ed_r and "Cash" in ed_r and "3000.00" not in ed_r, "السند مُعبّأ بمبلغ الدفعة وطريقتها"
assert 'stroke-dashoffset="-17"' in ov and "pm-r-was" in ov, "الحلقة: السابق ثم هذه الدفعة"
assert 'aria-live' not in ov and "sr-only" in ov
assert 'id="pmOverlay"' not in c.get("/finance").get_data(as_text=True), "تظهر مرّة واحدة"
p = recs()[0]
assert p.paid_amount == "3,000" and [x["method"] for x in p.payments] == ["رصيد سابق", "نقد"]
from datetime import datetime  # noqa: E402
assert p.payments[-1]["date"] == datetime.now(server._UAE).date().isoformat(), "تاريخ الدفعة بتوقيت الإمارات"
# من ملف المعتمر: يكتمل السداد ← ختم «مدفوع بالكامل» ورسالة شكر
ed = c.get("/hujjaj/0", query_string={"fp": fp(0)}).get_data(as_text=True)
assert 'id="payments"' in ed and 'name="back" value="edit"' in ed and "رصيد افتتاحي" in ed
r = e.post("/finance/0/pay", data={"fp": fp(0), "amount": "3000", "method": "بطاقة", "back": "edit"})
assert "/hujjaj/0" in r.headers["Location"] and r.headers["Location"].endswith("#payments")
ed = e.get(r.headers["Location"].split("#")[0]).get_data(as_text=True)
ov = ed.split('id="pmOverlay"')[1].split("</script>")[0]
assert 'class="pm-overlay full"' in ed and "pm-seal" in ov and "اكتمل السداد" in ov
assert "شكر وإشعار بالاكتمال" in ov and "اكتمل" in unquote(unescape(re.search(r'href="(https://wa\.me/[^"]+)"', ov).group(1)))
assert 'data-to="100"' in ov
line = ed.split('class="ph-line"')[1].split("</ol>")[0]
assert line.count("<li") == 3 and "2,000" in line and "3,000" in line and "بطاقة" in line
assert '<details class="panel pay-hist" id="payments" open>' in ed, "يُفتح القسم بعد الدفعة"
# الصلاحيات والحالات الخاطئة
assert "ph-add" not in v.get("/hujjaj/0", query_string={"fp": fp(0)}).get_data(as_text=True), "المطّلع لا يسجّل"
n0 = len(recs()[0].payments)
v.post("/finance/0/pay", data={"fp": fp(0), "amount": "50"})
c.post("/finance/0/pay", data={"fp": fp(0), "amount": "-5"})
c.post("/finance/0/pay", data={"fp": fp(0), "amount": "abc"})
assert len(recs()[0].payments) == n0, "لا دفعة من المطّلع ولا بمبلغ غير صالح"
r = c.post("/finance/0/pay", data={"fp": "zz", "amount": "10", "back": "edit"})
assert "msg=stale" in r.headers["Location"] and len(recs()[0].payments) == n0
nopay = c.get("/hujjaj/1", query_string={"fp": fp(1)}).get_data(as_text=True)
assert "لا دفعات مسجّلة بعد" in nopay and 'id="pmOverlay"' not in nopay
print("[ok] لحظة الدفعة: سند وعدّ ونسبة، ختم عند الاكتمال، واتساب، مرّة واحدة، سجلّ الدفعات، صلاحيات")

# ---- ٢) رفيق المعتمر في الحرم ----
mk = prayer.CITIES["makkah"]


def mins(t):
    h, m = t.split(":")
    return int(h) * 60 + int(m)


# مواقيت أمّ القرى المنشورة لمكة 2023-06-21: 04:12 05:39 12:23 15:41 19:07 20:37 (±2 دقيقة)
ref = ["04:12", "05:39", "12:23", "15:41", "19:07", "20:37"]
got = prayer.times(date(2023, 6, 21), mk[1], mk[2])
assert all(abs(mins(a) - mins(b)) <= 2 for a, b in zip(got, ref)), got
for d in (date(2026, 1, 15), date(2026, 4, 1), date(2026, 7, 20), date(2026, 10, 5)):
    for k, (_n, la, lo) in prayer.CITIES.items():
        t = [mins(x) for x in prayer.times(d, la, lo)]
        assert t == sorted(t) and 3 * 60 < t[0] < 6 * 60 and 11 * 60 + 50 < t[2] < 12 * 60 + 40, (d, k, t)
        assert t[5] - t[4] == 90
rt = prayer.times(date(2027, 2, 20), mk[1], mk[2], ramadan=True)
assert mins(rt[5]) - mins(rt[4]) == 120, "العشاء بعد المغرب بساعتين في رمضان"
tb = prayer.table(date(2027, 2, 20), 2, server._uq_ramadan)
assert mins(tb["2027-02-20"]["makkah"][5]) - mins(tb["2027-02-20"]["makkah"][4]) == 120
# رمضان بتقويم أمّ القرى (لا الحسابي): العيد 2027-03-09 ليس من رمضان، و2030-01-05 أوّله
assert server._uq_ramadan(date(2027, 3, 8)) and not server._uq_ramadan(date(2027, 3, 9))
assert server._uq_ramadan(date(2030, 1, 5)) and not server._uq_ramadan(date(2030, 1, 4))
assert server._uq_ramadan(date(2026, 3, 19)) and not server._uq_ramadan(date(2026, 3, 20))


def person(i):
    c.post(f"/hujjaj/{i}/link", data={"fp": fp(i), "action": "create"})
    tok = public.find_person("umrah", recs()[i].uid)
    return anon.get("/p/" + tok).get_data(as_text=True)


soon, far, during, after = person(0), person(1), person(2), person(3)
for page, show in ((soon, True), (far, False), (during, True), (after, False)):
    assert ('id="haram"' in page) == show, page[:200]
data = json.loads(unescape(re.search(r'<script type="application/json" id="haramData">(.*?)</script>',
                                     during, re.S).group(1)))
assert T.isoformat() in data["days"] and (T - timedelta(days=1)).isoformat() in data["days"]
assert (T + timedelta(days=6)).isoformat() in data["days"], "حتى اليوم التالي للعودة"
assert len(data["days"][T.isoformat()]["madinah"]) == 6 and data["names"][0] == "الفجر"
assert "اتّبع أذان الحرم" in during and 'id="hrTap"' in during and "haram.js" in during
assert during.index("</header>") < during.index('id="haram"') < during.index("للطوارئ") if "للطوارئ" in during \
    else during.index("</header>") < during.index('id="haram"'), "القسم أوّل الصفحة بعد الترويسة"
js = anon.get("/static/haram.js")
assert js.status_code == 200 and b"wakeLock" in js.data and b"makkahNow" in js.data
js.close()
print("[ok] رفيق الحرم: مواقيت أمّ القرى (±2 د)، رمضان، يظهر قبل السفر بـ٣ أيام وأثناءه فقط، عدّاد الأشواط")

# ---- ٣) ختم الأصالة ----
co = {"name_ar": "المصطفى للحج والعمرة", "phone": "+971 2 555 0000"}
st = storage.load_settings()
st["company"] = co
storage.save_settings(st)
SIDS = {s.username: k for k, s in server._SESSIONS.items()}


def attach(kind, d, uid="aa11", who="owner"):
    with server.app.test_request_context("/"):
        server.session["sid"] = SIDS[who]
        server._attach_verify(kind, d, uid=uid)
    return d


d1 = attach("receipt", {"number": "0119", "date": "2026-11-13", "name": "أحمد علي الكعبي", "amount": "2000.00", "bank": "نقد"})
d2 = attach("receipt", {"number": "0119", "date": "2026-11-20", "name": "أحمد علي الكعبي", "amount": "3000.00", "bank": "بطاقة"})
d3 = attach("receipt", {k: v for k, v in d1.items() if k != "verify_url"})
dc = attach("contract", {"number": "CON-0120", "date": "2026-11-13", "guest_ar": "أحمد علي الكعبي", "title_ar": "عقد خدمات عمرة"})
di = attach("invoice", {"number": "INV-0121", "date": "2026-11-13", "guest_ar": "أحمد علي الكعبي", "amount": "6000.00"})
for d in (d1, d2, d3, dc, di):
    assert "/v/" in d.get("verify_url", ""), d
assert d1["verify_url"] == d3["verify_url"] != d2["verify_url"], "مبلغ آخر بنفس الرقم ← رمز آخر"
# أفراد العائلة يتشاركون رقم المستند: لكلٍّ رمزه واسمه (لا يحلّ أحدهما محلّ الآخر)
dm = attach("receipt", {"number": "0119", "date": "2026-11-13", "name": "مريم سعيد", "amount": "2000.00", "bank": "نقد"}, uid="cc33")
cm = attach("contract", {"number": "CON-0120", "date": "2026-11-13", "guest_ar": "مريم سعيد"}, uid="cc33")
assert dm["verify_url"] != d1["verify_url"] and cm["verify_url"] != dc["verify_url"]
assert "مريم" in anon.get("/v/" + dm["verify_url"].rsplit("/", 1)[1]).get_data(as_text=True)
assert "أحمد" in anon.get("/v/" + dc["verify_url"].rsplit("/", 1)[1]).get_data(as_text=True)
assert len(public.person_docs("umrah", "aa11")) >= 4 and len(public.person_docs("umrah", "cc33")) == 2
# المطّلع (قراءة فقط) لا يُصدر ختماً «أصلياً»: PDF بلا تسجيل في سجلّ التحقّق
assert "verify_url" not in attach("receipt", {"number": "9999", "name": "Any Body", "amount": "50000"}, uid="", who="view")
n_docs = len(public._load()["docs"])
r = v.post("/documents/receipt/manual/pdf", json={"number": "9999", "name": "Any Body", "amount": "50000", "bank": "Cash"})
assert r.status_code == 200 and len(public._load()["docs"]) == n_docs, "المطّلع لا يسجّل مستنداً للتحقّق"
tok = d1["verify_url"].rsplit("/", 1)[1]
vp = anon.get("/v/" + tok)
html = vp.get_data(as_text=True)
assert vp.status_code == 200 and "مستند أصلي" in html and "vf-seal" in html and "سند قبض" in html
assert "2,000" in html and "نقد" in html and "0119" in html
assert "أحمد علي الكعبي" not in html and "أحمد" in html, "الاسم مُقنَّع"
assert "wa.me/971549964801" in html and "tel:+97125550000" in html and "/trips" in html
ct = anon.get("/v/" + dc["verify_url"].rsplit("/", 1)[1]).get_data(as_text=True)
assert "عقد خدمات" in ct and "عقد خدمات عمرة" in ct and "المبلغ" not in ct.split("vf-rows")[1].split("</dl>")[0]
bad = anon.get("/v/not-a-real-token")
assert bad.status_code == 404 and "لا يوجد مستند بهذا الرمز" in bad.get_data(as_text=True)
assert "vf-stage bad" in bad.get_data(as_text=True)
# رمز QR في الـ PDF رابطُ التحقّق (السند والعقد)
from hajj_app import pdf_io  # noqa: E402
rec = recs()[0]
tmp = tempfile.mkdtemp()
rp, cp = os.path.join(tmp, "r.pdf"), os.path.join(tmp, "c.pdf")
pdf_io.export_receipt_pdf(rec, rp, company=co, data=d1)
pdf_io.export_contract_pdf(rec, cp, company=co, data=dict(dc, body="البند الأول\nنص البند"))
try:
    import cv2
    import fitz
    import numpy as np
    for path, url in ((rp, d1["verify_url"]), (cp, dc["verify_url"])):
        txt = ""
        # كاشف OpenCV العادي يُخفق أحياناً (أو يرفع خطأً) على الصفحة كاملة — الرمز
        # عشوائي في كل تشغيل؛ نجرّب عدّة دقّات ثم كاشف Aruco قبل الحكم بأنّه غير مقروء.
        dets = [cv2.QRCodeDetector()] + ([cv2.QRCodeDetectorAruco()]
                                         if hasattr(cv2, "QRCodeDetectorAruco") else [])
        for det in dets:
            for dpi in (200, 300, 150, 250):
                with fitz.open(path) as doc:
                    pix = doc[-1].get_pixmap(dpi=dpi)
                img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
                try:
                    txt = det.detectAndDecode(img[:, :, :3].copy())[0]
                except cv2.error:
                    txt = ""
                if txt:
                    break
            if txt:
                break
        assert txt == url, (path, txt, url)
    print("[ok] رمز QR في السند والعقد يُقرأ رابطَ التحقّق")
except ImportError:
    print("[skip] قراءة QR من الـ PDF (لا cv2)")
# المستند يظهر في «رحلتي» صاحبِه
assert "سند قبض" in person(0)
print("[ok] ختم الأصالة: رمز لكل مستند ونسخة، صفحة بختم وبيانات مُقنَّعة، صفحة الرمز الخاطئ 404")
print("ALL OK")
