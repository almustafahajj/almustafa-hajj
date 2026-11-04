# -*- coding: utf-8 -*-
"""البورتال: الجلسات تبقى بعد إعادة تشغيل الخادم، صفحة «الجلسات النشطة» للمدير،
والنسخة الاحتياطية الخارجية التلقائية بالبريد."""
import io
import os
import sys
import tempfile
import time
import zipfile
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["HAJJ_DATA_DIR"] = tempfile.mkdtemp(prefix="sessoff_")

from hajj_app import auth  # noqa: E402

try:
    from webapp import server, websessions, offsite, backup, mailer
    server.app.config["CSRF_ENABLED"] = False
except ImportError as exc:
    print(f"[skip] مسارات الويب: {exc}")
    print("ALL OK")
    sys.exit(0)

UA_PHONE = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
            "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")
owner, _rk = auth.create_account("owner", "Passw0rd!x")
auth.add_account(owner, "sara", "Passw0rd!s", role="editor")
auth.add_account(owner, "omar", "Passw0rd!o", role="viewer")
c = server.app.test_client()
c.post("/login", data={"username": "owner", "password": "Passw0rd!x"})
s = server.app.test_client()
s.post("/login", data={"username": "sara", "password": "Passw0rd!s"},
       headers={"User-Agent": UA_PHONE})


def users_on_disk():
    return sorted(r["user"] for r in websessions.list_all())


# ---- ١) الجلسة محفوظة على القرص، والمفتاح لا يُكتب كما هو ----
assert users_on_disk() == ["owner", "sara"], users_on_disk()
raw = "".join(p.read_text(encoding="utf-8") for p in websessions.root().glob("*.json"))
import base64  # noqa: E402
assert base64.b64encode(owner.data_key).decode() not in raw, "مفتاح البيانات مكشوف على القرص"
sid_sara = next(k for k, v in server._SESSIONS.items() if v.username == "sara")
from cryptography.fernet import Fernet  # noqa: E402
assert websessions.restore(sid_sara, Fernet.generate_key().decode()) is None, "مفتاح آخر لا يفتح"

# ---- ٢) إعادة تشغيل الخادم (تفريغ الذاكرة) لا تُخرج أحداً ----
server._SESSIONS.clear()
server._LAST_SEEN.clear()
assert c.get("/dashboard").status_code == 200, "المدير خرج بعد إعادة التشغيل"
assert s.get("/dashboard").status_code == 200, "المحرّر خرج بعد إعادة التشغيل"
assert {v.username for v in server._SESSIONS.values()} == {"owner", "sara"}
with s.session_transaction() as fs:
    assert fs.get("sk"), "مفتاح الجلسة في ملف الارتباط"

# بعد إعادة التشغيل: متصفّح بلا مفتاح (ملف ارتباط قديم) لا يستعيد شيئاً
server._SESSIONS.pop(sid_sara)
x = server.app.test_client()
with x.session_transaction() as fs:
    fs["sid"] = sid_sara
assert x.get("/dashboard").status_code == 302

# ---- ٣) صفحة الجلسات النشطة ----
page = c.get("/sessions").get_data(as_text=True)
assert "الجلسات النشطة" in page and "sara" in page and "آيفون · Safari" in page, page[-1500:]
assert "(جلستك)" in page and "نشطة الآن" in page
assert s.get("/sessions").status_code == 302, "غير المدير لا يرى الجلسات"
assert s.post(f"/sessions/{websessions.sid_id(sid_sara)}/end").status_code == 302
assert s.get("/dashboard").status_code == 200, "غير المدير لا يُنهي جلسات"

# إنهاء جلسة سارة
c.post(f"/sessions/{websessions.sid_id(sid_sara)}/end")
assert users_on_disk() == ["owner"]
r = s.get("/dashboard")
assert r.status_code == 302 and "/login" in r.headers["Location"]
# المدير لا يُنهي جلسته من هنا
mine = websessions.sid_id(next(k for k, v in server._SESSIONS.items() if v.username == "owner"))
c.post(f"/sessions/{mine}/end")
assert c.get("/dashboard").status_code == 200

# إنهاء كل الجلسات الأخرى
o = server.app.test_client()
o.post("/login", data={"username": "omar", "password": "Passw0rd!o"})
s.post("/login", data={"username": "sara", "password": "Passw0rd!s"})
assert users_on_disk() == ["omar", "owner", "sara"]
c.post("/sessions/end-others")
assert users_on_disk() == ["owner"]
assert o.get("/dashboard").status_code == 302 and c.get("/dashboard").status_code == 200

# الخروج يحذف الملف، وحذف الحساب يُنهي جلساته
o.post("/login", data={"username": "omar", "password": "Passw0rd!o"})
with o.session_transaction() as fs:
    tok = fs.get("csrf")
o.get(f"/logout?t={tok}")
assert users_on_disk() == ["owner"]
o.post("/login", data={"username": "omar", "password": "Passw0rd!o"})
c.post("/accounts/omar/delete")
assert "omar" not in users_on_disk() and o.get("/dashboard").status_code == 302

# الخروج بعد عدم النشاط يحذف الملف أيضاً
s.post("/login", data={"username": "sara", "password": "Passw0rd!s"})
auth.set_policy(owner, session_minutes=15)
sid_sara = next(k for k, v in server._SESSIONS.items() if v.username == "sara")
server._LAST_SEEN[sid_sara] = time.time() - 16 * 60
assert s.get("/dashboard").status_code == 302
assert users_on_disk() == ["owner"]
auth.set_policy(owner, session_minutes=0)

# ---- ٤) النسخة الخارجية بالبريد ----
mailer.OUTBOX = []
assert not offsite.due()
page = c.get("/backup").get_data(as_text=True)
assert "نسخة خارج الخادم" in page
c.post("/backup/offsite", data={"email": "ayman@gmail.com", "freq": "weekly",
                                "password": "Backup!pw1", "confirm": "Backup!pw2"})
assert not offsite.load().get("enabled"), "كلمتا مرور غير متطابقتين"
c.post("/backup/offsite", data={"email": "ayman@gmail.com", "freq": "weekly",
                                "password": "", "confirm": ""})
assert not offsite.load().get("enabled"), "كلمة المرور مطلوبة أوّل مرّة"
c.post("/backup/offsite", data={"email": "ayman@gmail.com", "freq": "weekly",
                                "password": "Backup!pw1", "confirm": "Backup!pw1"})
cfg = offsite.load()
assert cfg["enabled"] and "Backup!pw1" not in Path(offsite._path()).read_text(encoding="utf-8")
assert offsite.due(), "أوّل نسخة مستحقّة فوراً"

c.post("/backup/offsite/send")
assert len(mailer.OUTBOX) == 1, mailer.OUTBOX
m = mailer.OUTBOX[0]
assert m["to"] == "ayman@gmail.com" and len(m["attachments"]) == 1
name, data = m["attachments"][0]
assert name.endswith(".zip")
assert not offsite.due() and offsite.load()["last_ok"]

# المرفق يُستعاد: zip فيه .almbak يُفكّ بكلمة مرور النسخ
tmp = Path(tempfile.mkdtemp())
att = tmp / name
att.write_bytes(data)
backup.unwrap_mail_zip(att)
backup.decrypt_file(att, tmp / "out.zip", "Backup!pw1")
with zipfile.ZipFile(tmp / "out.zip") as z:
    assert "auth.json" in z.namelist(), z.namelist()
try:
    backup.decrypt_file(att, tmp / "bad.zip", "wrong-pass")
    raise AssertionError("كلمة مرور خاطئة فتحت النسخة")
except ValueError:
    pass

# الاستحقاق: أسبوعياً، وبعد فشل محاولة جديدة بعد ٣ ساعات
now = time.time()
cfg = offsite.load()
assert not offsite.due(cfg, now + 5 * 86400)
assert offsite.due(cfg, now + 7 * 86400)
cfg["last_try"] = now + 7 * 86400 - 60
assert not offsite.due(cfg, now + 7 * 86400), "لا إعادة قبل ٣ ساعات من آخر محاولة"
offsite._update(last_ok=now - 8 * 86400, last_try=0)
mailer.OUTBOX.clear()
mine_sid = next(k for k, v in server._SESSIONS.items() if v.username == "owner")
assert offsite.maybe_run(server._SESSIONS[mine_sid])
for _ in range(100):
    if mailer.OUTBOX:
        break
    time.sleep(0.05)
assert len(mailer.OUTBOX) == 1, "الإرسال التلقائي في الخلفية"

# فشل الإرسال يظهر شارة على قسم الإدارة
offsite._update(last_err="رفضت Brevo الإرسال (400).")
assert "رفضت Brevo" in c.get("/backup").get_data(as_text=True)
with server.app.test_request_context():
    from flask import session as fsession
    fsession["sid"] = mine_sid
    assert server._nav_badges().get("admin", {}).get("level") == "danger"

# الإيقاف
c.post("/backup/offsite", data={"action": "disable"})
assert not offsite.load()["enabled"] and not offsite.due()

print("ALL OK")
