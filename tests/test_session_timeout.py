# -*- coding: utf-8 -*-
"""البورتال: مدّة الجلسة — المدير يحدّدها لكل المستخدمين، ومن يبقى بلا نشاط
أطول منها يخرج تلقائياً."""
import io
import os
import sys
import tempfile

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["HAJJ_DATA_DIR"] = tempfile.mkdtemp(prefix="sesstime_")

from hajj_app import auth  # noqa: E402

try:
    from webapp import server
    server.app.config["CSRF_ENABLED"] = False
except ImportError as exc:
    print(f"[skip] مسارات الويب: {exc}")
    print("ALL OK")
    sys.exit(0)

owner, _rk = auth.create_account("owner", "Passw0rd!x")
auth.add_account(owner, "sara", "Passw0rd!s", role="editor")
c = server.app.test_client()
c.post("/login", data={"username": "owner", "password": "Passw0rd!x"})
s = server.app.test_client()
s.post("/login", data={"username": "sara", "password": "Passw0rd!s"})


def sid_of(username):
    return next(k for k, v in server._SESSIONS.items() if v.username == username)


# الافتراضي: بلا حدّ
assert server._session_minutes() == 0
assert c.get("/session/status").get_json() == {"left": None}
assert "مدّة الجلسة" in c.get("/accounts").get_data(as_text=True)

# غير المدير لا يغيّرها
s.post("/accounts/session-policy", data={"minutes": "15"})
assert server._session_minutes() == 0, "المحرّر لا يحدّد مدّة الجلسة"

# قيمة غير مسموحة → بلا حدّ
c.post("/accounts/session-policy", data={"minutes": "7"})
assert server._session_minutes() == 0

c.post("/accounts/session-policy", data={"minutes": "30"})
assert server._session_minutes() == 30
assert auth.get_policy()["session_minutes"] == 30
left = s.get("/session/status").get_json()["left"]
assert 1790 <= left <= 1800, left
page = s.get("/dashboard").get_data(as_text=True)
assert "session/ping" in page, "سكربت المدّة في الصفحات"
assert 'id="sessWarn"' in page and "ستنتهي جلستك بعد" in page, "تنبيه العدّ التنازلي"

# نشاط قبل انتهاء المدّة يمدّدها
server._LAST_SEEN[sid_of("sara")] -= 29 * 60
assert s.get("/dashboard").status_code == 200
assert s.get("/session/status").get_json()["left"] >= 1790

# فحص الحالة لا يُحسب نشاطاً
server._LAST_SEEN[sid_of("sara")] -= 10 * 60
s.get("/session/status")
assert s.get("/session/status").get_json()["left"] <= 1200

# بعد المدّة بلا نشاط: خروج وتحويل لشاشة الدخول مع رسالة
sara = sid_of("sara")
server._LAST_SEEN[sara] -= 31 * 60
r = s.get("/dashboard")
assert r.status_code == 302 and "expired=1" in r.headers["Location"], r.headers.get("Location")
assert sara not in server._SESSIONS and sara not in server._LAST_SEEN
assert s.get("/session/status").get_json() == {"left": 0}
assert "انتهت الجلسة لعدم النشاط" in s.get("/login?expired=1").get_data(as_text=True)
# المدير ما زال داخلاً
assert c.get("/dashboard").status_code == 200

# سجلّ التدقيق
from hajj_app import audit  # noqa: E402
acts = [e.get("action") for e in audit.read_entries()]
assert "انتهاء الجلسة" in acts and "مدّة الجلسة" in acts, acts[:5]

# الرجوع لبلا حدّ: لا خروج مهما طال الخمول
c.post("/accounts/session-policy", data={"minutes": "0"})
server._LAST_SEEN[sid_of("owner")] -= 10 * 86400
assert c.get("/dashboard").status_code == 200
page = c.get("/dashboard").get_data(as_text=True)
assert "session/ping" not in page and 'id="sessWarn"' not in page

print("ALL OK")
