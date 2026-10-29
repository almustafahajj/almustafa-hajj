# -*- coding: utf-8 -*-
"""البورتال: إيميلات العمل — رمز الدخول على الإيميل، و«نسيت كلمة المرور»
بموافقة المدير ثم رابط لمرة واحدة، وإرسال Brevo نفسه."""
import io
import json
import os
import re
import sys
import tempfile

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["HAJJ_DATA_DIR"] = tempfile.mkdtemp(prefix="email_")
os.environ.pop("BREVO_API_KEY", None)
os.environ.pop("MAIL_FROM", None)

from hajj_app import app_mode, auth, storage  # noqa: E402
from hajj_app.mrz import PassportData  # noqa: E402

try:
    from webapp import server, mailer, resets
    server.app.config["CSRF_ENABLED"] = False
except ImportError as exc:
    print(f"[skip] مسارات الويب: {exc}")
    print("ALL OK")
    sys.exit(0)

# ---- 1) الإرسال عبر Brevo (بلا شبكة) ----
assert not mailer.configured() and mailer.status() == "no-key"
os.environ["BREVO_API_KEY"] = "xkeysib-test"
assert mailer.status() == "no-sender"
os.environ["MAIL_FROM"] = "noreply@ntravel.ae"
assert mailer.configured()
sent = {}


class _Resp:
    status = 201

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def fake_urlopen(req, timeout=0):
    sent["url"], sent["key"] = req.full_url, req.get_header("Api-key")
    sent["body"] = json.loads(req.data.decode("utf-8"))
    return _Resp()


real = mailer.urllib.request.urlopen
mailer.urllib.request.urlopen = fake_urlopen
ok, _ = mailer.send("a@ntravel.ae", "عنوان", "<p>نص</p>")
mailer.urllib.request.urlopen = real
assert ok and sent["url"] == mailer.API_URL and sent["key"] == "xkeysib-test"
assert sent["body"]["sender"]["email"] == "noreply@ntravel.ae"
assert sent["body"]["to"] == [{"email": "a@ntravel.ae"}]
assert mailer.send("ليس-إيميل", "x", "y")[0] is False
print("[ok] Brevo: المفتاح في الترويسة، المرسل من MAIL_FROM، ورفض العناوين الخاطئة")

mailer.OUTBOX = []                      # بقية الاختبارات بلا إرسال فعلي


def last_code():
    return re.search(r"(\d{6})", mailer.OUTBOX[-1]["subject"]).group(1)


owner, _rk = auth.create_account("owner", "Passw0rd!x")
auth.add_account(owner, "boss2", "Passw0rd!b", role="admin")
auth.add_account(owner, "sara", "Passw0rd!s", role="editor")
app_mode.set_mode(app_mode.UMRAH)
c = server.app.test_client()
c.post("/login", data={"username": "owner", "password": "Passw0rd!x"})
SESS = server._SESSIONS[next(iter(server._SESSIONS))]
storage.save_records([PassportData(full_name_ar="أحمد")], session=SESS)

# ---- 2) المدير يضبط إيميلات العمل ----
c.post("/accounts/sara/email", data={"email": "sara@ntravel.ae"})
c.post("/accounts/owner/email", data={"email": "owner@ntravel.ae"})
c.post("/accounts/boss2/email", data={"email": "SARA@ntravel.ae"})       # مكرّر
assert auth.get_email("sara") == "sara@ntravel.ae" and auth.get_email("boss2") == ""
assert "مستخدم لحساب آخر" in c.get("/accounts").get_data(as_text=True)
c.post("/accounts/boss2/email", data={"email": "بلا صيغة"})
assert auth.get_email("boss2") == ""
c.post("/accounts/boss2/email", data={"email": "boss2@ntravel.ae"})
page = c.get("/accounts").get_data(as_text=True)
assert "sara@ntravel.ae" in page and "رسالة تجريبية" in page
c.post("/accounts/mail-test")
assert mailer.OUTBOX[-1]["to"] == "owner@ntravel.ae"
s = server.app.test_client()
s.post("/login", data={"username": "sara", "password": "Passw0rd!s"})
s.post("/accounts/owner/email", data={"email": "evil@x.com"})            # محرّر
assert auth.get_email("owner") == "owner@ntravel.ae"
print("[ok] إيميل العمل: يضبطه المدير فقط، بلا تكرار، وبصيغة صحيحة + رسالة تجريبية")

# ---- 3) رمز الدخول على الإيميل ----
s.post("/account/2fa", data={"action": "email_send"})
code = last_code()
assert mailer.OUTBOX[-1]["to"] == "sara@ntravel.ae"
s.post("/account/2fa", data={"action": "email_enable", "code": "000000" if code != "000000" else "111111"})
assert not auth.has_email_2fa("sara")
s.post("/account/2fa", data={"action": "email_enable", "code": code})
assert auth.has_email_2fa("sara")
s2 = server.app.test_client()
n0 = len(mailer.OUTBOX)
r = s2.post("/login", data={"username": "sara", "password": "Passw0rd!s"})
assert r.headers["Location"].endswith("/login/2fa") and len(mailer.OUTBOX) == n0 + 1
code = last_code()
page = s2.get("/login/2fa").get_data(as_text=True)
assert "sa•••@ntravel.ae" in page
r = s2.post("/login/2fa", data={"code": "999999" if code != "999999" else "123456"})
assert "الرمز غير صحيح" in r.get_data(as_text=True)
assert s2.get("/dashboard").status_code == 302                        # لم يدخل بعد
r = s2.post("/login/2fa", data={"action": "email"})                    # إعادة فوراً تُرفض
assert "انتظر" in r.get_data(as_text=True)
r = s2.post("/login/2fa", data={"code": code})
assert r.headers["Location"].endswith("/dashboard") and s2.get("/dashboard").status_code == 200
# الإلزام يقبل رمز الإيميل بديلاً عن التطبيق
auth.set_policy(SESS, require_totp=True)
assert s2.get("/dashboard").status_code == 200
assert s2.get("/account/2fa").status_code == 200
auth.set_policy(SESS, require_totp=False)
# المدير يلغيه (ضاع الوصول للإيميل)
c.post("/accounts/sara/2fa-reset")
assert not auth.has_email_2fa("sara")
print("[ok] رمز الإيميل: تفعيل بالتحقّق، يُرسل عند الدخول، لمرة واحدة، ويلغيه المدير")

# ---- 4) نسيت كلمة المرور: طلب ← موافقة المدير ← رابط ← كلمة جديدة ----
f = server.app.test_client()
n0 = len(mailer.OUTBOX)
r = f.post("/forgot", data={"who": "مجهول"})
assert "وصل طلبك" in r.get_data(as_text=True) and len(mailer.OUTBOX) == n0   # بلا تلميح
r = f.post("/forgot", data={"who": "SARA@ntravel.ae"})
assert "وصل طلبك" in r.get_data(as_text=True)
to = [m["to"] for m in mailer.OUTBOX[n0:]]
assert sorted(to) == ["boss2@ntravel.ae", "owner@ntravel.ae", "sara@ntravel.ae"], to
f.post("/forgot", data={"who": "sara"})                                 # لا يتكرّر
assert len(resets.pending()) == 1 and len(mailer.OUTBOX) == n0 + 3
rid = resets.pending()[0]["id"]
page = c.get("/accounts").get_data(as_text=True)
assert "طلبات استعادة كلمة المرور" in page and "موافقة وإرسال الرابط" in page
s.post(f"/accounts/resets/{rid}/approve")                               # المحرّر لا يوافق
assert resets.pending()[0]["status"] == "pending"
c.post(f"/accounts/resets/{rid}/approve")
assert resets.pending()[0]["status"] == "approved"
mail = mailer.OUTBOX[-1]
assert mail["to"] == "sara@ntravel.ae"
link = re.search(r'href="([^"]+/reset/[^"]+)"', mail["html"]).group(1)
token = link.rsplit("/reset/", 1)[1]
assert token not in json.dumps(resets.load())                           # السرّ لا يُحفظ
assert f.get("/reset/خطأ").status_code == 404
assert "لحساب «sara»" in f.get(f"/reset/{token}").get_data(as_text=True)
r = f.post(f"/reset/{token}", data={"password": "NewPass#1", "confirm": "غير"})
assert "غير متطابقتين" in r.get_data(as_text=True)
r = f.post(f"/reset/{token}", data={"password": "NewPass#1", "confirm": "NewPass#1"})
assert r.status_code == 302 and "reset=1" in r.headers["Location"]
assert mailer.OUTBOX[-1]["subject"] == "تغيّرت كلمة مرورك"
assert f.get(f"/reset/{token}").status_code == 404                      # لمرة واحدة
assert resets.pending() == []
try:
    auth.login("sara", "Passw0rd!s")
    raise AssertionError("القديمة يجب أن تُرفض")
except auth.AuthError:
    pass
hs = auth.login("sara", "NewPass#1")
app_mode.set_mode(app_mode.UMRAH)
assert [r.full_name_ar for r in storage.load_records(session=hs)[0]] == ["أحمد"]
assert auth.get_email("sara") == "sara@ntravel.ae"
assert s.get("/dashboard").status_code == 302                            # جلسته القديمة خرجت
print("[ok] الاستعادة: طلب عام بلا تلميح، يصل المديرين وصاحبه، موافقة المدير فقط، "
      "رابط لمرة واحدة يفتح البيانات نفسها")

# ---- 5) المدير لا يوافق على طلبه، والرفض، وحدّ الطلبات ----
f.post("/forgot", data={"who": "owner"})
rid = next(r["id"] for r in resets.pending() if r["user"] == "owner")
c.post(f"/accounts/resets/{rid}/approve")
assert resets.load()[rid]["status"] == "pending"
assert "يوافق عليه مدير آخر" in c.get("/accounts").get_data(as_text=True)
c.post(f"/accounts/resets/{rid}/deny")
assert resets.pending() == []
for _ in range(6):
    r = f.post("/forgot", data={"who": "nobody"})
assert "طلبات كثيرة" in r.get_data(as_text=True)
# إعادة تعيين المدير تُبلغ صاحب الحساب
n0 = len(mailer.OUTBOX)
c.post("/accounts/sara/password", data={"password": "Another#2"})
assert mailer.OUTBOX[-1]["to"] == "sara@ntravel.ae" and len(mailer.OUTBOX) == n0 + 1
print("[ok] لا موافقة على طلبك، الرفض يحذف، حدّ للطلبات، وتنبيه عند تعيين المدير")

# ---- 6) البريد غير مفعّل: لا شيء يُرسل ولا ينغلق أحد ----
mailer.OUTBOX = None
os.environ.pop("BREVO_API_KEY", None)
auth.set_email_2fa(auth.login("boss2", "Passw0rd!b"), True)
b = server.app.test_client()
r = b.post("/login", data={"username": "boss2", "password": "Passw0rd!b"})
assert r.headers["Location"].endswith("/dashboard")
r = b.post("/forgot", data={"who": "boss2"})
assert resets.pending() == []
print("[ok] بلا مفتاح Brevo: تبقى الميزات متوقّفة دون تعطيل الدخول")
print("ALL OK")
