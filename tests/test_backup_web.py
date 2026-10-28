# -*- coding: utf-8 -*-
"""البورتال: النسخ الاحتياطي — النسخة اليومية، التنزيل المشفّر بكلمة مرور،
الاستعادة (من ملف أو من نسخة على الخادم) مع نسخة أمان، والحماية من الملفّات الخبيثة."""
import io
import os
import sys
import tempfile
import zipfile
from datetime import date, timedelta
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["HAJJ_DATA_DIR"] = tempfile.mkdtemp(prefix="backup_web_")

from hajj_app import app_mode, auth, storage  # noqa: E402
from hajj_app.mrz import PassportData  # noqa: E402

try:
    from webapp import server, backup
    server.app.config["CSRF_ENABLED"] = False
except ImportError as exc:
    print(f"[skip] مسارات الويب: {exc}")
    print("ALL OK")
    sys.exit(0)

owner, _rk = auth.create_account("owner", "Passw0rd!x")
auth.add_account(owner, "sara", "Passw0rd!s", role="editor")
c = server.app.test_client()
c.post("/login", data={"username": "owner", "password": "Passw0rd!x"})
SESS = server._SESSIONS[next(iter(server._SESSIONS))]
app_mode.set_mode(app_mode.UMRAH)
storage.save_records([PassportData(full_name_ar="أحمد"), PassportData(full_name_ar="بلال")],
                     session=SESS)
(backup.data_dir() / "images").mkdir(exist_ok=True)
(backup.data_dir() / "images" / "img1.passport").write_bytes(b"ENCRYPTED-IMAGE")
(backup.data_dir() / "web_secret.key").write_text("secret")


def names(session=SESS):
    app_mode.set_mode(app_mode.UMRAH)
    return [r.full_name_ar for r in storage.load_records(session=session)[0]]


# ---- 1) التشفير على أجزاء: صحيح/خاطئ/تالف ----
src = backup.tempfile_path(".bin")
src.write_bytes(os.urandom(backup._CHUNK * 2 + 123))            # أكثر من جزأين
enc, out = backup.tempfile_path(".almbak"), backup.tempfile_path(".bin")
backup.encrypt_file(src, enc, "كلمة-سرّ-طويلة")
backup.decrypt_file(enc, out, "كلمة-سرّ-طويلة")
assert out.read_bytes() == src.read_bytes() and enc.read_bytes().startswith(backup.MAGIC)
for bad_pw, blob in (("خطأ-خطأ-خطأ", enc.read_bytes()),
                     ("كلمة-سرّ-طويلة", enc.read_bytes()[:-40])):      # مقطوع
    enc2 = backup.tempfile_path(".almbak")
    enc2.write_bytes(blob)
    try:
        backup.decrypt_file(enc2, out, bad_pw)
        raise AssertionError("كان يجب أن يُرفض")
    except ValueError:
        pass
print("[ok] التشفير: AES-GCM على أجزاء، كلمة مرور خاطئة/ملف مقطوع يُرفضان")

# ---- 2) النسخة اليومية: مرّة في اليوم، والتقليم ----
backup._LAST_CHECK["day"] = None
c.get("/dashboard")                                       # أول طلب في اليوم
autos = [p for p in backup.list_snapshots() if p.stem.endswith("_auto")]
assert len(autos) == 1
with zipfile.ZipFile(autos[0]) as z:
    zn = z.namelist()
assert "auth.json" in zn and "umrah.json" in zn and "web_secret.key" not in zn
assert not any(n.startswith("images/") for n in zn)       # اليومية بلا صور
c.get("/dashboard")
assert len([p for p in backup.list_snapshots() if p.stem.endswith("_auto")]) == 1
for i in range(20):                                       # أيام سابقة كثيرة
    (backup.snaps_dir() / f"2020-01-{i + 1:02d}_000000_auto.zip").write_bytes(b"x")
backup.prune()
assert len([p for p in backup.list_snapshots() if p.stem.endswith("_auto")]) == backup.KEEP_DAYS
print("[ok] النسخة اليومية التلقائية مرّة في اليوم، ويبقى آخر ١٤")

# ---- 3) التنزيل المشفّر ----
page = c.get("/backup").get_data(as_text=True)
assert "تنزيل نسخة كاملة" in page and "يومية تلقائية" in page
r = c.post("/backup/download", data={"password": "1234", "confirm": "1234"})
assert r.status_code == 302 and "٨ خانات" in c.get("/backup").get_data(as_text=True)
r = c.post("/backup/download", data={"password": "Backup#2026", "confirm": "Backup#2026",
                                     "images": "1"})
assert r.status_code == 200 and "attachment" in r.headers["Content-Disposition"]
assert ".almbak" in r.headers["Content-Disposition"]
blob = r.data
assert blob.startswith(backup.MAGIC) and b"auth.json" not in blob       # مشفّر
dl = backup.tempfile_path(".almbak")
dl.write_bytes(blob)
zz = backup.tempfile_path(".zip")
backup.decrypt_file(dl, zz, "Backup#2026")
with zipfile.ZipFile(zz) as z:
    assert "images/img1.passport" in z.namelist() and "auth.json" in z.namelist()
print("[ok] التنزيل: ملف .almbak مشفّر بكلمة المرور ومعه الصور")

# ---- 4) الاستعادة من الملف المنزّل ----
storage.save_records([PassportData(full_name_ar="تغيير لاحق")], session=SESS)
assert names() == ["تغيير لاحق"]
r = c.post("/backup/restore", data={"password": "خطأ", "file": (io.BytesIO(blob), "b.almbak")},
           content_type="multipart/form-data")
assert r.status_code == 302 and "غير صحيحة" in c.get("/backup").get_data(as_text=True)
assert names() == ["تغيير لاحق"]                                     # لم يتغيّر شيء
r = c.post("/backup/restore", data={"password": "Backup#2026",
                                    "file": (io.BytesIO(blob), "b.almbak")},
           content_type="multipart/form-data")
assert r.status_code == 302 and "restored=1" in r.headers["Location"]
assert server._SESSIONS == {}                                        # خرج الجميع
assert c.get("/dashboard").status_code == 302
assert "استُعيدت النسخة" in c.get("/login?restored=1").get_data(as_text=True)
c.post("/login", data={"username": "owner", "password": "Passw0rd!x"})
SESS = server._SESSIONS[next(iter(server._SESSIONS))]
assert names(SESS) == ["أحمد", "بلال"]                               # عادت البيانات
assert any(p.stem.endswith("_before-restore") for p in backup.list_snapshots())
print("[ok] الاستعادة من ملف: كلمة مرور خاطئة تُرفض، والصحيحة تعيد البيانات بعد نسخة أمان")

# ---- 5) الاستعادة من نسخة على الخادم + الحماية ----
storage.save_records([PassportData(full_name_ar="ثالث")], session=SESS)
safety = next(p for p in backup.list_snapshots() if p.stem.endswith("_before-restore"))
c.post("/backup/restore", data={"snapshot": safety.name})
c.post("/login", data={"username": "owner", "password": "Passw0rd!x"})
SESS = server._SESSIONS[next(iter(server._SESSIONS))]
assert names(SESS) == ["تغيير لاحق"]                                 # نسخة الأمان نفسها
r = c.post("/backup/restore", data={"snapshot": "../auth.json"})
assert "غير موجودة" in c.get("/backup").get_data(as_text=True)
evil = backup.tempfile_path(".zip")
with zipfile.ZipFile(evil, "w") as z:
    z.writestr("auth.json", "{}")
    z.writestr("../../outside.txt", "x")
try:
    backup.restore_zip(evil)
    raise AssertionError("ملف خبيث")
except ValueError:
    pass
assert not (Path(backup.data_dir()).parent.parent / "outside.txt").exists()
with zipfile.ZipFile(evil, "w") as z:
    z.writestr("umrah.json", "x")
try:
    backup.restore_zip(evil)
    raise AssertionError("بلا auth.json")
except ValueError:
    pass
# المحرّر لا يصل للنسخ الاحتياطي
e = server.app.test_client()
e.post("/login", data={"username": "sara", "password": "Passw0rd!s"})
assert e.get("/backup").status_code == 302 and e.post("/backup/now").status_code == 302
assert "النسخ الاحتياطي" not in e.get("/dashboard").get_data(as_text=True)
print("[ok] الاستعادة من نسخة الخادم + رفض المسارات الخبيثة + للمدير فقط")

# ---- 6) إصلاحات المراجعة: كلّ أو لا شيء، بلا بقايا، الصور، سجلّ التدقيق ----
from hajj_app import audit as _audit  # noqa: E402
c.post("/login", data={"username": "owner", "password": "Passw0rd!x"})
SESS = server._SESSIONS[next(iter(server._SESSIONS))]
storage.save_records([PassportData(full_name_ar="قبل")], session=SESS)
base = backup.snapshot("manual")                                   # بلا صور
img = backup.data_dir() / "images" / "img1.passport"
img.write_bytes(b"NEWER-IMAGE")
(backup.data_dir() / "documents_umrah.json").write_text("NEWER")      # ليس في النسخة؟
with zipfile.ZipFile(base) as z:
    had_docs = "documents_umrah.json" in z.namelist()
storage.save_records([PassportData(full_name_ar="بعد")], session=SESS)
_audit.record("قيد بعد النسخة", "x", user="owner")
# فشل في منتصف التبديل ← تُعاد البيانات كما كانت تماماً
real_replace = os.replace
calls = {"n": 0}


def flaky(a, b):
    calls["n"] += 1
    if calls["n"] == 4:
        raise OSError(28, "No space left on device")
    return real_replace(a, b)


os.replace = flaky
try:
    backup.restore_zip(base)
    raise AssertionError("كان يجب أن يفشل")
except ValueError as exc:
    assert "أُعيدت البيانات كما كانت" in str(exc)
finally:
    os.replace = real_replace
assert names(SESS) == ["بعد"] and img.read_bytes() == b"NEWER-IMAGE"
assert not (backup.data_dir() / ".restore-stage").exists()
assert not (backup.data_dir() / ".restore-old").exists()
# نسخة تالفة لا تمسّ شيئاً
broken = backup.tempfile_path(".zip")
broken.write_bytes(base.read_bytes()[:200])
try:
    backup.restore_zip(broken)
    raise AssertionError("تالفة")
except ValueError:
    pass
assert names(SESS) == ["بعد"]
# استعادة ناجحة: نسخة بلا صور تُبقي الصور الحالية، وما ليس في النسخة لا يبقى
backup.restore_zip(base)
assert names(SESS) == ["قبل"] and img.read_bytes() == b"NEWER-IMAGE"
assert (backup.data_dir() / "documents_umrah.json").exists() == had_docs
assert any(e["action"] == "قيد بعد النسخة" for e in _audit.read_entries())  # السجلّ باقٍ
try:
    with zipfile.ZipFile(evil, "w") as z:
        z.writestr("auth.json", "{}")
        z.writestr("images/.", "x")
    backup.restore_zip(evil)
    raise AssertionError("images/. مرفوض")
except ValueError:
    pass
# نسخة الأمان قبل الاستعادة تشمل الصور
c.post("/backup/restore", data={"snapshot": base.name})
safety = max((p for p in backup.list_snapshots() if p.stem.endswith("_before-restore")),
             key=lambda p: p.name)
with zipfile.ZipFile(safety) as z:
    assert "images/img1.passport" in z.namelist()
assert server._PENDING == {} and server._TOTP_SETUP == {}
print("[ok] الاستعادة كلّ أو لا شيء + الصور + سجلّ التدقيق باقٍ + نسخة أمان بالصور")
print("ALL OK")
