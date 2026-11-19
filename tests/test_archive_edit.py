# -*- coding: utf-8 -*-
"""البورتال: تعديل المستندات المحفوظة في الأرشيف — المحرّر معبّأ بالبيانات، والحفظ في
المكان نفسه (نفس المعرّف والرقم ورمز التحقّق)، والصلاحيات، وروابط العودة."""
import io, json, os, re, sys, tempfile
from datetime import date
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["HAJJ_DATA_DIR"] = tempfile.mkdtemp(prefix="arch_edit_")
from hajj_app import auth, storage, app_mode, audit  # noqa: E402
from hajj_app.mrz import PassportData  # noqa: E402
try:
    from webapp import server
    server.app.config["CSRF_ENABLED"] = False
except ImportError as exc:
    print(f"[skip] مسارات الويب: {exc}"); print("ALL OK"); sys.exit(0)

owner, _rk = auth.create_account("owner", "Passw0rd!x")
auth.add_account(owner, "sara", "Passw0rd!s", role="editor")
auth.add_account(owner, "view", "Passw0rd!v", role="viewer")
c = server.app.test_client()
c.post("/login", data={"username": "owner", "password": "Passw0rd!x"})
e = server.app.test_client()
e.post("/login", data={"username": "sara", "password": "Passw0rd!s"})
v = server.app.test_client()
v.post("/login", data={"username": "view", "password": "Passw0rd!v"})
S = next(x for x in server._SESSIONS.values() if x.username == "owner")
app_mode.set_mode(app_mode.UMRAH)
storage.save_records([PassportData(full_name_ar="أحمد سالم العلي", passport_number="P100",
                                   phone="0501234567", nationality_ar="إماراتي", uid="u-ahmed")],
                     session=S)
T = date.today().isoformat()


def D_of(html):
    """بيانات المحرّر كما ضُمّنت في الصفحة (const D = {...};)."""
    m = re.search(r"const D = (.*?);\nconst SCHEMA", html, re.S)
    assert m, "لم أجد بيانات المحرّر"
    return json.loads(m.group(1))


def docs():
    return storage.load_documents(session=S)


def doc(i):
    return next(d for d in docs() if d.get("id") == i)


# ---- ١) سند قبض من السجلّ ثم تعديل مبلغه من الأرشيف ----
ed = c.get("/doc/0/receipt").get_data(as_text=True)
rd = D_of(ed)
rd["amount"] = "1500"
r = c.post("/doc/0/receipt/pdf", json=rd)
assert r.status_code == 200 and r.data[:4] == b"%PDF", (r.status_code, r.data[:200])
rid = docs()[-1]["id"]
n_before = len(docs())
num = doc(rid)["number"]

arch = c.get("/archive").get_data(as_text=True)
assert f"/archive/{rid}/edit" in arch and "تعديل" in arch, "زرّ «تعديل» في الأرشيف"
assert "عُدّل" not in arch, "لا علامة «عُدّل» قبل أي تعديل"

page = c.get(f"/archive/{rid}/edit")
assert page.status_code == 200 and "no-store" in page.headers.get("Cache-Control", "")
html = page.get_data(as_text=True)
assert "تعديل سند قبض" in html, "عنوان المحرّر"
assert "X-Back-Link" in html and "حُفظ التعديل في الأرشيف" in html, "رسالة الحفظ وزرّ العودة"
assert f"/archive/{rid}/edit/pdf" in html, "الحفظ يذهب لمسار التعديل لا لإصدار جديد"
D = D_of(html)
assert D.get("amount") == "1500" and D.get("number") == num, "المحرّر معبّأ بالبيانات المحفوظة"
assert "_rec" not in D

D["amount"] = "2750"
r = c.post(f"/archive/{rid}/edit/pdf", json=D)
assert r.status_code == 200 and r.data[:4] == b"%PDF", (r.status_code, r.data[:200])
assert r.headers.get("X-Back-Link") == "/archive", r.headers.get("X-Back-Link")
assert "X-WA-Link" not in r.headers and "X-Next-Link" not in r.headers
assert len(docs()) == n_before, "التعديل لا يضيف مستنداً جديداً"
ent = doc(rid)
assert ent["data"]["amount"] == "2750" and ent["number"] == num, "حُفظ في المكان نفسه بنفس الرقم"
assert ent["edited"] and ent["edited_by"] == "owner" and ent["name"] == "أحمد سالم العلي"
assert ent["idx"] == 0, "يبقى مربوطاً بصاحبه"
from hajj_app.fields import num_to_words_en  # noqa: E402
assert ent["data"]["amount_words"] == num_to_words_en(2750.0), ("المبلغ كتابةً يتبع المبلغ الجديد",
                                                              ent["data"]["amount_words"])
arch = c.get("/archive").get_data(as_text=True)
assert "عُدّل" in arch and ent["edited"].replace("T", "  ") in arch, "وقت التعديل تحت التاريخ"
rec_docs = c.get("/hujjaj/0/docs").get_data(as_text=True)
assert "عُدّل" in rec_docs, "العلامة في صفحة مستندات الشخص أيضاً"
assert any("تعديل مستند مؤرشف" in str(x) for x in audit.read_entries(50)), "التعديل مسجّل في السجلّ"
# إعادة الفتح/الطباعة تُخرج النسخة المعدّلة
assert c.get(f"/archive/{rid}.pdf").data[:4] == b"%PDF"
assert D_of(c.get(f"/archive/{rid}/edit").get_data(as_text=True))["amount"] == "2750"

# ---- ٢) فاوتشر يدوي: رمز التحقّق نفسه وصفحته العامة تتحدّث ----
STAY = ["مكة المكرمة", "فيرمونت مكة (برج الساعة)", "ثنائي", "1", "", "2026-12-03", "2026-12-06", "3", ""]
r = c.post("/documents/voucher/manual/pdf", json={"number": "MA0034", "guest_ar": "عبير حسن أحمد",
                                                  "stays": [STAY]})
assert r.status_code == 200
vid = docs()[-1]["id"]
vurl = doc(vid)["data"]["verify_url"]
tok = vurl.rsplit("/v/", 1)[1]
assert "فيرمونت" in server.app.test_client().get(f"/v/{tok}").get_data(as_text=True)
V = D_of(c.get(f"/archive/{vid}/edit").get_data(as_text=True))
V["stays"] = [["مكة المكرمة", "هيلتون مكة", "ثنائي", "1", "", "2026-12-03", "2026-12-07", "4", ""]]
r = c.post(f"/archive/{vid}/edit/pdf", json=V)
assert r.status_code == 200 and r.data[:4] == b"%PDF"
assert doc(vid)["data"]["verify_url"] == vurl, "رمز QR نفسه بعد التعديل"
pub = server.app.test_client().get(f"/v/{tok}").get_data(as_text=True)
assert "هيلتون مكة" in pub and "فيرمونت" not in pub, "صفحة التحقّق تعرض البيانات المعدّلة"
assert doc(vid)["name"] == "يدوي بلا اسم"

# ---- ٣) طلب مواصلات يدوي: اسمه يتبع الضيف، وبعد الحفظ زرّ «تأكيد للضيف» ----
MOV = [[T, "من مطار جدة الى الفندق في مكة", "1", "GMC", "2026", "10:30"]]
r = c.post("/documents/treq/manual/pdf", json={"number": "MA-T0100", "guest_ar": "خالد يوسف",
                                               "phone": "0507654321", "movements": MOV})
assert r.status_code == 200
tid = docs()[-1]["id"]
assert doc(tid)["name"] == "خالد يوسف (يدوي)"
TQ = D_of(c.get(f"/archive/{tid}/edit").get_data(as_text=True))
assert TQ["movements"] == MOV
TQ["guest_ar"] = "سالم يوسف"
TQ["movements"] = MOV + [[T, "من الفندق في مكة الى محطة قطار مكة", "1", "GMC", "2026", "16:00"]]
r = c.post(f"/archive/{tid}/edit/pdf", json=TQ)
assert r.status_code == 200 and r.headers.get("X-Next-Link") == f"/archive/{tid}/tconf"
assert doc(tid)["name"] == "سالم يوسف (يدوي)", "الاسم في الأرشيف يتبع الضيف المعدّل"
assert len(doc(tid)["data"]["movements"]) == 2
assert "16:00" in c.get(f"/archive/{tid}/tconf").get_data(as_text=True), "التأكيد يأخذ الحركات المعدّلة"
assert "X-Next-Link" in c.get(f"/archive/{tid}/edit").get_data(as_text=True)

# ---- ٤) تأكيد مواصلات: بعد التعديل رابط واتساب بالجوال الجديد ----
r = c.post(f"/archive/{tid}/tconf/pdf", json={"number": "MA-C0005", "guest_ar": "سالم يوسف",
                                              "phone": "0507654321", "movements": [MOV[0][:2] + MOV[0][3:]]})
assert r.status_code == 200
cid = docs()[-1]["id"]
assert doc(cid)["kind"] == "tconf"
CF = D_of(c.get(f"/archive/{cid}/edit").get_data(as_text=True))
assert "X-WA-Link" in c.get(f"/archive/{cid}/edit").get_data(as_text=True)
CF["phone"] = "0551112222"
r = c.post(f"/archive/{cid}/edit/pdf", json=CF)
assert r.status_code == 200
assert r.headers.get("X-WA-Link", "").startswith("https://wa.me/971551112222?text="), r.headers.get("X-WA-Link")

# ---- ٥) المحرّر (editor) يعدّل، والمطّلع لا ----
page = e.get(f"/archive/{rid}/edit")
assert page.status_code == 200 and "تعديل سند قبض" in page.get_data(as_text=True)
D2 = D_of(page.get_data(as_text=True)); D2["amount"] = "3000"
assert e.post(f"/archive/{rid}/edit/pdf", json=D2).status_code == 200
assert doc(rid)["edited_by"] == "sara" and doc(rid)["data"]["amount"] == "3000"
assert doc(rid)["data"]["amount_words"] == num_to_words_en(3000.0)
# كتابة المبلغ يدوياً مع تغييره: يبقى ما كتبه المستخدم
D2 = D_of(e.get(f"/archive/{rid}/edit").get_data(as_text=True))
D2.update(amount="3000.50", amount_words="three thousand and fifty fils")
assert e.post(f"/archive/{rid}/edit/pdf", json=D2).status_code == 200
assert doc(rid)["data"]["amount_words"] == "three thousand and fifty fils", "لا يُستبدل نصّ كتبه المستخدم"
D2 = D_of(e.get(f"/archive/{rid}/edit").get_data(as_text=True))
D2.update(amount="3000", amount_words=num_to_words_en(3000.0))
assert e.post(f"/archive/{rid}/edit/pdf", json=D2).status_code == 200
va = v.get("/archive").get_data(as_text=True)
assert f"/archive/{rid}.pdf" in va and f"/archive/{rid}/edit" not in va, "المطّلع بلا زرّ تعديل"
assert "/archive" in v.get(f"/archive/{rid}/edit").headers.get("Location", "")
r = v.post(f"/archive/{rid}/edit/pdf", json=dict(D2, amount="1"))
assert r.status_code == 403 and doc(rid)["data"]["amount"] == "3000", "المطّلع لا يعدّل"

# ---- ٦) معرّف خاطئ، بيانات تالفة، وبلا دخول ----
assert "/archive" in c.get("/archive/nope/edit").headers.get("Location", "")
assert c.post("/archive/nope/edit/pdf", json={"amount": "1"}).status_code == 404
assert c.post(f"/archive/{rid}/edit/pdf", data="xx", content_type="application/json").status_code == 400
assert c.post(f"/archive/{rid}/edit/pdf", json=[1, 2]).status_code == 400
anon = server.app.test_client()
assert "/login" in anon.get(f"/archive/{rid}/edit").headers.get("Location", "")
assert anon.post(f"/archive/{rid}/edit/pdf", json=D2).status_code == 401
assert doc(rid)["data"]["amount"] == "3000"

# ---- ٧) من صفحة مستندات الشخص: العودة إليها، ورابط خارجي يُرفض ----
rec_docs = c.get("/hujjaj/0/docs").get_data(as_text=True)
assert f"/archive/{rid}/edit?back=/hujjaj/0/docs" in rec_docs, "زرّ التعديل في صفحة الشخص"
html = c.get(f"/archive/{rid}/edit?back=/hujjaj/0/docs").get_data(as_text=True)
assert 'href="/hujjaj/0/docs"' in html, "زرّ الرجوع لصفحة الشخص"
D3 = D_of(html)
r = c.post(f"/archive/{rid}/edit/pdf?back=/hujjaj/0/docs", json=D3)
assert r.headers.get("X-Back-Link") == "/hujjaj/0/docs"
for bad in ("//evil.example/x", "https://evil.example/", "/\\evil.example"):
    r = c.post(f"/archive/{rid}/edit/pdf", query_string={"back": bad}, json=D3)
    assert r.headers.get("X-Back-Link") == "/archive", (bad, r.headers.get("X-Back-Link"))
    assert "evil" not in c.get(f"/archive/{rid}/edit", query_string={"back": bad}).get_data(as_text=True)

# ---- ٨) الصفحة توضّح الميزة ----
assert "زرّ «تعديل» يفتح المستند" in c.get("/archive").get_data(as_text=True)
print("ALL OK")
