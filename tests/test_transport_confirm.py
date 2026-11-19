# -*- coding: utf-8 -*-
"""البورتال: تأكيد المواصلات للضيف — المستند، رسالة واتساب، الأرشيف، وصفحة التحقّق."""
import io, os, re, sys, tempfile
from datetime import date, timedelta
from urllib.parse import unquote
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["HAJJ_DATA_DIR"] = tempfile.mkdtemp(prefix="tconf_")
from hajj_app import auth, storage, app_mode, umrah, pdf_io  # noqa: E402
from hajj_app.mrz import PassportData  # noqa: E402
try:
    from webapp import server
    server.app.config["CSRF_ENABLED"] = False
except ImportError as exc:
    print(f"[skip] مسارات الويب: {exc}"); print("ALL OK"); sys.exit(0)

owner, _rk = auth.create_account("owner", "Passw0rd!x")
auth.add_account(owner, "sara", "Passw0rd!s", role="editor")
c = server.app.test_client()
c.post("/login", data={"username": "owner", "password": "Passw0rd!x"})
S = next(v for v in server._SESSIONS.values() if v.username == "owner")
app_mode.set_mode(app_mode.UMRAH)

T = date.today()
DEP = (T + timedelta(days=10)).isoformat()
trips = [umrah.UmrahTrip(code="U1", name="رمضان الأول", depart_date=DEP,
                         return_date=(T + timedelta(days=18)).isoformat(), capacity="30")]
st = storage.load_settings()
umrah.save_trips(st, trips)
storage.save_settings(st)
storage.save_records([PassportData(full_name_ar="أحمد سالم العلي", passport_number="P100",
                                   phone="0501234567", trip="U1", nationality_ar="إماراتي")],
                     session=S)
# بصمة السجلّ كما يضعها المحرّر نفسه (يتحقّق منها الحفظ)
FP = re.search(r'"_rec": "([^"]+)"', c.get("/doc/0/receipt").get_data(as_text=True)).group(1)
rec = storage.load_records(session=S)[0][0]          # (السجلات، ملاحظة)


def wa_text(link):
    return unquote(link.split("?text=", 1)[1])


# ---- ١) المستند الجديد يظهر في «المستندات» وفي صفحة مستندات الشخص ----
docs_page = c.get("/documents").get_data(as_text=True)
assert "تأكيد مواصلات للضيف" in docs_page and "/documents/tconf" in docs_page
rd = c.get("/hujjaj/0/docs").get_data(as_text=True)
assert "تأكيد مواصلات للضيف" in rd and "/doc/0/tconf" in rd

# ---- ٢) المحرّر بلا طلب مواصلات سابق: الحركات من البرنامج + زرّ الإرسال بعد الحفظ ----
ed = c.get("/doc/0/tconf").get_data(as_text=True)
assert "تأكيد حجز مواصلات" in ed and "X-WA-Link" in ed and "nextBar" in ed, "محرّر التأكيد بزرّ واتساب"
assert DEP in ed, "أوّل حركة بتاريخ مغادرة البرنامج"
assert "جوال الضيف" in ed and "اسم السائق" in ed and "وقت الانطلاق" in ed
assert "X-WA-Link" not in c.get("/doc/0/treq").get_data(as_text=True), "طلب الناقل بلا زرّ إرسال للضيف"

# ---- ٣) بعد طلب مواصلات للناقل: التأكيد يأخذ الحركات نفسها ----
MOVES = [[DEP, "من مطار جدة الى الفندق في مكة", "1", "GMC", "2026", "10:30"],
         [(T + timedelta(days=14)).isoformat(), "من الفندق في مكة الى محطة قطار مكة", "1", "GMC", "2026", "16:00"]]
r = c.post("/doc/0/treq/pdf", json={"_rec": FP, "number": "MA-T0009", "date": T.isoformat(),
                                    "recipient": "شركة النقل", "honorific": "السيد",
                                    "guest_ar": "أحمد سالم العلي", "phone": "0501234567",
                                    "persons": "3", "movements": MOVES})
assert r.status_code == 200 and r.data[:4] == b"%PDF", (r.status_code, r.data[:300])
assert "X-WA-Link" not in r.headers, "طلب الناقل لا يحمل رابط إرسال للضيف"
ed = c.get("/doc/0/tconf").get_data(as_text=True)
assert "10:30" in ed and "من الفندق في مكة الى محطة قطار مكة" in ed, "الحركات منقولة من طلب المواصلات"
built = pdf_io.build_transport_confirm_data(rec, treq={"movements": MOVES, "persons": "3"})
assert built["movements"][0] == [DEP, MOVES[0][1], "GMC", "2026", "10:30"], "بلا عمود عدد السيارات"
assert built["persons"] == "3" and built["notes"]

# ---- ٤) الحفظ: PDF + رابط واتساب لجوال الضيف برسالة التأكيد كاملة ----
data = dict(built, _rec=FP, number="MA-C0001", driver="أبو خالد", driver_phone="+966 55 000 1111")
r = c.post("/doc/0/tconf/pdf", json=data)
assert r.status_code == 200 and r.data[:4] == b"%PDF", "تأكيد المواصلات PDF"
link = r.headers.get("X-WA-Link", "")
assert link.startswith("https://wa.me/971501234567?text="), link
msg = wa_text(link)
for needle in ("السلام عليكم السيد أحمد", "يسعدنا تأكيد حجز المواصلات", "من مطار جدة الى الفندق في مكة",
               "الانطلاق 10:30", "🚐 GMC 2026", "السائق: أبو خالد", "رقم التأكيد: MA-C0001",
               "تفاصيل التأكيد: http", "/v/", "عمرة مقبولة"):
    assert needle in msg, f"الرسالة ينقصها: {needle}\n{msg}"
d0 = date.fromisoformat(DEP)
assert server._AR_DAYS[d0.weekday()] in msg and server._AR_MONTHS[d0.month - 1] in msg, "التاريخ بالعربي"
assert "\n\n\n" not in msg

# ---- ٥) الأرشيف وصفحة مستندات الشخص: زرّ «إرسال للضيف» ----
arch = storage.load_documents(session=S)
assert [d["kind"] for d in arch] == ["treq", "tconf"]
assert arch[-1]["data"].get("verify_url"), "التأكيد مسجّل للتحقّق (QR)"
rd = c.get("/hujjaj/0/docs").get_data(as_text=True)
assert "إرسال للضيف" in rd and "https://wa.me/971501234567" in rd
ap = c.get("/archive").get_data(as_text=True)
assert "تأكيد حجز مواصلات" in ap and ap.count("إرسال للضيف") == 1, "الزرّ للتأكيد فقط لا لطلب الناقل"

# ---- ٦) صفحة التحقّق العامة: جدول الحركة بلا هواتف ولا أسماء كاملة ----
tok = arch[-1]["data"]["verify_url"].rsplit("/v/", 1)[1]
pub = server.app.test_client().get(f"/v/{tok}")
pv = pub.get_data(as_text=True)
assert pub.status_code == 200 and "مستند أصلي" in pv and "تأكيد حجز مواصلات" in pv
assert "من مطار جدة الى الفندق في مكة" in pv and "الانطلاق" in pv and "10:30" in pv
assert server._AR_DAYS[d0.weekday()] in pv, "التاريخ بصيغة عربية مقروءة"
assert "0501234567" not in pv and "000 1111" not in pv and "أبو خالد" not in pv, "لا هواتف ولا سائق في الصفحة العامة"
assert "أحمد س. ا." in pv and "أحمد سالم العلي" not in pv, "الاسم مختصر"

# ---- ٧) إعادة الإصدار للشخص نفسه: الرقم والرابط ثابتان ----
again = c.get("/doc/0/tconf").get_data(as_text=True)
assert '"number": "MA-C0001"' in again, "رقم التأكيد ثابت للشخص"
r = c.post("/doc/0/tconf/pdf", json=dict(data, movements=MOVES[:1]))
tok2 = storage.load_documents(session=S)[-1]["data"]["verify_url"].rsplit("/v/", 1)[1]
assert tok2 == tok, "رمز التحقّق نفسه بعد التعديل"
assert "محطة قطار مكة" not in server.app.test_client().get(f"/v/{tok}").get_data(as_text=True), \
    "الصفحة العامة تتحدّث بآخر نسخة"

# ---- ٨) رمز النداء المختار يُقدَّم، والرقم غير الصالح لا يعطي رابطاً ----
r = c.post("/doc/0/tconf/pdf", json=dict(data, phone_code="+966 السعودية", phone="0551112222"))
assert r.headers.get("X-WA-Link", "").startswith("https://wa.me/966551112222?text=")
r = c.post("/doc/0/tconf/pdf", json=dict(data, phone=""))
assert r.status_code == 200 and r.headers.get("X-WA-Link") == "", "بلا جوال: يُحفظ ولا رابط"

# ---- ٩) التأكيد اليدوي بلا سجلّ ----
man = c.get("/documents/tconf/manual")
assert man.status_code == 200 and "X-WA-Link" in man.get_data(as_text=True)
r = c.post("/documents/tconf/manual/pdf", json={"number": "MA-C0099", "guest_ar": "ضيف يدوي",
                                                 "phone": "+971 50 999 8888", "movements": MOVES})
assert r.status_code == 200 and r.data[:4] == b"%PDF"
assert r.headers.get("X-WA-Link", "").startswith("https://wa.me/971509998888?text=")

# ---- ١٠) المحرّر يصدر ويرسل أيضاً ----
e = server.app.test_client()
e.post("/login", data={"username": "sara", "password": "Passw0rd!s"})
r = e.post("/doc/0/tconf/pdf", json=data)
assert r.status_code == 200 and r.headers.get("X-WA-Link", "").startswith("https://wa.me/")

# ---- ١١) ملفّ PDF مباشرة: بلا بيانات (من السجلّ) ومع جدول فارغ ----
out = os.path.join(os.environ["HAJJ_DATA_DIR"], "tconf.pdf")
pdf_io.export_transport_confirm_pdf(rec, out)
assert os.path.getsize(out) > 2000
pdf_io.export_transport_confirm_pdf(rec, out, data={"number": "X", "movements": []})
assert os.path.getsize(out) > 2000

# ---- ١٢) رسالة الحج تختم بالحجّ المبرور ----
from flask import session as _fs  # noqa: E402
with server.app.test_request_context():
    _fs["mode"] = app_mode.HAJJ
    assert "حجّاً مبروراً" in server._tconf_message({"guest_ar": "سعيد"}, {})
with server.app.test_request_context():
    assert server._tconf_wa(None) is None and server._tconf_wa({"phone": "12"}) is None

# ---- ١٣) من طلب المواصلات مباشرةً: بعد حفظ الطلب زرّ «إصدار تأكيد للضيف» ----
import json  # noqa: E402
assert "X-Next-Link" in c.get("/doc/0/treq").get_data(as_text=True), "محرّر الطلب يُظهر زرّ التأكيد بعد الحفظ"
assert "X-Next-Link" in c.get("/documents/treq/manual").get_data(as_text=True)
assert "X-Next-Link" not in c.get("/doc/0/receipt").get_data(as_text=True), "السند بلا زرّ تأكيد"
r = c.post("/documents/treq/manual/pdf", json={
    "number": "MA-T0050", "recipient": "شركة النقل", "honorific": "السيدة",
    "guest_ar": "مريم سعيد النعيمي", "phone_code": "+966 السعودية", "phone": "0559876543", "persons": "4",
    "movements": [[DEP, "من مطار المدينة الى الفندق في المدينة", "2", "FORD", "2027", "22:45"]]})
assert r.status_code == 200 and r.data[:4] == b"%PDF"
nxt = r.headers.get("X-Next-Link", "")
assert nxt.startswith("/archive/") and nxt.endswith("/tconf"), nxt
tdoc = storage.load_documents(session=S)[-1]
assert tdoc["kind"] == "treq" and tdoc["name"] == "مريم سعيد النعيمي (يدوي)", "الطلب اليدوي يُؤرشف باسم ضيفه"
ed = c.get(nxt)
et = ed.get_data(as_text=True)
assert ed.status_code == 200 and "من الطلب MA-T0050" in et and "X-WA-Link" in et
assert "22:45" in et and "مريم سعيد النعيمي" in et and "من مطار المدينة الى الفندق في المدينة" in et
assert "0559876543" in et and "+966" in et, "جوال الضيف ورمز دولته من الطلب"
n1 = re.search(r'"number": "([^"]+)"', et).group(1)
assert re.search(r'"number": "([^"]+)"', c.get(nxt).get_data(as_text=True)).group(1) == n1, \
    "رقم التأكيد ثابت لهذا الطلب"
cd = json.loads(re.search(r"const D = (\{.*?\});\n", et, re.S).group(1))
cd["driver"] = "سالم"
r = c.post(nxt + "/pdf", json=cd)
assert r.status_code == 200 and r.data[:4] == b"%PDF"
lk = r.headers.get("X-WA-Link", "")
assert lk.startswith("https://wa.me/966559876543?text="), lk
m2 = wa_text(lk)
assert "السلام عليكم السيدة مريم" in m2 and "الانطلاق 22:45" in m2 and "السائق: سالم" in m2 and "/v/" in m2
last = storage.load_documents(session=S)[-1]
assert last["kind"] == "tconf" and last["name"] == "مريم سعيد النعيمي (يدوي)" and last["data"]["verify_url"]
assert "مريم س. ا." in server.app.test_client().get(
    "/v/" + last["data"]["verify_url"].rsplit("/v/", 1)[1]).get_data(as_text=True)

# الأرشيف وصفحة الشخص: زرّ «تأكيد للضيف» بجانب كل طلب مواصلات
ap = c.get("/archive").get_data(as_text=True)
assert f'href="{nxt}"' in ap and "تأكيد للضيف" in ap
treq0 = next(d for d in storage.load_documents(session=S) if d["kind"] == "treq" and d["number"] == "MA-T0009")
assert f"/archive/{treq0['id']}/tconf" in c.get("/hujjaj/0/docs").get_data(as_text=True)
# طلب مربوط بسجلّ: رقم الشخص نفسه، والرمز العام نفسه (لا تأكيدان للشخص الواحد)
et0 = c.get(f"/archive/{treq0['id']}/tconf").get_data(as_text=True)
assert '"number": "MA-C0001"' in et0 and "10:30" in et0
r = c.post(f"/archive/{treq0['id']}/tconf/pdf", json=json.loads(
    re.search(r"const D = (\{.*?\});\n", et0, re.S).group(1)))
assert r.status_code == 200 and r.headers.get("X-WA-Link", "").startswith("https://wa.me/971501234567")
last = storage.load_documents(session=S)[-1]
assert last["idx"] == 0 and last["name"] == "أحمد سالم العلي" and last["data"]["verify_url"].endswith(tok)

# من عرض سعر: حفظ طلب المواصلات يعيد زرّ التأكيد أيضاً
st = storage.load_settings()
umrah.save_quote(st, "U1", {"number": "MA-Q0031", "lang": "ar", "date": T.isoformat(),
                            "addressed_title": "السيد", "addressed_to": "محمد أحمد",
                            "car_type": "GMC", "car_model": "2026", "car_count": "1",
                            "transport_lines": [[DEP, "مطار جدة", "الفندق في مكة"]],
                            "show_transport": True})
storage.save_settings(st)
qe = c.get("/quotes/U1/MA-Q0031/doc/treq").get_data(as_text=True)
assert "X-Next-Link" in qe
qd = json.loads(re.search(r"const D = (\{.*?\});\n", qe, re.S).group(1))
qd["phone"] = "0507770000"
r = c.post("/quotes/U1/MA-Q0031/doc/treq/pdf", json=qd)
assert r.status_code == 200 and r.headers.get("X-Next-Link", "").endswith("/tconf")
qt = c.get(r.headers["X-Next-Link"]).get_data(as_text=True)
assert "محمد أحمد" in qt and "0507770000" in qt
# الفاوتشر من العرض بلا زرّ تأكيد، ومعرّفات غير صالحة تُرفض
assert "X-Next-Link" not in c.get("/quotes/U1/MA-Q0031/doc/voucher").get_data(as_text=True)
assert c.get(f"/archive/{last['id']}/tconf").status_code == 302, "التأكيد يُبنى من طلب مواصلات فقط"
assert c.get("/archive/nope/tconf").status_code == 302
assert c.post("/archive/nope/tconf/pdf", json={}).status_code == 404
assert server.app.test_client().get(nxt).status_code == 302, "يحتاج تسجيل دخول"
# المحرّر (صلاحية تحرير) يستخدمه أيضاً
assert e.get(nxt).status_code == 200

# ---- ١٤) ختم الأصالة على الآيفون: اسم الشركة المنحني بحروف مُشكَّلة جاهزة ----
# Safari يرصّ حروف textPath منفصلة بلا وصل ولا ترتيب؛ نرسل الأشكال الجاهزة بترتيب العرض.
ring = server._svg_ar("المصطفى للحج والعمرة")
assert all(0xFE70 <= ord(ch) <= 0xFEFF or ch == " " for ch in ring), "كل الحروف بأشكالها المتّصلة الجاهزة"
assert ring[0] == "ﺓ" and ring[-1] == "ﺍ", "ترتيب العرض: التاء المربوطة يساراً والألف يميناً"
assert server._svg_ar("") == "" and server._svg_ar("AL") == "AL"
pv = server.app.test_client().get(f"/v/{tok}").get_data(as_text=True)
assert f'unicode-bidi="bidi-override"><textPath href="#vfTop" startOffset="50%" text-anchor="middle">{ring}<' in pv
css = open(os.path.join(ROOT, "webapp", "static", "style.css"), encoding="utf-8").read()
assert "unicode-bidi:bidi-override" in css.split(".vf-ring-ar{", 1)[1].split("}", 1)[0]

print("ALL OK")
