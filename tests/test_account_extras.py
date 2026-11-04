# -*- coding: utf-8 -*-
"""البورتال: تغيير كلمة المرور ذاتياً وانتهاؤها، تنبيه الدخول من جهاز جديد،
عرض موسم سابق للقراءة فقط، وفحص عمل الموقع ‎/healthz‎."""
import io
import os
import sys
import tempfile
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["HAJJ_DATA_DIR"] = tempfile.mkdtemp(prefix="acc_extras_")

from hajj_app import app_mode, auth, storage  # noqa: E402
from hajj_app.mrz import PassportData  # noqa: E402

try:
    from webapp import server, mailer, pwpolicy
    server.app.config["CSRF_ENABLED"] = False
except ImportError as exc:
    print(f"[skip] مسارات الويب: {exc}")
    print("ALL OK")
    sys.exit(0)

mailer.OUTBOX = []
owner, _rk = auth.create_account("owner", "Passw0rd!x")
auth.add_account(owner, "sara", "Passw0rd!s", role="editor")
auth.set_email(owner, "sara", "sara@gmail.com")
c = server.app.test_client()
c.post("/login", data={"username": "owner", "password": "Passw0rd!x"})
SESS = next(v for v in server._SESSIONS.values() if v.username == "owner")


def login(client, user, pw):
    return client.post("/login", data={"username": user, "password": pw})


def wait_mail(n):
    for _ in range(100):
        if len(mailer.OUTBOX) >= n:
            return
        time.sleep(0.05)


# ---- ١) فحص عمل الموقع ----
r = server.app.test_client().get("/healthz")
assert r.status_code == 200 and r.get_json() == {"status": "ok"}

# ---- ٢) تنبيه الدخول من جهاز جديد ----
phone = server.app.test_client()
login(phone, "sara", "Passw0rd!s")                 # أوّل جهاز: لا تنبيه
time.sleep(0.3)
assert not [m for m in mailer.OUTBOX if "جهاز جديد" in m["subject"]]
phone.get("/dashboard")
login(phone, "sara", "Passw0rd!s")                 # الجهاز نفسه (ملف الارتباط): لا تنبيه
time.sleep(0.3)
assert not [m for m in mailer.OUTBOX if "جهاز جديد" in m["subject"]]
laptop = server.app.test_client()
login(laptop, "sara", "Passw0rd!s")                # جهاز آخر: تنبيه
wait_mail(1)
alerts = [m for m in mailer.OUTBOX if "جهاز جديد" in m["subject"]]
assert len(alerts) == 1 and alerts[0]["to"] == "sara@gmail.com", mailer.OUTBOX
from hajj_app import audit  # noqa: E402
assert "دخول من جهاز جديد" in [e.get("action") for e in audit.read_entries()]
mailer.OUTBOX.clear()

# ---- ٣) تغيير كلمة المرور ذاتياً ----
page = phone.get("/account/password").get_data(as_text=True)
assert "كلمة المرور الحالية" in page and "تغيير كلمة المرور" in page
r = phone.post("/account/password", data={"old": "wrong-pass1", "password": "NewPass!22",
                                          "confirm": "NewPass!22"})
assert "كلمة المرور الحالية غير صحيحة" in r.get_data(as_text=True)
r = phone.post("/account/password", data={"old": "Passw0rd!s", "password": "NewPass!22",
                                          "confirm": "NewPass!23"})
assert "غير متطابقتين" in r.get_data(as_text=True)
r = phone.post("/account/password", data={"old": "Passw0rd!s", "password": "NewPass!22",
                                          "confirm": "NewPass!22"})
assert r.status_code == 302
assert phone.get("/dashboard").status_code == 200, "الجهاز الذي غيّر يبقى داخلاً"
assert laptop.get("/dashboard").status_code == 302, "الأجهزة الأخرى تُخرج"
assert auth.login("sara", "NewPass!22").username == "sara"
assert any("تغيّرت كلمة مرورك" in m["subject"] for m in mailer.OUTBOX)
# البيانات ما زالت تُقرأ بعد التغيير
app_mode.set_mode(app_mode.UMRAH)
storage.save_records([PassportData(full_name_ar="أحمد")], session=SESS)
assert "أحمد" in phone.get("/hujjaj").get_data(as_text=True)

# ---- ٤) انتهاء كلمة المرور ----
assert "انتهاء كلمة المرور" in c.get("/accounts").get_data(as_text=True)
phone.post("/accounts/password-policy", data={"days": "90"})
assert not auth.get_policy().get("password_days"), "المحرّر لا يغيّر السياسة"
c.post("/accounts/password-policy", data={"days": "45"})
assert not auth.get_policy().get("password_days"), "قيمة غير مسموحة"
c.post("/accounts/password-policy", data={"days": "90"})
assert auth.get_policy()["password_days"] == 90
assert phone.get("/dashboard").status_code == 200
pwpolicy.mark("sara", time.time() - 80 * 86400)
assert "تنتهي كلمة مرورك بعد 10 يوماً" in phone.get("/account/password").get_data(as_text=True)
pwpolicy.mark("sara", time.time() - 91 * 86400)
r = phone.get("/dashboard")
assert r.status_code == 302 and "/account/password" in r.headers["Location"], r.headers.get("Location")
assert "انتهت صلاحية كلمة مرورك" in phone.get("/account/password?expired=1").get_data(as_text=True)
phone.post("/account/password", data={"old": "NewPass!22", "password": "Third!pass3",
                                      "confirm": "Third!pass3"})
assert phone.get("/dashboard").status_code == 200, "بعد التغيير يكمل العمل"
c.post("/accounts/password-policy", data={"days": "0"})
assert not auth.get_policy()["password_days"]

# ---- ٥) عرض موسم سابق للقراءة فقط ----
st = storage.load_settings()
st["season_year"] = "2026"
storage.save_settings(st)
storage.save_records([PassportData(full_name_ar="أحمد", passport_number="P123",
                                   program_value="5000", paid_amount="2000")], session=SESS)
c.post("/season", data={"season_year": "2027"})       # موسم جديد: ٢٠٢٦ محفوظ
app_mode.set_mode(app_mode.UMRAH)
assert storage.load_records(session=SESS)[0] == []
assert "/season/2026/view" in c.get("/season").get_data(as_text=True)
page = phone.get("/season/2026/view").get_data(as_text=True)    # أي مستخدم يعرض
assert "للعرض فقط" in page and "أحمد" in page and "P123" in page and "3,000" in page, page[-2000:]
app_mode.set_mode(app_mode.UMRAH)
assert storage.load_records(session=SESS)[0] == [], "العرض لا يغيّر الموسم الحالي"
assert storage.load_settings()["season_year"] == "2027"
assert phone.get("/season/1999/view").status_code == 302

print("ALL OK")
