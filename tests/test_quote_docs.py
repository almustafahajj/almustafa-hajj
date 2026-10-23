# -*- coding: utf-8 -*-
"""فاوتشر الفندق وطلب المواصلات من عرض سعر محفوظ (بالرقم المرجعي):
البحث بالرقم، تحويل البيانات (عربي/إنجليزي)، توليد PDF، ومسارات الويب."""
import io
import os
import sys
import tempfile

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TMP = tempfile.mkdtemp(prefix="quote_docs_")
os.environ["HAJJ_DATA_DIR"] = _TMP

from hajj_app import app_mode, pdf_io, storage, umrah  # noqa: E402
from hajj_app.mrz import PassportData  # noqa: E402

app_mode.set_mode(app_mode.UMRAH)

QUOTE_AR = {
    "number": "MA-Q0007", "lang": "ar", "date": "2026-10-20",
    "addressed_title": "السيد", "addressed_to": "محمد أحمد",
    "guests": [["2", "كبير"], ["1", "طفل"]],
    "stays": [
        ["مكة المكرمة", "4", "فيرمونت مكة (برج الساعة)", "ثنائي", "1",
         "مطلّة حرم", "إفطار", "2026-11-01", ""],
        ["المدينة المنورة", "", "أنوار المدينة موفنبيك", "ثلاثي", "",
         "غير مطلّة", "إفطار", "2026-11-05", "2026-11-08"],
        ["", "", "", "", "", "", "", "", ""],
    ],
    "flights": [["2026-11-01", "الاتحاد للطيران", "08:00", "أبوظبي (AUH)",
                 "10:30", "جدة (JED)"]],
    "car_type": "GMC", "car_model": "2026", "car_count": "2",
    "transport_lines": [["2026-11-01", "مطار جدة", "الفندق في مكة"],
                        ["2026-11-05", "فندق مكة", "فندق المدينة"]],
    "show_transport": True,
}
QUOTE_EN = dict(QUOTE_AR, number="MA-Q0012", lang="en",
                addressed_title="Mr.", addressed_to="John Smith",
                guests=[["3", "Adult"]],
                stays=[["Makkah", "3", "Swissôtel Makkah", "Double", "2",
                        "Haram View", "Breakfast", "2026-12-01", ""]],
                transport_lines=[["", "Jeddah Airport", "Makkah Hotel"]])

# ---- 1) البحث بالرقم المرجعي ----
settings = {"umrah_quotes": {"U1": [QUOTE_AR], "_manual": [QUOTE_EN]}}
assert umrah.find_quote(settings, "MA-Q0007") == ("U1", QUOTE_AR)
assert umrah.find_quote(settings, " ma-q0007 ") == ("U1", QUOTE_AR)
assert umrah.find_quote(settings, "7") == ("U1", QUOTE_AR)
assert umrah.find_quote(settings, "Q12") == ("_manual", QUOTE_EN)
assert umrah.find_quote(settings, "MA-Q0099") == (None, None)
assert umrah.find_quote(settings, "") == (None, None)
assert umrah.find_quote({}, "MA-Q0007") == (None, None)
assert umrah.find_quote({"umrah_quotes": []}, "7") == (None, None)
# الرقم نفسه تحت برنامجين (حُفظ من سطح المكتب ثم من الويب) → لا اختيار صامت
_old = dict(QUOTE_AR, addressed_to="نسخة قديمة")
dup = {"umrah_quotes": {"U1": [_old], "_manual": [QUOTE_AR]}}
assert umrah.find_quote(dup, "MA-Q0007") == (None, None)
assert [c for c, _q in umrah.find_quotes(dup, "7")] == ["U1", "_manual"]
# المطابقة التامّة أولى من المختصرة
mix = {"umrah_quotes": {"U1": [dict(QUOTE_AR, number="Q7")], "U2": [QUOTE_AR]}}
assert umrah.find_quote(mix, "MA-Q0007") == ("U2", QUOTE_AR)
print("[ok] find_quote: رقم كامل/مختصر/غير موجود/مكرّر")

# ---- 2) فاوتشر من عرض عربي ----
v = pdf_io.voucher_data_from_quote(QUOTE_AR, number="MA0005")
assert v["number"] == "MA0005" and v["lang"] == "ar"
assert v["guest_ar"] == "محمد أحمد" and v["guest_en"] == ""
assert v["quote_ref"] == "MA-Q0007"
assert len(v["stays"]) == 2, v["stays"]               # الصفّ الفارغ أُسقط
mk, md = v["stays"]
# [المدينة، الفندق، نوع الغرفة، عدد الغرف، الإطلالة، الدخول، المغادرة، الليالي، الوجبات]
assert mk == ["مكة المكرمة", "فيرمونت مكة (برج الساعة)", "ثنائي", "1",
              "مطلّة حرم", "2026-11-01", "2026-11-05", "4", "إفطار"], mk
assert md[3] == "1" and md[6] == "2026-11-08" and md[7] == "3", md
# التنقّلات في صفّ واحد (صفّ لكل تنقّل يدفع الشروط إلى صفحة ثانية)
assert v["transport_rows"] == [
    ["GMC", "2026", "من مطار جدة إلى الفندق في مكة؛ "
                    "من فندق مكة إلى فندق المدينة"]], v["transport_rows"]
assert v["terms"] and v["contacts"]                    # من القيَم الافتراضية
assert ["عمليات المدينة", "عبد العزيز", "+966 55 910 3216"] in v["contacts"]
assert ["Madinah Operations", "عبد العزيز", "+966 55 910 3216"] in (
    pdf_io.voucher_data_from_quote(QUOTE_EN)["contacts"])
assert all(len(r) == 9 for r in v["stays"])
print("[ok] فاوتشر من عرض عربي")

# ---- 3) فاوتشر من عرض إنجليزي ----
ve = pdf_io.voucher_data_from_quote(QUOTE_EN, number="MA0006")
assert ve["lang"] == "en" and ve["guest_en"] == "JOHN SMITH"
assert ve["stays"][0][:5] == ["Makkah", "Swissôtel Makkah", "Double", "2",
                              "Haram View"]
assert ve["stays"][0][6] == "2026-12-04"
assert ve["transport_rows"] == [
    ["GMC", "2026", "From Jeddah Airport to Makkah Hotel"]]
assert ve["status"] == "CONFIRMED"
print("[ok] فاوتشر من عرض إنجليزي")

# المواصلات مخفيّة في العرض → لا خطة نقل في الفاوتشر
vh = pdf_io.voucher_data_from_quote(dict(QUOTE_AR, show_transport=False))
assert vh["transport_rows"] == []
# سيارة بلا بنود تنقّل → صفّ بوجهة عامّة
vn = pdf_io.voucher_data_from_quote(dict(QUOTE_AR, transport_lines=[]))
assert len(vn["transport_rows"]) == 1 and vn["transport_rows"][0][0] == "GMC"
# عرض شبه فارغ لا يُسقِط البناء
pdf_io.voucher_data_from_quote({})
pdf_io.voucher_data_from_quote({"stays": [["مكة"]], "transport_lines": [["x"]]})
pdf_io.voucher_data_from_quote({"stays": None, "flights": [None, "x", {"a": 1}],
                                "guests": "2"})
pdf_io.transport_request_data_from_quote({"stays": [None], "guests": [["٢"]]})

# تواريخ الإقامة تُستكمل تسلسلياً من «الفترة من» كما في PDF العرض
chain = dict(QUOTE_AR, period_from="2026-11-01", stays=[
    ["مكة المكرمة", "4", "هيلتون مكة", "ثنائي", "1", "", "إفطار", "", ""],
    ["المدينة المنورة", "3", "هيلتون المدينة", "ثنائي", "1", "", "إفطار",
     "", ""]])
vc = pdf_io.voucher_data_from_quote(chain)
assert [r[5:8] for r in vc["stays"]] == [["2026-11-01", "2026-11-05", "4"],
                                         ["2026-11-05", "2026-11-08", "3"]]
# الدخول اليدوي للأولى يُحترم والثانية تتبعها
chain["stays"][0][7] = "2026-11-02"
vc = pdf_io.voucher_data_from_quote(chain)
assert [r[5:7] for r in vc["stays"]] == [["2026-11-02", "2026-11-06"],
                                         ["2026-11-06", "2026-11-09"]]
print("[ok] حالات الحافّة للفاوتشر وتسلسل التواريخ")

# ---- قيَم العرض تتبع لغة المستند لا علَم لغة العرض ----
# عرض إنجليزي بُدّلت لغته إلى العربية (القيَم بقيت إنجليزية) → طلب عربي خالص
switched = dict(QUOTE_EN, lang="ar", stays=[
    ["Makkah", "3", "Hilton Makkah", "One-Bedroom Suite", "1", "Haram View",
     "Breakfast", "2026-12-01", ""]],
    flights=[["2026-12-01", "Etihad Airways", "08:00", "Abu Dhabi (AUH)",
              "10:30", "Jeddah (JED)"]])
ts = pdf_io.transport_request_data_from_quote(switched)
assert ts["bookings"] == [["مكة المكرّمة", "هيلتون مكة", "جناح غرفة وصالة",
                           "مطلّة حرم"]], ts["bookings"]
assert ts["flights"][0][1] == "الاتحاد للطيران"
assert ts["flights"][0][4:] == ["أبوظبي (AUH)", "10:30", "جدة (JED)"]
assert ts["movements"][0][1] == "من مطار جدة الى الفندق في مكة"
# عرض عربي بُدّلت لغته إلى الإنجليزية → فاوتشر إنجليزي بقيَم إنجليزية
vs = pdf_io.voucher_data_from_quote(dict(QUOTE_AR, lang="en"))
assert vs["stays"][0][:5] == ["Makkah", "Fairmont Makkah (Clock Tower)",
                              "Double", "1", "Haram View"], vs["stays"][0]
assert "From Jeddah Airport to Makkah Hotel" in vs["transport_rows"][0][2]
assert not any("؀" <= ch <= "ۿ"
               for r in vs["stays"] for c in r for ch in c)
print("[ok] القيَم تُترجم حسب لغة المستند")

# ---- 4) طلب مواصلات من عرض عربي ----
t = pdf_io.transport_request_data_from_quote(QUOTE_AR, number="MA-T0003")
assert t["number"] == "MA-T0003" and t["quote_ref"] == "MA-Q0007"
assert t["honorific"] == "السيد" and t["guest_ar"] == "محمد أحمد"
assert t["persons"] == "3"
assert t["bookings"] == [
    ["مكة المكرمة", "فيرمونت مكة (برج الساعة)", "ثنائي", "مطلّة حرم"],
    ["المدينة المنورة", "أنوار المدينة موفنبيك", "ثلاثي", "غير مطلّة"]]
assert t["flights"] == [["2026-11-01", "الاتحاد للطيران", "", "08:00",
                         "أبوظبي (AUH)", "10:30", "جدة (JED)"]]
assert t["movements"] == [
    ["2026-11-01", "من مطار جدة الى الفندق في مكة", "2", "GMC", "2026", ""],
    ["2026-11-05", "من الفندق في مكة الى الفندق في المدينة", "2", "GMC",
     "2026", ""]], t["movements"]
assert t["movements"][0][1] in pdf_io.TREQ_ROUTE_OPTIONS
print("[ok] طلب مواصلات من عرض عربي")

# ---- 5) طلب مواصلات من عرض إنجليزي (يُحوَّل للعربية) ----
te = pdf_io.transport_request_data_from_quote(QUOTE_EN)
assert te["honorific"] == "السيد" and te["persons"] == "3"
assert te["bookings"] == [["مكة المكرّمة", "سويس أوتيل مكة", "ثنائي",
                           "مطلّة حرم"]], te["bookings"]
assert te["movements"][0][1] == "من مطار جدة الى الفندق في مكة", te["movements"]
assert te["quote_ref"] == "MA-Q0012"
tm = pdf_io.transport_request_data_from_quote(
    dict(QUOTE_EN, addressed_title="Messrs."))
assert tm["honorific"] == "السادة"
# بلا بنود تنقّل → قالب الحركة الافتراضي بسيارة العرض
tn = pdf_io.transport_request_data_from_quote(dict(QUOTE_AR, transport_lines=[]))
assert tn["movements"] and all(m[3] == "GMC" and m[4] == "2026" and m[2] == "2"
                               for m in tn["movements"])
pdf_io.transport_request_data_from_quote({})
print("[ok] طلب مواصلات من عرض إنجليزي وحالات الحافّة")

# ---- 6) توليد PDF فعلي من البيانات المحوّلة ----
out = os.path.join(_TMP, "out")
os.makedirs(out, exist_ok=True)
for name, data in (("v_ar", v), ("v_en", ve)):
    p = os.path.join(out, name + ".pdf")
    pdf_io.export_umrah_voucher_pdf(PassportData(), p, data=data)
    assert os.path.getsize(p) > 1000
for name, data in (("t_ar", t), ("t_en", te)):
    p = os.path.join(out, name + ".pdf")
    pdf_io.export_umrah_transport_request_pdf(PassportData(), p, data=data)
    assert os.path.getsize(p) > 1000
print("[ok] توليد PDF للفاوتشر والطلب")


# ---- قوائم منسدلة في الفاوتشر والطلب كما في عرض السعر ----
def _cols(schema, table):
    return {c["key"]: c for s in schema if s.get("table") == table
            for c in s["columns"]}


def _fields(schema):
    return {f["key"]: f for s in schema for f in s.get("fields", [])}


qa = {(s.get("table"), c["key"]): c.get("options")
      for s in pdf_io.umrah_quotation_schema("ar")
      for c in s.get("columns", []) + s.get("fields", [])}
vs_ar = _cols(pdf_io.voucher_schema("ar"), "stays")
for k in ("city", "hotel", "room", "rooms", "view", "nights", "meals"):
    assert vs_ar[k]["type"] == "selectfree", k
    assert vs_ar[k]["options"] == qa[("stays", k)], k      # نفس خيارات العرض
assert vs_ar["cin"]["type"] == "date"                     # التواريخ تبقى تقويماً
vt = _cols(pdf_io.voucher_schema("ar"), "transport_rows")
assert vt["car"]["options"] == qa[(None, "car_type")]
assert vt["model"]["options"] == qa[(None, "car_model")]
assert "من مطار جدة إلى الفندق في مكة" in vt["dest"]["options"]
vf = _fields(pdf_io.voucher_schema("ar"))
assert vf["lang"]["type"] == "select"                     # اللغة تبقى صارمة
assert vf["status"]["type"] == "selectfree" and v["status"] in vf["status"]["options"]
vs_en = _cols(pdf_io.voucher_schema("en"), "stays")
assert "Makkah" in vs_en["city"]["options"] and "Haram View" in vs_en["view"]["options"]
assert ve["status"] in _fields(pdf_io.voucher_schema("en"))["status"]["options"]
assert pdf_io.VOUCHER_SCHEMA == pdf_io.voucher_schema("ar")
tb = _cols(pdf_io.TREQ_SCHEMA, "bookings")
assert tb["hotel"]["options"] == qa[("stays", "hotel")]
tfl = _cols(pdf_io.TREQ_SCHEMA, "flights")
assert tfl["carrier"]["options"] == qa[("flights", "carrier")]
assert tfl["from"]["type"] == "selectfree" and tfl["date"]["type"] == "date"
tm_ = _cols(pdf_io.TREQ_SCHEMA, "movements")
for m in t["movements"]:                    # خطوط السير المعبّأة من العرض ضمن الخيارات
    assert m[1] in tm_["route"]["options"], m[1]
assert tm_["car"]["options"] == qa[(None, "car_type")]
assert tm_["count"]["type"] == "selectfree"
tf_ = _fields(pdf_io.TREQ_SCHEMA)
assert tf_["honorific"]["type"] == "selectfree" and tf_["persons"]["type"] == "selectfree"
assert "+971 الإمارات" in tf_["phone_code"]["options"]
print("[ok] القوائم المنسدلة في الفاوتشر والطلب = خيارات عرض السعر")

# ---- 7) مسارات الويب ----
try:
    from webapp import server
except ImportError as exc:                   # Flask غير مثبّت في هذه البيئة
    print(f"[skip] مسارات الويب: {exc}")
    print("ALL OK")
    sys.exit(0)


class _FakeSession:
    username, is_admin, can_edit = "tester", True, True

    def encrypt(self, b):
        return b

    def decrypt(self, b):
        return b


server._SESSIONS["sid-test"] = _FakeSession()
storage.save_settings({"umrah_quotes": {"U1": [QUOTE_AR],
                                        "_manual": [QUOTE_EN]}})
client = server.app.test_client()
with client.session_transaction() as s:
    s["sid"] = "sid-test"
    s["mode"] = app_mode.UMRAH

r = client.get("/quotes")
assert r.status_code == 200
html = r.get_data(as_text=True)
assert "/quotes/U1/MA-Q0007/doc/voucher" in html
assert "/quotes/_manual/MA-Q0012/doc/treq" in html

r = client.get("/documents")
assert "/documents/voucher/from-quote" in r.get_data(as_text=True)

# رقم مرجعي مطابق → تحويل مباشر للمحرّر
r = client.get("/documents/voucher/from-quote?q=7")
assert r.status_code == 302, r.status_code
assert r.headers["Location"].endswith("/quotes/U1/MA-Q0007/doc/voucher")
# بحث بالاسم → قائمة
r = client.get("/documents/treq/from-quote?q=john")
body = r.get_data(as_text=True)
assert r.status_code == 200
assert "/quotes/_manual/MA-Q0012/doc/treq" in body
assert "/quotes/U1/MA-Q0007/doc/" not in body
r = client.get("/documents/treq/from-quote?q=zzz")
assert "لا يوجد عرض" in r.get_data(as_text=True)
# نوع غير مدعوم
assert client.get("/documents/invoice/from-quote").status_code == 302

# المحرّر معبّأ من العرض برقم فاوتشر جديد
r = client.get("/quotes/U1/MA-Q0007/doc/voucher")
assert r.status_code == 200
page = r.get_data(as_text=True)
assert "فيرمونت مكة" in page and "MA-Q0007" in page and "MA0001" in page
assert storage.load_settings().get("voucher_seq") == 1
assert '"type": "selectfree"' in page and "رافلز مكة بالاس" in page   # قوائم
# فاوتشر إنجليزي ← قوائم إنجليزية؛ الفاوتشر اليدوي بقوائم كذلك
page_en = client.get("/quotes/_manual/MA-Q0012/doc/voucher").get_data(as_text=True)
assert "Raffles Makkah Palace" in page_en
man = client.get("/documents/voucher/manual").get_data(as_text=True)
assert '"type": "selectfree"' in man and "رافلز مكة بالاس" in man
r = client.get("/quotes/U1/MA-Q0007/doc/treq")
assert r.status_code == 200 and "MA-T0001" in r.get_data(as_text=True)
man = client.get("/documents/treq/manual").get_data(as_text=True)
assert "من الفندق في مكة الى الفندق في المدينة" in man
assert client.get("/quotes/U1/MA-Q0999/doc/voucher").status_code == 302
assert client.get("/quotes/U1/MA-Q0007/doc/invoice").status_code == 302

# الحفظ → PDF + أرشفة مربوطة برقم العرض
r = client.post("/quotes/U1/MA-Q0007/doc/voucher/pdf", json=v)
assert r.status_code == 200 and r.mimetype == "application/pdf"
assert r.data[:4] == b"%PDF"
r = client.post("/quotes/_manual/MA-Q0012/doc/treq/pdf", json=te)
assert r.status_code == 200 and r.data[:4] == b"%PDF"
docs = storage.load_documents(session=server._SESSIONS["sid-test"])
assert [d["kind"] for d in docs] == ["voucher", "treq"]
assert docs[0]["data"]["quote_ref"] == "MA-Q0007"
assert "عرض MA-Q0007" in docs[0]["name"] and "محمد أحمد" in docs[0]["name"]
assert "عرض MA-Q0012" in docs[1]["name"]
# إعادة الطباعة من الأرشيف تعمل
r = client.get(f"/archive/{docs[0]['id']}.pdf")
assert r.status_code == 200 and r.data[:4] == b"%PDF"
assert client.post("/quotes/U1/MA-Q0007/doc/x/pdf", json={}).status_code == 404

# رقم مكرّر تحت برنامجين → قائمة اختيار بدل تحويل صامت لنسخة قد تكون قديمة
storage.save_settings({"umrah_quotes": {
    "U1": [dict(QUOTE_AR, addressed_to="نسخة قديمة")], "_manual": [QUOTE_AR]}})
r = client.get("/documents/voucher/from-quote?q=MA-Q0007")
body = r.get_data(as_text=True)
assert r.status_code == 200 and "محفوظ أكثر من مرّة" in body
assert "/quotes/U1/MA-Q0007/doc/voucher" in body
assert "/quotes/_manual/MA-Q0007/doc/voucher" in body

# رقم عرض/رمز برنامج فيه رموز HTML أو ' لا يُحقن في صفحة المحرّر
evil_num = "<img src=x onerror=alert(1)>"
storage.save_settings({"umrah_quotes": {"Sha'ban": [
    dict(QUOTE_AR, number=evil_num)]}})
from urllib.parse import quote as _pq  # noqa: E402
r = client.get(f"/quotes/{_pq(chr(83) + 'ha' + chr(39) + 'ban')}/"
               f"{_pq(evil_num, safe='')}/doc/voucher")
page = r.get_data(as_text=True)
assert r.status_code == 200
import re as _re  # noqa: E402
_title = _re.search(r"<title>(.*?)</title>", page, _re.S).group(1)
_h1 = _re.search(r"<h1>(.*?)</h1>", page, _re.S).group(1)
for _t in (_title, _h1):                  # العنوان مُهرَّب (البيانات تبقى JSON آمناً)
    assert "<img" not in _t and "&lt;img src=x" in _t, _t
assert "fetch('" not in page and 'fetch("/quotes/Sha' in page

# بلا جلسة → تسجيل الدخول
anon = server.app.test_client()
assert anon.get("/quotes/U1/MA-Q0007/doc/voucher").status_code == 302
assert anon.post("/quotes/U1/MA-Q0007/doc/voucher/pdf", json={}).status_code == 401
print("[ok] مسارات الويب: القائمة/البحث/المحرّر/PDF/الأرشيف")

print("ALL OK")
